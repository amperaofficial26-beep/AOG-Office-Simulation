"""Pemanggil model AI (Groq, OpenRouter, Aion Labs) untuk karyawan yang bekerja.

Semua panggilan memakai API OpenAI-compatible via urllib, jadi tidak ada
dependensi tambahan. Setiap kegagalan dicoba ulang ke model fallback, lalu ke
provider lain, supaya karyawan tidak pernah "macet" karena satu model mati.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

from .config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    HTTP_TIMEOUT,
    MAX_CONTEXT_CHARS,
    PROVIDERS,
    get_key,
)
from .models import ALL_FALLBACK, MODELS, RETIRED, model_label, provider_of


class LLMError(RuntimeError):
    pass


class LLMResult(dict):
    """Hasil panggilan model: teks + metadata pemakaian."""

    @property
    def text(self) -> str:
        return self.get("text", "")

    @property
    def model(self) -> str:
        return self.get("model", "")

    @property
    def provider(self) -> str:
        return self.get("provider", "")


# ----------------------------------------------------------------------------- transport
def _endpoint(provider: str) -> tuple[str, str]:
    meta = PROVIDERS[provider]
    return meta["base_url"].rstrip("/") + "/chat/completions", meta["label"]


def _headers(provider: str) -> dict[str, str]:
    key = get_key(provider)
    if not key:
        raise LLMError(f"API key {PROVIDERS[provider]['key_env']} belum diisi di Secrets")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        # Beberapa gateway menolak User-Agent bawaan Python.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AOG-Virtual-Office/2.0",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/amperaofficial26-beep"
        headers["X-Title"] = "AOG Virtual Office"
    return headers


def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # pragma: no cover - bergantung jaringan
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {exc.code} — {detail}") from exc
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Balasan bukan JSON: {raw[:200]}") from exc



def _extract_text(payload: dict[str, Any]) -> str:
    """Ambil konten jawaban, bukan kanal penalaran internal."""
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content")

    # Format respons berupa teks biasa.
    if isinstance(content, str):
        return content.strip()

    # Format respons berupa daftar blok konten.
    if isinstance(content, list):
        answer_parts = []

        for part in content:
            if not isinstance(part, dict):
                continue

            # Lewati blok yang secara eksplisit bukan teks jawaban.
            if part.get("type") not in (None, "text", "output_text"):
                continue

            # Jangan ambil blok yang ditandai sebagai reasoning.
            if part.get("channel") == "reasoning":
                continue

            text = part.get("text")
            if isinstance(text, str) and text.strip():
                answer_parts.append(text.strip())

        return "\n".join(answer_parts).strip()

    # Jangan gunakan message["reasoning"] sebagai jawaban cadangan.
    return ""



def _usage(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage") or {}
    try:
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return 0, 0


# ----------------------------------------------------------------------------- prompt
SYSTEM_PROMPT = """Anda adalah {name}, {title} di {company}.
Anda adalah karyawan sungguhan dalam simulasi kantor; atasan Anda adalah {boss}.

Kepribadian Anda: {personality}
Kebiasaan khas: {quirks}

Aturan kerja:
1. Kerjakan tugas secara nyata dan tuntas — jangan menjawab dengan rencana saja.
2. Tulis dalam Bahasa Indonesia yang jelas, kecuali kode atau istilah teknis.
3. Jangan memakai emoji sama sekali; gunakan tanda baca biasa.
4. Strukturkan hasil dengan judul dan poin agar mudah disetujui atasan.
5. Bila tugas menyangkut kode, sertakan blok kode lengkap yang siap dipakai.
6. Akhiri dengan bagian "Ringkasan untuk Bos" maksimal 3 poin.
7. Jangan mengaku sebagai model AI atau menyebut nama model Anda di dalam hasil kerja.
"""


def build_system_prompt(
    emp: dict[str, Any],
    company: str = "perusahaan",
    boss: str = "Bos",
) -> str:
    quirks = emp.get("quirks") or []
    if isinstance(quirks, str):
        quirks = [quirks]
    return SYSTEM_PROMPT.format(
        name=emp.get("name", "Karyawan"),
        title=emp.get("title") or emp.get("role_label", "karyawan"),
        company=company,
        boss=boss,
        personality=emp.get("personality", "profesional"),
        quirks=", ".join(quirks) if quirks else "tidak ada",
    )


def build_task_prompt(
    title: str,
    brief: str,
    deliverable: str = "dokumen",
    priority: str = "normal",
    context: str = "",
    revision_note: str = "",
    history: Iterable[dict[str, Any]] | None = None,
) -> str:
    parts = [
        f"TUGAS: {title}",
        f"BENTUK KELUARAN: {deliverable}",
        f"PRIORITAS: {priority}",
        "",
        "BRIEF DARI BOS:",
        brief.strip() or "(tidak ada detail tambahan)",
    ]
    if context:
        parts += ["", "KONTEKS PROYEK (potongan repo/aplikasi):", context[:MAX_CONTEXT_CHARS]]
    if history:
        parts += ["", "RIWAYAT PENGERJAAN SEBELUMNYA:"]
        for item in list(history)[-2:]:
            parts.append(f"- {item.get('status', '?')}: {str(item.get('text', ''))[:600]}")
    if revision_note:
        parts += ["", "CATATAN REVISI DARI BOS:", revision_note.strip()]
    parts += ["", "Kerjakan sekarang dan serahkan hasil akhirnya."]
    return "\n".join(parts)



# -----------------------------------------------------------------------------
# panggilan
def chat(
    messages: list[dict[str, str]],
    model: str,
    provider: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_mode: bool = False,
) -> LLMResult:
    """Satu panggilan chat ke model tertentu. Tanpa fallback."""

    # 1. Pastikan model terdaftar di katalog.
    model_meta = MODELS.get(model)
    if model_meta is None:
        raise LLMError(
            f"Model '{model}' tidak terdaftar di katalog AOG Office Simulation."
        )

    # 2. Ambil provider resmi model dan cegah ketidakcocokan.
    known_provider = model_meta.get("provider", "")
    if provider and provider != known_provider:
        raise LLMError(
            f"Provider tidak cocok untuk model '{model}': "
            f"diminta '{provider}', seharusnya '{known_provider}'."
        )

    provider = provider or known_provider

    # 3. Pastikan provider memiliki konfigurasi.
    if not provider or provider not in PROVIDERS:
        raise LLMError(
            f"Provider '{provider}' tidak terdaftar dalam konfigurasi."
        )

    # 4. Siapkan endpoint dan payload permintaan.
    url, label = _endpoint(provider)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # 5. Kirim permintaan ke provider.
    data = _post(url, _headers(provider), payload)

    # 6. Periksa apakah provider mengembalikan teks.
    response_text = _extract_text(data)
    if not response_text:
        raise LLMError(
            f"{label} membalas kosong untuk model '{model}'."
        )

    # 7. Ambil informasi penggunaan token.
    tokens_in, tokens_out = _usage(data)

    # 8. Kembalikan hasil beserta identitas model dan provider.
    return LLMResult(
        text=response_text,
        model=model,
        model_label=model_label(model),
        provider=provider,
        provider_label=label,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency=0.0,
    )



def chat_with_fallback(
    messages: list[dict[str, str]],
    model: str,
    fallbacks: Iterable[str] = (),
    role_fallbacks: Iterable[str] = (),
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_mode: bool = False,
) -> tuple[LLMResult, list[str]]:
    """Coba model utama, lalu fallback role, lalu model cadangan global.

    Mengembalikan (hasil, daftar catatan percobaan).
    """
    chain: list[str] = []
    for candidate in [model, *fallbacks, *role_fallbacks, *ALL_FALLBACK]:
        if candidate and candidate not in chain:
            chain.append(candidate)

    notes: list[str] = []
    last_error: Exception | None = None
    for candidate in chain:
        if candidate in RETIRED:
            notes.append(f"{candidate} dilewati (model sudah dimatikan provider)")
            continue
        started = time.time()
        try:
            result = chat(
                messages,
                candidate,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            result["latency"] = round(time.time() - started, 2)
            if candidate != model:
                notes.append(f"Model utama gagal, dipakai cadangan: {candidate}")
            return result, notes
        except LLMError as exc:
            last_error = exc
            notes.append(f"{candidate} gagal: {exc}")
            continue
    raise LLMError(f"Semua model gagal. Percobaan terakhir: {last_error}")


def quick_reply(emp: dict[str, Any], user_text: str, company: str, boss: str, model: str | None = None) -> LLMResult:
    """Balasan singkat karyawan (untuk fitur mengobrol di dalam kantor)."""
    model = model or emp.get("model", ALL_FALLBACK[0])
    messages = [
        {"role": "system", "content": build_system_prompt(emp, company, boss) +
            "\nBalas singkat maksimal 3 kalimat, gaya santai seperti sedang mengobrol di kantor."},
        {"role": "user", "content": user_text},
    ]
    return chat_with_fallback(messages, model, role_fallbacks=emp.get("fallbacks", []), max_tokens=320)[0]


# ----------------------------------------------------------------------------- diagnostik
def test_key(provider: str, model: str) -> dict[str, Any]:
    """Kirim satu permintaan kecil untuk memastikan kunci & model benar-benar jalan."""
    started = time.time()
    try:
        result = chat(
            [{"role": "user", "content": "Jawab dengan satu kata: siap"}],
            model,
            provider=provider,
            max_tokens=16,
            temperature=0.2,
        )
        return {
            "ok": True,
            "provider": provider,
            "model": model,
            "reply": result.text[:80],
            "latency": round(time.time() - started, 2),
            "error": "",
        }
    except LLMError as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "reply": "",
            "latency": round(time.time() - started, 2),
            "error": str(exc),
        }


def provider_health() -> dict[str, dict[str, Any]]:
    """Ringkasan kesiapan tiap provider (kunci ada / tidak, model contoh)."""
    from .models import models_for

    out: dict[str, dict[str, Any]] = {}
    for provider, meta in PROVIDERS.items():
        catalogue = models_for(provider)
        first = next(iter(catalogue), "")
        out[provider] = {
            "label": meta["label"],
            "key_present": bool(get_key(provider)),
            "key_env": meta["key_env"],
            "base_url": meta["base_url"],
            "sample_model": first,
            "catalog_count": len(catalogue),
        }
    return out

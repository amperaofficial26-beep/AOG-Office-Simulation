"""Pembuatan gambar AI untuk karyawan Ruang AI Image (Cloudflare Workers AI / FLUX.1).

Endpoint yang dipakai adalah REST Workers AI::

    POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    {"prompt": "...", "steps": 4}
    ->  {"result": {"image": "<base64 PNG>"}}

Kunci yang dibutuhkan hanya ``CLOUDFLARE_API_KEY``. ``CLOUDFLARE_ACCOUNT_ID``
opsional: bila kosong, id akun dicari otomatis lewat ``GET /client/v4/accounts``
sehingga bos cukup menempel satu kunci saja di panel Pengaturan.

Semua hasil disimpan sebagai PNG di ``data/assets`` dan path-nya dicatat di
``task["files"]`` supaya bisa ditinjau bos di panel Persetujuan.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .config import get_account_id, get_key
from .models import RETIRED, model_label, models_for_kind

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
PROVIDER = "cloudflare"
MAX_PROMPT_CHARS = 1200  # FLUX.1 memotong prompt di atas ~512 token
IMAGE_TIMEOUT = 180  # detik: render gambar lebih lambat daripada chat

# Jumlah langkah denoising yang diterima tiap model. Di luar rentang ini API
# menolak permintaan, jadi nilainya dijepit sebelum dikirim.
STEP_RANGE: dict[str, tuple[int, int, int]] = {
    # model: (default, minimum, maksimum)
    "@cf/black-forest-labs/flux-1-schnell": (4, 4, 8),
    "@cf/black-forest-labs/flux-1-dev": (14, 12, 30),
    "@cf/bytedance/stable-diffusion-xl-lightning": (1, 1, 4),
}
FALLBACK_STEPS = (4, 1, 8)


class ImageError(RuntimeError):
    pass


class ImageResult(dict):
    """Hasil pembuatan gambar: teks laporan + path berkas + metadata."""

    @property
    def text(self) -> str:
        return self.get("text", "")

    @property
    def model(self) -> str:
        return self.get("model", "")

    @property
    def provider(self) -> str:
        return self.get("provider", PROVIDER)

    @property
    def file(self) -> str:
        return self.get("file", "")


# ----------------------------------------------------------------------------- transport
def _headers() -> dict[str, str]:
    key = get_key(PROVIDER)
    if not key:
        raise ImageError("API key CLOUDFLARE_API_KEY belum diisi di Secrets")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AOG-Virtual-Office/2.0",
    }


def _post(url: str, payload: dict[str, Any], timeout: int = IMAGE_TIMEOUT) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # pragma: no cover - bergantung jaringan
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise ImageError(f"Cloudflare HTTP {exc.code} — {detail}") from exc
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        raise ImageError(f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImageError(f"Balasan Cloudflare bukan JSON: {raw[:200]}") from exc
    if isinstance(data, dict) and data.get("errors"):
        first = data["errors"][0] if isinstance(data["errors"], list) else data["errors"]
        message = first.get("message", str(first)) if isinstance(first, dict) else str(first)
        raise ImageError(f"Cloudflare menolak permintaan: {message}")
    return data


def resolve_account_id(use_cache: bool = True) -> str:
    """Ambil CLOUDFLARE_ACCOUNT_ID; kalau kosong, cari akun pertama milik kunci itu."""
    configured = get_account_id()
    if configured:
        return configured

    from .state import load_cache, save_cache  # import lokal: hindari siklus

    cache_key = "cloudflare::account_id"
    if use_cache:
        cached = load_cache(cache_key)
        if cached:
            return str(cached)

    url = f"{CLOUDFLARE_API}/accounts?per_page=20&order_by=name"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - bergantung jaringan
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ImageError(f"Cloudflare HTTP {exc.code} saat mencari akun — {detail}") from exc
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        raise ImageError(f"{type(exc).__name__}: {exc}") from exc

    rows = payload.get("result") if isinstance(payload, dict) else None
    account_id = ""
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                account_id = str(row["id"])
                break
    if not account_id:
        raise ImageError(
            "Kunci Cloudflare tidak punya akun yang bisa diakses. "
            "Isi CLOUDFLARE_ACCOUNT_ID secara manual di panel Pengaturan."
        )
    save_cache(cache_key, account_id, ttl=3600)
    return account_id


def _clamp_steps(model: str, steps: int | None) -> int:
    default, low, high = STEP_RANGE.get(model, FALLBACK_STEPS)
    if steps is None:
        return default
    try:
        value = int(steps)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _decode_image(result: Any) -> bytes:
    """Ambil byte PNG dari balasan Workers AI (objek, string, atau data URI)."""
    encoded = ""
    if isinstance(result, dict):
        encoded = str(result.get("image") or result.get("b64_json") or "")
    elif isinstance(result, str):
        encoded = result
    if not encoded:
        raise ImageError("Cloudflare membalas tanpa data gambar.")
    if "," in encoded and encoded.lstrip().lower().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    encoded = "".join(encoded.split())
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError(f"Data gambar dari Cloudflare tidak valid: {exc}") from exc
    if not raw:
        raise ImageError("Gambar dari Cloudflare kosong.")
    return raw


def save_image(raw: bytes, slug: str) -> str:
    """Tulis PNG ke data/assets dan kembalikan path absolutnya."""
    from .config import asset_dir

    os.makedirs(asset_dir(), exist_ok=True)
    safe = re.sub(r"[^a-z0-9-]+", "-", str(slug).lower()).strip("-")[:60] or "gambar"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(asset_dir(), f"{stamp}-{safe}-{os.getpid()}.png")
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


# ----------------------------------------------------------------------------- prompt
def build_image_prompt(
    title: str,
    brief: str,
    deliverable: str = "gambar",
    revision_note: str = "",
    previous_prompt: str = "",
) -> str:
    """Susun prompt gambar dari brief bos (tanpa memanggil model tambahan)."""
    parts: list[str] = []
    if title:
        parts.append(str(title).strip())
    if brief:
        parts.append(re.sub(r"\s+", " ", str(brief)).strip())
    if revision_note:
        note = re.sub(r"\s+", " ", str(revision_note)).strip()
        parts.append(f"Perbaiki dari versi sebelumnya: {note}")
    prompt = " | ".join(p for p in parts if p)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    if not prompt:
        prompt = previous_prompt or "ilustrasi kantor modern, pencahayaan lembut"
    suffix = (
        " | gaya: ilustrasi profesional, komposisi rapi, pencahayaan lembut, "
        "tanpa teks di dalam gambar, rasio 16:9"
    )
    return (prompt + suffix)[:MAX_PROMPT_CHARS]


# ----------------------------------------------------------------------------- panggilan
def generate(
    prompt: str,
    model: str = "@cf/black-forest-labs/flux-1-schnell",
    steps: int | None = None,
    slug: str = "gambar",
    account_id: str = "",
) -> ImageResult:
    """Satu panggilan text-to-image. Tanpa fallback."""
    account = account_id or resolve_account_id()
    payload = {"prompt": prompt[:MAX_PROMPT_CHARS], "steps": _clamp_steps(model, steps)}
    url = f"{CLOUDFLARE_API}/accounts/{account}/ai/run/{model}"
    started = time.time()
    data = _post(url, payload)
    raw = _decode_image(data.get("result") if isinstance(data, dict) else data)
    path = save_image(raw, slug)
    return ImageResult(
        text="",
        model=model,
        model_label=model_label(model),
        provider=PROVIDER,
        provider_label="Cloudflare Workers AI",
        file=path,
        files=[path],
        prompt=prompt[:MAX_PROMPT_CHARS],
        steps=payload["steps"],
        width=0,
        height=0,
        bytes=len(raw),
        latency=round(time.time() - started, 2),
        tokens_in=0,
        tokens_out=0,
    )


def generate_with_fallback(
    prompt: str,
    model: str,
    fallbacks: Any = (),
    role_fallbacks: Any = (),
    steps: int | None = None,
    slug: str = "gambar",
) -> tuple[ImageResult, list[str]]:
    """Coba model utama, lalu fallback role, lalu model gambar lain di katalog."""
    catalogue = models_for_kind("image")
    chain: list[str] = []
    for candidate in [model, *(fallbacks or ()), *(role_fallbacks or ()), *catalogue]:
        if candidate and candidate not in chain and candidate in catalogue:
            chain.append(candidate)
    if not chain:
        raise ImageError("Tidak ada model gambar terdaftar di katalog AOG Office Simulation.")

    notes: list[str] = []
    last_error: Exception | None = None
    for candidate in chain:
        if candidate in RETIRED:
            notes.append(f"{candidate} dilewati (model sudah dimatikan provider)")
            continue
        try:
            result = generate(prompt, model=candidate, steps=steps, slug=slug)
            if candidate != model:
                notes.append(f"Model gambar utama gagal, dipakai cadangan: {candidate}")
            return result, notes
        except ImageError as exc:
            last_error = exc
            message = str(exc)
            notes.append(f"{candidate} gagal: {message}")
            # Kunci salah/kosong memengaruhi seluruh provider: berhenti mencoba.
            if "belum diisi" in message or "HTTP 401" in message or "HTTP 403" in message:
                break
            continue
    raise ImageError(f"Semua model gambar gagal. Percobaan terakhir: {last_error}")


# ----------------------------------------------------------------------------- laporan
def build_report(result: ImageResult, title: str, deliverable: str = "gambar") -> str:
    """Teks hasil kerja yang bisa dinilai quality gate dan ditinjau bos."""
    model_name = result.get("model_label") or result.get("model") or "FLUX.1"
    size_kb = round(float(result.get("bytes") or 0) / 1024.0, 1)
    lines = [
        f"## Hasil gambar: {title or 'aset visual'}",
        "",
        f"- Bentuk keluaran: {deliverable}",
        f"- Model: {model_name} ({result.get('steps', 0)} langkah)",
        f"- Berkas: `{os.path.basename(result.file)}` ({size_kb} KB)",
        "",
        "### Prompt akhir yang dikirim ke model",
        "",
        "```text",
        str(result.get("prompt", ""))[:MAX_PROMPT_CHARS],
        "```",
        "",
        "### Catatan pengerjaan",
        "",
        f"Gambar dirender {result.get('latency', 0)} detik lewat Cloudflare Workers AI "
        f"dengan akun Workers AI milik bos. Berkas PNG tersimpan di data/assets dan "
        f"ditampilkan langsung di kartu tugas untuk ditinjau.",
        "",
        "Ringkasan untuk Bos",
        f"- Aset visual '{title or deliverable}' selesai dirender dengan {model_name}.",
        f"- Prompt final tersimpan di atas agar bisa dipakai ulang atau direvisi.",
        "- Berkas PNG siap dipakai; bilang saja bila perlu variasi lain atau rasio berbeda.",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- diagnostik
def test_key(model: str = "@cf/black-forest-labs/flux-1-schnell") -> dict[str, Any]:
    """Render satu gambar kecil untuk memastikan kunci Cloudflare benar-benar jalan."""
    started = time.time()
    try:
        result = generate(
            "ikon kantor minimalis, latar polos, garis bersih",
            model=model,
            slug="uji-kunci",
        )
        return {
            "ok": True,
            "provider": PROVIDER,
            "model": model,
            "reply": f"Gambar uji tersimpan: {os.path.basename(result.file)}",
            "latency": round(time.time() - started, 2),
            "error": "",
            "file": result.file,
        }
    except ImageError as exc:
        return {
            "ok": False,
            "provider": PROVIDER,
            "model": model,
            "reply": "",
            "latency": round(time.time() - started, 2),
            "error": str(exc),
            "file": "",
        }


def health() -> dict[str, Any]:
    """Ringkasan kesiapan provider gambar untuk panel Model & Provider."""
    key_present = bool(get_key(PROVIDER))
    account = get_account_id()
    catalogue = models_for_kind("image")
    return {
        "provider": PROVIDER,
        "label": "Cloudflare Workers AI",
        "key_present": key_present,
        "key_env": "CLOUDFLARE_API_KEY",
        "account_id": account,
        "account_auto": not account,
        "sample_model": next(iter(catalogue), ""),
        "catalog_count": len(catalogue),
        "ready": key_present,
        "note": (
            "Cukup CLOUDFLARE_API_KEY; account id dicari otomatis."
            if not account
            else "Memakai CLOUDFLARE_ACCOUNT_ID dari Secrets."
        ),
    }

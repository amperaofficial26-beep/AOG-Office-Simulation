"""Pencarian web untuk karyawan Ruang Web Research (Tavily Search API).

Endpoint yang dipakai::

    POST https://api.tavily.com/search
    {"query": "...", "max_results": 6, "search_depth": "basic", "include_answer": true}
    ->  {"answer": "...", "results": [{"title", "url", "content", "score", ...}]}

Kunci yang dibutuhkan: ``TAVILY_API_KEY``. Kunci dikirim sebagai header
``Authorization: Bearer`` (cara baru) sekaligus field ``api_key`` di body (cara
lama) supaya tetap jalan di kedua versi API.

Hasil pencarian disusun menjadi laporan bersumber — semua URL berasal dari
balasan Tavily, tidak pernah dikarang oleh model.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import get_key
from .models import RETIRED, model_label, models_for_kind

TAVILY_API = "https://api.tavily.com"
PROVIDER = "tavily"
SEARCH_TIMEOUT = 45  # detik
DEFAULT_MAX_RESULTS = 6
MAX_SNIPPET_CHARS = 420

# model katalog -> (kedalaman pencarian, bentuk include_answer)
SEARCH_PROFILES: dict[str, tuple[str, Any]] = {
    "tavily-search": ("basic", True),
    "tavily-search-advanced": ("advanced", "advanced"),
}
FALLBACK_PROFILE = ("basic", True)


class SearchError(RuntimeError):
    pass


class SearchResult(dict):
    """Hasil pencarian: teks laporan + daftar sumber + metadata."""

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
    def sources(self) -> list[dict[str, Any]]:
        return list(self.get("sources") or [])


# ----------------------------------------------------------------------------- transport
def _headers() -> dict[str, str]:
    key = get_key(PROVIDER)
    if not key:
        raise SearchError("API key TAVILY_API_KEY belum diisi di Secrets")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AOG-Virtual-Office/2.0",
    }


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # pragma: no cover - bergantung jaringan
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SearchError(f"Tavily HTTP {exc.code} — {detail}") from exc
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        raise SearchError(f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SearchError(f"Balasan Tavily bukan JSON: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise SearchError("Balasan Tavily tidak berbentuk objek JSON.")
    return data


# ----------------------------------------------------------------------------- kueri
def build_query(title: str, brief: str = "", max_chars: int = 400) -> str:
    """Susun kueri pencarian dari judul + brief bos (tanpa panggilan model)."""
    parts = [str(title or "").strip(), re.sub(r"\s+", " ", str(brief or "")).strip()]
    query = " ".join(p for p in parts if p)
    query = re.sub(r"\s+", " ", query).strip()
    if not query:
        raise SearchError("Judul atau brief wajib diisi untuk pencarian web.")
    return query[:max_chars]


def _clean_snippet(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= MAX_SNIPPET_CHARS:
        return value
    return value[:MAX_SNIPPET_CHARS].rstrip() + "..."


def _normalise_sources(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Ambil sumber yang benar-benar dikembalikan Tavily (buang yang tanpa URL)."""
    rows = payload.get("results") or []
    sources: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return sources
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        try:
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        sources.append(
            {
                "title": str(row.get("title") or urllib.parse.urlparse(url).netloc or url).strip()[:200],
                "url": url,
                "snippet": _clean_snippet(row.get("content") or row.get("raw_content") or ""),
                "score": round(score, 4),
                "published_date": str(row.get("published_date") or "").strip()[:40],
            }
        )
        if len(sources) >= limit:
            break
    return sources


# ----------------------------------------------------------------------------- panggilan
def search(
    query: str,
    model: str = "tavily-search",
    max_results: int = DEFAULT_MAX_RESULTS,
    topic: str = "general",
) -> SearchResult:
    """Satu panggilan pencarian Tavily. Tanpa fallback."""
    key = get_key(PROVIDER)
    if not key:
        raise SearchError("API key TAVILY_API_KEY belum diisi di Secrets")
    depth, include_answer = SEARCH_PROFILES.get(model, FALLBACK_PROFILE)
    try:
        limit = max(1, min(20, int(max_results)))
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_RESULTS

    payload: dict[str, Any] = {
        "api_key": key,  # masih diterima API lama; header Bearer tetap dikirim
        "query": query,
        "max_results": limit,
        "search_depth": depth,
        "include_answer": include_answer,
        "include_raw_content": False,
        "include_images": False,
        "topic": topic or "general",
    }
    started = time.time()
    data = _post(f"{TAVILY_API}/search", payload)
    sources = _normalise_sources(data, limit)
    answer = str(data.get("answer") or "").strip()
    if not sources and not answer:
        detail = data.get("detail") or data.get("error") or data.get("message")
        if detail:
            raise SearchError(f"Tavily tidak mengembalikan hasil: {detail}")
        raise SearchError("Tavily tidak menemukan hasil untuk kueri tersebut.")

    return SearchResult(
        text="",
        model=model,
        model_label=model_label(model),
        provider=PROVIDER,
        provider_label="Tavily",
        query=query,
        answer=answer,
        sources=sources,
        follow_up=[str(q) for q in (data.get("follow_up_questions") or []) if q][:5],
        search_depth=depth,
        latency=round(time.time() - started, 2),
        tokens_in=0,
        tokens_out=0,
    )


def search_with_fallback(
    query: str,
    model: str,
    fallbacks: Any = (),
    role_fallbacks: Any = (),
    max_results: int = DEFAULT_MAX_RESULTS,
) -> tuple[SearchResult, list[str]]:
    """Coba model utama, fallback role, lalu model pencarian lain di katalog."""
    catalogue = models_for_kind("search")
    chain: list[str] = []
    for candidate in [model, *(fallbacks or ()), *(role_fallbacks or ()), *catalogue]:
        if candidate and candidate not in chain and candidate in catalogue:
            chain.append(candidate)
    if not chain:
        raise SearchError("Tidak ada model pencarian terdaftar di katalog AOG Office Simulation.")

    notes: list[str] = []
    last_error: Exception | None = None
    for candidate in chain:
        if candidate in RETIRED:
            notes.append(f"{candidate} dilewati (model sudah dimatikan provider)")
            continue
        try:
            result = search(query, model=candidate, max_results=max_results)
            if candidate != model:
                notes.append(f"Model pencarian utama gagal, dipakai cadangan: {candidate}")
            return result, notes
        except SearchError as exc:
            last_error = exc
            message = str(exc)
            notes.append(f"{candidate} gagal: {message}")
            if "belum diisi" in message or "HTTP 401" in message or "HTTP 403" in message:
                break
            continue
    raise SearchError(f"Semua model pencarian gagal. Percobaan terakhir: {last_error}")


# ----------------------------------------------------------------------------- laporan
def build_report(result: SearchResult, title: str, deliverable: str = "riset web") -> str:
    """Laporan riset bersumber: jawaban Tavily + daftar tautan asli."""
    model_name = result.get("model_label") or result.get("model") or "Tavily"
    sources = result.sources
    lines = [
        f"## Hasil pencarian web: {title or 'riset'}",
        "",
        f"- Bentuk keluaran: {deliverable}",
        f"- Model: {model_name} (kedalaman {result.get('search_depth', 'basic')})",
        f"- Kueri yang dipakai: `{result.get('query', '')}`",
        f"- Sumber ditemukan: {len(sources)}",
        f"- Waktu pencarian: {result.get('latency', 0)} detik",
        "",
    ]

    answer = str(result.get("answer") or "").strip()
    if answer:
        lines += ["### Ringkasan dari mesin pencari", "", answer, ""]

    if sources:
        lines += ["### Temuan per sumber", ""]
        for index, source in enumerate(sources, start=1):
            heading = f"{index}. {source['title']}"
            if source.get("published_date"):
                heading += f" ({source['published_date']})"
            lines += [heading, source["url"], ""]
            if source.get("snippet"):
                lines += [source["snippet"], ""]
    else:
        lines += [
            "### Temuan per sumber",
            "",
            "Tavily hanya mengembalikan ringkasan tanpa tautan untuk kueri ini.",
            "",
        ]

    follow_up = [q for q in (result.get("follow_up") or []) if str(q).strip()]
    if follow_up:
        lines += ["### Pertanyaan lanjutan yang disarankan", ""]
        lines += [f"- {q}" for q in follow_up]
        lines.append("")

    top = sources[0]["title"] if sources else "ringkasan mesin pencari"
    lines += [
        "### Catatan pengerjaan",
        "",
        "Semua tautan di atas berasal langsung dari balasan Tavily, bukan karangan. "
        "Isi ringkasan perlu dibaca ulang sebelum dipakai sebagai keputusan bisnis.",
        "",
        "Ringkasan untuk Bos",
        f"- {len(sources)} sumber web dikumpulkan lewat {model_name} untuk '{title or deliverable}'.",
        f"- Sumber teratas: {top}.",
        "- Sebutkan bila perlu penelusuran lanjutan dengan kedalaman advanced atau topik tertentu.",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- diagnostik
def test_key(model: str = "tavily-search") -> dict[str, Any]:
    """Satu pencarian kecil untuk memastikan kunci Tavily benar-benar jalan."""
    started = time.time()
    try:
        result = search("Streamlit framework", model=model, max_results=3)
        reply = (
            f"{len(result.sources)} sumber ditemukan"
            + (f": {result.sources[0]['url']}" if result.sources else "")
        )
        return {
            "ok": True,
            "provider": PROVIDER,
            "model": model,
            "reply": reply[:120],
            "latency": round(time.time() - started, 2),
            "error": "",
        }
    except SearchError as exc:
        return {
            "ok": False,
            "provider": PROVIDER,
            "model": model,
            "reply": "",
            "latency": round(time.time() - started, 2),
            "error": str(exc),
        }


def health() -> dict[str, Any]:
    """Ringkasan kesiapan provider pencarian untuk panel Model & Provider."""
    key_present = bool(get_key(PROVIDER))
    catalogue = models_for_kind("search")
    return {
        "provider": PROVIDER,
        "label": "Tavily",
        "key_present": key_present,
        "key_env": "TAVILY_API_KEY",
        "sample_model": next(iter(catalogue), ""),
        "catalog_count": len(catalogue),
        "ready": key_present,
        "note": "1.000 kredit/bulan gratis; basic 1 kredit, advanced 2 kredit.",
    }

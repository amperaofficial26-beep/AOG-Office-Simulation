"""Katalog model & roster karyawan.

Semua model di bawah diverifikasi AKTIF per 8 Oktober 2026:

* Groq      -> katalog live https://api.groq.com/openai/v1/models (butuh key).
               Llama 3.1/3.3, Llama 4 Scout/Maverick, Qwen3-32B, dan Kimi K2
               sudah DIMATIKAN Groq (Maret-Agustus 2026), jadi tidak dipakai.
* OpenRouter-> katalog publik https://openrouter.ai/api/v1/models. Model dengan
               field `expiration_date` dihindari (mis. google/gemini-2.5-*,
               qwen/qwen3.5-9b, poolside/laguna-*, z-ai/glm-4.x).
* Aion Labs -> katalog publik https://api.aionlabs.ai/v1/models (6 model live).

`probe()` mengecek ulang katalog live saat runtime dan menandai model yang
benar-benar ada, supaya roster otomatis menonaktifkan karyawan yang modelnya mati.
"""
from __future__ import annotations

import json
import time
import urllib.request

from .config import CACHE_TTL, PROVIDERS, get_key

VERIFIED_AT = "2026-10-08"

# ----------------------------------------------------------------------------- katalog
# role: jabatan fungsional. tier: kualitas. cost: 0 = gratis.
MODELS: dict[str, dict] = {
    # ---- Groq (super cepat, gratis) -------------------------------------------
    "openai/gpt-oss-120b": {
        "provider": "groq",
        "label": "GPT-OSS 120B",
        "context": 131072,
        "tier": "flagship",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Model terkuat Groq yang masih hidup. Pengganti resmi Llama 3.3 70B.",
    },
    "qwen/qwen3.6-27b": {
        "provider": "groq",
        "label": "Qwen 3.6 27B",
        "context": 131072,
        "tier": "vision+reasoning",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Bisa baca gambar — dipakai tim desain & riset visual.",
    },
    "openai/gpt-oss-20b": {
        "provider": "groq",
        "label": "GPT-OSS 20B",
        "context": 131072,
        "tier": "kilat",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "~1.000 token/detik. Untuk tugas kecil yang harus instan.",
    },
    "openai/gpt-oss-safeguard-20b": {
        "provider": "groq",
        "label": "GPT-OSS Safeguard 20B",
        "context": 131072,
        "tier": "keamanan",
        "cost": "gratis",
        "reasoning": True,
        "tools": False,
        "note": "Model moderasi — dipakai satpam konten sebelum rilis.",
    },
    "groq/compound-mini": {
        "provider": "groq",
        "label": "Groq Compound Mini",
        "context": 131072,
        "tier": "agen",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Sistem multi-model Groq (pilih model sendiri per langkah).",
    },
    # ---- OpenRouter (gratis, tanpa expiration_date) ----------------------------
    "nvidia/nemotron-3-ultra-550b-a55b:free": {
        "provider": "openrouter",
        "label": "Nemotron 3 Ultra 550B",
        "context": 1000000,
        "tier": "arsitek",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Konteks 1 juta token — arsitek sistem & reviewer kode.",
    },
    "nvidia/nemotron-3.5-lightning:free": {
        "provider": "openrouter",
        "label": "Nemotron 3.5 Lightning",
        "context": 1000000,
        "tier": "analis",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Cepat + konteks raksasa — analis data.",
    },
    "inclusionai/ling-3.1-flash": {
        "provider": "openrouter",
        "label": "Ling 3.1 Flash",
        "context": 262144,
        "tier": "coding",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Model kode, rilis 2 Oktober 2026 — tulang punggung ruang kode.",
    },
    "cohere/north-mini-code:free": {
        "provider": "openrouter",
        "label": "North Mini Code",
        "context": 256000,
        "tier": "coding",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Penulis modul & unit test yang rapi.",
    },
    "thinkingmachines/inkling:free": {
        "provider": "openrouter",
        "label": "Inkling",
        "context": 1048576,
        "tier": "riset",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Teks+gambar+audio, konteks 1 juta — periset utama.",
    },
    "thinkingmachines/inkling-small:free": {
        "provider": "openrouter",
        "label": "Inkling Small",
        "context": 1048576,
        "tier": "riset",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Versi ringan Inkling untuk riset kilat.",
    },
    "google/gemma-4-31b-it:free": {
        "provider": "openrouter",
        "label": "Gemma 4 31B",
        "context": 262144,
        "tier": "multimodal",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Teks+gambar+video — asisten desain & aset visual.",
    },
    "google/gemma-4-26b-a4b-it:free": {
        "provider": "openrouter",
        "label": "Gemma 4 26B MoE",
        "context": 262144,
        "tier": "multimodal",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "MoE hemat — cadangan tim desain.",
    },
    "apodex/apodex-1.1-mini:free": {
        "provider": "openrouter",
        "label": "Apodex 1.1 Mini",
        "context": 262144,
        "tier": "kilat",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Anak magang: cepat, murah, untuk tugas-tugas receh.",
    },
    "inclusionai/ling-3.0-flash-sante:free": {
        "provider": "openrouter",
        "label": "Ling 3.0 Flash Santé",
        "context": 262144,
        "tier": "dokumen",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Penyusun dokumentasi & README.",
    },
    "liquid/lfm-2.5-2.6b:free": {
        "provider": "openrouter",
        "label": "LFM 2.5 2.6B",
        "context": 65536,
        "tier": "resepsionis",
        "cost": "gratis",
        "reasoning": False,
        "tools": True,
        "note": "Sangat ringan — cocok untuk sortir pesan masuk.",
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "provider": "openrouter",
        "label": "Nemotron 3 Super 120B",
        "context": 262144,
        "tier": "QA",
        "cost": "gratis",
        "reasoning": True,
        "tools": True,
        "note": "Pengujian & peninjau kualitas keluaran.",
    },
    "nvidia/nemotron-3.5-content-safety:free": {
        "provider": "openrouter",
        "label": "Nemotron 3.5 Content Safety",
        "context": 128000,
        "tier": "keamanan",
        "cost": "gratis",
        "reasoning": False,
        "tools": False,
        "note": "Penyaring konten sebelum hasil kerja dipublikasi.",
    },
    # ---- OpenRouter (murah, tanpa expiration_date) -----------------------------
    "anthropic/claude-haiku-4.5": {
        "provider": "openrouter",
        "label": "Claude Haiku 4.5",
        "context": 200000,
        "tier": "premium",
        "cost": "$1/$5 per 1M",
        "reasoning": False,
        "tools": True,
        "note": "Premium murah untuk copywriting yang presisi.",
    },
    "moonshotai/kimi-k2.7-code": {
        "provider": "openrouter",
        "label": "Kimi K2.7 Code",
        "context": 262144,
        "tier": "coding",
        "cost": "murah",
        "reasoning": True,
        "tools": True,
        "note": "Cadangan senior engineer lintas repo.",
    },
    # ---- Aion Labs -------------------------------------------------------------
    "aion-labs/aion-3.5": {
        "provider": "aion",
        "label": "Aion 3.5",
        "context": 262144,
        "tier": "kreatif",
        "cost": "$3/$6 per 1M",
        "reasoning": True,
        "tools": True,
        "note": "Narasi kuat — kepala humas & storytelling merek.",
    },
    "aion-labs/aion-3.5-mini": {
        "provider": "aion",
        "label": "Aion 3.5 Mini",
        "context": 262144,
        "tier": "kreatif",
        "cost": "$0.7/$1.4 per 1M",
        "reasoning": True,
        "tools": True,
        "note": "Penulis konten harian (caption, thread, skrip).",
    },
    "aion-labs/aion-3.0": {
        "provider": "aion",
        "label": "Aion 3.0",
        "context": 131072,
        "tier": "kreatif",
        "cost": "$3/$6 per 1M",
        "reasoning": True,
        "tools": True,
        "note": "Sistem multi-model GLM — penulis naskah panjang.",
    },
    "aion-labs/aion-3.0-mini": {
        "provider": "aion",
        "label": "Aion 3.0 Mini",
        "context": 131072,
        "tier": "kreatif",
        "cost": "$0.7/$1.4 per 1M",
        "reasoning": True,
        "tools": True,
        "note": "Versi ringan Aion 3.0.",
    },
    "aion-labs/aion-2.0": {
        "provider": "aion",
        "label": "Aion 2.0",
        "context": 131072,
        "tier": "roleplay",
        "cost": "$0.8/$1.6 per 1M",
        "reasoning": True,
        "tools": True,
        "note": "Roleplay imersif — pelatih skenario & roleplay pelanggan.",
    },
    "aion-labs/aion-rp-llama-3.1-8b": {
        "provider": "aion",
        "label": "Aion-RP 1.0 (8B)",
        "context": 32768,
        "tier": "resepsionis",
        "cost": "$0.8/$1.6 per 1M",
        "reasoning": False,
        "tools": False,
        "note": "Ramah & ringan — resepsionis ruang penerima pesan.",
    },
}

# Model yang PASTI tidak dipakai lagi (sudah dimatikan provider) — dijaga agar
# konfigurasi lama otomatis dimigrasikan, bukan diam-diam error.
RETIRED: dict[str, str] = {
    "llama-3.1-8b-instant": "Groq mematikan Llama 3.1 8B (16 Agu 2026) → openai/gpt-oss-20b",
    "llama-3.3-70b-versatile": "Groq mematikan Llama 3.3 70B (16 Agu 2026) → pakai openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct": "Dimatikan Groq (17 Jul 2026) → openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "Dimatikan Groq (9 Mar 2026) → openai/gpt-oss-120b",
    "qwen/qwen3-32b": "Dimatikan Groq (17 Jul 2026) → qwen/qwen3.6-27b",
    "moonshotai/kimi-k2-instruct-0905": "Dimatikan Groq (15 Apr 2026) → openai/gpt-oss-120b",
    "meta-llama/llama-guard-4-12b": "Dimatikan Groq (5 Mar 2026) → openai/gpt-oss-safeguard-20b",
    "google/gemini-2.5-pro": "OpenRouter menandai expired 20 Okt 2026",
    "google/gemini-2.5-flash": "OpenRouter menandai expired 20 Okt 2026",
    "google/gemini-2.5-flash-lite": "OpenRouter menandai expired 20 Okt 2026",
    "qwen/qwen3.5-9b": "OpenRouter menandai expired 21 Okt 2026",
    "z-ai/glm-4.5": "OpenRouter menandai expired 31 Des 2026",
    "z-ai/glm-4.7": "OpenRouter menandai expired 31 Des 2026",
    "poolside/laguna-s-2.1": "OpenRouter menandai expired 31 Okt 2026",
    "poolside/laguna-xs-2.1": "OpenRouter menandai expired 31 Okt 2026",
    "bytedance-seed/seed-1.6": "OpenRouter menandai expired 11 Nov 2026",
}

# Fallback berjenjang per role: dicoba berurutan bila model utama gagal.
ROLE_FALLBACK: dict[str, list[str]] = {
    "engineer": ["inclusionai/ling-3.1-flash", "cohere/north-mini-code:free", "openai/gpt-oss-120b"],
    "architect": [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openai/gpt-oss-120b",
        "moonshotai/kimi-k2.7-code",
    ],
    "researcher": [
        "thinkingmachines/inkling:free",
        "nvidia/nemotron-3.5-lightning:free",
        "qwen/qwen3.6-27b",
    ],
    "writer": ["aion-labs/aion-3.5", "aion-labs/aion-3.0", "inclusionai/ling-3.0-flash-sante:free"],
    "designer": [
        "google/gemma-4-31b-it:free",
        "qwen/qwen3.6-27b",
        "google/gemma-4-26b-a4b-it:free",
    ],
    "qa": ["nvidia/nemotron-3-super-120b-a12b:free", "openai/gpt-oss-120b"],
    "ops": ["openai/gpt-oss-120b", "nvidia/nemotron-3-super-120b-a12b:free"],
    "analyst": [
        "nvidia/nemotron-3.5-lightning:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openai/gpt-oss-120b",
    ],
    "reception": [
        "liquid/lfm-2.5-2.6b:free",
        "aion-labs/aion-rp-llama-3.1-8b",
        "apodex/apodex-1.1-mini:free",
    ],
    "intern": ["apodex/apodex-1.1-mini:free", "openai/gpt-oss-20b"],
    "marketing": ["aion-labs/aion-3.5-mini", "anthropic/claude-haiku-4.5", "aion-labs/aion-3.0-mini"],
    "security": [
        "openai/gpt-oss-safeguard-20b",
        "nvidia/nemotron-3.5-content-safety:free",
    ],
}

ALL_FALLBACK = [
    "openai/gpt-oss-120b",
    "inclusionai/ling-3.1-flash",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "aion-labs/aion-3.5-mini",
    "openai/gpt-oss-20b",
]


def migrate_model(model_id: str) -> str:
    """Model lama yang mati → pengganti terdekat yang masih hidup."""
    if model_id in MODELS:
        return model_id
    catatan = RETIRED.get(model_id, "")
    if "→" in catatan:
        pengganti = catatan.split("→")[-1].strip()
        if pengganti in MODELS:
            return pengganti
    return ALL_FALLBACK[0]


def is_retired(model_id: str) -> bool:
    return model_id in RETIRED


def models_for(provider: str) -> dict[str, dict]:
    return {k: v for k, v in MODELS.items() if v["provider"] == provider}


def model_label(model_id: str) -> str:
    return MODELS.get(model_id, {}).get("label", model_id)


def provider_of(model_id: str) -> str:
    return MODELS.get(model_id, {}).get("provider", "")


# ----------------------------------------------------------------------------- probe live
def _fetch_json(url: str, key: str = "", timeout: int = 20) -> dict | list:
    headers = {
        "Accept": "application/json",
        # Aion Labs menolak User-Agent bawaan Python (403), jadi kita pakai UA browser.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AOG-Virtual-Office/2.0",
    }
    req = urllib.request.Request(url, headers=headers)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL tetap
        return json.loads(resp.read().decode("utf-8"))


def _normalise_ids(payload, provider: str) -> set[str]:
    """Ubah payload /models tiap provider menjadi set id model."""
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("models") or []
    else:
        rows = payload or []
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = row.get("id") or row.get("model") or ""
        if not mid:
            continue
        ids.add(mid)
        # Groq memakai id polos ("openai/gpt-oss-120b"); OpenRouter memakai slug
        # lengkap ("nvidia/nemotron-3-ultra-550b-a55b:free"). Normalisasi dua arah.
        ids.add(str(mid).split(":")[-1] if provider == "groq" else mid)
        ids.add(str(mid).replace(":free", ""))
    return ids


def probe(provider: str, use_cache: bool = True) -> dict:
    """Cek katalog live sebuah provider.

    Mengembalikan {"ok", "checked_at", "ids", "live", "dead", "error"}.
    `live`/`dead` dihitung dari katalog lokal MODELS milik provider itu.
    """
    from .state import load_cache, save_cache  # import lokal: hindari siklus

    cache_key = f"probe::{provider}"
    if use_cache:
        cached = load_cache(cache_key, ttl=CACHE_TTL)
        if cached is not None:
            return cached

    meta = PROVIDERS[provider]
    key = get_key(provider)
    result: dict = {
        "provider": provider,
        "ok": False,
        "checked_at": time.time(),
        "ids": [],
        "live": [],
        "dead": [],
        "key_present": bool(key),
        "error": "",
    }
    try:
        payload = _fetch_json(meta["models_url"], key=key)
        ids = _normalise_ids(payload, provider)
        result["ids"] = sorted(ids)
        result["ok"] = True
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        result["error"] = f"{type(exc).__name__}: {exc}"

    mine = models_for(provider)
    if result["ok"] and result["ids"]:
        live_ids = set(result["ids"])
        for mid in mine:
            bare = mid.replace(":free", "")
            if mid in live_ids or bare in live_ids:
                result["live"].append(mid)
            else:
                result["dead"].append(mid)
    else:
        # Tidak bisa diverifikasi (mis. katalog butuh key) → anggap sesuai katalog lokal.
        result["live"] = sorted(mine)
    save_cache(cache_key, result, ttl=CACHE_TTL)
    return result


def probe_all(use_cache: bool = True) -> dict[str, dict]:
    return {p: probe(p, use_cache=use_cache) for p in PROVIDERS}


def live_models(use_cache: bool = True) -> dict[str, bool]:
    """Peta model_id -> True bila terverifikasi hidup di katalog live."""
    status: dict[str, bool] = {}
    for provider, res in probe_all(use_cache=use_cache).items():
        for mid in models_for(provider):
            status[mid] = mid in res.get("live", [])
    return status

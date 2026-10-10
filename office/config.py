"""Konfigurasi global: kunci secrets, provider, dan batas-batas sistem."""
from __future__ import annotations

import os

try:  # pragma: no cover - streamlit selalu ada saat runtime app
    import streamlit as st

    _HAS_ST = True
except Exception:  # pragma: no cover - dipakai saat test tanpa streamlit
    st = None
    _HAS_ST = False


APP_NAME = "AOG Virtual Office"
APP_TAGLINE = "Kantor simulasi berisi karyawan model AI — Anda bosnya."
VERSION = "3.0.0"

# ----------------------------------------------------------------------------- secrets
SECRET_KEYS = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "aion": "AION_API_KEY",
    "github": "GITHUB_TOKEN",
}

# Nama alternatif yang masih diterima (memudahkan migrasi secrets lama)
SECRET_ALIASES = {
    "openrouter": ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "OPEN_ROUTER_API_KEY"],
    "aion": ["AION_API_KEY", "AION_LABS_API_KEY", "AIONLABS_API_KEY"],
    "groq": ["GROQ_API_KEY", "GROQ_KEY"],
    "github": ["GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"],
}


def _read_secret(name: str) -> str:
    """Ambil nilai secret dari st.secrets lalu environment variable."""
    if _HAS_ST:
        try:
            val = st.secrets.get(name, "")
            if val:
                return str(val).strip()
        except Exception:
            pass
    return str(os.environ.get(name, "")).strip()


def get_key(provider: str) -> str:
    """Kembalikan API key untuk provider (groq/openrouter/aion/github)."""
    for candidate in SECRET_ALIASES.get(provider, [SECRET_KEYS.get(provider, provider.upper())]):
        val = _read_secret(candidate)
        if val:
            return val
    return ""


def has_key(provider: str) -> bool:
    return bool(get_key(provider))


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_secrets_file() -> dict[str, str]:
    """Baca kunci yang tersimpan di .streamlit/secrets.toml (bila ada)."""
    try:
        import tomllib

        with open(SECRETS_FILE, "rb") as fh:
            data = tomllib.load(fh)
        return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def write_secrets_file(values: dict[str, str]) -> list[str]:
    """Gabungkan kunci baru ke secrets.toml tanpa menghapus kunci lama.

    Mengembalikan daftar nama kunci yang benar-benar ditulis.
    """
    current = read_secrets_file()
    written = []
    for key, value in values.items():
        value = (value or "").strip()
        if not value:
            continue
        current[key] = value
        written.append(key)
    if not written:
        return written
    os.makedirs(os.path.dirname(SECRETS_FILE), exist_ok=True)
    lines = [f'{k} = "{_escape_toml(v)}"' for k, v in current.items()]
    header = "# Kunci API AOG Virtual Office (jangan commit berkas ini)\n"
    tmp = SECRETS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(header + "\n".join(lines) + "\n")
    os.replace(tmp, SECRETS_FILE)
    return written


# ----------------------------------------------------------------------------- provider
PROVIDERS: dict[str, dict] = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_url": "https://api.groq.com/openai/v1/models",
        "key_env": "GROQ_API_KEY",
        "color": "#F55036",
        "tagline": "LPU super cepat — karyawan yang ngetiknya kilat",
        "free_tier": "30 req/menit · 1.000 req/hari · 8K token/menit",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": "https://openrouter.ai/api/v1/models",
        "key_env": "OPENROUTER_API_KEY",
        "color": "#8B5CF6",
        "tagline": "Ratusan model dalam satu kunci — departemen spesialis",
        "free_tier": "Model :free = 20 req/menit · 50 req/hari · 1.000 req/hari total",
    },
    "aion": {
        "label": "Aion Labs",
        "base_url": "https://api.aionlabs.ai/v1",
        "models_url": "https://api.aionlabs.ai/v1/models",
        "key_env": "AION_API_KEY",
        "color": "#22C55E",
        "tagline": "Model roleplay & narasi — tim kreatif dan humas",
        "free_tier": "15 req/menit · 20K token/hari",
    },
}

PROVIDER_ORDER = ["groq", "openrouter", "aion"]

# ----------------------------------------------------------------------------- batasan
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1200
MAX_CONTEXT_CHARS = 9000  # pemotong konteks supaya tidak boros token
HTTP_TIMEOUT = 90  # detik
CACHE_TTL = 300  # detik cache health-check & GitHub
TICK_MS = 1500  # interval auto-refresh panggung kantor

# ----------------------------------------------------------------------------- path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
SECRETS_FILE = os.path.join(ROOT_DIR, ".streamlit", "secrets.toml")
STATE_FILE = os.path.join(DATA_DIR, "office_state.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

for _d in (DATA_DIR, EXPORT_DIR):
    os.makedirs(_d, exist_ok=True)

# Nama boss (bisa diubah dari UI, disimpan di config.json)
DEFAULT_BOSS_NAME = "Boss Ampera"
DEFAULT_COMPANY = "Ampera Official Group"

"""Penyimpanan state kantor (JSON di disk) + cache kecil.

Dipakai oleh Streamlit yang stateless: semua yang harus bertahan antar-rerun
disimpan di data/office_state.json. Penulisan memakai file sementara + rename
agar tidak korup kalau proses mati di tengah jalan.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from typing import Any

from .config import (
    CACHE_TTL,
    CONFIG_FILE,
    DATA_DIR,
    DEFAULT_BOSS_NAME,
    DEFAULT_COMPANY,
    EXPORT_DIR,
    STATE_FILE,
    STREAMLIT_APP_URLS,
)

_CACHE: dict[str, tuple[float, Any]] = {}
_IO_LOCK = threading.RLock()
_SCHEMA_VERSION = 4

# ----------------------------------------------------------------------------- util
def _atomic_write(path: str, payload: Any) -> None:
    directory = os.path.dirname(path) or "."
    with _IO_LOCK:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def load_json(path: str, default: Any = None) -> Any:
    try:
        with _IO_LOCK, open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return copy.deepcopy(default) if default is not None else default
    except (json.JSONDecodeError, OSError, TypeError):
        return copy.deepcopy(default) if default is not None else default


def save_json(path: str, payload: Any) -> None:
    _atomic_write(path, payload)


# ----------------------------------------------------------------------------- cache
def load_cache(key: str, ttl: int = CACHE_TTL) -> Any | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    stamp, value = hit
    if time.time() - stamp > ttl:
        _CACHE.pop(key, None)
        return None
    return value


def save_cache(key: str, value: Any, ttl: int = CACHE_TTL) -> None:
    _CACHE[key] = (time.time(), value)


def clear_cache(prefix: str = "") -> int:
    keys = [k for k in _CACHE if not prefix or k.startswith(prefix)]
    for k in keys:
        _CACHE.pop(k, None)
    return len(keys)


# ----------------------------------------------------------------------------- config
def default_config() -> dict[str, Any]:
    return {
        "boss_name": DEFAULT_BOSS_NAME,
        "company": DEFAULT_COMPANY,
        "theme": "night",
        "auto_approve": False,
        "auto_refresh": True,
        "tick_ms": 1500,
        "show_model_badges": True,
        "sound": False,
        "github": {
            "owner": "amperaofficial26-beep",
            "repos": [
                "Ampera-Web-Design",
                "Ampera-Scribe",
                "Room-Chat-Ampera-Group",
            ],
            "branch": "main",
            "auto_sync": True,
        },
        "streamlit_apps": [
            {
                "name": "Ampera Web Design",
                "url": STREAMLIT_APP_URLS["Ampera-Web-Design"],
                "repo": "Ampera-Web-Design",
                "owner": "Karyawan Desain",
                "status": "belum dicek",
            },
            {
                "name": "Ampera Scribe",
                "url": STREAMLIT_APP_URLS["Ampera-Scribe"],
                "repo": "Ampera-Scribe",
                "owner": "Karyawan Dokumentasi",
                "status": "belum dicek",
            },
            {
                "name": "Room Chat Ampera Group",
                "url": STREAMLIT_APP_URLS["Room-Chat-Ampera-Group"],
                "repo": "Room-Chat-Ampera-Group",
                "owner": "Karyawan Hummas",
                "status": "belum dicek",
            },
        ],
    }


def load_config() -> dict[str, Any]:
    cfg = default_config()
    saved = load_json(CONFIG_FILE, {}) or {}
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    save_json(CONFIG_FILE, cfg)


def update_config(**patch: Any) -> dict[str, Any]:
    cfg = load_config()
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    save_config(cfg)
    return cfg


# ----------------------------------------------------------------------------- state
def empty_state() -> dict[str, Any]:
    return {
        "schema": _SCHEMA_VERSION,
        "created_at": time.time(),
        "sim_clock": time.time(),
        "day": 1,
        "employees": {},
        "tasks": [],
        "inbox": [],
        "log": [],
        "releases": [],
        "chats": {},
        "stats": {
            "tasks_created": 0,
            "tasks_done": 0,
            "tasks_rejected": 0,
            "tasks_revised": 0,
            "api_calls": 0,
            "api_errors": 0,
            "releases": 0,
            "xp": 0,
        },
    }


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    """Normalisasi state lama/rusak tanpa membuang progres pengguna."""
    if not isinstance(state, dict):
        return empty_state()
    base = empty_state()
    for key in ("created_at", "sim_clock", "day", "employees", "tasks", "inbox", "log", "releases", "chats"):
        if key in state:
            base[key] = copy.deepcopy(state[key])

    # Merge dari default ke nilai lama, bukan sebaliknya, agar statistik baru
    # selalu tersedia setelah upgrade schema.
    old_stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    for key, default in base["stats"].items():
        try:
            base["stats"][key] = max(0, int(old_stats.get(key, default)))
        except (TypeError, ValueError):
            base["stats"][key] = default

    for key in ("tasks", "inbox", "log", "releases"):
        if not isinstance(base[key], list):
            base[key] = []
    if not isinstance(base["employees"], dict):
        base["employees"] = {}
    if not isinstance(base["chats"], dict):
        base["chats"] = {}

    # Field baru task diberi default. Item rusak dilewati daripada membuat
    # seluruh kantor gagal dibuka.
    clean_tasks = []
    for task in base["tasks"]:
        if not isinstance(task, dict) or not task.get("tid"):
            continue
        task.setdefault("history", [])
        task.setdefault("revision_history", [])
        task.setdefault("quality", {})
        task.setdefault("quality_score", 0)
        task.setdefault("attempt_count", 0)
        task.setdefault("previous_result", "")
        task.setdefault("files", [])
        task.setdefault("sources", [])
        clean_tasks.append(task)
    base["tasks"] = clean_tasks
    base["schema"] = _SCHEMA_VERSION
    return base


def load_state() -> dict[str, Any]:
    raw = load_json(STATE_FILE, None)
    if raw is None:
        state = empty_state()
        save_json(STATE_FILE, state)
        return state
    state = migrate_state(raw)
    # roster selalu disegarkan dari models.ROSTER supaya model yang mati
    # otomatis tergantikan tanpa menghapus progres tugas.
    from .roster import sync_employees

    state["employees"] = sync_employees(state.get("employees", {}))
    return state


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def reset_state() -> dict[str, Any]:
    state = empty_state()
    from .roster import sync_employees

    state["employees"] = sync_employees({})
    save_json(STATE_FILE, state)
    return state


# ----------------------------------------------------------------------------- ekspor
def export_snapshot(prefix: str = "office") -> str:
    """Tulis salinan state + config ke data/exports dan kembalikan path-nya."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(EXPORT_DIR, f"{prefix}-{stamp}.json")
    save_json(
        path,
        {"config": load_config(), "state": load_json(STATE_FILE, empty_state()), "exported_at": stamp},
    )
    return path


def data_dir() -> str:
    return DATA_DIR

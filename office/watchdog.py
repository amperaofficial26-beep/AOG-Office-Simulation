"""Pengawas aplikasi Streamlit milik bos.

Pengawas berjalan di thread latar (daemon) selama aplikasi ini hidup. Setiap interval
setiap aplikasi terdaftar (URL + repo) dicek. Bila aplikasi mati atau tidur
(hibernasi Streamlit Community Cloud), pengawas me-reboot-nya dengan membuat commit
kosong di branch default repo-nya lewat GitHub REST API. Push ke repo yang terhubung
membuat Streamlit Community Cloud membangun ulang dan menjalankan ulang aplikasi,
setara dengan tombol "Reboot app" (Streamlit tidak menyediakan API reboot publik).

Pengaman:
* `fail_threshold` pengecekan gagal berturut-turut sebelum reboot (hindari reboot palsu),
* jeda `cooldown_min` menit antar-reboot per aplikasi,
* batas `max_reboots_per_day` reboot per aplikasi per hari.

Token GitHub diambil dari secrets (GITHUB_TOKEN) lewat `office.config.get_key`.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from . import apps as apps_mod
from .config import GITHUB_API, WATCHDOG_FILE, get_key
from .state import load_config, load_json, save_json, update_config

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "interval_min": 5,
    "fail_threshold": 2,
    "cooldown_min": 30,
    "max_reboots_per_day": 6,
}
MAX_EVENTS = 50
REBOOT_MESSAGE = "chore: reboot Streamlit via AOG Pengawas ({stamp} UTC)"

_LOCK = threading.RLock()  # satu siklus pengecekan dalam satu waktu
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


# ----------------------------------------------------------------------------- pengaturan
def settings() -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    override = load_config().get("watchdog", {})
    if isinstance(override, dict):
        merged.update({k: v for k, v in override.items() if k in DEFAULT_SETTINGS})
    return merged


def set_enabled(value: bool) -> None:
    update_config(watchdog={"enabled": bool(value)})


# ----------------------------------------------------------------------------- state
def _load() -> dict[str, Any]:
    data = load_json(WATCHDOG_FILE, {}) or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("apps", {})
    data.setdefault("events", [])
    data.setdefault("last_cycle", 0)
    return data


def _save(data: dict[str, Any]) -> None:
    save_json(WATCHDOG_FILE, data)


def _event(data: dict[str, Any], name: str, message: str) -> None:
    data["events"].append({"ts": time.time(), "app": name, "message": message})
    data["events"] = data["events"][-MAX_EVENTS:]


def snapshot() -> dict[str, Any]:
    """Keadaan pengawas untuk ditampilkan di UI."""
    data = _load()
    return {
        "settings": settings(),
        "last_cycle": data.get("last_cycle", 0),
        "apps": data.get("apps", {}),
        "events": list(reversed(data.get("events", [])))[:10],
        "thread_alive": bool(_THREAD and _THREAD.is_alive()),
        "token": bool(get_key("github")),
    }


# ----------------------------------------------------------------------------- target
def split_repo(repo: str, default_owner: str) -> tuple[str, str]:
    """'owner/repo' atau 'repo' (memakai owner GitHub dari config)."""
    repo = (repo or "").strip().strip("/")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner, name
    owner = load_config().get("github", {}).get("owner", "") or default_owner
    return owner, repo


def targets() -> list[dict[str, Any]]:
    """Aplikasi yang punya URL dan repo, siap diawasi."""
    out = []
    for row in apps_mod.apps():
        url = str(row.get("url", "")).strip()
        repo = str(row.get("repo", "")).strip()
        if not url or not repo:
            continue
        owner, name = split_repo(repo, "")
        if not owner or not name:
            continue
        out.append({"name": row.get("name", name), "url": url, "owner": owner, "repo": name})
    return out


# ----------------------------------------------------------------------------- GitHub
class RebootError(RuntimeError):
    pass


def _api(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_key("github")
    if not token:
        raise RebootError("GITHUB_TOKEN belum diisi di Secrets, reboot tidak bisa dilakukan.")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AOG-Virtual-Office",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RebootError(f"GitHub HTTP {exc.code} pada {path}: {detail}") from exc
    except Exception as exc:
        raise RebootError(f"{type(exc).__name__}: {exc}") from exc


def reboot_repo(owner: str, repo: str, branch: str = "") -> str:
    """Picu redeploy dengan commit kosong di branch default. Mengembalikan SHA commit baru."""
    info = _api("GET", f"/repos/{owner}/{repo}")
    branch = branch or info.get("default_branch") or "main"
    head = _api("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")["object"]["sha"]
    tree = _api("GET", f"/repos/{owner}/{repo}/git/commits/{head}")["tree"]["sha"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    commit = _api(
        "POST",
        f"/repos/{owner}/{repo}/git/commits",
        {"message": REBOOT_MESSAGE.format(stamp=stamp), "tree": tree, "parents": [head]},
    )
    _api("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": False})
    return commit["sha"]


# ----------------------------------------------------------------------------- siklus
def classify(result: dict[str, Any]) -> str:
    if result.get("ok"):
        return "hidup"
    if result.get("sleeping"):
        return "tidur"
    return "mati"


def run_cycle(force: bool = False) -> dict[str, Any]:
    """Cek semua aplikasi lalu reboot yang bermasalah.

    `force=True` (tombol manual) melewati `fail_threshold`, tetapi tetap menghormati
    jeda dan batas harian agar tidak membanjiri repo dengan commit.
    """
    with _LOCK:
        data = _load()
        cfg = settings()
        now = time.time()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for target in targets():
            rec = data["apps"].setdefault(
                target["url"],
                {"fail_streak": 0, "last_reboot_at": 0, "reboot_day": "", "reboots_today": 0},
            )
            result = apps_mod.check_url(target["url"])
            status = classify(result)
            rec.update(
                name=target["name"],
                repo=f"{target['owner']}/{target['repo']}",
                status=status,
                checked_at=now,
                latency_ms=result.get("latency_ms", 0),
                error=result.get("error", ""),
            )
            if status == "hidup":
                if rec["fail_streak"]:
                    _event(data, target["name"], "kembali hidup")
                rec["fail_streak"] = 0
                continue

            rec["fail_streak"] += 1
            if not cfg.get("enabled") and not force:
                continue
            if rec["fail_streak"] < int(cfg["fail_threshold"]) and not force:
                continue
            if now - rec.get("last_reboot_at", 0) < int(cfg["cooldown_min"]) * 60:
                continue
            if rec.get("reboot_day") == today and rec.get("reboots_today", 0) >= int(cfg["max_reboots_per_day"]):
                _event(data, target["name"], "batas reboot harian tercapai, dilewati")
                continue

            try:
                sha = reboot_repo(target["owner"], target["repo"])
            except RebootError as exc:
                _event(data, target["name"], f"gagal reboot ({status}): {exc}")
                continue
            if rec.get("reboot_day") != today:
                rec["reboot_day"], rec["reboots_today"] = today, 0
            rec["reboots_today"] += 1
            rec["last_reboot_at"] = now
            rec["fail_streak"] = 0
            _event(data, target["name"], f"status {status} → reboot dipicu (commit {sha[:7]})")

        data["last_cycle"] = now
        _save(data)
        return data


# ----------------------------------------------------------------------------- latar belakang
def _loop() -> None:
    while not _STOP.is_set():
        cfg = settings()
        if cfg.get("enabled"):
            try:
                run_cycle()
            except Exception as exc:  # pragma: no cover - jangan sampai thread mati
                with _LOCK:
                    data = _load()
                    _event(data, "pengawas", f"siklus gagal: {type(exc).__name__}: {exc}")
                    _save(data)
        _STOP.wait(max(1, int(cfg.get("interval_min", 5))) * 60)


def ensure_running() -> bool:
    """Pastikan thread pengawas hidup (aman dipanggil berulang kali oleh Streamlit)."""
    global _THREAD
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="aog-pengawas", daemon=True)
        _THREAD.start()
        return True

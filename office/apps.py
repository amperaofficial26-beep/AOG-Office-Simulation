"""Registri aplikasi Streamlit milik bos + pemeriksa status URL.

Aplikasi didaftarkan lewat UI (nama + URL + repo terkait). Statusnya dicek dengan
HTTP HEAD/GET singkat, jadi panel "Ruang Rilis" menunjukkan mana yang hidup.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Any

from .config import STREAMLIT_APP_URLS
from .state import load_config, update_config

CHECK_TIMEOUT = 12

# Teks halaman "aplikasi tidur" milik Streamlit Community Cloud (hibernasi setelah 12 jam tanpa trafik).
SLEEP_MARKERS = ("gone to sleep due to inactivity", "get this app back up", "app state: zzzz")


def apps() -> list[dict[str, Any]]:
    rows = [dict(r) for r in load_config().get("streamlit_apps", [])]
    for row in rows:  # isi URL yang kosong dari daftar bawaan (berdasarkan nama repo)
        if not str(row.get("url", "")).strip() and row.get("repo") in STREAMLIT_APP_URLS:
            row["url"] = STREAMLIT_APP_URLS[row["repo"]]
    return rows


def save_apps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = []
    for row in rows:
        clean.append(
            {
                "name": str(row.get("name", "")).strip() or "Aplikasi tanpa nama",
                "url": str(row.get("url", "")).strip(),
                "repo": str(row.get("repo", "")).strip(),
                "owner": str(row.get("owner", "")).strip(),
                "status": str(row.get("status", "belum dicek")),
                "checked_at": row.get("checked_at", 0),
                "latency_ms": row.get("latency_ms", 0),
                "note": str(row.get("note", "")),
            }
        )
    update_config(streamlit_apps=clean)
    return clean


def add_app(name: str, url: str, repo: str = "", owner: str = "") -> list[dict[str, Any]]:
    rows = apps()
    rows.append(
        {
            "name": name.strip() or "Aplikasi baru",
            "url": url.strip(),
            "repo": repo.strip(),
            "owner": owner.strip(),
            "status": "belum dicek",
            "checked_at": 0,
            "latency_ms": 0,
            "note": "",
        }
    )
    return save_apps(rows)


def remove_app(index: int) -> list[dict[str, Any]]:
    rows = apps()
    if 0 <= index < len(rows):
        rows.pop(index)
    return save_apps(rows)


def check_url(url: str) -> dict[str, Any]:
    """Cek satu URL: mengembalikan status, kode HTTP, dan latensi."""
    if not url:
        return {"ok": False, "status": "tanpa URL", "code": 0, "latency_ms": 0, "error": "URL kosong"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    started = time.time()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (AOG-Virtual-Office health check)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:  # noqa: S310
            code = int(resp.status)
            body = resp.read(65536).decode("utf-8", errors="replace")
        latency = int((time.time() - started) * 1000)
        lowered = body.lower()
        sleeping = any(marker in lowered for marker in SLEEP_MARKERS)
        streamlit_like = "streamlit" in lowered or "_stcore" in lowered or code == 200
        if sleeping:
            return {
                "ok": False,
                "status": "tidur",
                "code": code,
                "latency_ms": latency,
                "streamlit_like": streamlit_like,
                "sleeping": True,
                "error": "aplikasi sedang tidur (hibernasi Streamlit)",
            }
        return {
            "ok": 200 <= code < 400,
            "status": "hidup" if 200 <= code < 400 else f"kode {code}",
            "code": code,
            "latency_ms": latency,
            "streamlit_like": streamlit_like,
            "sleeping": False,
            "error": "",
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": f"HTTP {exc.code}",
            "code": exc.code,
            "sleeping": False,
            "latency_ms": int((time.time() - started) * 1000),
            "error": str(exc.reason),
        }
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        return {
            "ok": False,
            "status": "tidak terjangkau",
            "code": 0,
            "sleeping": False,
            "latency_ms": int((time.time() - started) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }


def check_all() -> list[dict[str, Any]]:
    """Cek semua aplikasi terdaftar lalu simpan hasilnya."""
    rows = apps()
    for row in rows:
        result = check_url(row.get("url", ""))
        row["status"] = result["status"]
        row["latency_ms"] = result["latency_ms"]
        row["checked_at"] = time.time()
        row["note"] = result.get("error", "")
    save_apps(rows)
    return rows


def summary(rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Ringkasan jumlah aplikasi per status."""
    rows = rows if rows is not None else apps()
    alive = sum(1 for r in rows if r.get("status") == "hidup")
    unknown = sum(1 for r in rows if r.get("status") == "belum dicek")
    tanpa_url = sum(1 for r in rows if r.get("status") == "tanpa URL")
    dead = sum(
        1 for r in rows if r.get("status") not in ("hidup", "belum dicek", "tanpa URL")
    )
    return {
        "total": len(rows),
        "hidup": alive,
        "mati": dead,
        "tanpa_url": tanpa_url,
        "belum_dicek": unknown,
    }

"""Mesin permainan: alur tugas, persetujuan bos, aktivitas karyawan, dan statistik."""
from __future__ import annotations

import random
import time
from typing import Any

from . import llm
from .config import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from .models import ROLE_FALLBACK, model_label, provider_of
from .models_data import (
    EMP_COFFEE,
    EMP_GAMING,
    EMP_IDLE,
    EMP_NAP,
    EMP_WALKING,
    EMP_WORKING,
    TASK_APPROVED,
    TASK_ARCHIVED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_REJECTED,
    TASK_REVIEW,
    TASK_WORKING,
    Employee,
    Task,
    new_id,
    now,
)
from .quality import clean_response, evaluate_response, recommended_max_tokens
from .roster import BOSS_SPOT, ROOMS, break_spot, desk_spot, employee_from_state
from .state import load_config, load_state, save_state

BREAK_STATES = [EMP_COFFEE, EMP_GAMING, EMP_NAP, EMP_IDLE]
BREAK_DURATION = 45.0  # detik sebelum karyawan kembali ke mejanya
VALID_PRIORITIES = {"rendah", "normal", "tinggi"}
PRIORITY_ORDER = {"tinggi": 0, "normal": 1, "rendah": 2}
RUNNABLE_STATES = {TASK_QUEUED, TASK_FAILED, TASK_REJECTED}


# ----------------------------------------------------------------------------- helpers
def _log(state: dict[str, Any], text: str, kind: str = "info", who: str = "") -> None:
    state.setdefault("log", []).insert(
        0,
        {"at": now(), "text": text, "kind": kind, "who": who},
    )
    del state["log"][200:]


def _stats(state: dict[str, Any], key: str, amount: int = 1) -> None:
    state.setdefault("stats", {})
    state["stats"][key] = state["stats"].get(key, 0) + amount


def _emp(state: dict[str, Any], eid: str) -> dict[str, Any] | None:
    return state.get("employees", {}).get(eid)


def get_task(state: dict[str, Any], tid: str) -> dict[str, Any] | None:
    for task in state.get("tasks", []):
        if task.get("tid") == tid:
            return task
    return None


def tasks_by_status(state: dict[str, Any], *statuses: str) -> list[dict[str, Any]]:
    wanted = set(statuses)
    return [t for t in state.get("tasks", []) if t.get("status") in wanted]


def employee_obj(state: dict[str, Any], eid: str) -> Employee | None:
    data = _emp(state, eid)
    return employee_from_state(data) if data else None


# ----------------------------------------------------------------------------- tugas
def create_task(
    state: dict[str, Any],
    *,
    title: str,
    brief: str,
    assignee: str,
    deliverable: str = "dokumen",
    priority: str = "normal",
    room: str = "",
    repo_context: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    emp = _emp(state, assignee)
    if emp is None:
        raise ValueError(f"Karyawan {assignee} tidak ditemukan")
    title = str(title or "").strip()
    brief = str(brief or "").strip()
    if not title:
        raise ValueError("Judul tugas wajib diisi")
    if not brief:
        raise ValueError("Brief tugas wajib diisi")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Prioritas tidak valid: {priority}")
    task_room = room or emp.get("room", "code")
    if task_room not in ROOMS:
        raise ValueError(f"Ruang tugas tidak valid: {task_room}")
    task = Task(
        tid=new_id("TGS"),
        title=title[:180],
        brief=brief[:20_000],
        assignee=assignee,
        room=task_room,
        deliverable=str(deliverable or "dokumen").strip() or "dokumen",
        priority=priority,
        repo_context=str(repo_context or "")[:50_000],
        model_used=emp.get("model", ""),
        provider_used=emp.get("provider", provider_of(emp.get("model", ""))),
    ).to_dict()
    task["history"].append({"at": now(), "status": TASK_QUEUED, "text": f"Tugas dibuat oleh bos untuk {emp['name']}"})
    state.setdefault("tasks", []).insert(0, task)
    _stats(state, "tasks_created")

    # karyawan berjalan ke ruang tugas
    emp["target_room"] = task["room"]
    emp["state"] = EMP_WALKING
    emp["state_until"] = now() + 1.6
    _log(state, f"Bos menugaskan {emp['name']}: {task['title']}", "task", emp["name"])
    save_state(state)
    return state, task


def run_task(state: dict[str, Any], tid: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Jalankan tugas secara nyata: panggil model milik karyawan."""
    task = get_task(state, tid)
    if task is None:
        return state, None
    if task.get("status") not in RUNNABLE_STATES:
        # Idempotensi: tombol ganda/rerun Streamlit tidak boleh memanggil API
        # atau mengubah hasil yang sudah menunggu persetujuan.
        return state, task
    emp = _emp(state, task["assignee"])
    cfg = load_config()
    if emp is None:
        task["status"] = TASK_FAILED
        task["error"] = "Karyawan yang ditugaskan tidak ada."
        save_state(state)
        return state, task

    emp["state"] = EMP_WORKING
    emp["state_until"] = now() + 12
    emp["target_room"] = task["room"]
    task["status"] = TASK_WORKING
    task["started_at"] = now()
    task["progress"] = 0.15
    save_state(state)

    messages = [
        {
            "role": "system",
            "content": llm.build_system_prompt(emp, cfg.get("company", "perusahaan"), cfg.get("boss_name", "Bos")),
        },
        {
            "role": "user",
            "content": llm.build_task_prompt(
                title=task["title"],
                brief=task["brief"],
                deliverable=task["deliverable"],
                priority=task["priority"],
                context=task.get("repo_context", ""),
                revision_note=task.get("boss_note", "") if task.get("revision_count") else "",
                history=task.get("history", []),
                role=emp.get("role", ""),
                previous_result=task.get("previous_result", "") if task.get("revision_count") else "",
            ),
        },
    ]

    task["progress"] = 0.55
    save_state(state)
    try:
        result, notes = llm.chat_with_fallback(
            messages,
            model=task.get("model_used") or emp.get("model", ""),
            fallbacks=[m for m in (emp.get("fallbacks") or [])],
            role_fallbacks=ROLE_FALLBACK.get(emp.get("role", ""), []),
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=max(DEFAULT_MAX_TOKENS, recommended_max_tokens(task["deliverable"], task["priority"])),
        )
    except llm.LLMError as exc:
        task["status"] = TASK_FAILED
        task["error"] = str(exc)
        task["finished_at"] = now()
        task["history"].append({"at": now(), "status": TASK_FAILED, "text": str(exc)})
        emp["state"] = EMP_IDLE
        emp["state_until"] = 0.0
        emp["mood"] = max(5, int(emp.get("mood", 80)) - 12)
        _stats(state, "api_errors")
        _log(state, f"{emp['name']} gagal mengerjakan {task['title']}: {exc}", "error", emp["name"])
        save_state(state)
        return state, task

    _stats(state, "api_calls")
    task["result"] = clean_response(result.text)
    task["quality"] = evaluate_response(task["result"], task["deliverable"], task["brief"])
    task["quality_score"] = task["quality"]["score"]
    task["attempt_count"] = int(task.get("attempt_count", 0)) + 1
    task["model_used"] = result.model
    task["provider_used"] = result.provider
    task["tokens_in"] = int(result.get("tokens_in") or 0)
    task["tokens_out"] = int(result.get("tokens_out") or 0)
    task["duration"] = round(float(result.get("latency") or 0.0), 2)
    task["progress"] = 1.0
    task["finished_at"] = now()
    task["status"] = TASK_REVIEW
    task["error"] = ""
    task["history"].append(
        {
            "at": now(),
            "status": TASK_REVIEW,
            "text": f"Selesai oleh {model_label(result.model)} dalam {task['duration']} detik",
        }
    )
    for note in notes:
        task["history"].append({"at": now(), "status": TASK_REVIEW, "text": note})

    emp["xp"] = int(emp.get("xp", 0)) + 12
    emp["level"] = 1 + int(emp["xp"]) // 100
    emp["energy"] = max(5, int(emp.get("energy", 90)) - 9)
    emp["mood"] = min(100, int(emp.get("mood", 80)) + 4)
    emp["last_task_at"] = now()
    emp["state"] = EMP_IDLE
    emp["state_until"] = now() + 2
    _log(
        state,
        f"{emp['name']} menyerahkan hasil: {task['title']}",
        "review",
        emp["name"],
    )
    save_state(state)
    return state, task


def run_queue(state: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    """Jalankan antrean secara deterministik: prioritas lalu waktu pembuatan.

    Snapshot id dibuat sebelum eksekusi agar perubahan status selama loop tidak
    membuat tugas terlewat atau terpanggil dua kali pada rerun Streamlit.
    """
    queue = [t for t in state.get("tasks", []) if t.get("status") == TASK_QUEUED]
    queue.sort(
        key=lambda t: (
            PRIORITY_ORDER.get(t.get("priority", "normal"), 1),
            float(t.get("created_at") or 0),
            str(t.get("tid", "")),
        )
    )
    if limit is not None:
        queue = queue[: max(0, int(limit))]
    completed: list[dict[str, Any]] = []
    for tid in [t["tid"] for t in queue]:
        _, result = run_task(state, tid)
        if result is not None:
            completed.append(result)
    return completed


def approve_task(
    state: dict[str, Any],
    tid: str,
    note: str = "",
    rating: int = 0,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    task = get_task(state, tid)
    if task is None:
        return state, None
    if task.get("status") != TASK_REVIEW:
        return state, task
    emp = _emp(state, task["assignee"])
    task["status"] = TASK_APPROVED
    task["decided_at"] = now()
    task["boss_note"] = note
    if rating:
        task["rating"] = max(1, min(5, int(rating)))
    task["history"].append({"at": now(), "status": TASK_APPROVED, "text": note or "Disetujui bos"})
    _stats(state, "tasks_done")
    _stats(state, "xp", 20)
    if emp:
        emp["tasks_done"] = int(emp.get("tasks_done", 0)) + 1
        emp["xp"] = int(emp.get("xp", 0)) + 25
        emp["level"] = 1 + int(emp["xp"]) // 100
        emp["mood"] = min(100, int(emp.get("mood", 80)) + 10)
        emp["state"] = EMP_IDLE
        emp["state_until"] = now() + 3
    _log(state, f"Bos menyetujui: {task['title']}", "approve", emp["name"] if emp else "")
    save_state(state)
    return state, task


def reject_task(
    state: dict[str, Any],
    tid: str,
    note: str = "",
    rerun: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    task = get_task(state, tid)
    if task is None:
        return state, None
    if task.get("status") != TASK_REVIEW:
        return state, task
    emp = _emp(state, task["assignee"])
    task["previous_result"] = task.get("result", "")
    task.setdefault("revision_history", []).append(
        {
            "at": now(),
            "result": task.get("result", ""),
            "quality_score": task.get("quality_score", 0),
            "note": note.strip() or "Perbaiki hasil sebelumnya.",
        }
    )
    del task["revision_history"][:-5]
    task["status"] = TASK_REJECTED
    task["decided_at"] = now()
    task["boss_note"] = note
    task["revision_count"] = int(task.get("revision_count", 0)) + 1
    task["history"].append(
        {"at": now(), "status": TASK_REJECTED, "text": note or "Ditolak bos, diminta perbaikan"}
    )
    _stats(state, "tasks_rejected")
    _stats(state, "tasks_revised")
    if emp:
        emp["tasks_rejected"] = int(emp.get("tasks_rejected", 0)) + 1
        emp["mood"] = max(5, int(emp.get("mood", 80)) - 14)
        emp["state"] = EMP_WALKING
        emp["state_until"] = now() + 2
    _log(state, f"Bos menolak: {task['title']}", "reject", emp["name"] if emp else "")
    if rerun:
        task["status"] = TASK_QUEUED
        task["progress"] = 0.0
        task["history"].append({"at": now(), "status": TASK_QUEUED, "text": "Dikerjakan ulang dengan catatan bos"})
        _log(state, f"{emp['name'] if emp else 'Karyawan'} mengerjakan ulang: {task['title']}", "task")
    save_state(state)
    return state, task


def archive_task(state: dict[str, Any], tid: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    task = get_task(state, tid)
    if task is None:
        return state, None
    task["status"] = TASK_ARCHIVED
    save_state(state)
    return state, task


def clear_archived(state: dict[str, Any]) -> dict[str, Any]:
    before = len(state.get("tasks", []))
    state["tasks"] = [t for t in state.get("tasks", []) if t.get("status") != TASK_ARCHIVED]
    removed = before - len(state["tasks"])
    _log(state, f"{removed} tugas arsip dibersihkan", "info")
    save_state(state)
    return state


# ----------------------------------------------------------------------------- rilis
def publish_release(
    state: dict[str, Any],
    task_ids: list[str],
    title: str = "",
    notes: str = "",
    repo: str = "",
) -> dict[str, Any]:
    wanted = set(task_ids)
    chosen = [
        t for t in state.get("tasks", [])
        if t.get("tid") in wanted and t.get("status") == TASK_APPROVED
    ]
    if not chosen:
        raise ValueError("Paket rilis harus berisi minimal satu tugas yang sudah disetujui")
    release = {
        "rid": new_id("REL"),
        "title": title or f"Paket rilis {time.strftime('%d %b %H:%M')}",
        "notes": notes,
        "repo": repo,
        "at": now(),
        "tasks": [
            {
                "tid": t["tid"],
                "title": t["title"],
                "assignee": t["assignee"],
                "model": t.get("model_used", ""),
            }
            for t in chosen
        ],
    }
    state.setdefault("releases", []).insert(0, release)
    for t in chosen:
        t["status"] = TASK_ARCHIVED
        t["history"].append({"at": now(), "status": TASK_ARCHIVED, "text": f"Masuk rilis {release['title']}"})
    _stats(state, "releases")
    _stats(state, "xp", 60)
    _log(state, f"Paket rilis diterbitkan: {release['title']} ({len(chosen)} tugas)", "release")
    save_state(state)
    return release


# ----------------------------------------------------------------------------- pesan
def push_inbox(
    state: dict[str, Any],
    sender: str,
    subject: str,
    body: str,
    channel: str = "email",
) -> dict[str, Any]:
    sender = str(sender or "Anonim").strip()[:120] or "Anonim"
    subject = str(subject or "(tanpa subjek)").strip()[:200] or "(tanpa subjek)"
    body = str(body or "").strip()[:20_000]
    channel = str(channel or "email").strip()[:40] or "email"
    msg = {
        "mid": new_id("MSG"),
        "sender": sender,
        "subject": subject,
        "body": body,
        "channel": channel,
        "at": now(),
        "read": False,
        "handled": "",
    }
    state.setdefault("inbox", []).insert(0, msg)
    del state["inbox"][120:]
    recep = next((e for e in state.get("employees", {}).values() if e.get("role") == "reception"), None)
    if recep:
        recep["state"] = EMP_WORKING
        recep["state_until"] = now() + 4
        recep["target_room"] = "reception"
    _log(state, f"Pesan masuk dari {sender}: {subject}", "inbox")
    save_state(state)
    return msg


def mark_read(state: dict[str, Any], mid: str) -> dict[str, Any]:
    for msg in state.get("inbox", []):
        if msg.get("mid") == mid:
            msg["read"] = True
            break
    save_state(state)
    return state


def delegate_message(state: dict[str, Any], mid: str, eid: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Ubah pesan masuk menjadi tugas untuk karyawan tertentu."""
    msg = next((m for m in state.get("inbox", []) if m.get("mid") == mid), None)
    if msg is None:
        return state, None
    if msg.get("handled"):
        return state, get_task(state, msg["handled"])
    emp = _emp(state, eid)
    if emp is None:
        return state, None
    state, task = create_task(
        state,
        title=msg["subject"][:80] or "Balasan pesan",
        brief=(
            f"Pesan dari {msg['sender']} melalui {msg['channel']}:\n\n{msg['body']}\n\n"
            "Susun balasan atau tindak lanjut yang siap dikirim."
        ),
        assignee=eid,
        deliverable="balasan pesan",
        priority="tinggi",
        room=emp.get("room", "reception"),
    )
    msg["handled"] = task["tid"]
    msg["read"] = True
    _log(state, f"Pesan {msg['subject'][:40]} didelegasikan ke {emp['name']}", "task", emp["name"])
    save_state(state)
    return state, task


def simulate_incoming(state: dict[str, Any]) -> dict[str, Any]:
    """Kirim satu pesan masuk acak (untuk meramaikan simulasi)."""
    pool = [
        ("Klien — PT Sinar Lampung", "Minta demo aplikasi Streamlit minggu ini",
         "Halo, kami tertarik melihat demo aplikasi yang sedang dikembangkan. Bisa dijadwalkan minggu ini?",
         "email"),
        ("Tim Produk", "Butuh halaman status layanan",
         "Pengguna sering bertanya layanan sedang down atau tidak. Mohon dibuat halaman status sederhana.",
         "chat"),
        ("Komunitas Telegram", "Laporan bug pada form",
         "Beberapa anggota melaporkan tombol kirim tidak merespons saat koneksi lambat.", "chat"),
        ("Partner", "Kolaborasi konten",
         "Kami ingin menawarkan kolaborasi konten untuk kampanye bulan depan.", "email"),
        ("Calon pengguna", "Pertanyaan harga",
         "Apakah aplikasi ini berbayar? Bagaimana skema langganannya?", "email"),
        ("Tim Internal", "Minta dokumentasi API",
         "Tim lain kesulitan memakai API kita. Tolong siapkan dokumentasi singkat plus contoh.", "chat"),
    ]
    sender, subject, body, channel = random.choice(pool)
    push_inbox(state, sender, subject, body, channel)
    return state


# ----------------------------------------------------------------------------- aktivitas
def tick(state: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Satu langkah simulasi: selesaikan jalan, pulihkan energi, atur aktivitas santai."""
    cfg = cfg or load_config()
    ts = now()
    busy = {
        t["assignee"]
        for t in state.get("tasks", [])
        if t.get("status") in (TASK_WORKING, TASK_QUEUED, TASK_REVIEW)
    }
    for emp in state.get("employees", {}).values():
        until = float(emp.get("state_until") or 0.0)
        current = emp.get("state", EMP_IDLE)
        if until and ts >= until:
            # aktivitas selesai
            if current == EMP_WALKING:
                emp["room"] = emp.get("target_room") or emp.get("room", "code")
                emp["pos"] = list(desk_spot(emp["room"], abs(hash(emp["eid"])) % 3))
                emp["target_room"] = ""
                emp["state"] = EMP_WORKING if emp["eid"] in busy else EMP_IDLE
                emp["state_until"] = ts + random.uniform(6, 14)
            elif current in BREAK_STATES:
                emp["state"] = EMP_WALKING
                emp["target_room"] = emp.get("home_room") or _home_room(emp)
                emp["state_until"] = ts + 1.8
            elif current == EMP_WORKING and emp["eid"] not in busy:
                emp["state"] = EMP_IDLE
                emp["state_until"] = ts + random.uniform(8, 20)
            else:
                emp["state"] = EMP_IDLE
                emp["state_until"] = ts + random.uniform(8, 20)
        # pemulihan energi
        emp["energy"] = min(100, int(emp.get("energy", 90)) + (2 if current in BREAK_STATES else 1))
        # kalau energi habis dan tidak sedang bekerja, pergi ke pantry
        if int(emp.get("energy", 90)) < 25 and emp["eid"] not in busy and current == EMP_IDLE:
            emp["home_room"] = emp.get("home_room") or _home_room(emp)
            emp["target_room"] = "break"
            emp["state"] = EMP_WALKING
            emp["state_until"] = ts + 1.8
        # karyawan menganggur kadang jalan-jalan
        elif current == EMP_IDLE and emp["eid"] not in busy and random.random() < 0.04:
            pick = random.choice([r for r in ROOMS if r != emp.get("room")])
            emp["home_room"] = emp.get("home_room") or _home_room(emp)
            emp["target_room"] = pick
            emp["state"] = EMP_WALKING
            emp["state_until"] = ts + random.uniform(1.4, 2.4)
            emp["facing"] = 1 if ROOMS[pick].gx > ROOMS[emp.get("room", "code")].gx else -1
        elif current == EMP_IDLE and random.random() < 0.05:
            emp["state"] = random.choice([EMP_IDLE, EMP_COFFEE, EMP_GAMING, EMP_NAP])
            emp["state_until"] = ts + random.uniform(6, 16)
    # jam kantor
    state["sim_clock"] = ts
    if ts - float(state.get("last_day_at") or ts) > 600:
        state["day"] = int(state.get("day", 1)) + 1
        state["last_day_at"] = ts
        _log(state, f"Hari kerja ke-{state['day']} dimulai", "info")
    save_state(state)
    return state


def _home_room(emp: dict[str, Any]) -> str:
    from .roster import ROSTER_BY_ID

    base = ROSTER_BY_ID.get(emp.get("eid", ""))
    return base.room if base else emp.get("room", "code")


def send_to_break(state: dict[str, Any], eid: str, duration: float = BREAK_DURATION) -> dict[str, Any]:
    emp = _emp(state, eid)
    if emp is None:
        return state
    emp["home_room"] = emp.get("home_room") or _home_room(emp)
    emp["target_room"] = "break"
    emp["state"] = EMP_WALKING
    emp["state_until"] = now() + 1.6
    emp["energy"] = 100
    _log(state, f"{emp['name']} diizinkan istirahat ke pantry", "info", emp["name"])
    save_state(state)
    return state


def recall_employee(state: dict[str, Any], eid: str) -> dict[str, Any]:
    emp = _emp(state, eid)
    if emp is None:
        return state
    emp["target_room"] = emp.get("home_room") or _home_room(emp)
    emp["state"] = EMP_WALKING
    emp["state_until"] = now() + 1.6
    _log(state, f"{emp['name']} dipanggil kembali ke meja", "info", emp["name"])
    save_state(state)
    return state


def chat_with_employee(state: dict[str, Any], eid: str, text: str) -> tuple[dict[str, Any], str]:
    emp = _emp(state, eid)
    if emp is None:
        return state, "Karyawan tidak ditemukan."
    text = str(text or "").strip()
    if not text:
        return state, "Pesan kosong."
    cfg = load_config()
    history = state.setdefault("chats", {}).setdefault(eid, [])
    try:
        result = llm.quick_reply(
            emp,
            text,
            cfg.get("company", "perusahaan"),
            cfg.get("boss_name", "Bos"),
            history=history,
        )
        reply = result.text
        _stats(state, "api_calls")
        emp["state"] = EMP_IDLE
        emp["state_until"] = now() + 3
        _log(state, f"Bos mengobrol dengan {emp['name']}", "info", emp["name"])
    except llm.LLMError as exc:
        reply = f"(belum bisa membalas: {exc})"
        _stats(state, "api_errors")
    state.setdefault("chats", {}).setdefault(eid, []).append(
        {"at": now(), "who": "boss", "text": text}
    )
    state["chats"][eid].append({"at": now(), "who": eid, "text": reply})
    del state["chats"][eid][:-24]
    save_state(state)
    return state, reply


# ----------------------------------------------------------------------------- ringkasan
def pending_count(state: dict[str, Any]) -> int:
    return len(tasks_by_status(state, TASK_REVIEW))


def summary(state: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for task in state.get("tasks", []):
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    return {
        "stats": state.get("stats", {}),
        "counts": counts,
        "pending": counts.get(TASK_REVIEW, 0),
        "employees": len(state.get("employees", {})),
        "inbox_unread": sum(1 for m in state.get("inbox", []) if not m.get("read")),
        "releases": len(state.get("releases", [])),
        "day": state.get("day", 1),
    }


def boss_position() -> tuple[float, float]:
    return BOSS_SPOT


def break_position(index: int = 0) -> tuple[float, float]:
    return break_spot(index)


def fresh_state() -> dict[str, Any]:
    state = load_state()
    tick(state)
    return state

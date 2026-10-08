"""Struktur data karyawan, ruang, dan tugas."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from .models import ROLE_FALLBACK, model_label, provider_of

# ----------------------------------------------------------------------------- status
TASK_QUEUED = "menunggu"
TASK_WORKING = "dikerjakan"
TASK_REVIEW = "menunggu persetujuan"
TASK_APPROVED = "disetujui"
TASK_REJECTED = "ditolak"
TASK_FAILED = "gagal"
TASK_ARCHIVED = "arsip"

TASK_STATES = [
    TASK_QUEUED,
    TASK_WORKING,
    TASK_REVIEW,
    TASK_APPROVED,
    TASK_REJECTED,
    TASK_FAILED,
    TASK_ARCHIVED,
]

TASK_ICON = {
    TASK_QUEUED: "schedule",
    TASK_WORKING: "precision_manufacturing",
    TASK_REVIEW: "pending_hourglass_bottom" if False else "hourglass_bottom",
    TASK_APPROVED: "task_alt",
    TASK_REJECTED: "close",
    TASK_FAILED: "error",
    TASK_ARCHIVED: "inventory_2",
}

TASK_COLOR = {
    TASK_QUEUED: "#94A3B8",
    TASK_WORKING: "#FBBF24",
    TASK_REVIEW: "#38BDF8",
    TASK_APPROVED: "#22C55E",
    TASK_REJECTED: "#F87171",
    TASK_FAILED: "#EF4444",
    TASK_ARCHIVED: "#64748B",
}

EMP_IDLE = "santai"
EMP_WALKING = "berjalan"
EMP_WORKING = "bekerja"
EMP_MEETING = "rapat"
EMP_COFFEE = "ngopi"
EMP_GAMING = "main game"
EMP_NAP = "istirahat"
EMP_CHAT = "mengobrol"
EMP_PRESENT = "presentasi"

EMP_STATES = [EMP_IDLE, EMP_WALKING, EMP_WORKING, EMP_MEETING, EMP_COFFEE, EMP_GAMING, EMP_NAP, EMP_CHAT, EMP_PRESENT]

EMP_ICON = {
    EMP_IDLE: "self_improvement",
    EMP_WALKING: "directions_run",
    EMP_WORKING: "precision_manufacturing",
    EMP_MEETING: "groups",
    EMP_COFFEE: "local_cafe",
    EMP_GAMING: "sports_esports",
    EMP_NAP: "nightlight",
    EMP_CHAT: "forum",
    EMP_PRESENT: "present_to_all" if False else "campaign",
}


# ----------------------------------------------------------------------------- ruang
@dataclass
class Room:
    rid: str
    name: str
    icon: str
    color: str
    desc: str
    # posisi grid isometrik (kolom, baris) + ukuran ruangan dalam tile
    gx: float
    gy: float
    gw: int = 3
    gh: int = 3
    furniture: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["furniture"] = list(self.furniture)
        return d


@dataclass
class Employee:
    eid: str
    name: str
    role: str
    role_label: str
    title: str
    provider: str
    model: str
    room: str
    personality: str
    greeting: str
    quirks: tuple[str, ...]
    skin: str = "#F6C9A0"
    hair: str = "#3B2A20"
    shirt: str = "#2563EB"
    accent: str = "#F59E0B"
    glasses: bool = False
    hair_style: str = "short"
    xp: int = 0
    level: int = 1
    tasks_done: int = 0
    tasks_rejected: int = 0
    mood: int = 80  # 0..100
    energy: int = 90  # 0..100
    state: str = EMP_IDLE
    state_until: float = 0.0
    target_room: str = ""
    pos: tuple[float, float] = (0.0, 0.0)
    facing: int = 1  # 1 kanan, -1 kiri
    hired_at: float = field(default_factory=time.time)
    last_task_at: float = 0.0
    desk: tuple[float, float] = (0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quirks"] = list(self.quirks)
        d["pos"] = list(self.pos)
        d["desk"] = list(self.desk)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Employee":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        data = {k: v for k, v in raw.items() if k in known}
        data["quirks"] = tuple(data.get("quirks") or ())
        data["pos"] = tuple(data.get("pos") or (0.0, 0.0))
        data["desk"] = tuple(data.get("desk") or (0.0, 0.0))
        return cls(**data)

    @property
    def model_name(self) -> str:
        return model_label(self.model)

    @property
    def fallbacks(self) -> list[str]:
        return ROLE_FALLBACK.get(self.role, [])


# ----------------------------------------------------------------------------- tugas
@dataclass
class Task:
    tid: str
    title: str
    brief: str
    assignee: str
    room: str
    deliverable: str = "dokumen"
    priority: str = "normal"  # rendah | normal | tinggi
    status: str = TASK_QUEUED
    progress: float = 0.0
    result: str = ""
    error: str = ""
    model_used: str = ""
    provider_used: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    decided_at: float = 0.0
    boss_note: str = ""
    revision_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    duration: float = 0.0
    rating: int = 0
    files: list[str] = field(default_factory=list)
    repo_context: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        data = {k: v for k, v in raw.items() if k in known}
        data.setdefault("files", [])
        data.setdefault("history", [])
        return cls(**data)

    @property
    def state_icon(self) -> str:
        return TASK_ICON.get(self.status, "assignment")

    @property
    def state_color(self) -> str:
        return TASK_COLOR.get(self.status, "#94A3B8")

    @property
    def provider(self) -> str:
        return self.provider_used or provider_of(self.model_used)


def new_id(prefix: str = "T") -> str:
    return f"{prefix}-{int(time.time() * 1000) % 10**8:08d}-{uuid.uuid4().hex[:4]}"


def now() -> float:
    return time.time()

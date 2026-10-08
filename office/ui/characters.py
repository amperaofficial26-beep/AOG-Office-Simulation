"""Karakter SVG beranimasi untuk setiap karyawan.

Setiap karakter digambar sebagai grup SVG dengan kelas status (st-idle,
st-work, st-walk, st-coffee, st-game, st-nap, st-chat). Animasi dijalankan
sepenuhnya oleh CSS di office.ui.theme, jadi kantor tetap hidup tanpa JavaScript
dan tanpa emoji.
"""
from __future__ import annotations

import math
from html import escape as _esc
from typing import Any

from ..models_data import (
    EMP_CHAT,
    EMP_COFFEE,
    EMP_GAMING,
    EMP_IDLE,
    EMP_MEETING,
    EMP_NAP,
    EMP_PRESENT,
    EMP_WALKING,
    EMP_WORKING,
)
from ..icons import icon_svg

STATE_CLASS = {
    EMP_IDLE: "st-idle",
    EMP_WALKING: "st-walk",
    EMP_WORKING: "st-work",
    EMP_MEETING: "st-chat",
    EMP_COFFEE: "st-coffee",
    EMP_GAMING: "st-game",
    EMP_NAP: "st-nap",
    EMP_CHAT: "st-chat",
    EMP_PRESENT: "st-chat",
}

STATE_BADGE = {
    EMP_IDLE: "self_improvement",
    EMP_WALKING: "directions_run",
    EMP_WORKING: "precision_manufacturing",
    EMP_MEETING: "groups",
    EMP_COFFEE: "local_cafe",
    EMP_GAMING: "sports_esports",
    EMP_NAP: "nightlight",
    EMP_CHAT: "forum",
    EMP_PRESENT: "campaign",
}

# Warna lokal agar tidak bergantung tema saat di-render ke SVG
INK = "#0B1020"


def _path_from_material(name: str, size: int = 14, color: str = "#FFFFFF") -> str:
    """Ubah ikon Material menjadi path mentah (tanpa <svg>) untuk disisipkan di SVG."""
    html = icon_svg(name, size=size, color=color)
    start = html.find(">") + 1
    end = html.rfind("</svg>")
    return f'<g fill="{color}">{html[start:end]}</g>' 


def _hair_back(style: str, color: str) -> str:
    if style == "long":
        return (
            f'<path d="M17,20 C16,32 15,38 17,44 L22,44 C20,36 20,30 21,22 Z" fill="{color}" opacity=".95"/>'
            f'<path d="M43,20 C44,32 45,38 43,44 L38,44 C40,36 40,30 39,22 Z" fill="{color}" opacity=".95"/>'
        )
    if style == "ponytail":
        return (
            f'<path d="M41,16 C52,18 54,32 48,40 C45,44 42,43 43,38 C45,30 44,22 40,19 Z" fill="{color}"/>'
        )
    if style == "bun":
        return f'<circle cx="30" cy="9" r="5.4" fill="{color}"/>'
    return ""


def _hair_front(style: str, color: str) -> str:
    if style == "buzz":
        return f'<path d="M21,17 C23,9 37,9 39,17 C34,13 26,13 21,17 Z" fill="{color}"/>'
    if style in ("long", "ponytail"):
        return f'<path d="M19,21 C19,10 41,10 41,21 C37,15 23,15 19,21 Z" fill="{color}"/>'
    if style == "bun":
        return f'<path d="M20,18 C22,8 38,8 40,18 C35,14 25,14 20,18 Z" fill="{color}"/>'
    return f'<path d="M19,19 C21,9 39,9 41,19 C36,14 24,14 19,19 Z" fill="{color}"/>'


def _face(eyes_color: str, mouth: str) -> str:
    eye_h = 3.0
    if mouth == "nap":
        mouth_svg = '<path d="M27,29 q3,2 6,0" stroke="#8A5A44" stroke-width="1.2" fill="none" stroke-linecap="round"/>'
    elif mouth == "work":
        mouth_svg = '<rect x="27" y="28.6" width="6" height="1.6" rx=".8" fill="#8A5A44"/>'
    else:
        mouth_svg = '<path d="M26.6,28.4 q3.4,3.2 6.8,0" stroke="#8A5A44" stroke-width="1.3" fill="none" stroke-linecap="round"/>'
    return (
        f'<g class="eye"><ellipse cx="25.6" cy="23.4" rx="1.35" ry="{eye_h/2}" fill="{eyes_color}"/></g>'
        f'<g class="eye"><ellipse cx="34.4" cy="23.4" rx="1.35" ry="{eye_h/2}" fill="{eyes_color}"/></g>'
        f"{mouth_svg}"
    )


def _glasses(color: str) -> str:
    return (
        f'<g stroke="{color}" stroke-width="1.1" fill="none" opacity=".9">'
        '<rect x="22.4" y="21.2" width="6.6" height="4.8" rx="1.6"/>'
        '<rect x="31.0" y="21.2" width="6.6" height="4.8" rx="1.6"/>'
        '<path d="M29,23.4 h2"/><path d="M22.4,23.2 h-2.6"/><path d="M37.6,23.2 h2.6"/></g>'
    )


def _legs(pants: str, shoes: str) -> str:
    return (
        f'<rect class="leg l1" x="23.6" y="56" width="5.4" height="20" rx="2.6" fill="{pants}"/>'
        f'<rect class="leg l2" x="31" y="56" width="5.4" height="20" rx="2.6" fill="{pants}"/>'
        f'<rect x="22.6" y="74.4" width="7.4" height="3.4" rx="1.7" fill="{shoes}"/>'
        f'<rect x="30" y="74.4" width="7.4" height="3.4" rx="1.7" fill="{shoes}"/>'
    )


def _torso(shirt: str, accent: str) -> str:
    return (
        f'<rect class="torso" x="20" y="33" width="20" height="25" rx="7" fill="{shirt}"/>'
        f'<path d="M24,35 L30,41 L36,35" stroke="{accent}" stroke-width="2.2" fill="none" '
        'stroke-linecap="round" opacity=".95"/>'
    )


def _arm(skin: str, shirt: str, cls: str, x: float, hand_x: float) -> str:
    return (
        f'<g class="arm {cls}"><rect x="{x}" y="35" width="4.6" height="16" rx="2.3" fill="{shirt}"/>'
        f'<circle cx="{hand_x}" cy="51" r="2.6" fill="{skin}"/></g>'
    )


def _prop(state: str, accent: str, skin: str) -> str:
    if state == EMP_WORKING:
        return (
            '<g transform="translate(6,50)">'
            '<rect x="0" y="6" width="26" height="2.6" rx="1.2" fill="#94A3B8"/>'
            '<rect x="3" y="-4" width="20" height="11" rx="1.6" fill="#0F172A" stroke="#334155" stroke-width="1"/>'
            '<g class="screen"><rect x="5" y="-2" width="16" height="7" rx="1" fill="#0EA5E9" opacity=".55"/>'
            '<rect x="6.4" y="-0.6" width="10" height="1.1" rx=".5" fill="#E0F2FE"/>'
            '<rect x="6.4" y="1.4" width="7" height="1.1" rx=".5" fill="#7DD3FC"/></g></g>'
        )
    if state == EMP_COFFEE:
        return (
            '<g transform="translate(11,44)">'
            '<rect x="0" y="0" width="7.4" height="8.6" rx="1.6" fill="#F8FAFC" stroke="#CBD5E1" stroke-width=".9"/>'
            '<path d="M7.4,2.4 q3.2,.8 0,3.6" stroke="#CBD5E1" stroke-width="1" fill="none"/>'
            f'<rect x="1.2" y="1.2" width="5" height="2.2" rx="1" fill="{accent}" opacity=".8"/>'
            '<g class="steam"><path d="M3,-1 q1.6,-2 0,-4" stroke="#94A3B8" stroke-width="1" fill="none" opacity=".7"/></g>'
            '<g class="steam s2"><path d="M5.4,-1 q1.6,-2 0,-4" stroke="#94A3B8" stroke-width="1" fill="none" opacity=".7"/></g></g>'
        )
    if state == EMP_GAMING:
        return (
            '<g transform="translate(18,46)">'
            f'<rect x="0" y="0" width="24" height="10" rx="5" fill="{accent}"/>'
            '<circle cx="6" cy="5" r="2.1" fill="#0B1020" opacity=".75"/>'
            '<circle cx="18" cy="5" r="2.1" fill="#0B1020" opacity=".75"/>'
            '<rect x="10.4" y="3.4" width="3.2" height="3.2" rx="1" fill="#0B1020" opacity=".6"/></g>'
        )
    if state == EMP_NAP:
        return (
            '<g fill="#93A0BF" font-family="ui-monospace, monospace" font-size="9" font-weight="700">'
            '<text class="zzz" x="44" y="14">z</text>'
            '<text class="zzz z2" x="48" y="8">z</text>'
            '<text class="zzz z3" x="52" y="2">z</text></g>'
        )
    if state in (EMP_CHAT, EMP_PRESENT, EMP_MEETING):
        return (
            f'<g class="bubble" transform="translate(40,4)">'
            f'<rect x="0" y="0" width="22" height="14" rx="4" fill="{accent}"/>'
            f'<path d="M5,14 l0,5 l6,-5 z" fill="{accent}"/>'
            '<circle cx="7" cy="7" r="1.5" fill="#0B1020" opacity=".7"/>'
            '<circle cx="11.5" cy="7" r="1.5" fill="#0B1020" opacity=".7"/>'
            '<circle cx="16" cy="7" r="1.5" fill="#0B1020" opacity=".7"/></g>'
        )
    return ""


def character_svg(
    emp: dict[str, Any],
    *,
    scale: float = 1.0,
    show_tag: bool = True,
    show_badge: bool = True,
    uid_suffix: str = "",
) -> str:
    """Gambar satu karyawan sebagai <g class="char"> siap disisipkan ke panggung."""
    state = emp.get("state", EMP_IDLE)
    eid = f"{emp.get('eid', 'emp')}{uid_suffix}"
    skin = emp.get("skin", "#F6C9A0")
    hair = emp.get("hair", "#3B2A20")
    shirt = emp.get("shirt", "#2563EB")
    accent = emp.get("accent", "#F59E0B")
    glasses = bool(emp.get("glasses"))
    hair_style = emp.get("hair_style", "short")
    facing = 1 if int(emp.get("facing", 1) or 1) >= 0 else -1
    pants = "#1F2937"
    shoes = "#0F172A"
    mood = int(emp.get("mood", 80))
    mouth = "nap" if state == EMP_NAP else ("work" if state == EMP_WORKING else ("sad" if mood < 35 else "smile"))

    transform = f'translate(-32,-78) scale({scale * facing},{scale})' if facing < 0 else f"translate(-32,-78) scale({scale})"

    tag = ""
    if show_tag:
        name = _esc(emp.get("name", "Karyawan").split()[0])
        level = emp.get("level", 1)
        badge = ""
        if show_badge:
            badge = (
                f'<g transform="translate(14,-52)">'
                f'<rect x="-7" y="-7" width="14" height="14" rx="4" fill="{accent}"/>'
                f'<g transform="translate(-4.5,-4.5) scale(0.375)">'
                f'{_path_from_material(STATE_BADGE.get(state, "widgets"), 24, "#0B1020")}</g></g>'
            )
        tag = (
            f'<g transform="translate(0,-92)">'
            f'<rect x="-{7*len(name)//2+10}" y="-11" width="{7*len(name)+20}" height="15" rx="7.5" '
            f'fill="#0B1020" opacity=".72" stroke="{accent}" stroke-width=".8"/>'
            f'<text class="nametag" x="0" y="0" text-anchor="middle" fill="#F8FAFC">{name} · L{level}</text></g>{badge}'
        )

    pulse = ""
    if state in (EMP_WORKING, EMP_WALKING):
        color = "#FBBF24" if state == EMP_WORKING else "#38BDF8"
        pulse = f'<ellipse class="pulse" cx="0" cy="0" rx="9" ry="4.5" fill="{color}" opacity=".35"/>'

    return (
        f'<g class="char {STATE_CLASS.get(state, "st-idle")}" data-eid="{eid}">'
        f'<ellipse cx="0" cy="0" rx="12" ry="4.6" fill="#020617" opacity=".35"/>{pulse}'
        f'<g transform="{transform}">'
        f'<g class="char-body">'
        f'{_hair_back(hair_style, hair)}'
        f'<g class="arm a1"><rect x="16.4" y="35" width="4.6" height="16" rx="2.3" fill="{shirt}"/>'
        f'<circle cx="18.7" cy="51" r="2.6" fill="{skin}"/></g>'
        f'{_legs(pants, shoes)}'
        f'{_torso(shirt, accent)}'
        f'<g class="arm a2"><rect x="39" y="35" width="4.6" height="16" rx="2.3" fill="{shirt}"/>'
        f'<circle cx="41.3" cy="51" r="2.6" fill="{skin}"/></g>'
        f'<g class="head">'
        f'<rect x="27.4" y="28" width="5.2" height="6" rx="2" fill="{skin}"/>'
        f'<circle cx="30" cy="20" r="11" fill="{skin}"/>'
        f'<circle cx="19.4" cy="21" r="1.9" fill="{skin}"/>'
        f'<circle cx="40.6" cy="21" r="1.9" fill="{skin}"/>'
        f'{_hair_front(hair_style, hair)}'
        f'{_face("#1F2937", mouth)}'
        f'{_glasses("#0F172A") if glasses else ""}'
        f'</g>'
        f'{_prop(state, accent, skin)}'
        f'</g></g>{tag}</g>'
    )


def boss_svg(name: str = "Bos", accent: str = "#FACC15", scale: float = 1.15) -> str:
    """Karakter bos (Anda) yang berdiri di ruang bos."""
    return (
        '<g class="char st-idle" data-eid="boss">'
        '<ellipse cx="0" cy="0" rx="13" ry="5" fill="#020617" opacity=".4"/>'
        f'<g transform="translate(-32,-78) scale({scale})">'
        '<g class="char-body">'
        '<g class="arm a1"><rect x="16.4" y="35" width="4.6" height="16" rx="2.3" fill="#0F172A"/>'
        '<circle cx="18.7" cy="51" r="2.6" fill="#F6C9A0"/></g>'
        '<rect class="leg l1" x="23.6" y="56" width="5.4" height="20" rx="2.6" fill="#111827"/>'
        '<rect class="leg l2" x="31" y="56" width="5.4" height="20" rx="2.6" fill="#111827"/>'
        '<rect x="22.6" y="74.4" width="7.4" height="3.4" rx="1.7" fill="#020617"/>'
        '<rect x="30" y="74.4" width="7.4" height="3.4" rx="1.7" fill="#020617"/>'
        f'<rect class="torso" x="20" y="33" width="20" height="25" rx="7" fill="#111827"/>'
        f'<path d="M24,35 L30,42 L36,35" stroke="{accent}" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f'<rect x="28.6" y="42" width="2.8" height="9" rx="1.2" fill="{accent}"/>'
        '<g class="arm a2"><rect x="39" y="35" width="4.6" height="16" rx="2.3" fill="#111827"/>'
        '<circle cx="41.3" cy="51" r="2.6" fill="#F6C9A0"/></g>'
        '<g class="head"><rect x="27.4" y="28" width="5.2" height="6" rx="2" fill="#F6C9A0"/>'
        '<circle cx="30" cy="20" r="11" fill="#F6C9A0"/>'
        '<path d="M19,18 C21,8 39,8 41,18 C36,13 24,13 19,18 Z" fill="#1F1B16"/>'
        '<g class="eye"><ellipse cx="25.6" cy="23.4" rx="1.35" ry="1.5" fill="#1F2937"/></g>'
        '<g class="eye"><ellipse cx="34.4" cy="23.4" rx="1.35" ry="1.5" fill="#1F2937"/></g>'
        '<path d="M26.4,28.4 q3.6,3.4 7.2,0" stroke="#8A5A44" stroke-width="1.3" fill="none" stroke-linecap="round"/>'
        '<g stroke="#0F172A" stroke-width="1.1" fill="none" opacity=".9">'
        '<rect x="22.4" y="21.2" width="6.6" height="4.8" rx="1.6"/><rect x="31" y="21.2" width="6.6" height="4.8" rx="1.6"/>'
        '<path d="M29,23.4 h2"/></g></g></g></g>'
        f'<g transform="translate(0,-100)"><rect x="-{7*len(name)//2+12}" y="-11" width="{7*len(name)+24}" height="16" '
        f'rx="8" fill="#0B1020" opacity=".8" stroke="{accent}" stroke-width=".9"/>'
        f'<text class="nametag" x="0" y="1" text-anchor="middle" fill="{accent}">{_esc(name)}</text></g>'
        '</g>'
    )


def state_label(state: str) -> str:
    return {
        EMP_IDLE: "Santai",
        EMP_WALKING: "Berjalan",
        EMP_WORKING: "Bekerja",
        EMP_MEETING: "Rapat",
        EMP_COFFEE: "Ngopi",
        EMP_GAMING: "Main game",
        EMP_NAP: "Istirahat",
        EMP_CHAT: "Mengobrol",
        EMP_PRESENT: "Presentasi",
    }.get(state, state)


def mood_icon(mood: int) -> str:
    if mood >= 75:
        return "sentiment_very_satisfied" if _has("sentiment_very_satisfied") else "mood"
    if mood >= 45:
        return "mood"
    if mood >= 25:
        return "sentiment_neutral" if _has("sentiment_neutral") else "mood"
    return "sick"


def _has(name: str) -> bool:
    try:
        from .icons_data import ICONS

        return name in ICONS
    except Exception:
        return False


def walk_offset(progress: float) -> float:
    """Kecil: dipakai untuk menghitung langkah visual (0..1)."""
    return max(0.0, min(1.0, float(progress)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, float(t)))


def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

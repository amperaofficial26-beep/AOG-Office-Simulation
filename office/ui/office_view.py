"""Panggung kantor isometrik: lantai, dinding, perabot, dan karakter beranimasi."""
from __future__ import annotations

import random
from html import escape as _esc
from typing import Any

from ..config import DEFAULT_BOSS_NAME
from ..models_data import EMP_IDLE, EMP_WALKING, TASK_REVIEW
from ..roster import BOSS_SPOT, ROOMS, ROOM_ORDER, break_spot, desk_spot
from ..icons import icon_svg
from .characters import boss_svg, character_svg, lerp

TILE_W = 104.0
TILE_H = 52.0
WALK_SECONDS = 3.0  # durasi transisi berjalan (harus < TICK interval agar mulus)


# ----------------------------------------------------------------------------- proyeksi
def iso(gx: float, gy: float) -> tuple[float, float]:
    return ((gx - gy) * TILE_W / 2.0, (gx + gy) * TILE_H / 2.0)


def room_polygon(room: Any) -> str:
    pts = [
        iso(room.gx, room.gy),
        iso(room.gx + room.gw, room.gy),
        iso(room.gx + room.gw, room.gy + room.gh),
        iso(room.gx, room.gy + room.gh),
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def polygon_bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def view_box(extra_top: float = 120.0, extra_bottom: float = 40.0, pad: float = 40.0) -> tuple[float, float, float, float]:
    pts: list[tuple[float, float]] = []
    for room in ROOMS.values():
        pts += [
            iso(room.gx, room.gy),
            iso(room.gx + room.gw, room.gy),
            iso(room.gx + room.gw, room.gy + room.gh),
            iso(room.gx, room.gy + room.gh),
        ]
    x0, y0, x1, y1 = polygon_bbox(pts)
    return (x0 - pad, y0 - extra_top, (x1 - x0) + 2 * pad, (y1 - y0) + extra_top + extra_bottom)


# ----------------------------------------------------------------------------- perabot
def _iso_box(cx: float, cy: float, w: float, d: float, h: float, top: str, left: str, right: str) -> str:
    """Kotak isometrik: w,d = ukuran tapak (px), h = tinggi (px)."""
    hw, hd = w / 2.0, d / 2.0
    top_pts = [(cx, cy - hd), (cx + hw, cy), (cx, cy + hd), (cx - hw, cy)]
    left_pts = [(cx - hw, cy), (cx, cy + hd), (cx, cy + hd + h), (cx - hw, cy + h)]
    right_pts = [(cx + hw, cy), (cx, cy + hd), (cx, cy + hd + h), (cx + hw, cy + h)]
    fmt = lambda pts: " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (
        f'<polygon points="{fmt(top_pts)}" fill="{top}"/>'
        f'<polygon points="{fmt(left_pts)}" fill="{left}"/>'
        f'<polygon points="{fmt(right_pts)}" fill="{right}"/>'
    )


def _desk(cx: float, cy: float) -> str:
    return (
        f'<rect x="{cx-24:.1f}" y="{cy+6:.1f}" width="4" height="14" fill="#334155"/>'
        f'<rect x="{cx+20:.1f}" y="{cy+6:.1f}" width="4" height="14" fill="#334155"/>'
        + _iso_box(cx, cy, 58, 28, 7, "#C8A165", "#96703C", "#7C5A2E")
    )


def _monitor(cx: float, cy: float, screen: str = "#38BDF8", lines: bool = True) -> str:
    body = (
        f'<rect x="{cx-2:.1f}" y="{cy-12:.1f}" width="4" height="9" fill="#475569"/>'
        f'<rect x="{cx-7:.1f}" y="{cy-4:.1f}" width="14" height="3" rx="1.5" fill="#334155"/>'
        f'<rect x="{cx-17:.1f}" y="{cy-32:.1f}" width="34" height="22" rx="2.5" fill="#0F172A" '
        'stroke="#334155" stroke-width="1"/>'
        f'<g class="screen"><rect x="{cx-14.5:.1f}" y="{cy-29.5:.1f}" width="29" height="17" rx="1.5" '
        f'fill="{screen}" opacity=".35"/>'
    )
    if lines:
        body += (
            f'<g class="codeline">'
            f'<rect x="{cx-12:.1f}" y="{cy-27:.1f}" width="18" height="1.6" rx=".8" fill="#E0F2FE"/>'
            f'<rect x="{cx-12:.1f}" y="{cy-23:.1f}" width="12" height="1.6" rx=".8" fill="#BAE6FD"/>'
            f'<rect x="{cx-12:.1f}" y="{cy-19:.1f}" width="21" height="1.6" rx=".8" fill="#7DD3FC"/>'
            f'<rect x="{cx-12:.1f}" y="{cy-15:.1f}" width="9" height="1.6" rx=".8" fill="#E0F2FE"/></g>'
        )
    return body + "</g>"


def _server(cx: float, cy: float) -> str:
    out = _iso_box(cx, cy, 34, 20, 34, "#334155", "#1F2937", "#172033")
    for i in range(3):
        y = cy - 30 + i * 9
        out += (
            f'<rect x="{cx-10:.1f}" y="{y:.1f}" width="20" height="4" rx="1" fill="#0F172A"/>'
            f'<circle cx="{cx-6:.1f}" cy="{y+2:.1f}" r="1.2" fill="#22C55E" class="screen"/>'
            f'<circle cx="{cx-2:.1f}" cy="{y+2:.1f}" r="1.2" fill="#38BDF8"/>'
        )
    return out


def _plant(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx-8:.1f},{cy-6:.1f} q8,4 16,0 l-2,12 q-6,3 -12,0 z" fill="#B45309"/>'
        f'<path d="M{cx:.1f},{cy-6:.1f} C{cx-12:.1f},{cy-18:.1f} {cx-6:.1f},{cy-26:.1f} {cx:.1f},{cy-24:.1f} '
        f'C{cx+6:.1f},{cy-26:.1f} {cx+12:.1f},{cy-18:.1f} {cx:.1f},{cy-6:.1f} Z" fill="#16A34A"/>'
        f'<path d="M{cx:.1f},{cy-8:.1f} C{cx-4:.1f},{cy-16:.1f} {cx+4:.1f},{cy-20:.1f} {cx:.1f},{cy-24:.1f}" '
        'stroke="#15803D" stroke-width="1.4" fill="none"/>'
    )


def _sofa(cx: float, cy: float, color: str = "#334155") -> str:
    return _iso_box(cx, cy - 6, 46, 22, 9, "#475569", "#334155", "#293548") + _iso_box(
        cx, cy - 14, 46, 8, 14, color, "#273449", "#1F2937"
    )


def _coffee(cx: float, cy: float) -> str:
    return (
        _iso_box(cx, cy, 26, 18, 30, "#475569", "#334155", "#273449")
        + f'<rect x="{cx-9:.1f}" y="{cy-26:.1f}" width="18" height="12" rx="2" fill="#0F172A"/>'
        + f'<rect x="{cx-6:.1f}" y="{cy-23:.1f}" width="12" height="6" rx="1" fill="#FBBF24" class="screen"/>'
        + f'<rect x="{cx-5:.1f}" y="{cy-12:.1f}" width="10" height="7" rx="1.5" fill="#E2E8F0"/>'
        + f'<g class="steam"><path d="M{cx:.1f},{cy-14:.1f} q3,-4 0,-8" stroke="#94A3B8" stroke-width="1.2" '
        'fill="none" opacity=".7"/></g>'
        + f'<g class="steam s2"><path d="M{cx+4:.1f},{cy-14:.1f} q3,-4 0,-8" stroke="#94A3B8" stroke-width="1.2" '
        'fill="none" opacity=".7"/></g>'
    )


def _arcade(cx: float, cy: float) -> str:
    return (
        _iso_box(cx, cy, 26, 20, 38, "#7C3AED", "#5B21B6", "#4C1D95")
        + f'<rect x="{cx-9:.1f}" y="{cy-34:.1f}" width="18" height="12" rx="1.6" fill="#0F172A"/>'
        + f'<rect x="{cx-7:.1f}" y="{cy-32:.1f}" width="14" height="8" rx="1" fill="#22D3EE" class="screen" '
        'opacity=".8"/>'
        + f'<rect x="{cx-6:.1f}" y="{cy-18:.1f}" width="12" height="4" rx="2" fill="#0F172A"/>'
    )


def _bookshelf(cx: float, cy: float) -> str:
    out = _iso_box(cx, cy, 40, 16, 34, "#7C5A2E", "#5C4222", "#4A351B")
    for row in range(3):
        y = cy - 30 + row * 10
        for i in range(5):
            color = ["#38BDF8", "#F472B6", "#FBBF24", "#34D399", "#A78BFA"][i]
            out += f'<rect x="{cx-16+i*7:.1f}" y="{y:.1f}" width="4" height="7" fill="{color}" opacity=".9"/>'
    return out


def _easel(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx-10:.1f},{cy+8:.1f} L{cx:.1f},{cy-26:.1f} L{cx+10:.1f},{cy+8:.1f}" stroke="#94A3B8" '
        'stroke-width="2" fill="none"/>'
        f'<rect x="{cx-13:.1f}" y="{cy-30:.1f}" width="26" height="18" rx="1.6" fill="#F8FAFC" '
        'stroke="#CBD5E1" stroke-width="1"/>'
        f'<circle cx="{cx-5:.1f}" cy="{cy-24:.1f}" r="3.4" fill="#F472B6"/>'
        f'<path d="M{cx-9:.1f},{cy-15:.1f} q8,-8 18,-2" stroke="#38BDF8" stroke-width="2" fill="none"/>'
    )


def _whiteboard(cx: float, cy: float) -> str:
    return (
        f'<rect x="{cx-24:.1f}" y="{cy-38:.1f}" width="48" height="28" rx="2" fill="#F1F5F9" '
        'stroke="#CBD5E1" stroke-width="1"/>'
        f'<path d="M{cx-18:.1f},{cy-30:.1f} h22 M{cx-18:.1f},{cy-25:.1f} h30 M{cx-18:.1f},{cy-20:.1f} h16" '
        'stroke="#94A3B8" stroke-width="1.6" stroke-linecap="round"/>'
        f'<circle cx="{cx+13:.1f}" cy="{cy-28:.1f}" r="5" fill="none" stroke="#38BDF8" stroke-width="1.6"/>'
        f'<rect x="{cx-22:.1f}" y="{cy-10:.1f}" width="3" height="14" fill="#94A3B8"/>'
        f'<rect x="{cx+19:.1f}" y="{cy-10:.1f}" width="3" height="14" fill="#94A3B8"/>'
    )


def _trophy(cx: float, cy: float) -> str:
    return (
        _iso_box(cx, cy, 20, 14, 12, "#475569", "#334155", "#273449")
        + f'<path d="M{cx-6:.1f},{cy-26:.1f} h12 v5 a6,6 0 0 1 -12,0 z" fill="#FACC15"/>'
        + f'<path d="M{cx-6:.1f},{cy-24:.1f} q-5,1 -2,6 M{cx+6:.1f},{cy-24:.1f} q5,1 2,6" stroke="#FACC15" '
        'stroke-width="1.6" fill="none"/>'
        + f'<rect x="{cx-2:.1f}" y="{cy-19:.1f}" width="4" height="6" fill="#EAB308"/>'
    )


FURNITURE_BUILDERS = {
    "desk": _desk,
    "monitor": _monitor,
    "server": _server,
    "plant": _plant,
    "sofa": _sofa,
    "coffee": _coffee,
    "arcade": _arcade,
    "bookshelf": _bookshelf,
    "easel": _easel,
    "whiteboard": _whiteboard,
    "trophy": _trophy,
}


def furniture_for_room(room: Any) -> str:
    """Letakkan perabot secara deterministik di dalam ruangan."""
    rng = random.Random(room.rid)
    cx0, cy0 = iso(room.gx + room.gw / 2.0, room.gy + room.gh / 2.0)
    out: list[str] = []
    items = list(room.furniture)
    # baris belakang (dinding) dulu, lalu tengah
    back_y = -room.gh * TILE_H * 0.30
    for i, item in enumerate(items):
        builder = FURNITURE_BUILDERS.get(item)
        if builder is None:
            continue
        dx = (i - (len(items) - 1) / 2.0) * (TILE_W * 0.72)
        dy = back_y + rng.uniform(-6, 6) + (10 if i % 2 else 0)
        if item == "monitor":
            continue  # monitor digambar menyatu dengan meja
        out.append(builder(cx0 + dx, cy0 + dy))
    # meja + monitor di area kerja
    if "desk" in items:
        for i, spot in enumerate([(0.30, 0.72), (0.72, 0.36), (0.55, 0.80)]):
            if i >= max(1, len(items) - 2):
                break
            gx = room.gx + room.gw * spot[0]
            gy = room.gy + room.gh * spot[1]
            x, y = iso(gx, gy)
            out.append(_desk(x, y - 6))
            out.append(_monitor(x, y - 12, screen=room.color))
    return "".join(out)


# ----------------------------------------------------------------------------- ruangan
def _room_plate(room: Any, x: float, y: float, unread: int = 0) -> str:
    name = _esc(room.name)
    width = max(120, 7.6 * len(name) + 46)
    badge = ""
    if unread:
        badge = (
            f'<g transform="translate({width/2 - 8:.1f},-8)"><circle r="8.5" fill="#EF4444"/>'
            f'<text x="0" y="3.4" text-anchor="middle" fill="#FFF" '
            f'font-size="10" font-weight="700">{unread}</text></g>'
        )
    return (
        f'<g transform="translate({x:.1f},{y:.1f})">'
        f'<rect x="{-width/2:.1f}" y="-13" width="{width:.1f}" height="22" rx="11" '
        f'fill="#0B1020" opacity=".78" stroke="{room.color}" stroke-width="1"/>'
        f'<g transform="translate({-width/2+9:.1f},-8) scale(0.62)">{_mat(room.icon, room.color)}</g>'
        f'<text class="room-label" x="4" y="2" text-anchor="middle" fill="#F8FAFC">{name}</text>{badge}</g>'
    )


def _mat(name: str, color: str) -> str:
    """Path ikon Material dibungkus <g fill> agar warna tidak hilang."""
    html = icon_svg(name, 24, color)
    inner = html[html.find(">") + 1 : html.rfind("</svg>")]
    return f'<g fill="{color}">{inner}</g>' 


def room_svg(
    room: Any,
    *,
    unread: int = 0,
    highlight: bool = False,
) -> tuple[str, str, tuple[float, float]]:
    pts = room_polygon(room)
    top_left = iso(room.gx, room.gy)
    top_right = iso(room.gx + room.gw, room.gy)
    bottom = iso(room.gx + room.gw / 2.0, room.gy + room.gh)
    wall_h = 42.0
    stroke_w = 2.2 if highlight else 1.2
    stroke = room.color if highlight else "#2A3552"

    # dinding belakang (kiri & kanan)
    wall_left = (
        f'<polygon points="{top_left[0]:.1f},{top_left[1]:.1f} {top_right[0]:.1f},{top_right[1]:.1f} '
        f'{top_right[0]:.1f},{top_right[1]-wall_h:.1f} {top_left[0]:.1f},{top_left[1]-wall_h:.1f}" '
        f'fill="{room.color}" opacity=".13"/>'
    )
    wall_edge = (
        f'<path d="M{top_left[0]:.1f},{top_left[1]-wall_h:.1f} L{top_right[0]:.1f},{top_right[1]-wall_h:.1f}" '
        f'stroke="{room.color}" stroke-width="1.4" opacity=".5" fill="none"/>'
    )
    floor = f'<polygon points="{pts}" fill="{room.color}" opacity=".22"/>'
    # garis ubin
    lines: list[str] = []
    for i in range(1, room.gw):
        a = iso(room.gx + i, room.gy)
        b = iso(room.gx + i, room.gy + room.gh)
        lines.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                     'stroke="#FFFFFF" stroke-opacity=".05" stroke-width="1"/>')
    for j in range(1, room.gh):
        a = iso(room.gx, room.gy + j)
        b = iso(room.gx + room.gw, room.gy + j)
        lines.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                     'stroke="#FFFFFF" stroke-opacity=".05" stroke-width="1"/>')
    outline = f'<polygon points="{pts}" fill="none" stroke="{stroke}" stroke-width="{stroke_w}"/>'
    hit = (
        f'<polygon class="room-hit" points="{pts}" fill="transparent">'
        f"<title>{_esc(room.name)} — {_esc(room.desc)}</title></polygon>"
    )
    furn = furniture_for_room(room)
    plate = _room_plate(room, (top_left[0] + top_right[0]) / 2.0, top_left[1] - wall_h - 30, unread)
    return (
        f'<g class="room" data-room="{room.rid}">{wall_left}{floor}{"".join(lines)}'
        f"{outline}{wall_edge}{furn}{hit}</g>"
    ), plate, bottom


# ----------------------------------------------------------------------------- panggung
def render_office(
    state: dict[str, Any],
    *,
    theme: str = "night",
    show_model: bool = True,
    selected_room: str = "",
    selected_emp: str = "",
) -> str:
    """Bangun seluruh SVG kantor lengkap dengan karakter di dalamnya."""
    unread_by_room: dict[str, int] = {}
    for msg in state.get("inbox", []):
        if not msg.get("read"):
            unread_by_room["reception"] = unread_by_room.get("reception", 0) + 1
    pending_by_room: dict[str, int] = {}
    for task in state.get("tasks", []):
        if task.get("status") == TASK_REVIEW:
            emp = state.get("employees", {}).get(task.get("assignee", ""), {})
            rid = emp.get("room") or task.get("room") or "code"
            pending_by_room[rid] = pending_by_room.get(rid, 0) + 1

    rooms_svg: list[str] = []
    plates_svg: list[str] = []
    for rid in ROOM_ORDER:
        room = ROOMS[rid]
        body, plate, _bottom = room_svg(
            room,
            unread=unread_by_room.get(rid, 0) + pending_by_room.get(rid, 0),
            highlight=(rid == selected_room),
        )
        rooms_svg.append(body)
        plates_svg.append(plate)

    # karakter: posisi diinterpolasi supaya berjalan terlihat halus
    chars: list[tuple[float, str]] = []
    for eid, emp in state.get("employees", {}).items():
        gx, gy = _char_pos(emp)
        pos = iso(gx, gy)  # konversi grid -> layar
        depth = gx + gy
        ring = (
            '<ellipse cx="0" cy="0" rx="16" ry="6.5" fill="none" stroke="#FACC15" '
            'stroke-width="1.6" stroke-dasharray="3 3" class="pulse"/>'
            if eid == selected_emp
            else ""
        )
        body = (
            f'<g transform="translate({pos[0]:.1f},{pos[1]:.1f})">{ring}'
            f"{character_svg(emp, scale=0.95, uid_suffix='-s')}</g>"
        )
        chars.append((depth, body))

    chars.sort(key=lambda item: item[0])
    chars_svg = "".join(body for _, body in chars)

    # bos berdiri di ruang bos
    boss_name = DEFAULT_BOSS_NAME
    try:
        from ..state import load_config

        boss_name = load_config().get("boss_name") or DEFAULT_BOSS_NAME
    except Exception:  # pragma: no cover - saat state belum ada
        pass
    bx, by = iso(BOSS_SPOT[0], BOSS_SPOT[1])
    boss = f'<g transform="translate({bx:.1f},{by:.1f})">{boss_svg(boss_name)}</g>'

    x, y, w, h = view_box()
    label = _esc(f"{boss_name} · hari kerja ke-{state.get('day', 1)}")
    return f"""
<div class="office-wrap">
<svg class="office-svg" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}" preserveAspectRatio="xMidYMid meet"
     role="img" aria-label="Denah kantor simulasi">
  <g>{''.join(rooms_svg)}</g>
  <g>{boss}{chars_svg}</g>
  <g>{''.join(plates_svg)}</g>
  <g transform="translate({x + 18:.0f},{y + 24:.0f})">
    <text class="room-sub" fill="#93A0BF" font-size="10">{label}</text>
  </g>
</svg>
</div>
"""


def _char_pos(emp: dict[str, Any]) -> tuple[float, float]:
    """Posisi karakter di grid: interpolasi dari pos menuju spot tujuan."""
    from ..models_data import EMP_COFFEE, EMP_GAMING, EMP_NAP, now

    pos = list(emp.get("pos") or [0.0, 0.0])
    state = emp.get("state", EMP_IDLE)
    idx = abs(hash(emp.get("eid", ""))) % 4
    if state == EMP_WALKING:
        target_room = emp.get("target_room") or ""
        spot = break_spot(idx) if target_room == "break" else desk_spot(target_room or emp.get("room", "code"), idx % 3)
        until = float(emp.get("state_until") or 0.0)
        remaining = max(0.0, until - now())
        t = 1.0 - min(1.0, remaining / WALK_SECONDS)
        return (lerp(pos[0], spot[0], t), lerp(pos[1], spot[1], t))
    if state in (EMP_COFFEE, EMP_GAMING, EMP_NAP) and emp.get("room") == "break":
        return break_spot(idx)
    return (float(pos[0]), float(pos[1]))


def room_legend(rooms: list[str] | None = None) -> str:
    items = []
    for rid in rooms or ROOM_ORDER:
        room = ROOMS[rid]
        items.append(
            f'<span class="chip" style="border-color:{room.color}55">'
            f'<span class="dot" style="background:{room.color}"></span>{room.name}</span>'
        )
    return f'<div class="row" style="gap:6px">{"".join(items)}</div>'

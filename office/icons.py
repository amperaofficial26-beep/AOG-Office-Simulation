"""Renderer ikon Material.

Semua ikon aplikasi memakai jalur SVG asli Material Symbols (filled), di-inline
langsung ke HTML supaya tetap tampil tanpa jaringan (tidak ada emoji, tidak ada
font eksternal).
"""
from __future__ import annotations

from .ui.icons_data import ICONS

# Alias nyaman supaya pemanggilan di UI tetap terbaca
ALIASES = {
    "kantor": "apartment",
    "kode": "code",
    "pesan": "mark_chat_unread",
    "riset": "psychology",
    "marketing": "campaign",
    "desain": "palette",
    "qa": "bug_report",
    "ops": "settings",
    "data": "storage",
    "break": "local_cafe",
    "bos": "supervisor_account",
    "approve": "task_alt",
    "reject": "close",
    "tugas": "assignment",
    "revisi": "edit",
    "gaji": "paid",
    "karyawan": "badge",
    "tim": "diversity_3",
    "github": "github",
    "deploy": "rocket_launch",
    "reload": "refresh",
    "simpan": "save",
    "kirim": "send",
    "bintang": "star",
    "peringkat": "leaderboard",
    "arsip": "inventory_2",
    "unduh": "download",
    "kunci": "lock",
    "sehat": "verified",
    "error": "error",
    "info": "info",
    "warning": "warning",
}

DEFAULT_ICON = "widgets"

# Brand mark yang kita simpan sebagai SVG sendiri, bukan bagian Material Symbols.
# Shortcode Streamlit hanya menerima ikon Material, jadi untuk brand kita
# kembalikan string kosong (widget tetap jalan, ikon digambar lewat HTML kita).
BRAND_ICONS = {"github"}


def resolve(name: str) -> str:
    """Ubah nama/alias menjadi key ikon yang benar-benar ada di data."""
    if not name:
        return DEFAULT_ICON
    name = str(name).strip()
    if name in ICONS:
        return name
    if name in ALIASES and ALIASES[name] in ICONS:
        return ALIASES[name]
    norm = name.replace("-", "_").replace(" ", "_").lower()
    if norm in ICONS:
        return norm
    if norm in ALIASES and ALIASES[norm] in ICONS:
        return ALIASES[norm]
    return DEFAULT_ICON


def icon_svg(name: str, size: int = 18, color: str = "currentColor", opacity: float = 1.0) -> str:
    """Kembalikan string <svg> inline untuk sebuah ikon Material."""
    key = resolve(name)
    spec = ICONS[key]
    vb = spec["vb"]
    paths = "".join(f'<path d="{d}"/>' for d in spec["d"])
    return (
        f'<svg class="mi" viewBox="{vb}" width="{size}" height="{size}" '
        f'fill="{color}" opacity="{opacity}" aria-hidden="true" '
        f'focusable="false" style="flex:none;vertical-align:-{max(2, size // 7)}px">'
        f"{paths}</svg>"
    )


def icon(name: str, size: int = 18, color: str = "currentColor", opacity: float = 1.0) -> str:
    return icon_svg(name, size=size, color=color, opacity=opacity)


def mat(name: str) -> str:
    """Shortcode Material untuk widget Streamlit: ``:material/nama_ikon:``.

    Dipakai pada parameter ``icon=`` milik st.button, st.metric, st.toast, dsb.
    Nama yang tidak dikenal otomatis dipetakan ke ikon default supaya Streamlit
    tidak menolak shortcode-nya.
    """
    key = resolve(name)
    if key in BRAND_ICONS:
        return ""
    return f":material/{key}:"


def labeled(name: str, text: str, size: int = 18, color: str = "currentColor", gap: int = 8) -> str:
    """Ikon + teks dalam satu baris yang rapi."""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:{gap}px">'
        f'{icon_svg(name, size=size, color=color)}<span>{text}</span></span>'
    )


def available() -> list[str]:
    """Semua nama ikon yang tersedia (untuk panel pengembang)."""
    return sorted(ICONS)

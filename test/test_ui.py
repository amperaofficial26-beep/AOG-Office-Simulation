"""Pengujian lapisan tampilan: ikon Material, karakter SVG, panggung kantor."""
from __future__ import annotations

import re

import pytest

from office.icons import ALIASES, BRAND_ICONS, available, icon_svg, labeled, mat, resolve
from office.models_data import EMP_COFFEE, EMP_GAMING, EMP_NAP, EMP_WALKING, EMP_WORKING
from office.roster import ROOM_ORDER, ROOMS, sync_employees
from office.state import empty_state
from office.ui.characters import STATE_CLASS, boss_svg, character_svg, state_label
from office.ui.icons_data import ICONS
from office.ui.office_view import iso, render_office, room_legend, room_polygon, view_box


@pytest.fixture
def state():
    st = empty_state()
    st["employees"] = sync_employees({})
    return st


# ----------------------------------------------------------------------------- ikon
def test_ikon_material_tersedia_dan_banyak():
    assert len(ICONS) >= 200
    for wajib in ("terminal", "mark_chat_unread", "psychology", "palette", "bug_report", "supervisor_account"):
        assert wajib in ICONS, f"ikon wajib {wajib} hilang"


def test_setiap_ikon_punya_path_valid():
    for name, spec in ICONS.items():
        assert spec["d"], f"{name} tidak punya path"
        for d in spec["d"]:
            assert d.strip().startswith(("M", "m", "C", "c")), f"{name}: path tidak lazim"


def test_alias_menyelesaikan_ke_ikon_ada():
    for alias, target in ALIASES.items():
        assert resolve(alias) in ICONS, f"alias {alias} -> {target} tidak ada"


def test_resolve_ikon_tak_dikenal_jatuh_ke_default():
    assert resolve("ikon_ngawur_xyz") == "widgets"
    assert resolve("") == "widgets"


def test_icon_svg_menghasilkan_svg_inline():
    svg = icon_svg("terminal", size=20, color="#38BDF8")
    assert svg.startswith("<svg")
    assert 'fill="#38BDF8"' in svg
    assert "<path" in svg
    assert "</svg>" in svg


def test_shortcode_material_untuk_widget_streamlit():
    assert mat("terminal") == ":material/terminal:"
    # ikon tidak dikenal dipetakan ke default agar tidak ditolak Streamlit
    assert mat("tidak_ada") == ":material/widgets:"


def test_shortcode_material_valid_menurut_streamlit():
    """Streamlit memvalidasi shortcode; pastikan semua ikon Material kita lolos."""
    pytest.importorskip("streamlit")
    from streamlit.string_util import validate_material_icon

    for name in available():
        if name in BRAND_ICONS:
            continue
        assert mat(name) == f":material/{name}:"
        validate_material_icon(mat(name))


def test_brand_icon_tidak_dikirim_sebagai_shortcode():
    """GitHub memakai brand mark sendiri, bukan ikon Material."""
    assert mat("github") == ""
    assert "github" in BRAND_ICONS
    assert "<path" in icon_svg("github")


def test_labeled_menggabungkan_ikon_dan_teks():
    html = labeled("assignment", "Tugas baru", 16)
    assert "<svg" in html and "Tugas baru" in html


# ----------------------------------------------------------------------------- karakter
def test_karakter_mengandung_kelas_animasi(state):
    emp = state["employees"]["sari"]
    emp["state"] = EMP_WORKING
    svg = character_svg(emp)
    assert "st-work" in svg
    assert 'class="arm a1"' in svg
    assert 'class="leg l1"' in svg
    assert 'class="eye"' in svg


def test_semua_status_punya_kelas_animasi():
    assert set(STATE_CLASS) >= {EMP_WORKING, EMP_WALKING, EMP_COFFEE, EMP_GAMING, EMP_NAP}


@pytest.mark.parametrize("state_name", ["bekerja", "berjalan", "ngopi", "main game", "istirahat", "mengobrol", "santai"])
def test_karakter_tetap_valid_pada_semua_status(state, state_name):
    emp = state["employees"]["ayu"]
    emp["state"] = state_name
    svg = character_svg(emp)
    assert svg.count("<g") == svg.count("</g>"), "grup SVG tidak seimbang"
    assert state_label(state_name)


def test_properti_khusus_per_status(state):
    emp = state["employees"]["putri"]
    emp["state"] = EMP_COFFEE
    assert "steam" in character_svg(emp)
    emp["state"] = EMP_GAMING
    assert 'class="arm a1"' in character_svg(emp)
    emp["state"] = EMP_NAP
    assert "zzz" in character_svg(emp)
    emp["state"] = EMP_WORKING
    assert "codeline" in character_svg(emp) or "screen" in character_svg(emp)


def test_varian_rambut_digambar(state):
    for style in ("short", "long", "ponytail", "bun", "buzz"):
        emp = state["employees"]["fajar"]
        emp["hair_style"] = style
        assert "<path" in character_svg(emp)


def test_kacamata_opsional(state):
    emp = state["employees"]["raka"]
    emp["glasses"] = True
    assert "stroke-width=\"1.1\"" in character_svg(emp)
    emp["glasses"] = False
    assert character_svg(emp).count('stroke-width="1.1"') == 0


def test_bos_memakai_aksen_keemasan():
    svg = boss_svg("Boss Ampera")
    assert "Boss Ampera" in svg
    assert "#FACC15" in svg


# ----------------------------------------------------------------------------- panggung
def test_proyeksi_isometrik():
    assert iso(0, 0) == (0.0, 0.0)
    x, y = iso(1, 0)
    assert x > 0 and y > 0
    x2, y2 = iso(0, 1)
    assert x2 < 0 and y2 > 0


def test_polygon_ruangan_berisi_empat_titik():
    for rid in ROOM_ORDER:
        pts = room_polygon(ROOMS[rid]).split()
        assert len(pts) == 4


def test_viewbox_cukup_lebar():
    x, y, w, h = view_box()
    assert w > 1000 and h > 500


def test_render_office_lengkap(state):
    html = render_office(state)
    assert '<svg class="office-svg"' in html
    for rid in ROOM_ORDER:
        assert ROOMS[rid].name in html, f"ruang {rid} tidak tergambar"
    for emp in state["employees"].values():
        assert emp["name"].split()[0] in html, f"karyawan {emp['name']} tidak muncul"
    assert html.count("<svg") == html.count("</svg>")


def test_render_office_menandai_pesan_belum_dibaca(state):
    state["inbox"] = [{"mid": "m1", "sender": "Klien", "subject": "Halo", "body": "x", "read": False, "channel": "email"}]
    html = render_office(state)
    assert "#EF4444" in html  # badge merah di ruang penerima pesan


def test_legenda_ruangan():
    html = room_legend()
    assert "Ruang Kode" in html and "Pantry" in html


def test_svg_kantor_adalah_xml_valid(state):
    """SVG harus lolos parser XML; teks berisi & atau < wajib di-escape."""
    import xml.etree.ElementTree as ET

    state["employees"]["sari"]["name"] = "Sari & Rekan <QA>"
    html = render_office(state)
    svg = html[html.find("<svg") : html.rfind("</svg>") + len("</svg>")]
    ET.fromstring(svg)  # melempar bila ada karakter mentah


def test_tooltip_ruangan_terescape(state):
    """Nama ruang dengan tanda & tidak boleh menghasilkan XML rusak."""
    import xml.etree.ElementTree as ET

    from office.roster import ROOMS

    ROOMS["break"].name = "Pantry & Ruang Santai"
    try:
        html = render_office(state)
        svg = html[html.find("<svg") : html.rfind("</svg>") + len("</svg>")]
        assert "&amp;" in svg
        ET.fromstring(svg)
    finally:
        ROOMS["break"].name = "Pantry dan Ruang Santai"

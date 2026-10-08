"""Uji asap aplikasi Streamlit full-screen: panggung + HUD tanpa exception."""
from __future__ import annotations

import pathlib

import pytest

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

TOPBAR_SLUGS = ["tugas", "inbox", "approval", "karyawan", "github", "apps", "models", "settings"]
ROOM_SLUGS = ["boss", "code", "research", "design", "marketing", "reception", "qa", "data", "ops", "break"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    from office import config
    from office import state as state_mod

    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(state_mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(state_mod, "CONFIG_FILE", str(tmp_path / "config.json"))
    app_path = pathlib.Path(__file__).resolve().parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()
    return at


def buka(app, slug: str):
    tombol = next((b for b in app.button if b.key == f"tb_{slug}"), None)
    assert tombol is not None, f"tombol HUD {slug} tidak ditemukan"
    tombol.click().run()
    return app


def test_aplikasi_berjalan_tanpa_error(app):
    assert not app.exception, app.exception


def test_panggung_kantor_fullscreen_ada(app):
    app.run()
    svg = [md.value for md in app.markdown if '<svg class="office-svg"' in md.value]
    assert svg, "panggung kantor tidak tergambar"
    assert "Ruang Kode" in svg[0]
    assert "Ruang Penerima Pesan" in svg[0]
    assert "Pantry" in svg[0]


def test_css_hud_dimuat(app):
    style = [md.value for md in app.markdown if "stMainBlockContainer" in md.value]
    assert style, "CSS HUD tidak dimuat"
    assert "rotate(90deg)" in style[0], "aturan rotasi landscape untuk ponsel tidak ada"


def test_bar_atas_memuat_semua_fitur(app):
    for slug in TOPBAR_SLUGS:
        assert any(b.key == f"tb_{slug}" for b in app.button), f"tb_{slug} hilang"


def test_bar_bawah_memuat_semua_ruang(app):
    for slug in ROOM_SLUGS:
        assert any(b.key == f"bb_{slug}" for b in app.button), f"bb_{slug} hilang"


@pytest.mark.parametrize("slug", TOPBAR_SLUGS)
def test_setiap_drawer_render(app, slug):
    buka(app, slug)
    assert not app.exception, f"drawer {slug} error: {app.exception}"


def test_drawer_bisa_ditutup(app):
    buka(app, "settings")
    close = next(b for b in app.button if b.key == "drawer_close")
    close.click().run()
    assert not app.exception


def test_ruang_dibuka_dari_bar_bawah(app):
    tombol = next(b for b in app.button if b.key == "bb_code")
    tombol.click().run()
    assert not app.exception
    mds = " ".join(md.value for md in app.markdown)
    assert "Ruang Kode" in mds


def test_tidak_ada_emoji_di_antarmuka(app):
    import re

    emoji = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF\u2190-\u21FF\u2B00-\u2BFF]"
    )
    for md in app.markdown:
        assert not emoji.search(md.value), f"emoji di markdown: {md.value[:80]}"
    for button in app.button:
        assert not emoji.search(button.label), f"emoji di tombol: {button.label}"


def test_form_tugas_menghasilkan_antrean(app):
    buka(app, "tugas")
    tombol = [b for b in app.button if b.label == "Kirim tugas"]
    assert tombol, "tombol kirim tugas tidak ada"
    assert app.text_area, "form tugas tidak punya kolom brief"


def test_pesan_masuk_bisa_dibuat(app):
    buka(app, "inbox")
    tombol = next((b for b in app.button if "Simulasi pesan masuk" in b.label), None)
    assert tombol is not None
    tombol.click().run()
    assert not app.exception
    assert len(app.session_state["office_state"]["inbox"]) >= 1


def test_github_menampilkan_kartu_terhubung(app):
    from office.config import get_key

    if not get_key("github"):
        pytest.skip("token GitHub tidak tersedia di lingkungan uji")
    buka(app, "github")
    mds = " ".join(md.value for md in app.markdown)
    assert "Terhubung sebagai" in mds


def test_pengaturan_form_kunci_ada(app):
    buka(app, "settings")
    placeholders = [ti for ti in app.text_input]
    assert any("GITHUB_TOKEN" in (p.label or "") for p in placeholders)
    assert any("GROQ_API_KEY" in (p.label or "") for p in placeholders)

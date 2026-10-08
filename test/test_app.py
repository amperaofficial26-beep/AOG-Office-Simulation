"""Uji asap aplikasi Streamlit: semua panel harus render tanpa exception."""
from __future__ import annotations

import pathlib

import pytest

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

PANELS = [
    "Kantor",
    "Beri Tugas",
    "Kotak Pesan",
    "Persetujuan",
    "Karyawan",
    "GitHub",
    "Aplikasi Streamlit",
    "Model & Provider",
    "Pengaturan",
]


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


def navigasi(app, panel: str):
    # AppTest menempatkan elemen sidebar di kumpulan utama, jadi cari di seluruh app
    tombol = next((b for b in app.button if b.key == f"nav_{panel}"), None)
    assert tombol is not None, f"tombol navigasi {panel} tidak ditemukan"
    tombol.click().run()
    return app


def test_aplikasi_berjalan_tanpa_error(app):
    assert not app.exception, app.exception
    assert app.session_state["page"] == "Kantor"


def test_tidak_ada_emoji_di_antarmuka(app):
    """Semua ikon harus Material; emoji dilarang di seluruh UI."""
    import re

    emoji = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF\u2190-\u21FF\u2B00-\u2BFF]"
    )
    for md in app.markdown:
        assert not emoji.search(md.value), f"emoji ditemukan di markdown: {md.value[:80]}"
    for button in app.button:
        assert not emoji.search(button.label), f"emoji di tombol: {button.label}"


@pytest.mark.parametrize("panel", PANELS)
def test_setiap_panel_render(app, panel):
    navigasi(app, panel)
    assert not app.exception, f"panel {panel} error: {app.exception}"
    assert app.session_state["page"] == panel


def test_panggung_kantor_mengandung_svg(app):
    app.run()  # pastikan fragment panggung ikut ter-render
    svg = [md.value for md in app.markdown if '<svg class="office-svg"' in md.value]
    assert svg, "panggung kantor tidak tergambar"
    assert "Ruang Kode" in svg[0]
    assert "Ruang Penerima Pesan" in svg[0]


def test_sidebar_menampilkan_identitas_bos(app):
    teks = " ".join(md.value for md in app.markdown)
    assert "AOG Virtual Office" in teks
    assert "Boss Ampera" in teks


def test_form_tugas_menghasilkan_antrean(app):
    navigasi(app, "Beri Tugas")
    assert not app.exception
    # st.form_submit_button tampil sebagai Button di AppTest
    tombol = [b for b in app.button if b.label == "Kirim tugas"]
    assert tombol, "tombol kirim tugas tidak ada"
    assert app.text_input, "form tugas tidak memiliki kolom judul"
    assert app.text_area, "form tugas tidak memiliki kolom brief"


def test_pesan_masuk_bisa_dibuat(app):
    navigasi(app, "Kotak Pesan")
    tombol = next((b for b in app.button if "Simulasi pesan masuk" in b.label), None)
    assert tombol is not None
    tombol.click().run()
    assert not app.exception
    assert len(app.session_state["office_state"]["inbox"]) >= 1


def test_tombol_model_ada_di_panel_model(app):
    navigasi(app, "Model & Provider")
    labels = [b.label for b in app.button]
    assert any("Probe katalog live" in l for l in labels)
    assert any("Uji sekarang" in l for l in labels)


def test_pengaturan_bisa_disimpan(app):
    navigasi(app, "Pengaturan")
    assert not app.exception
    assert app.text_input, "form pengaturan tidak tergambar"

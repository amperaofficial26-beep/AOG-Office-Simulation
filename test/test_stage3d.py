"""Regresi panggung 3D: ruang lengkap dan jaringan CPU tidak hilang saat update."""
from __future__ import annotations

from office.roster import ROOMS
from office.ui.stage3d import THREE_ASSET, _component_html, build_html, build_payload


def test_setiap_ruang_memiliki_daftar_perabot_dan_spot_kerja():
    payload = build_payload(ROOMS, [])
    assert len(payload["rooms"]) == len(ROOMS)
    for room in payload["rooms"]:
        assert room["furniture"], room["rid"]
        assert room["spots"], room["rid"]
    assert {"sofa", "coffee", "arcade"} <= set(ROOMS["break"].furniture)
    assert "whiteboard" in ROOMS["meeting"].furniture


def test_jalur_listrik_ke_aplikasi_dan_furnitur_spesifik_tersedia():
    html = _component_html()
    for side in ('side:"n"', 'side:"e"', 'side:"s"', 'side:"w"'):
        assert side in html
    for app in ("GITHUB", "MODEL AI", "STREAMLIT", "DEPLOY", "DATA", "OTOMASI", "INBOX", "TUGAS"):
        assert f'label:"{app}"' in html
    for furniture in ("makeConference", "makeCafeTable", "makePrinter", "makeWallArt"):
        assert furniture in html
    assert 'ink.addColorStop(1,"rgba(56,189,248,0)")' in html  # soft mask di ujung
    assert "animateCircuits(t);" in html
    assert "prefers-reduced-motion: reduce" in html


def test_three_js_dikirim_lokal_tanpa_cdn():
    assert THREE_ASSET.exists()
    component = _component_html()
    assert '<script src="./three.min.js"></script>' in component
    preview = build_html(build_payload(ROOMS, []))
    assert "cdnjs" not in preview
    assert 'src="__THREE__"' not in preview
    assert "var EMBED=__DATA__" not in preview
    assert "THREE.WebGLRenderer" in preview

"""Pengujian denah kantor dan roster karyawan."""
from __future__ import annotations

import pytest

from office.roster import (
    DESK_SPOTS,
    ROSTER,
    ROOMS,
    ROOM_ORDER,
    desk_spot,
    room_bounds,
    roster_table,
    suggested_employee,
    sync_employees,
)


def _overlaps(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def test_ruangan_tidak_tumpang_tindih():
    bounds = {rid: room_bounds(rid) for rid in ROOM_ORDER}
    checked = 0
    for i, rid_a in enumerate(ROOM_ORDER):
        for rid_b in ROOM_ORDER[i + 1 :]:
            checked += 1
            assert not _overlaps(bounds[rid_a], bounds[rid_b]), f"{rid_a} tumpang tindih dengan {rid_b}"
    assert checked > 20


def test_setiap_ruangan_punya_spot_meja():
    for rid in ROOM_ORDER:
        assert DESK_SPOTS.get(rid), f"ruang {rid} tidak punya spot meja"


def test_spot_meja_berada_di_dalam_ruangan():
    for rid in ROOM_ORDER:
        x0, y0, x1, y1 = room_bounds(rid)
        for spot in DESK_SPOTS[rid]:
            assert x0 <= spot[0] <= x1, f"spot {spot} di luar {rid} (x)"
            assert y0 <= spot[1] <= y1, f"spot {spot} di luar {rid} (y)"


def test_roster_unik_dan_lengkap():
    ids = [e.eid for e in ROSTER]
    names = [e.name for e in ROSTER]
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert len(ROSTER) >= 10
    roles = {e.role for e in ROSTER}
    for wajib in ("engineer", "qa", "researcher", "designer", "marketing", "ops", "analyst", "reception"):
        assert wajib in roles, f"tidak ada karyawan dengan role {wajib}"


def test_setiap_karyawan_punya_kepribadian_dan_kebiasaan():
    for emp in ROSTER:
        assert emp.personality
        assert emp.greeting
        assert len(emp.quirks) >= 2, f"{emp.name} butuh minimal 2 kebiasaan"
        assert emp.room in ROOMS


def test_ruangan_terpakai_oleh_minimal_satu_karyawan():
    dipakai = {e.room for e in ROSTER}
    for rid in (
        "code", "qa", "research", "design", "marketing", "ops", "data", "reception",
        "ai_image", "web_research",
    ):
        assert rid in dipakai, f"ruang {rid} kosong tanpa karyawan"


def test_karyawan_gambar_dan_riset_web_ada():
    roles = {e.role: e for e in ROSTER}
    assert roles["image_artist"].room == "ai_image"
    assert roles["web_search"].room == "web_research"
    assert roles["image_artist"].model.startswith("@cf/"), "karyawan gambar wajib memakai FLUX.1"
    assert roles["web_search"].model.startswith("tavily-"), "karyawan riset web wajib memakai Tavily"


def test_saran_karyawan_gambar_dan_riset_web():
    assert suggested_employee("gambar") in {e.eid for e in ROSTER if e.role == "image_artist"}
    assert suggested_employee("riset web") in {e.eid for e in ROSTER if e.role == "web_search"}
    # Kata kunci di brief memperkuat saran meski bentuk keluarannya umum.
    assert suggested_employee("riset", brief="cari di web sumber tren kompetitor terbaru") in {
        e.eid for e in ROSTER if e.role in ("researcher", "web_search")
    }


def test_sinkronisasi_menambah_karyawan_baru():
    merged = sync_employees({})
    assert set(merged) == {e.eid for e in ROSTER}
    assert merged["raka"]["fallbacks"]


def test_sinkronisasi_mempertahankan_progres():
    merged = sync_employees({"sari": {"xp": 320, "level": 4, "tasks_done": 12, "mood": 55, "state": "ngopi"}})
    assert merged["sari"]["xp"] == 320
    assert merged["sari"]["tasks_done"] == 12
    assert merged["sari"]["state"] == "ngopi"


def test_sinkronisasi_memigrasikan_model_mati():
    merged = sync_employees({"raka": {"model": "llama-3.3-70b-versatile"}})
    assert merged["raka"]["model"] == "openai/gpt-oss-120b"
    assert merged["raka"]["provider"] == "groq"


def test_sinkronisasi_menghormati_model_pilihan_user():
    merged = sync_employees({"sari": {"model": "cohere/north-mini-code:free"}})
    assert merged["sari"]["model"] == "cohere/north-mini-code:free"


def test_saran_karyawan_berdasarkan_jenis_keluaran():
    assert ROSTER and suggested_employee("kode") in {e.eid for e in ROSTER}
    assert suggested_employee("desain") in {e.eid for e in ROSTER if e.role == "designer"}
    assert suggested_employee("balasan pesan") in {e.eid for e in ROSTER if e.role == "reception"}


def test_roster_table_siap_pakai():
    rows = roster_table()
    assert len(rows) == len(ROSTER)
    assert {"nama", "jabatan", "ruang", "provider", "model"} <= set(rows[0])


@pytest.mark.parametrize("index", [0, 5, 99])
def test_desk_spot_tidak_error_pada_index_besar(index):
    assert desk_spot("code", index) in DESK_SPOTS["code"]

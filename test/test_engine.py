"""Pengujian alur kerja: tugas -> dikerjakan model -> persetujuan -> rilis.

Panggilan jaringan ke model AI dipalsukan (monkeypatch) supaya pengujian cepat,
deterministik, dan tidak menghabiskan kuota API Anda.
"""
from __future__ import annotations

import time

import pytest

from office import engine, llm
from office.roster import sync_employees
from office.models_data import (
    TASK_APPROVED,
    TASK_ARCHIVED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_REVIEW,
)


class FakeResult(dict):
    @property
    def text(self):
        return self.get("text", "")

    @property
    def model(self):
        return self.get("model", "")

    @property
    def provider(self):
        return self.get("provider", "")


@pytest.fixture
def state(tmp_path, monkeypatch):
    """State segar yang disimpan di direktori sementara."""
    from office import state as state_mod

    monkeypatch.setattr(state_mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(state_mod, "CONFIG_FILE", str(tmp_path / "config.json"))
    fresh = state_mod.empty_state()
    fresh["employees"] = sync_employees({})
    monkeypatch.setattr(state_mod, "load_json", lambda path, default=None: fresh if "state" in path else (default or {}))
    monkeypatch.setattr(state_mod, "save_json", lambda path, payload: None)
    return fresh


@pytest.fixture
def fake_llm(monkeypatch):
    """Ganti panggilan model dengan balasan tetap."""
    calls: list[str] = []

    def fake(messages, model, provider=None, **kwargs):
        calls.append(model)
        return FakeResult(
            text="Hasil kerja uji.\n\nRingkasan untuk Bos:\n- poin satu\n- poin dua",
            model=model,
            model_label=model,
            provider=provider or "groq",
            provider_label="Groq",
            tokens_in=120,
            tokens_out=64,
            latency=1.25,
        )

    monkeypatch.setattr(llm, "chat_with_fallback", lambda messages, model, **kw: (fake(None, model), []))
    return calls


def test_buat_tugas_masuk_antrean(state):
    state, task = engine.create_task(
        state,
        title="Perbaiki tombol kirim",
        brief="Tombol tidak responsif saat koneksi lambat.",
        assignee="sari",
        deliverable="perbaikan bug",
        priority="tinggi",
    )
    assert task["status"] == TASK_QUEUED
    assert task["assignee"] == "sari"
    assert state["tasks"][0]["tid"] == task["tid"]
    assert state["stats"]["tasks_created"] == 1
    assert state["employees"]["sari"]["state"] == "berjalan"


def test_tugas_ditolak_untuk_karyawan_tak_dikenal(state):
    with pytest.raises(ValueError):
        engine.create_task(state, title="x", brief="y", assignee="tidak-ada")


def test_tugas_dikerjakan_dan_masuk_antrean_persetujuan(state, fake_llm):
    state, task = engine.create_task(state, title="Buat util tanggal", brief="Fungsi format tanggal ID", assignee="sari")
    state, done = engine.run_task(state, task["tid"])
    assert done is not None
    assert done["status"] == TASK_REVIEW
    assert "Ringkasan untuk Bos" in done["result"]
    assert done["tokens_out"] == 64
    assert done["duration"] == 1.25
    assert state["stats"]["api_calls"] == 1
    assert state["employees"]["sari"]["xp"] > 0
    assert fake_llm, "model tidak pernah dipanggil"


def test_persetujuan_menambah_progres_karyawan(state, fake_llm):
    state, task = engine.create_task(state, title="Riset kompetitor", brief="Bandingkan 3 produk", assignee="ayu")
    state, task = engine.run_task(state, task["tid"])
    before = state["employees"]["ayu"]["tasks_done"]
    state, approved = engine.approve_task(state, task["tid"], note="Bagus, lanjut.", rating=5)
    assert approved["status"] == TASK_APPROVED
    assert approved["boss_note"] == "Bagus, lanjut."
    assert approved["rating"] == 5
    assert state["employees"]["ayu"]["tasks_done"] == before + 1
    assert state["stats"]["tasks_done"] == 1


def test_penolakan_mengembalikan_tugas_ke_antrean(state, fake_llm):
    state, task = engine.create_task(state, title="Tulis artikel", brief="Artikel 500 kata", assignee="dinda")
    state, task = engine.run_task(state, task["tid"])
    state, rejected = engine.reject_task(state, task["tid"], note="Terlalu panjang, ringkas.", rerun=True)
    assert rejected["status"] == TASK_QUEUED
    assert rejected["revision_count"] == 1
    assert rejected["boss_note"] == "Terlalu panjang, ringkas."
    assert state["stats"]["tasks_rejected"] == 1


def test_penolakan_tanpa_rerun(state, fake_llm):
    state, task = engine.create_task(state, title="Tulis artikel", brief="x", assignee="dinda")
    state, task = engine.run_task(state, task["tid"])
    state, rejected = engine.reject_task(state, task["tid"], note="tidak dipakai", rerun=False)
    assert rejected["status"] == "ditolak"


def test_kegagalan_model_ditandai(state, monkeypatch):  # noqa: D103
    def boom(messages, model, **kwargs):
        raise llm.LLMError("HTTP 401 - kunci tidak valid")

    monkeypatch.setattr(llm, "chat_with_fallback", boom)
    state, task = engine.create_task(state, title="Tugas gagal", brief="x", assignee="bimo")
    state, failed = engine.run_task(state, task["tid"])
    assert failed["status"] == TASK_FAILED
    assert "401" in failed["error"]
    assert state["stats"]["api_errors"] == 1


def test_rilis_mengarsipkan_tugas(state, fake_llm):
    ids = []
    for judul, emp in (("Fitur A", "sari"), ("Fitur B", "bimo")):
        state, task = engine.create_task(state, title=judul, brief="x", assignee=emp)
        state, task = engine.run_task(state, task["tid"])
        state, _ = engine.approve_task(state, task["tid"])
        ids.append(task["tid"])
    release = engine.publish_release(state, ids, title="Rilis 1.0", repo="Ampera-Web-Design")
    assert len(release["tasks"]) == 2
    assert state["stats"]["releases"] == 1
    assert all(t["status"] == TASK_ARCHIVED for t in state["tasks"] if t["tid"] in ids)


def test_pesan_masuk_dan_delegasi(state):
    msg = engine.push_inbox(state, "Klien", "Minta demo", "Isi pesan", "email")
    assert state["inbox"][0]["mid"] == msg["mid"]
    assert engine.summary(state)["inbox_unread"] == 1
    state, task = engine.delegate_message(state, msg["mid"], "lala")
    assert task is not None
    assert task["assignee"] == "lala"
    assert state["inbox"][0]["handled"] == task["tid"]
    assert state["inbox"][0]["read"] is True


def test_tandai_dibaca(state):
    msg = engine.push_inbox(state, "A", "B", "C", "chat")
    engine.mark_read(state, msg["mid"])
    assert state["inbox"][0]["read"] is True
    assert engine.summary(state)["inbox_unread"] == 0


def test_simulasi_pesan_masuk(state):
    before = len(state.get("inbox", []))
    engine.simulate_incoming(state)
    assert len(state["inbox"]) == before + 1


def test_tick_memindahkan_karyawan(state):
    emp = state["employees"]["sari"]
    emp["target_room"] = "qa"
    emp["state"] = "berjalan"
    emp["state_until"] = time.time() - 1  # sudah lewat
    engine.tick(state)
    assert emp["room"] == "qa"
    assert emp["state"] in ("bekerja", "santai")


def test_tick_memulihkan_energi_dan_mengirim_ke_pantry(state):
    emp = state["employees"]["putri"]
    emp["energy"] = 5
    emp["state"] = "santai"
    emp["state_until"] = 0
    engine.tick(state)
    assert emp["target_room"] == "break"
    assert emp["state"] == "berjalan"


def test_istirahat_dan_panggil_kembali(state):
    engine.send_to_break(state, "kenji")
    assert state["employees"]["kenji"]["energy"] == 100
    assert state["employees"]["kenji"]["target_room"] == "break"
    engine.recall_employee(state, "kenji")
    from office.roster import ROSTER_BY_ID

    assert state["employees"]["kenji"]["target_room"] == ROSTER_BY_ID["kenji"].room


def test_ringkasan_state(state, fake_llm):
    engine.push_inbox(state, "X", "Y", "Z", "chat")
    state, task = engine.create_task(state, title="T", brief="b", assignee="tomi")
    state, task = engine.run_task(state, task["tid"])
    summ = engine.summary(state)
    assert summ["pending"] == 1
    assert summ["employees"] == len(state["employees"])
    assert summ["inbox_unread"] == 1


def test_arsip_dan_bersihkan(state, fake_llm):
    state, task = engine.create_task(state, title="T", brief="b", assignee="sari")
    state, task = engine.run_task(state, task["tid"])
    engine.approve_task(state, task["tid"])
    engine.archive_task(state, task["tid"])
    assert engine.get_task(state, task["tid"])["status"] == TASK_ARCHIVED
    engine.clear_archived(state)
    assert engine.get_task(state, task["tid"]) is None


def test_prompt_berisi_kepribadian_dan_aturan(state):
    emp = state["employees"]["nadia"]
    prompt = llm.build_system_prompt(emp, "Ampera Official Group", "Boss Ampera")
    assert "Nadia Kusuma" in prompt
    assert "QA Engineer" in prompt or "Kepala Pengujian" in prompt
    assert "emoji" in prompt  # aturan tanpa emoji
    assert "Ringkasan untuk Bos" in prompt


def test_prompt_tugas_menyertakan_konteks_dan_revisi():
    text = llm.build_task_prompt(
        title="Judul",
        brief="Isi brief",
        deliverable="kode",
        priority="tinggi",
        context="REPO: contoh/app.py",
        revision_note="Ringkas lagi",
    )
    assert "Judul" in text
    assert "REPO: contoh/app.py" in text
    assert "Ringkas lagi" in text

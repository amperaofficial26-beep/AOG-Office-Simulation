"""Regresi untuk workflow idempotent, revisi, antrean, dan percakapan."""
from __future__ import annotations

from office import engine, llm
from office.models_data import TASK_APPROVED, TASK_QUEUED, TASK_REVIEW
from office.roster import rank_employees, sync_employees
from office.state import empty_state, migrate_state


class Result(dict):
    @property
    def text(self):
        return self["text"]

    @property
    def model(self):
        return self["model"]

    @property
    def provider(self):
        return self["provider"]


def fresh(monkeypatch):
    state = empty_state()
    state["employees"] = sync_employees({})
    monkeypatch.setattr(engine, "save_state", lambda state: None)
    monkeypatch.setattr(engine, "load_config", lambda: {"company": "AOG", "boss_name": "Bos"})
    return state


def fake_result(model="openai/gpt-oss-120b"):
    return Result(
        text=("## Hasil\nPekerjaan telah disusun secara konkret dan dapat diperiksa. " * 8)
        + "\n\n## Ringkasan untuk Bos\n- Hasil siap ditinjau.\n- Asumsi sudah dinyatakan.",
        model=model,
        provider="groq",
        tokens_in=100,
        tokens_out=200,
        latency=0.2,
    )


def test_approve_idempotent_tidak_menggandakan_statistik(monkeypatch):
    state = fresh(monkeypatch)
    _, task = engine.create_task(state, title="Dokumen", brief="Tulis dokumen final", assignee="sari")
    task["status"] = TASK_REVIEW
    task["result"] = "hasil"
    engine.approve_task(state, task["tid"])
    engine.approve_task(state, task["tid"])
    assert task["status"] == TASK_APPROVED
    assert state["stats"]["tasks_done"] == 1
    assert state["employees"]["sari"]["tasks_done"] == 1


def test_run_task_tidak_memanggil_api_untuk_status_review(monkeypatch):
    state = fresh(monkeypatch)
    _, task = engine.create_task(state, title="Dokumen", brief="Tulis dokumen final", assignee="sari")
    task["status"] = TASK_REVIEW
    monkeypatch.setattr(llm, "chat_with_fallback", lambda *a, **k: (_ for _ in ()).throw(AssertionError("API terpanggil")))
    _, same = engine.run_task(state, task["tid"])
    assert same is task


def test_revisi_mengirim_hasil_sebelumnya_ke_prompt(monkeypatch):
    state = fresh(monkeypatch)
    captured = []

    def fake(messages, model, **kwargs):
        captured.append(messages[-1]["content"])
        return fake_result(model), []

    monkeypatch.setattr(llm, "chat_with_fallback", fake)
    _, task = engine.create_task(state, title="Artikel", brief="Tulis artikel final", assignee="dinda", deliverable="artikel")
    engine.run_task(state, task["tid"])
    first = task["result"]
    engine.reject_task(state, task["tid"], "Ringkas pembukanya", rerun=True)
    assert task["status"] == TASK_QUEUED
    engine.run_task(state, task["tid"])
    assert "HASIL VERSI SEBELUMNYA" in captured[-1]
    assert first[:100] in captured[-1]
    assert len(task["revision_history"]) == 1


def test_antrean_mendahulukan_prioritas_tinggi(monkeypatch):
    state = fresh(monkeypatch)
    _, low = engine.create_task(state, title="Rendah", brief="detail", assignee="sari", priority="rendah")
    _, high = engine.create_task(state, title="Tinggi", brief="detail", assignee="bimo", priority="tinggi")
    order = []

    def run(state, tid):
        order.append(tid)
        task = engine.get_task(state, tid)
        task["status"] = TASK_REVIEW
        return state, task

    monkeypatch.setattr(engine, "run_task", run)
    engine.run_queue(state)
    assert order == [high["tid"], low["tid"]]


def test_delegasi_pesan_idempotent(monkeypatch):
    state = fresh(monkeypatch)
    msg = engine.push_inbox(state, "Klien", "Halo", "Tolong balas")
    _, first = engine.delegate_message(state, msg["mid"], "lala")
    _, second = engine.delegate_message(state, msg["mid"], "sari")
    assert first["tid"] == second["tid"]
    assert len(state["tasks"]) == 1


def test_migrasi_melengkapi_statistik_dan_task_lama():
    old = {"schema": 1, "stats": {"tasks_done": "3"}, "tasks": [{"tid": "T-1", "status": "menunggu"}]}
    new = migrate_state(old)
    assert new["schema"] > 1
    assert new["stats"]["tasks_done"] == 3
    assert "api_errors" in new["stats"]
    assert "quality" in new["tasks"][0]
    assert "chats" in new


def test_rekomendasi_mempertimbangkan_beban_kerja():
    state = empty_state()
    state["employees"] = sync_employees({})
    baseline = rank_employees("kode", state)
    leader = baseline[0][0]
    state["tasks"] = [
        {"tid": f"T-{i}", "status": TASK_QUEUED, "assignee": leader}
        for i in range(6)
    ]
    assert rank_employees("kode", state)[0][0] != leader

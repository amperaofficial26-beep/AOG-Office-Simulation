"""Pengujian alur tugas karyawan non-chat: gambar (FLUX.1) dan riset web (Tavily).

Panggilan API dipalsukan supaya pengujian cepat dan tidak menghabiskan kuota.
"""
from __future__ import annotations

import pytest

from office import engine, imageai, llm, websearch
from office.models import modality_of
from office.models_data import TASK_FAILED, TASK_REVIEW
from office.roster import ROSTER_BY_ID, sync_employees


@pytest.fixture
def state(tmp_path, monkeypatch):
    from office import state as state_mod

    monkeypatch.setattr(state_mod, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(state_mod, "CONFIG_FILE", str(tmp_path / "config.json"))
    fresh = state_mod.empty_state()
    fresh["employees"] = sync_employees({})
    monkeypatch.setattr(state_mod, "load_json", lambda path, default=None: fresh if "state" in path else (default or {}))
    monkeypatch.setattr(state_mod, "save_json", lambda path, payload: None)
    return fresh


@pytest.fixture
def gambar_jadi(tmp_path):
    """Hasil gambar palsu lengkap dengan berkas PNG di disk."""
    path = tmp_path / "assets" / "hasil.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    return imageai.ImageResult(
        text="",
        model="@cf/black-forest-labs/flux-1-schnell",
        model_label="FLUX.1 Schnell",
        provider="cloudflare",
        provider_label="Cloudflare Workers AI",
        file=str(path),
        files=[str(path)],
        prompt="banner peluncuran aplikasi kantor | gaya: ilustrasi profesional",
        steps=4,
        bytes=36,
        latency=2.5,
        tokens_in=0,
        tokens_out=0,
    )


# ----------------------------------------------------------------------------- routing
def test_karyawan_baru_terdaftar_di_roster():
    assert ROSTER_BY_ID["kirana"].role == "image_artist"
    assert ROSTER_BY_ID["kirana"].room == "ai_image"
    assert ROSTER_BY_ID["kirana"].provider == "cloudflare"
    assert ROSTER_BY_ID["wira"].role == "web_search"
    assert ROSTER_BY_ID["wira"].room == "web_research"
    assert ROSTER_BY_ID["wira"].provider == "tavily"


def test_modality_model_karyawan_baru():
    assert modality_of(ROSTER_BY_ID["kirana"].model) == "image"
    assert modality_of(ROSTER_BY_ID["wira"].model) == "search"
    assert modality_of(ROSTER_BY_ID["sari"].model) == "chat"


# ----------------------------------------------------------------------------- tugas gambar
def test_tugas_gambar_menghasilkan_berkas(state, gambar_jadi, monkeypatch):
    dipanggil = {}

    def fake_generate(prompt, model, fallbacks=(), role_fallbacks=(), steps=None, slug="gambar"):
        dipanggil.update(prompt=prompt, model=model, slug=slug)
        return gambar_jadi, []

    monkeypatch.setattr(imageai, "generate_with_fallback", fake_generate)
    state, task = engine.create_task(
        state,
        title="Banner peluncuran aplikasi kantor",
        brief="Gedung kantor modern saat senja dengan warna oranye.",
        assignee="kirana",
        deliverable="gambar",
    )
    state, task = engine.run_task(state, task["tid"])

    assert task["status"] == TASK_REVIEW
    assert task["files"] == [str(gambar_jadi.file)]
    assert task["provider_used"] == "cloudflare"
    assert task["model_used"] == "@cf/black-forest-labs/flux-1-schnell"
    assert task["quality_score"] >= 60, task["quality"]["issues"]
    assert "Gedung kantor modern saat senja" in dipanggil["prompt"]
    assert dipanggil["slug"] == task["tid"]
    assert "Ringkasan untuk Bos" in task["result"]


def test_tugas_gambar_gagal_dicatat(state, monkeypatch):
    def gagal(*a, **k):
        raise imageai.ImageError("Semua model gambar gagal. Percobaan terakhir: kuota habis")

    monkeypatch.setattr(imageai, "generate_with_fallback", gagal)
    state, task = engine.create_task(
        state, title="Ikon aplikasi", brief="Ikon sederhana untuk aplikasi kantor.",
        assignee="kirana", deliverable="gambar",
    )
    state, task = engine.run_task(state, task["tid"])

    assert task["status"] == TASK_FAILED
    assert "kuota habis" in task["error"]
    assert state["employees"]["kirana"]["mood"] < 80
    assert state["stats"]["api_errors"] == 1


# ----------------------------------------------------------------------------- tugas riset web
def test_tugas_riset_web_menyimpan_sumber(state, monkeypatch):
    hasil = websearch.SearchResult(
        text="",
        model="tavily-search",
        model_label="Tavily Search",
        provider="tavily",
        provider_label="Tavily",
        query="tren harga panel surya 2026 untuk laporan bos",
        answer="Harga panel surya turun 12 persen.",
        sources=[
            {
                "title": "Laporan Pasar Energi Surya",
                "url": "https://contoh.example/laporan-surya",
                "snippet": "Harga modul turun karena kelebihan pasokan.",
                "score": 0.91,
                "published_date": "2026-09-14",
            }
        ],
        follow_up=[],
        search_depth="basic",
        latency=1.1,
    )
    seen = {}

    def fake_search(query, model, fallbacks=(), role_fallbacks=(), max_results=6):
        seen.update(query=query, model=model)
        return hasil, []

    monkeypatch.setattr(websearch, "search_with_fallback", fake_search)
    state, task = engine.create_task(
        state,
        title="tren harga panel surya 2026",
        brief="Kumpulkan sumber untuk laporan bos, sertakan tanggal terbit.",
        assignee="wira",
        deliverable="riset web",
    )
    state, task = engine.run_task(state, task["tid"])

    assert task["status"] == TASK_REVIEW
    assert seen["model"] == "tavily-search"
    assert "panel surya" in seen["query"]
    assert task["sources"][0]["url"] == "https://contoh.example/laporan-surya"
    assert "https://contoh.example/laporan-surya" in task["result"]
    assert task["provider_used"] == "tavily"
    assert task["quality_score"] >= 60, task["quality"]["issues"]


def test_tugas_riset_web_gagal_dicatat(state, monkeypatch):
    def gagal(*a, **k):
        raise websearch.SearchError("API key TAVILY_API_KEY belum diisi di Secrets")

    monkeypatch.setattr(websearch, "search_with_fallback", gagal)
    state, task = engine.create_task(
        state, title="Cari kompetitor", brief="Daftar pesaing utama di pasar lokal.",
        assignee="wira", deliverable="riset web",
    )
    state, task = engine.run_task(state, task["tid"])

    assert task["status"] == TASK_FAILED
    assert "TAVILY_API_KEY belum diisi" in task["error"]


# ----------------------------------------------------------------------------- karyawan chat tidak terganggu
def test_karyawan_chat_tetap_lewat_llm(state, monkeypatch):
    dipakai = []

    def fake_chat(messages, model, **kw):
        dipakai.append(model)
        return (
            llm.LLMResult(
                text="Perbaikan selesai.\n\nRingkasan untuk Bos:\n- poin satu\n- poin dua",
                model=model, provider="openrouter", tokens_in=10, tokens_out=5, latency=0.4,
            ),
            [],
        )

    monkeypatch.setattr(llm, "chat_with_fallback", fake_chat)
    monkeypatch.setattr(imageai, "generate_with_fallback", lambda *a, **k: pytest.fail("tidak boleh dipanggil"))
    monkeypatch.setattr(websearch, "search_with_fallback", lambda *a, **k: pytest.fail("tidak boleh dipanggil"))

    state, task = engine.create_task(
        state, title="Perbaiki tombol kirim", brief="Tombol tidak responsif.",
        assignee="sari", deliverable="perbaikan bug",
    )
    state, task = engine.run_task(state, task["tid"])

    assert dipakai and task["status"] == TASK_REVIEW
    assert task["provider_used"] == "openrouter"


def test_obrolan_karyawan_gambar_meminjam_model_chat(state, monkeypatch):
    dipakai = []

    def fake_chat(messages, model, fallbacks=(), role_fallbacks=(), **kw):
        dipakai.append(model)
        return (
            llm.LLMResult(text="Siap, Bos.", model=model, provider="groq", tokens_in=1, tokens_out=1, latency=0.1),
            [],
        )

    monkeypatch.setattr(llm, "chat_with_fallback", fake_chat)
    state, balasan = engine.chat_with_employee(state, "kirana", "Bisa bikin logo?")

    assert balasan == "Siap, Bos."
    assert dipakai == [llm.ALL_FALLBACK[0]], "karyawan gambar harus mengobrol lewat model chat"


def test_revisi_gambar_memakai_prompt_sebelumnya(state, gambar_jadi, monkeypatch):
    monkeypatch.setattr(imageai, "generate_with_fallback", lambda *a, **k: (gambar_jadi, []))
    state, task = engine.create_task(
        state, title="Banner", brief="Gedung kantor saat senja.", assignee="kirana", deliverable="gambar",
    )
    state, task = engine.run_task(state, task["tid"])
    prompt_lama = "prompt versi lama yang harus diingat"
    task["previous_result"] = f"### Prompt akhir\n\n```text\n{prompt_lama}\n```\n"

    assert engine._previous_prompt(task) == prompt_lama
    assert engine._previous_prompt({"previous_result": "tanpa blok kode"}) == ""

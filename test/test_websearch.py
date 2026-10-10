"""Pengujian karyawan Ruang Web Research: Tavily Search API (tanpa jaringan)."""
from __future__ import annotations

import io
import json

import pytest

from office import websearch
from office.models import models_for_kind
from office.quality import evaluate_response

BALASAN = {
    "query": "harga panel surya 2026",
    "answer": "Harga panel surya turun sekitar 12 persen dibanding tahun lalu.",
    "follow_up_questions": ["Merek mana yang paling efisien?"],
    "results": [
        {
            "title": "Laporan Pasar Energi Surya",
            "url": "https://contoh.example/laporan-surya",
            "content": "Harga modul fotovoltaik turun karena kelebihan pasokan pabrik.",
            "score": 0.91,
            "published_date": "2026-09-14",
        },
        {
            "title": "Sumber tanpa tautan",
            "url": "bukan-url",
            "content": "Harus dibuang karena tidak bisa diverifikasi.",
            "score": 0.5,
        },
        {
            "title": "Berita Industri",
            "url": "https://contoh.example/berita",
            "content": "Permintaan instalasi atap rumah naik dua digit.",
            "score": 0.42,
        },
    ],
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture(autouse=True)
def kunci_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-token-uji")


def pasang_balasan(monkeypatch, payload, requests=None):
    def fake_urlopen(req, timeout=None):
        if requests is not None:
            requests.append(req)
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(websearch.urllib.request, "urlopen", fake_urlopen)


# ----------------------------------------------------------------------------- kueri
def test_kueri_dibangun_dari_judul_dan_brief():
    query = websearch.build_query("Riset kompetitor", "  Bandingkan   tiga penyedia lokal ")
    assert query == "Riset kompetitor Bandingkan tiga penyedia lokal"


def test_kueri_panjang_dipotong():
    assert len(websearch.build_query("x" * 900, "", max_chars=120)) == 120


def test_kueri_kosong_ditolak():
    with pytest.raises(websearch.SearchError, match="wajib diisi"):
        websearch.build_query("   ", "")


# ----------------------------------------------------------------------------- pencarian
def test_pencarian_mengembalikan_sumber_bersih(monkeypatch):
    dilihat = []
    pasang_balasan(monkeypatch, BALASAN, dilihat)

    hasil = websearch.search("harga panel surya 2026", model="tavily-search", max_results=6)

    assert dilihat[0].full_url == "https://api.tavily.com/search"
    assert dilihat[0].get_header("Authorization") == "Bearer tvly-token-uji"
    payload = json.loads(dilihat[0].data.decode())
    assert payload["api_key"] == "tvly-token-uji"
    assert payload["search_depth"] == "basic"
    assert payload["include_answer"] is True
    assert payload["max_results"] == 6

    assert hasil.provider == "tavily"
    assert hasil.model == "tavily-search"
    assert hasil["answer"].startswith("Harga panel")
    assert [s["url"] for s in hasil.sources] == [
        "https://contoh.example/laporan-surya",
        "https://contoh.example/berita",
    ], "sumber tanpa URL http(s) wajib dibuang"
    assert hasil.sources[0]["score"] == 0.91
    assert hasil["follow_up"] == ["Merek mana yang paling efisien?"]


def test_pencarian_advanced_memakai_kedalaman_dev(monkeypatch):
    dilihat = []
    pasang_balasan(monkeypatch, BALASAN, dilihat)
    websearch.search("tren ai 2026", model="tavily-search-advanced")
    payload = json.loads(dilihat[0].data.decode())
    assert payload["search_depth"] == "advanced"
    assert payload["include_answer"] == "advanced"


def test_max_results_dijepit(monkeypatch):
    dilihat = []
    pasang_balasan(monkeypatch, BALASAN, dilihat)
    websearch.search("uji", max_results=999)
    assert json.loads(dilihat[0].data.decode())["max_results"] == 20


def test_kunci_kosong_ditolak(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(websearch.SearchError, match="TAVILY_API_KEY belum diisi"):
        websearch.search("uji")


def test_tanpa_hasil_ditolak(monkeypatch):
    pasang_balasan(monkeypatch, {"results": [], "answer": ""})
    with pytest.raises(websearch.SearchError, match="tidak menemukan hasil"):
        websearch.search("kueri yang tidak ada hasilnya")


def test_detail_error_tavily_diterjemahkan(monkeypatch):
    pasang_balasan(monkeypatch, {"results": [], "answer": "", "detail": "kredit habis"})
    with pytest.raises(websearch.SearchError, match="kredit habis"):
        websearch.search("uji")


def test_http_error_diterjemahkan(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"invalid api key"}')
        )

    monkeypatch.setattr(websearch.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(websearch.SearchError, match="Tavily HTTP 401"):
        websearch.search("uji")


def test_balasan_bukan_objek_ditolak(monkeypatch):
    pasang_balasan(monkeypatch, ["bukan", "objek"])
    with pytest.raises(websearch.SearchError, match="tidak berbentuk objek"):
        websearch.search("uji")


# ----------------------------------------------------------------------------- fallback
def test_fallback_pindah_model_pencarian(monkeypatch):
    dicoba = []

    def fake_search(query, model, max_results=6, topic="general"):
        dicoba.append(model)
        if model == "tavily-search-advanced":
            raise websearch.SearchError("Tavily HTTP 429 — terlalu sering")
        return websearch.SearchResult(text="", model=model, provider="tavily", sources=[], query=query)

    monkeypatch.setattr(websearch, "search", fake_search)
    hasil, notes = websearch.search_with_fallback("tren ai", model="tavily-search-advanced")
    assert dicoba[0] == "tavily-search-advanced"
    assert hasil.model == "tavily-search"
    assert any("dipakai cadangan" in n for n in notes)


def test_fallback_berhenti_bila_kunci_salah(monkeypatch):
    dicoba = []

    def fake_search(query, model, max_results=6, topic="general"):
        dicoba.append(model)
        raise websearch.SearchError("Tavily HTTP 401 — kunci tidak sah")

    monkeypatch.setattr(websearch, "search", fake_search)
    with pytest.raises(websearch.SearchError, match="Semua model pencarian gagal"):
        websearch.search_with_fallback("tren ai", model="tavily-search")
    assert dicoba == ["tavily-search"]


# ----------------------------------------------------------------------------- laporan
def test_laporan_lolos_quality_gate(monkeypatch):
    pasang_balasan(monkeypatch, BALASAN)
    hasil = websearch.search("harga panel surya 2026")
    laporan = websearch.build_report(hasil, "Riset harga panel surya", "riset web")
    penilaian = evaluate_response(laporan, "riset web", "riset harga panel surya 2026")
    assert penilaian["passed"], penilaian["issues"]
    assert "https://contoh.example/laporan-surya" in laporan
    assert "Ringkasan untuk Bos" in laporan
    assert "kueri" in laporan.lower()


def test_laporan_tanpa_sumber_tidak_lolos_gate(monkeypatch):
    pasang_balasan(monkeypatch, {"answer": "Ringkasan tanpa tautan.", "results": []})
    hasil = websearch.search("kueri sepi")
    laporan = websearch.build_report(hasil, "Topik sepi", "riset web")
    assert "tanpa tautan" in laporan
    penilaian = evaluate_response(laporan, "riset web", "topik sepi")
    assert any("tautan sumber" in isu for isu in penilaian["issues"])


def test_health_mencerminkan_kunci(monkeypatch):
    sehat = websearch.health()
    assert sehat["key_present"] and sehat["ready"]
    assert sehat["catalog_count"] == len(models_for_kind("search"))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert not websearch.health()["key_present"]


def test_test_key_berhasil_dan_gagal(monkeypatch):
    pasang_balasan(monkeypatch, BALASAN)
    sukses = websearch.test_key()
    assert sukses["ok"] and "sumber ditemukan" in sukses["reply"]
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    gagal = websearch.test_key()
    assert not gagal["ok"] and "belum diisi" in gagal["error"]

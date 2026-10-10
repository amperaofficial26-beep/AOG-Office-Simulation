"""Pengujian karyawan Ruang AI Image: Cloudflare Workers AI / FLUX.1.

Semua pengujian hermetic — jaringan dipalsukan lewat monkeypatch dan berkas
gambar ditulis ke direktori sementara.
"""
from __future__ import annotations

import base64
import io
import json

import pytest

from office import config, imageai
from office.models import models_for_kind
from office.quality import evaluate_response

# PNG 1x1 valid (dipakai sebagai balasan palsu Workers AI).
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PNG_BYTES = base64.b64decode(PNG_B64)
MODEL = "@cf/black-forest-labs/flux-1-schnell"


class FakeResponse(io.BytesIO):
    """Objek minimum yang diterima `with urllib.request.urlopen(...) as resp`."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture(autouse=True)
def lingkungan(monkeypatch, tmp_path):
    """Kunci Cloudflare terisi, cache mati, aset masuk direktori sementara."""
    import office.state as state_mod

    monkeypatch.setattr(state_mod, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(state_mod, "save_cache", lambda *a, **k: None)
    monkeypatch.setattr(config, "ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-token-uji")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "akun-uji-123")
    return tmp_path


def pasang_balasan(monkeypatch, payload, requests=None):
    """Palsukan urlopen supaya membalas payload JSON tetap."""

    def fake_urlopen(req, timeout=None):
        if requests is not None:
            requests.append(req)
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(imageai.urllib.request, "urlopen", fake_urlopen)


# ----------------------------------------------------------------------------- kunci & akun
def test_kunci_kosong_ditolak(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_KEY", raising=False)
    with pytest.raises(imageai.ImageError, match="CLOUDFLARE_API_KEY belum diisi"):
        imageai.generate("kucing di meja kantor", model=MODEL)


def test_account_id_dipakai_dari_secret(monkeypatch):
    def gagal(*a, **k):  # pragma: no cover - tidak boleh dipanggil
        raise AssertionError("tidak boleh menembak jaringan")

    monkeypatch.setattr(imageai.urllib.request, "urlopen", gagal)
    assert imageai.resolve_account_id() == "akun-uji-123"


def test_account_id_dicari_otomatis(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    dilihat = []
    pasang_balasan(monkeypatch, {"result": [{"id": "akun-otomatis-999", "name": "Ampera"}]}, dilihat)
    assert imageai.resolve_account_id() == "akun-otomatis-999"
    assert "/accounts" in dilihat[0].full_url


def test_account_id_otomatis_gagal_bila_tidak_ada_akun(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    pasang_balasan(monkeypatch, {"result": []})
    with pytest.raises(imageai.ImageError, match="CLOUDFLARE_ACCOUNT_ID"):
        imageai.resolve_account_id()


# ----------------------------------------------------------------------------- langkah & prompt
@pytest.mark.parametrize(
    "model, langkah, diharapkan",
    [
        (MODEL, None, 4),
        (MODEL, 1, 4),  # di bawah minimum FLUX.1 Schnell
        (MODEL, 99, 8),  # di atas maksimum
        ("@cf/black-forest-labs/flux-1-dev", None, 14),
        ("@cf/bytedance/stable-diffusion-xl-lightning", None, 1),
        ("model-tak-dikenal", 3, 3),
    ],
)
def test_langkah_render_dijepit_ke_rentang_model(model, langkah, diharapkan):
    assert imageai._clamp_steps(model, langkah) == diharapkan


def test_prompt_dibangun_dari_brief_dan_revisi():
    prompt = imageai.build_image_prompt(
        "Banner peluncuran",
        "Gedung kantor   modern saat senja,\nwarna oranye.",
        revision_note="  Kurangi   saturasi ",
    )
    assert "Banner peluncuran" in prompt
    assert "Gedung kantor modern saat senja" in prompt
    assert "Kurangi saturasi" in prompt
    assert len(prompt) <= imageai.MAX_PROMPT_CHARS


def test_prompt_panjang_dipotong():
    prompt = imageai.build_image_prompt("Judul", "x" * 5000)
    assert len(prompt) == imageai.MAX_PROMPT_CHARS


# ----------------------------------------------------------------------------- generate
def test_generate_menyimpan_png_dan_mencatat_metadata(lingkungan, monkeypatch):
    dilihat = []
    pasang_balasan(monkeypatch, {"result": {"image": PNG_B64}}, dilihat)

    result = imageai.generate("maskot kantor, latar polos", model=MODEL, slug="TGS-uji")

    assert dilihat[0].full_url.endswith(f"/accounts/akun-uji-123/ai/run/{MODEL}")
    assert json.loads(dilihat[0].data.decode())["prompt"].startswith("maskot kantor")
    assert dilihat[0].get_header("Authorization") == "Bearer cf-token-uji"
    assert result.file.startswith(str(lingkungan / "assets"))
    with open(result.file, "rb") as fh:
        assert fh.read() == PNG_BYTES
    assert result.model == MODEL
    assert result.provider == "cloudflare"
    assert result["bytes"] == len(PNG_BYTES)


def test_generate_menerima_data_uri(monkeypatch, lingkungan):
    pasang_balasan(monkeypatch, {"result": {"image": f"data:image/png;base64,{PNG_B64}"}})
    result = imageai.generate("ikon", model=MODEL)
    with open(result.file, "rb") as fh:
        assert fh.read() == PNG_BYTES


def test_generate_menerima_balasan_string_polos(monkeypatch, lingkungan):
    pasang_balasan(monkeypatch, {"result": PNG_B64})
    assert imageai.generate("ikon", model=MODEL)["bytes"] == len(PNG_BYTES)


def test_generate_tanpa_data_gambar_ditolak(monkeypatch):
    pasang_balasan(monkeypatch, {"result": {}})
    with pytest.raises(imageai.ImageError, match="tanpa data gambar"):
        imageai.generate("ikon", model=MODEL)


def test_generate_base64_rusak_ditolak(monkeypatch):
    pasang_balasan(monkeypatch, {"result": {"image": "bukan-base64!!"}})
    with pytest.raises(imageai.ImageError, match="tidak valid"):
        imageai.generate("ikon", model=MODEL)


def test_error_cloudflare_diterjemahkan(monkeypatch):
    pasang_balasan(monkeypatch, {"success": False, "errors": [{"code": 7003, "message": "kuota habis"}]})
    with pytest.raises(imageai.ImageError, match="kuota habis"):
        imageai.generate("ikon", model=MODEL)


def test_balasan_bukan_json_ditolak(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return FakeResponse(b"<html>gateway error</html>")

    monkeypatch.setattr(imageai.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(imageai.ImageError, match="bukan JSON"):
        imageai.generate("ikon", model=MODEL)


# ----------------------------------------------------------------------------- fallback
def test_fallback_pindah_ke_model_gambar_lain(monkeypatch):
    dicoba = []

    def fake_generate(prompt, model, steps=None, slug="gambar", account_id=""):
        dicoba.append(model)
        if model == MODEL:
            raise imageai.ImageError("Cloudflare HTTP 503 — model sibuk")
        return imageai.ImageResult(text="", model=model, provider="cloudflare", file="", files=[], bytes=1)

    monkeypatch.setattr(imageai, "generate", fake_generate)
    result, notes = imageai.generate_with_fallback("maskot", model=MODEL)
    assert dicoba[0] == MODEL and len(dicoba) >= 2
    assert result.model != MODEL
    assert any("dipakai cadangan" in n for n in notes)


def test_fallback_berhenti_bila_kunci_salah(monkeypatch):
    dicoba = []

    def fake_generate(prompt, model, steps=None, slug="gambar", account_id=""):
        dicoba.append(model)
        raise imageai.ImageError("Cloudflare HTTP 403 — token tidak sah")

    monkeypatch.setattr(imageai, "generate", fake_generate)
    with pytest.raises(imageai.ImageError, match="Semua model gambar gagal"):
        imageai.generate_with_fallback("maskot", model=MODEL)
    assert dicoba == [MODEL], "provider yang kuncinya salah tidak boleh dicoba berulang"


def test_fallback_tanpa_model_gambar(monkeypatch):
    monkeypatch.setattr(imageai, "models_for_kind", lambda kind: {})
    with pytest.raises(imageai.ImageError, match="Tidak ada model gambar"):
        imageai.generate_with_fallback("maskot", model="model-hantu")


# ----------------------------------------------------------------------------- laporan & diagnostik
def test_lolos_quality_gate_gambar(monkeypatch, lingkungan):
    pasang_balasan(monkeypatch, {"result": {"image": PNG_B64}})
    result = imageai.generate("banner peluncuran aplikasi kantor", model=MODEL)
    laporan = imageai.build_report(result, "Banner peluncuran aplikasi kantor", "gambar")
    penilaian = evaluate_response(laporan, "gambar", "banner peluncuran aplikasi kantor")
    assert penilaian["passed"], penilaian["issues"]
    assert "Ringkasan untuk Bos" in laporan
    assert "```text" in laporan


def test_health_mencerminkan_kunci_dan_akun(monkeypatch):
    sehat = imageai.health()
    assert sehat["key_present"] and sehat["ready"]
    assert sehat["account_id"] == "akun-uji-123"
    assert sehat["catalog_count"] == len(models_for_kind("image"))
    monkeypatch.delenv("CLOUDFLARE_API_KEY", raising=False)
    assert not imageai.health()["key_present"]


def test_test_key_berhasil(monkeypatch, lingkungan):
    pasang_balasan(monkeypatch, {"result": {"image": PNG_B64}})
    hasil = imageai.test_key()
    assert hasil["ok"] and "tersimpan" in hasil["reply"]
    assert hasil["file"].endswith(".png")


def test_test_key_gagal_tanpa_kunci(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_KEY", raising=False)
    hasil = imageai.test_key()
    assert not hasil["ok"]
    assert "belum diisi" in hasil["error"]

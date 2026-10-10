"""Pengujian penyimpanan secrets.toml dari UI."""
from __future__ import annotations

import pytest

from office import config


@pytest.fixture
def secrets_tmp(tmp_path, monkeypatch):
    target = tmp_path / "secrets.toml"
    monkeypatch.setattr(config, "SECRETS_FILE", str(target))
    return target


def test_tulis_dan_baca_roundtrip(secrets_tmp):
    written = config.write_secrets_file(
        {"GITHUB_TOKEN": "github_pat_abc123", "GROQ_API_KEY": ""}
    )
    assert written == ["GITHUB_TOKEN"]  # nilai kosong tidak ditulis
    data = config.read_secrets_file()
    assert data["GITHUB_TOKEN"] == "github_pat_abc123"


def test_mempertahankan_kunci_lama(secrets_tmp):
    config.write_secrets_file({"GROQ_API_KEY": "gsk_1", "AION_API_KEY": "aion_1"})
    config.write_secrets_file({"GITHUB_TOKEN": "github_pat_x"})
    data = config.read_secrets_file()
    assert data == {
        "GROQ_API_KEY": "gsk_1",
        "AION_API_KEY": "aion_1",
        "GITHUB_TOKEN": "github_pat_x",
    }


def test_karakter_khusus_diescape(secrets_tmp):
    config.write_secrets_file({"GITHUB_TOKEN": 'tok"en\\dengan"kutip'})
    data = config.read_secrets_file()
    assert data["GITHUB_TOKEN"] == 'tok"en\\dengan"kutip'


def test_tanpa_nilai_tidak_menyentuh_berkas(secrets_tmp):
    assert config.write_secrets_file({"GITHUB_TOKEN": "   "}) == []
    assert not secrets_tmp.exists()


def test_berkas_rusak_dibaca_kosong(secrets_tmp):
    secrets_tmp.write_text("ini bukan toml = = =")
    assert config.read_secrets_file() == {}


def test_kunci_gambar_dan_pencarian_terdaftar(secrets_tmp):
    """Kunci Cloudflare (FLUX.1) dan Tavily ditulis utuh ke secrets.toml."""
    written = config.write_secrets_file(
        {
            "CLOUDFLARE_API_KEY": "cf-token-123",
            "CLOUDFLARE_ACCOUNT_ID": "akun-abc",
            "TAVILY_API_KEY": "tvly-xyz",
            "KUNCI_KOSONG": "   ",
        }
    )
    assert set(written) == {"CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "TAVILY_API_KEY"}
    data = config.read_secrets_file()
    assert data["CLOUDFLARE_API_KEY"] == "cf-token-123"
    assert data["CLOUDFLARE_ACCOUNT_ID"] == "akun-abc"
    assert data["TAVILY_API_KEY"] == "tvly-xyz"
    assert "KUNCI_KOSONG" not in data


def test_nama_alternatif_kunci_diterima(monkeypatch):
    """Nama lama/alias tetap dikenali supaya secrets lama tidak perlu ditulis ulang."""
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-dari-nama-utama")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-dari-nama-utama")
    assert config.get_key("cloudflare") == "cf-dari-nama-utama"
    assert config.get_account_id() == ""
    assert config.has_key("cloudflare") and config.has_key("tavily")

    monkeypatch.delenv("CLOUDFLARE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("CF_API_TOKEN", "cf-dari-alias")
    monkeypatch.setenv("TAVILY_KEY", "tvly-dari-alias")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "akun-dari-env")
    assert config.get_key("cloudflare") == "cf-dari-alias"
    assert config.get_key("tavily") == "tvly-dari-alias"
    assert config.get_account_id() == "akun-dari-env"


def test_provider_punya_jenis_keluaran():
    assert config.provider_kind("groq") == config.KIND_CHAT
    assert config.provider_kind("cloudflare") == config.KIND_IMAGE
    assert config.provider_kind("tavily") == config.KIND_SEARCH
    assert config.provider_kind("provider-tidak-ada") == config.KIND_CHAT
    assert config.CHAT_PROVIDER_ORDER == ["groq", "openrouter", "aion"]
    assert "cloudflare" in config.PROVIDER_ORDER and "tavily" in config.PROVIDER_ORDER

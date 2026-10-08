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

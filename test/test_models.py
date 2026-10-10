"""Pengujian katalog model: integritas katalog, migrasi model mati, dan probe live.

Semua pengujian hermetic — jaringan dan cache dimatikan lewat monkeypatch.
"""
from __future__ import annotations

import pytest

from office import models
from office.config import PROVIDERS


@pytest.fixture(autouse=True)
def tanpa_cache(monkeypatch):
    """Probe tidak boleh menyentuh cache atau jaringan saat diuji."""
    import office.state as state_mod

    monkeypatch.setattr(state_mod, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(state_mod, "save_cache", lambda *a, **k: None)


# ----------------------------------------------------------------------------- integritas katalog
def test_katalog_model_valid():
    assert len(models.MODELS) >= 15
    for mid, meta in models.MODELS.items():
        assert meta["provider"] in PROVIDERS, f"{mid}: provider tidak dikenal"
        assert meta["label"], f"{mid}: label kosong"
        assert isinstance(meta["context"], int) and meta["context"] > 0, f"{mid}: konteks tidak valid"
        assert "reasoning" in meta and "tools" in meta, f"{mid}: kemampuan tidak lengkap"


def test_model_retired_tidak_bertabrakan_dengan_katalog():
    for mid in models.RETIRED:
        assert mid not in models.MODELS, f"{mid} ada di RETIRED dan MODELS sekaligus"


def test_semua_pengganti_fallback_ada_di_katalog():
    for role, chain in models.ROLE_FALLBACK.items():
        for mid in chain:
            assert mid in models.MODELS, f"fallback {role}: {mid} tidak ada di katalog"
    for mid in models.ALL_FALLBACK:
        assert mid in models.MODELS, f"fallback global {mid} tidak ada di katalog"
    assert models.ALL_FALLBACK[0] in models.MODELS


# ----------------------------------------------------------------------------- migrasi
def test_migrate_model_hidup_tetap():
    assert models.migrate_model("openai/gpt-oss-120b") == "openai/gpt-oss-120b"


@pytest.mark.parametrize(
    "lama, baru",
    [
        ("llama-3.3-70b-versatile", "openai/gpt-oss-120b"),
        ("qwen/qwen3-32b", "qwen/qwen3.6-27b"),
    ],
)
def test_migrate_model_mati_ke_pengganti(lama, baru):
    assert lama in models.RETIRED
    assert models.migrate_model(lama) == baru
    assert baru in models.MODELS


def test_migrate_model_expired_tanpa_pengganti_jatuh_ke_fallback():
    # Tanda expired tanpa "→" tidak punya pengganti eksplisit.
    assert "→" not in models.RETIRED["z-ai/glm-4.5"]
    assert models.migrate_model("z-ai/glm-4.5") == models.ALL_FALLBACK[0]


def test_migrate_model_tak_dikenal_jatuh_ke_fallback():
    assert models.migrate_model("model-ngawur-tidak-ada") == models.ALL_FALLBACK[0]


def test_is_retired():
    assert models.is_retired("llama-3.1-8b-instant")
    assert not models.is_retired("openai/gpt-oss-120b")


# ----------------------------------------------------------------------------- utilitas katalog
def test_models_for_memfilter_per_provider():
    groq = models.models_for("groq")
    assert groq and all(m["provider"] == "groq" for m in groq.values())
    gabungan: set[str] = set()
    for provider in PROVIDERS:
        punya = models.models_for(provider)
        assert all(m["provider"] == provider for m in punya.values())
        gabungan |= set(punya)
    assert gabungan == set(models.MODELS), "ada model yang tidak tercakup provider mana pun"


def test_model_label_dan_provider_of():
    assert models.model_label("openai/gpt-oss-120b") == models.MODELS["openai/gpt-oss-120b"]["label"]
    assert models.model_label("model-ngawur") == "model-ngawur"
    assert models.provider_of("aion-labs/aion-3.5") == "aion"
    assert models.provider_of("model-ngawur") == ""


# ----------------------------------------------------------------------------- jenis keluaran
def test_modality_model_chat_gambar_dan_pencarian():
    assert models.modality_of("openai/gpt-oss-120b") == "chat"
    assert models.modality_of("@cf/black-forest-labs/flux-1-schnell") == "image"
    assert models.modality_of("tavily-search") == "search"
    assert models.modality_of("model-ngawur") == "chat"


def test_models_for_kind_memisahkan_katalog():
    gambar = models.models_for_kind("image")
    cari = models.models_for_kind("search")
    assert gambar and all(m["provider"] == "cloudflare" for m in gambar.values())
    assert cari and all(m["provider"] == "tavily" for m in cari.values())
    assert not set(gambar) & set(cari)
    assert set(models.models_for_kind("chat")) | set(gambar) | set(cari) == set(models.MODELS)


def test_provider_baru_punya_katalog_dan_fallback_role():
    assert models.models_for("cloudflare"), "Cloudflare belum punya model di katalog"
    assert models.models_for("tavily"), "Tavily belum punya model di katalog"
    for role in ("image_artist", "web_search"):
        assert models.ROLE_FALLBACK[role], f"role {role} tidak punya rantai fallback"
        for mid in models.ROLE_FALLBACK[role]:
            assert mid in models.MODELS


def test_probe_provider_tanpa_katalog_publik_dilewati(monkeypatch):
    def tidak_dipanggil(*a, **k):  # pragma: no cover - harus dilewati
        raise AssertionError("provider tanpa katalog tidak boleh menembak jaringan")

    monkeypatch.setattr(models, "_fetch_json", tidak_dipanggil)
    res = models.probe("tavily", use_cache=False)
    assert res["skipped"] and not res["ok"]
    assert res["live"] == sorted(models.models_for("tavily"))
    assert res["dead"] == []


def test_probe_cloudflare_tanpa_kunci_dilewati(monkeypatch):
    monkeypatch.setattr(models, "get_key", lambda provider: "")
    monkeypatch.setattr(models, "get_account_id", lambda: "")
    res = models.probe("cloudflare", use_cache=False)
    assert res["skipped"]
    assert "CLOUDFLARE_ACCOUNT_ID" in res["error"]
    assert res["live"] == sorted(models.models_for("cloudflare"))


def test_probe_cloudflare_memakai_katalog_live(monkeypatch):
    monkeypatch.setattr(models, "get_key", lambda provider: "cf-token")
    monkeypatch.setattr(models, "get_account_id", lambda: "akun-123")
    dilihat = []

    def katalog(url, key="", timeout=20):
        dilihat.append(url)
        return {"result": [{"name": "@cf/black-forest-labs/flux-1-schnell"}]}

    monkeypatch.setattr(models, "_fetch_json", katalog)
    res = models.probe("cloudflare", use_cache=False)
    assert res["ok"] and "@cf/black-forest-labs/flux-1-schnell" in res["live"]
    assert "@cf/black-forest-labs/flux-1-dev" in res["dead"]
    assert "/accounts/akun-123/ai/models/search" in dilihat[0]


def test_normalise_ids_groq_dan_openrouter():
    groq = models._normalise_ids({"data": [{"id": "openai/gpt-oss-120b"}]}, "groq")
    assert "openai/gpt-oss-120b" in groq
    orr = models._normalise_ids(
        {"data": [{"id": "nvidia/nemotron-3-ultra-550b-a55b:free"}]}, "openrouter"
    )
    assert "nvidia/nemotron-3-ultra-550b-a55b:free" in orr
    assert "nvidia/nemotron-3-ultra-550b-a55b" in orr  # varian tanpa :free
    assert models._normalise_ids([], "groq") == set()


# ----------------------------------------------------------------------------- probe live
def test_probe_memisahkan_live_dan_dead(monkeypatch):
    hidup = "openai/gpt-oss-120b"
    mati = "groq/compound-mini"
    monkeypatch.setattr(
        models, "_fetch_json", lambda *a, **k: {"data": [{"id": hidup}]}
    )
    res = models.probe("groq", use_cache=False)
    assert res["ok"] and hidup in res["live"] and mati in res["dead"]


def test_probe_gagal_menganggap_katalog_lokal(monkeypatch):
    def gagal(*a, **k):
        raise OSError("jaringan mati")

    monkeypatch.setattr(models, "_fetch_json", gagal)
    res = models.probe("aion", use_cache=False)
    assert not res["ok"]
    assert "OSError" in res["error"]
    # Tidak bisa diverifikasi → semua model provider dianggap sesuai katalog lokal.
    assert res["live"] == sorted(models.models_for("aion"))


def test_probe_all_dan_live_models(monkeypatch):
    monkeypatch.setattr(models, "_fetch_json", lambda *a, **k: {"data": []})
    semua = models.probe_all(use_cache=False)
    assert set(semua) == set(PROVIDERS)
    status = models.live_models(use_cache=False)
    assert set(status) == set(models.MODELS)

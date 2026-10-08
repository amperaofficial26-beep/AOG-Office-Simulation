"""Pengujian integrasi GitHub (memakai API publik, dilewati bila jaringan mati)."""
from __future__ import annotations

import pytest

from office import github as gh

OWNER = "amperaofficial26-beep"
REPO = "Ampera-Scribe"


@pytest.fixture(autouse=True)
def _bersihkan_cache():
    from office.state import clear_cache

    clear_cache("gh::")
    yield
    clear_cache("gh::")


def _lewati_bila_terbatas(exc: gh.GitHubError) -> None:
    """GitHub membatasi 60 permintaan/jam tanpa token; itu bukan kegagalan kode."""
    pesan = str(exc)
    if "403" in pesan or "rate limit" in pesan.lower():
        pytest.skip(f"GitHub membatasi permintaan tanpa token: {pesan[:120]}")
    pytest.skip(f"GitHub tidak terjangkau: {pesan[:120]}")


def test_repo_bos_terbaca_tanpa_token():
    try:
        rows = gh.list_repos(OWNER, limit=100)
    except gh.GitHubError as exc:
        _lewati_bila_terbatas(exc)
    names = {r["name"] for r in rows}
    assert "Ampera-Scribe" in names
    assert "Ampera-Web-Design" in names
    assert "Room-Chat-Ampera-Group" in names
    for row in rows:
        assert row["full_name"].startswith(f"{OWNER}/")
        assert row["default_branch"]


def test_konteks_repo_tersusun_rapi():
    try:
        text = gh.build_context(OWNER, REPO, max_chars=4000)
    except gh.GitHubError as exc:
        _lewati_bila_terbatas(exc)
    if "tidak tersedia" in text:
        _lewati_bila_terbatas(gh.GitHubError(text))
    assert "REPO:" in text
    assert OWNER in text
    assert len(text) <= 4000


def test_commit_dan_pohon_berkas():
    try:
        commits = gh.commits(OWNER, REPO, limit=5)
        tree = gh.file_tree(OWNER, REPO, limit=50)
    except gh.GitHubError as exc:
        _lewati_bila_terbatas(exc)
    if commits:
        assert len(commits[0]["sha"]) == 7
        assert commits[0]["message"]
    assert tree == [] or "path" in tree[0]


def test_rate_limit_terbaca():
    try:
        rl = gh.rate_limit()
    except gh.GitHubError as exc:
        _lewati_bila_terbatas(exc)
    assert rl["limit"] > 0
    assert rl["remaining"] >= 0


def test_baca_berkas_404_menjadi_kosong():
    try:
        assert gh.read_file(OWNER, REPO, "berkas-yang-tidak-ada-xyz.py") == ""
    except gh.GitHubError:
        pytest.skip("GitHub tidak terjangkau")


def test_tulis_tanpa_token_ditolak_dengan_pesan_jelas():
    if gh.has_token():
        pytest.skip("GITHUB_TOKEN terisi, lewati uji penolakan")
    with pytest.raises(gh.GitHubError) as info:
        gh.create_issue(OWNER, REPO, "uji", "isi")
    assert "GITHUB_TOKEN" in str(info.value)


def test_konteks_repo_gagal_ditangani_rapi(monkeypatch):
    def boom(*a, **k):
        raise gh.GitHubError("HTTP 404")

    monkeypatch.setattr(gh, "repo_detail", boom)
    text = gh.build_context("tidak-ada", "tidak-ada")
    assert "tidak tersedia" in text

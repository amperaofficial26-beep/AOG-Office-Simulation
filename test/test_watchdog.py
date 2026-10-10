"""Pengujian pengawas aplikasi Streamlit: deteksi tidur/mati, ambang, jeda, dan reboot via GitHub."""
from __future__ import annotations

import http.server
import socketserver
import threading

import pytest

from office import apps as apps_mod
from office import watchdog


@pytest.fixture
def paths(tmp_path, monkeypatch):
    from office import config, state as state_mod

    cfg_path = str(tmp_path / "config.json")
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(state_mod, "CONFIG_FILE", cfg_path)
    wd_path = str(tmp_path / "watchdog.json")
    monkeypatch.setattr(watchdog, "WATCHDOG_FILE", wd_path)
    return wd_path


@pytest.fixture
def one_app(paths, monkeypatch):
    """Satu aplikasi terdaftar, token GitHub dianggap ada, reboot dicatat (tanpa API sungguhan)."""
    monkeypatch.setattr(
        apps_mod,
        "apps",
        lambda: [{"name": "Ampera Scribe", "url": "https://scribe.test/", "repo": "Ampera-Scribe", "owner": ""}],
    )
    monkeypatch.setattr(watchdog, "get_key", lambda provider: "token-palsu")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(watchdog, "reboot_repo", lambda owner, repo, branch="": calls.append((owner, repo)) or "abc1234")
    return calls


def _set_status(monkeypatch, ok: bool, sleeping: bool = False):
    result = {"ok": ok, "status": "hidup" if ok else ("tidur" if sleeping else "tidak terjangkau"),
              "code": 200 if ok else 0, "latency_ms": 5, "sleeping": sleeping, "error": "" if ok else "down"}
    monkeypatch.setattr(apps_mod, "check_url", lambda url: result)


@pytest.fixture(scope="module")
def server():
    """Server HTTP lokal yang meniru halaman hidup, halaman tidur Streamlit, dan error."""

    class Handler(http.server.BaseHTTPRequestHandler, socketserver.StreamRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/hidup":
                code, body = 200, b"<html><title>Streamlit</title><div id='root'></div></html>"
            elif self.path == "/tidur":
                code = 200
                body = (b"<html><body>App state: Zzzz. This app has gone to sleep due to inactivity. "
                        b"To wake the app up, click &quot;Yes, get this app back up!&quot;</body></html>")
            else:
                code, body = 500, b"server error"
            self.send_response(code)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_check_url_membedakan_hidup_tidur_dan_error(server):
    hidup = apps_mod.check_url(server + "/hidup")
    tidur = apps_mod.check_url(server + "/tidur")
    rusak = apps_mod.check_url(server + "/error")
    assert hidup["ok"] and hidup["status"] == "hidup" and not hidup["sleeping"]
    assert not tidur["ok"] and tidur["sleeping"] and tidur["status"] == "tidur"
    assert not rusak["ok"] and not rusak["sleeping"] and rusak["code"] == 500
    assert watchdog.classify(hidup) == "hidup"
    assert watchdog.classify(tidur) == "tidur"
    assert watchdog.classify(rusak) == "mati"


def test_reboot_hanya_setelah_ambang_gagal_berturut(one_app, monkeypatch):
    _set_status(monkeypatch, ok=False)
    watchdog.run_cycle()
    assert one_app == []  # kegagalan pertama belum memicu reboot
    watchdog.run_cycle()
    assert one_app == [("amperaofficial26-beep", "Ampera-Scribe")]


def test_jeda_cooldown_mencegah_reboot_berulang(one_app, monkeypatch):
    _set_status(monkeypatch, ok=False)
    for _ in range(4):
        watchdog.run_cycle()
    assert len(one_app) == 1  # siklus ke-3 dan ke-4 masih dalam jeda 30 menit


def test_status_hidup_mereset_hitungan_gagal(one_app, monkeypatch):
    _set_status(monkeypatch, ok=False)
    watchdog.run_cycle()
    _set_status(monkeypatch, ok=True)
    watchdog.run_cycle()
    _set_status(monkeypatch, ok=False)
    watchdog.run_cycle()
    assert one_app == []  # tidak pernah dua gagal berturut-turut
    snap = watchdog.snapshot()
    assert list(snap["apps"].values())[0]["fail_streak"] == 1


def test_aplikasi_tidur_juga_direboot(one_app, monkeypatch):
    _set_status(monkeypatch, ok=False, sleeping=True)
    watchdog.run_cycle()
    watchdog.run_cycle()
    assert one_app == [("amperaofficial26-beep", "Ampera-Scribe")]
    assert list(watchdog.snapshot()["apps"].values())[0]["status"] == "tidur"


def test_batas_reboot_harian(one_app, monkeypatch, paths):
    from office import config, state as state_mod

    monkeypatch.setattr(watchdog, "settings", lambda: {**watchdog.DEFAULT_SETTINGS, "cooldown_min": 0,
                                                       "max_reboots_per_day": 1, "fail_threshold": 1})
    _set_status(monkeypatch, ok=False)
    watchdog.run_cycle()
    watchdog.run_cycle()
    assert len(one_app) == 1
    events = watchdog.snapshot()["events"]
    assert any("batas reboot harian" in e["message"] for e in events)


def test_tanpa_token_tetap_mengawasi_dan_mencatat(paths, monkeypatch):
    monkeypatch.setattr(
        apps_mod, "apps",
        lambda: [{"name": "Web Design", "url": "https://web.test/", "repo": "Ampera-Web-Design", "owner": ""}],
    )
    monkeypatch.setattr(watchdog, "get_key", lambda provider: "")
    _set_status(monkeypatch, ok=False)
    watchdog.run_cycle()
    watchdog.run_cycle()
    events = watchdog.snapshot()["events"]
    assert any("GITHUB_TOKEN belum diisi" in e["message"] for e in events)


def test_reboot_repo_memakai_urutan_api_git_yang_benar(monkeypatch):
    calls = []
    responses = {
        ("GET", "/repos/o/r"): {"default_branch": "main"},
        ("GET", "/repos/o/r/git/ref/heads/main"): {"object": {"sha": "HEAD1"}},
        ("GET", "/repos/o/r/git/commits/HEAD1"): {"tree": {"sha": "TREE1"}},
        ("POST", "/repos/o/r/git/commits"): {"sha": "NEW2"},
        ("PATCH", "/repos/o/r/git/refs/heads/main"): {"ref": "refs/heads/main"},
    }

    def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        return responses[(method, path)]

    monkeypatch.setattr(watchdog, "_api", fake_api)
    assert watchdog.reboot_repo("o", "r") == "NEW2"
    assert [c[:2] for c in calls] == [k for k in responses]
    post_payload = calls[3][2]
    assert post_payload["tree"] == "TREE1" and post_payload["parents"] == ["HEAD1"]
    assert "reboot" in post_payload["message"].lower()
    assert calls[4][2] == {"sha": "NEW2", "force": False}


def test_split_repo_dan_target(paths, monkeypatch):
    assert watchdog.split_repo("Ampera-Scribe", "amperaofficial26-beep") == ("amperaofficial26-beep", "Ampera-Scribe")
    assert watchdog.split_repo("alice/proyek", "x") == ("alice", "proyek")
    monkeypatch.setattr(apps_mod, "load_config", lambda: {"streamlit_apps": [
        {"name": "Scribe", "url": "", "repo": "Ampera-Scribe"},  # URL kosong -> diisi dari daftar bawaan
        {"name": "Tanpa repo", "url": "https://x.test/", "repo": ""},
    ]})
    targets = watchdog.targets()
    assert len(targets) == 1
    assert targets[0]["url"] == "https://ampera-scribe.streamlit.app/"
    assert targets[0]["repo"] == "Ampera-Scribe"


def test_ensure_running_hanya_satu_thread(paths, monkeypatch):
    seen = []
    monkeypatch.setattr(watchdog, "run_cycle", lambda force=False: seen.append(1))
    monkeypatch.setattr(watchdog, "_THREAD", None)
    watchdog._STOP.clear()
    try:
        assert watchdog.ensure_running()
        first = watchdog._THREAD
        assert watchdog.ensure_running()
        assert watchdog._THREAD is first
        for _ in range(50):
            if seen:
                break
            threading.Event().wait(0.02)
        assert seen  # siklus pertama berjalan di latar belakang
    finally:
        watchdog._STOP.set()
        watchdog._STOP.clear()

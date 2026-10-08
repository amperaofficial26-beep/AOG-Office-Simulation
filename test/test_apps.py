"""Pengujian registri aplikasi Streamlit + pemeriksaan status URL."""
from __future__ import annotations

import http.server
import socketserver
import threading

import pytest

from office import apps as apps_mod


@pytest.fixture
def config_tmp(tmp_path, monkeypatch):
    from office import config, state as state_mod

    path = str(tmp_path / "config.json")
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    monkeypatch.setattr(state_mod, "CONFIG_FILE", path)
    return path


@pytest.fixture(scope="module")
def server():
    """Server HTTP lokal untuk menguji pemeriksaan status."""

    class Handler(http.server.BaseHTTPRequestHandler, socketserver.StreamRequestHandler):
        # StreamRequestHandler menyediakan rfile/wfile yang dipakai protokol HTTP
        def do_GET(self):  # noqa: N802 - nama wajib dari BaseHTTPRequestHandler
            if self.path == "/hidup":
                body = b"<html>streamlit app</html>"
                self.send_response(200)
            elif self.path == "/error":
                self.send_response(500)
                body = b"server error"
            else:
                self.send_response(404)
                body = b"not found"
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # senyapkan log
            return

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_daftar_awal_berisi_aplikasi_bos(config_tmp):
    rows = apps_mod.apps()
    names = " ".join(r["name"] for r in rows)
    assert "Ampera" in names
    assert len(rows) >= 3


def test_tambah_dan_hapus_aplikasi(config_tmp):
    rows = apps_mod.add_app("Uji App", "https://contoh.streamlit.app", "repo-uji")
    assert any(r["name"] == "Uji App" for r in rows)
    index = next(i for i, r in enumerate(rows) if r["name"] == "Uji App")
    rows = apps_mod.remove_app(index)
    assert not any(r["name"] == "Uji App" for r in rows)


def test_url_hidup_terdeteksi(config_tmp, server):
    result = apps_mod.check_url(f"{server}/hidup")
    assert result["ok"] is True
    assert result["status"] == "hidup"
    assert result["code"] == 200
    assert result["streamlit_like"] is True


def test_url_error_terdeteksi(config_tmp, server):
    result = apps_mod.check_url(f"{server}/error")
    assert result["ok"] is False
    assert "500" in result["status"]


def test_url_kosong_dan_tanpa_skema(config_tmp):
    assert apps_mod.check_url("")["status"] == "tanpa URL"
    # tanpa http:// tetap diperiksa (diberi https:// otomatis)
    result = apps_mod.check_url("127.0.0.1:1/tidak-ada")
    assert result["ok"] is False


def test_cek_semua_menyimpan_status(config_tmp, server):
    apps_mod.save_apps(
        [
            {"name": "Hidup", "url": f"{server}/hidup", "repo": "a", "owner": "sari"},
            {"name": "Mati", "url": f"{server}/error", "repo": "b", "owner": "nadia"},
            {"name": "Kosong", "url": "", "repo": "c", "owner": ""},
        ]
    )
    rows = apps_mod.check_all()
    assert rows[0]["status"] == "hidup"
    assert "500" in rows[1]["status"]
    assert rows[2]["status"] == "tanpa URL"
    s = apps_mod.summary(rows)
    assert s["total"] == 3
    assert s["hidup"] == 1
    assert s["mati"] == 1
    assert s["tanpa_url"] == 1
    assert s["belum_dicek"] == 0


def test_ringkasan_menghitung_belum_dicek(config_tmp):
    apps_mod.save_apps([{"name": "A", "url": "", "repo": "", "owner": "", "status": "belum dicek"}])
    assert apps_mod.summary()["belum_dicek"] == 1

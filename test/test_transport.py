"""Verifikasi transport nyata lewat server HTTP lokal (bukan jaringan publik).

Pengujian lain memalsukan `urlopen`; berkas ini menjalankan server HTTP sungguhan
di 127.0.0.1 supaya pembentukan URL, header Authorization, dan isi payload untuk
Cloudflare Workers AI (FLUX.1) serta Tavily benar-benar terbukti sampai ke socket.
"""
from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from office import config, imageai, websearch

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PNG_BYTES = base64.b64decode(PNG_B64)
MODEL_GAMBAR = "@cf/black-forest-labs/flux-1-schnell"

BALASAN_TAVILY = {
    "answer": "Harga panel surya turun 12 persen.",
    "results": [
        {
            "title": "Laporan Pasar Energi Surya",
            "url": "https://contoh.example/laporan-surya",
            "content": "Harga modul turun karena kelebihan pasokan.",
            "score": 0.91,
            "published_date": "2026-09-14",
        }
    ],
}


class _Handler(BaseHTTPRequestHandler):
    """Server tiruan yang mencatat setiap permintaan ke `self.server.diterima`."""

    def _kirim(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _catat(self, metode, payload):
        panjang = int(self.headers.get("Content-Length") or 0)
        mentah = self.rfile.read(panjang).decode("utf-8") if panjang else None
        self.server.diterima.append(
            {
                "metode": metode,
                "path": self.path,
                "auth": self.headers.get("Authorization", ""),
                "payload": json.loads(mentah) if mentah else None,
            }
        )

    def do_GET(self):  # noqa: N802
        self._catat("GET", None)
        self._kirim({"result": [{"id": "akun-lokal-001", "name": "Ampera"}]})

    def do_POST(self):  # noqa: N802
        self._catat("POST", None)
        if "/ai/run/" in self.path:
            self._kirim({"result": {"image": PNG_B64}})
        else:
            self._kirim(BALASAN_TAVILY)

    def log_message(self, *args):  # sunyi selama pengujian
        pass


@pytest.fixture
def server(monkeypatch, tmp_path):
    """Server HTTP lokal + kunci terisi + endpoint dialihkan ke server itu."""
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    httpd.diterima = []
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    monkeypatch.setattr(config, "ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.setattr(imageai, "CLOUDFLARE_API", f"http://127.0.0.1:{port}/client/v4")
    monkeypatch.setattr(websearch, "TAVILY_API", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-token-lokal")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-token-lokal")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_workers_ai_dipanggil_dengan_url_dan_payload_benar(server):
    assert imageai.resolve_account_id() == "akun-lokal-001"

    hasil = imageai.generate("maskot kantor, latar polos", model=MODEL_GAMBAR, slug="transport")

    cari_akun, render = server.diterima[0], server.diterima[1]
    assert cari_akun["path"].startswith("/client/v4/accounts?")
    assert cari_akun["auth"] == "Bearer cf-token-lokal"
    assert render["path"] == f"/client/v4/accounts/akun-lokal-001/ai/run/{MODEL_GAMBAR}"
    assert render["payload"] == {"prompt": hasil["prompt"], "steps": 4}
    with open(hasil.file, "rb") as fh:
        assert fh.read() == PNG_BYTES


def test_langkah_dikirim_sesuai_rentang_model(server):
    imageai.generate("ikon", model="@cf/black-forest-labs/flux-1-dev")
    assert server.diterima[-1]["payload"]["steps"] == 14
    imageai.generate("ikon", model="@cf/bytedance/stable-diffusion-xl-lightning")
    assert server.diterima[-1]["payload"]["steps"] == 1


def test_tavily_dipanggil_dengan_payload_pencarian(server):
    hasil = websearch.search("harga panel surya 2026", model="tavily-search")

    permintaan = server.diterima[-1]
    assert permintaan["path"] == "/search"
    assert permintaan["auth"] == "Bearer tvly-token-lokal"
    assert permintaan["payload"]["query"] == "harga panel surya 2026"
    assert permintaan["payload"]["search_depth"] == "basic"
    assert permintaan["payload"]["max_results"] == 6
    assert [s["url"] for s in hasil.sources] == ["https://contoh.example/laporan-surya"]


def test_prompt_panjang_tidak_melebihi_batas_model(server):
    prompt = imageai.build_image_prompt("Banner", "x" * 4000)
    imageai.generate(prompt, model=MODEL_GAMBAR)
    terkirim = server.diterima[-1]["payload"]["prompt"]
    assert len(terkirim) <= imageai.MAX_PROMPT_CHARS
    assert terkirim.startswith("Banner")

"""Pengujian kontrak kerja dan quality gate hasil karyawan."""
from office.quality import clean_response, evaluate_response, recommended_max_tokens, work_contract


def test_kontrak_spesifik_role_dan_keluaran():
    contract = work_contract("engineer", "kode")
    assert "implementasi" in contract
    assert "pengujian" in contract
    assert "mengklaim" in contract


def test_reasoning_internal_dibersihkan():
    raw = "<think>rahasia proses panjang</think>\n## Hasil\nKode final."
    cleaned = clean_response(raw)
    assert "rahasia" not in cleaned
    assert cleaned.startswith("## Hasil")


def test_penilaian_kode_mendeteksi_hasil_tidak_lengkap():
    report = evaluate_response("Sudah saya kerjakan.", "kode", "Buat parser tanggal")
    assert report["passed"] is False
    assert report["score"] < 60
    assert any("implementasi" in issue.lower() for issue in report["issues"])


def test_penilaian_kode_lengkap_lolos():
    text = """## Implementasi parser tanggal
Berikut fungsi final yang memvalidasi masukan dan mengembalikan pesan error yang jelas.

```python
from datetime import datetime

def parse_date(value: str) -> datetime:
    if not value:
        raise ValueError("tanggal wajib diisi")
    return datetime.strptime(value, "%Y-%m-%d")
```

## Pengujian dan verifikasi
Tambahkan unit test untuk tanggal valid, nilai kosong, serta format yang salah. Jalankan `pytest -q` dan pastikan seluruh test lama tetap lolos. Perubahan ini tidak mengubah kontrak fungsi lain dan hanya menambah parser tanggal yang diminta.

## Ringkasan untuk Bos
- Parser tanggal final sudah disediakan lengkap dengan validasi.
- Skenario test positif dan negatif sudah dijelaskan.
"""
    report = evaluate_response(text, "kode", "Buat parser tanggal dengan validasi dan unit test")
    assert report["passed"] is True
    assert report["metrics"]["code_blocks"] == 1


def test_budget_token_sesuai_jenis_pekerjaan():
    assert recommended_max_tokens("kode") > recommended_max_tokens("balasan pesan")
    assert recommended_max_tokens("kode", "tinggi") > recommended_max_tokens("kode", "normal")

"""Kontrak kerja dan pemeriksaan mutu keluaran karyawan.

Modul ini sengaja tidak bergantung pada Streamlit. Prompt dan hasil dapat diuji
secara deterministik sebelum ditampilkan di UI atau disetujui oleh bos.
"""
from __future__ import annotations

import re
from typing import Any

ROLE_PLAYBOOKS: dict[str, tuple[str, ...]] = {
    "architect": (
        "petakan batas sistem, aliran data, dependensi, dan trade-off",
        "bedakan keputusan wajib, asumsi, risiko, dan rencana migrasi",
    ),
    "engineer": (
        "hasilkan implementasi yang dapat dijalankan, bukan pseudocode",
        "bahas validasi input, error handling, kompatibilitas, dan pengujian",
    ),
    "qa": (
        "turunkan acceptance criteria menjadi skenario positif, negatif, dan edge case",
        "pisahkan temuan terverifikasi dari dugaan dan beri langkah reproduksi",
    ),
    "researcher": (
        "pisahkan fakta, inferensi, dan rekomendasi",
        "jangan mengarang sumber; tandai data yang belum dapat diverifikasi",
    ),
    "designer": (
        "jelaskan hierarki, state interaksi, aksesibilitas, dan ukuran yang operasional",
        "jaga desain yang sudah ada kecuali perubahan visual memang diminta",
    ),
    "marketing": (
        "sesuaikan pesan dengan audiens, kanal, tujuan, dan ajakan bertindak",
        "hindari klaim angka yang tidak didukung data",
    ),
    "writer": (
        "jaga alur, nada, audiens, dan konsistensi istilah",
        "berikan naskah final, bukan sekadar outline, kecuali outline yang diminta",
    ),
    "ops": (
        "utamakan langkah aman, idempotent, observability, rollback, dan verifikasi",
        "jangan mengaku sudah deploy atau menjalankan perintah bila belum dilakukan",
    ),
    "analyst": (
        "sebutkan definisi metrik, periode, satuan, asumsi, dan keterbatasan data",
        "jangan menciptakan angka; sediakan rumus bila data belum tersedia",
    ),
    "reception": (
        "jawab kebutuhan pengirim secara langsung, sopan, dan siap dikirim",
        "jangan menjanjikan harga, jadwal, atau keputusan yang belum disetujui bos",
    ),
    "security": (
        "urutkan risiko menurut dampak dan kemungkinan serta beri mitigasi konkret",
        "hindari mengekspos secret dan jangan menyatakan aman tanpa bukti pengujian",
    ),
    "intern": (
        "nyatakan asumsi dengan jujur dan kerjakan bagian yang dapat dipastikan",
        "minta keputusan hanya untuk hal yang benar-benar ambigu atau berisiko",
    ),
}

DELIVERABLE_CONTRACTS: dict[str, tuple[str, ...]] = {
    "kode": (
        "sertakan kode final lengkap atau patch yang jelas lokasi penerapannya",
        "sertakan cara menjalankan/verifikasi dan minimal satu pengujian penting",
    ),
    "perbaikan bug": (
        "jelaskan akar masalah, perubahan konkret, risiko regresi, dan pengujian reproduksi",
        "jangan menyatakan bug selesai bila kode atau bukti verifikasi tidak tersedia",
    ),
    "riset": (
        "sertakan temuan, bukti/sumber yang benar-benar tersedia, keterbatasan, dan rekomendasi",
        "jangan membuat URL, kutipan, angka, atau tanggal yang tidak ada di konteks",
    ),
    "artikel": (
        "berikan artikel final dengan judul, pembuka, isi terstruktur, dan penutup",
        "patuhi panjang dan audiens pada brief; jangan berhenti pada outline",
    ),
    "konten": (
        "berikan copy final sesuai kanal beserta CTA yang proporsional",
        "bila brief ambigu, pilih satu asumsi wajar dan nyatakan singkat",
    ),
    "desain": (
        "berikan spesifikasi implementabel: komponen, state, spacing, warna, dan aksesibilitas",
        "bedakan rekomendasi UX dari aset visual yang benar-benar sudah dibuat",
    ),
    "laporan": (
        "berikan ringkasan eksekutif, temuan, bukti, risiko, dan tindakan berikutnya",
        "semua angka harus berasal dari brief/konteks atau ditandai sebagai contoh",
    ),
    "deployment": (
        "sertakan prasyarat, langkah deploy, health check, rollback, dan penanganan secret",
        "gunakan perintah yang aman dan tandai placeholder secara eksplisit",
    ),
    "balasan pesan": (
        "tulis hanya balasan final yang siap dikirim, lalu ringkasan internal untuk bos",
        "jawab pertanyaan pengirim dan berikan next step tanpa janji yang tidak sah",
    ),
    "dokumen": (
        "hasilkan dokumen final yang terstruktur, spesifik, dan dapat ditindaklanjuti",
        "nyatakan asumsi serta bagian yang masih memerlukan keputusan",
    ),
}

MAX_RESULT_CHARS = 60_000


def work_contract(role: str, deliverable: str) -> str:
    """Buat instruksi mutu spesifik untuk jabatan dan bentuk keluaran."""
    role_rules = ROLE_PLAYBOOKS.get(role, ROLE_PLAYBOOKS["intern"])
    output_rules = DELIVERABLE_CONTRACTS.get(deliverable, DELIVERABLE_CONTRACTS["dokumen"])
    rows = ["STANDAR MUTU KHUSUS:"]
    rows.extend(f"- {rule}." for rule in (*role_rules, *output_rules))
    rows += [
        "- Jangan mengklaim telah membuka file, menjalankan test, menghubungi pihak, atau deploy jika tidak ada bukti di konteks.",
        "- Bila informasi penting tidak tersedia, tetap kerjakan semaksimal mungkin lalu tulis asumsi/keterbatasan secara ringkas.",
    ]
    return "\n".join(rows)


def clean_response(text: str) -> str:
    """Bersihkan kanal reasoning/tag internal tanpa mengubah substansi hasil."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<reasoning>.*?</reasoning>", "", value, flags=re.IGNORECASE | re.DOTALL)
    # Sebagian model mengawali jawaban dengan label proses internal satu baris.
    value = re.sub(
        r"^\s*(?:analysis|reasoning|proses berpikir|analisis internal)\s*:\s*[^\n]*(?:\n+|$)",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\n{4,}", "\n\n\n", value).strip()
    return value[:MAX_RESULT_CHARS]


def evaluate_response(text: str, deliverable: str, brief: str = "") -> dict[str, Any]:
    """Nilai mutu dasar tanpa model kedua atau biaya API tambahan.

    Skor bukan pengganti keputusan bos. Ia merupakan metadata audit agar hasil
    kosong, terlalu pendek, berisi reasoning, atau tidak sesuai bentuk keluaran
    mudah ditemukan.
    """
    value = clean_response(text)
    lower = value.lower()
    words = re.findall(r"\b[\wÀ-ÿ-]+\b", value)
    headings = len(re.findall(r"(?m)^#{1,6}\s+|^[A-Z][^\n]{2,60}:\s*$", value))
    code_blocks = value.count("```") // 2
    score = 100
    issues: list[str] = []
    strengths: list[str] = []

    if not value:
        score = 0
        issues.append("Hasil kosong.")
    else:
        if len(words) < 35:
            score -= 30
            issues.append("Hasil terlalu singkat untuk menunjukkan penyelesaian yang tuntas.")
        elif len(words) >= 90:
            strengths.append("Pembahasan cukup substantif.")
        if "ringkasan untuk bos" not in lower:
            score -= 12
            issues.append("Bagian 'Ringkasan untuk Bos' belum ada.")
        else:
            strengths.append("Memiliki ringkasan keputusan untuk bos.")
        if headings == 0 and len(words) > 120:
            score -= 8
            issues.append("Hasil panjang belum dipisahkan menjadi bagian yang mudah ditinjau.")
        if re.search(r"<think>|<reasoning>|\banalisis internal\s*:", lower):
            score -= 35
            issues.append("Kanal penalaran internal bocor ke hasil akhir.")
        if re.search(r"\b(sebagai (?:sebuah )?(?:ai|model bahasa)|saya tidak bisa membantu karena saya ai)\b", lower):
            score -= 15
            issues.append("Jawaban menyebut identitas model, bukan berperan sebagai karyawan.")

        if deliverable in {"kode", "perbaikan bug"}:
            if code_blocks == 0 and not re.search(r"\b(?:diff --git|file|berkas|fungsi|class|def |const |function )\b", lower):
                score -= 25
                issues.append("Tidak ada implementasi kode atau patch yang dapat diterapkan.")
            else:
                strengths.append("Memuat implementasi atau patch teknis.")
            if not re.search(r"\b(test|uji|verifikasi|pytest|unit test)\b", lower):
                score -= 10
                issues.append("Cara pengujian/verifikasi belum dijelaskan.")
        elif deliverable == "deployment":
            for keyword, message in (("rollback", "Rencana rollback belum ada."), ("verifikasi", "Langkah verifikasi deployment belum ada.")):
                if keyword not in lower and (keyword != "verifikasi" or "health check" not in lower):
                    score -= 10
                    issues.append(message)
        elif deliverable == "balasan pesan":
            if len(words) > 700:
                score -= 10
                issues.append("Balasan terlalu panjang untuk langsung dikirim.")
            if not re.search(r"\b(terima kasih|halo|yth|selamat)\b", lower):
                score -= 6
                issues.append("Sapaan atau pembuka sopan belum terlihat.")

        if brief and len(brief.strip()) > 20:
            significant = [w.lower() for w in re.findall(r"\b[\w-]{5,}\b", brief) if w.lower() not in {"untuk", "dengan", "harus", "tolong", "buatkan"}]
            if significant and not any(w in lower for w in significant[:20]):
                score -= 12
                issues.append("Hasil tampak kurang terkait dengan istilah penting pada brief.")

    return {
        "score": max(0, min(100, score)),
        "passed": score >= 60,
        "issues": issues,
        "strengths": strengths,
        "metrics": {
            "characters": len(value),
            "words": len(words),
            "headings": headings,
            "code_blocks": code_blocks,
        },
    }


def recommended_max_tokens(deliverable: str, priority: str = "normal") -> int:
    """Token budget berdasarkan bentuk pekerjaan, bukan satu angka untuk semua."""
    base = {
        "balasan pesan": 650,
        "konten": 900,
        "desain": 1400,
        "riset": 1800,
        "laporan": 1800,
        "artikel": 1800,
        "kode": 2200,
        "perbaikan bug": 2200,
        "deployment": 1600,
        "dokumen": 1500,
    }.get(deliverable, 1500)
    if priority == "tinggi":
        base = int(base * 1.15)
    return min(base, 3000)

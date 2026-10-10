# AOG Virtual Office

Game simulasi kantor berbasis **Streamlit** berisi karyawan-karyawan **model AI** yang bekerja
untuk Anda. Anda adalah **Bos**: memberi tugas, karyawan mengerjakannya dengan model AI
miliknya masing-masing, lalu Anda **menyetujui / menolak** hasilnya. Proyek terhubung ke
repo GitHub Anda (live via REST API) dan registri aplikasi Streamlit Anda.

Semua ikon memakai **Material Symbols** (bukan emoji) — tombol Streamlit memakai shortcode
`:material/nama_ikon:`, sedangkan panggung kantor menggambar path SVG Material secara inline
(diambil langsung dari repo resmi `google/material-design-icons`, 220 ikon).

## Menjalankan

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # lalu isi kunci Anda
streamlit run app.py
```

Uji otomatis:

```bash
python -m pytest test -q
```

Pratinjau panggung kantor statis: jalankan `python scripts/make_preview.py` (butuh `cairosvg`)
untuk menghasilkan `data/pratinjau_kantor.png` dari denah SVG.

## Secrets

```toml
GROQ_API_KEY = "gsk_..."
OPENROUTER_API_KEY = "sk-or-v1-..."
AION_API_KEY = "aion_..."
GITHUB_TOKEN = "github_pat_..."   # opsional: membuka integrasi GitHub live
```

Tanpa kunci sekalipun kantor tetap hidup (karakter berjalan, tugas masuk antrean),
tetapi karyawan belum bisa memanggil model sungguhan sampai kunci diisi.

## Provider & model yang dipakai (diverifikasi 8 Okt 2026)

Model dipilih dari katalog **live** tiap provider (`/v1/models`), bukan dari daftar lama.
Katalog Groq butuh kunci, sedangkan OpenRouter dan Aion Labs publik — keduanya dicek ulang
saat runtime lewat tombol **"Probe katalog live"** di panel *Model & Provider*; model yang
ternyata mati otomatis dinonaktifkan dan dipindah ke pengganti.

* **Groq** — Llama 3.1/3.3, Llama 4 Scout/Maverick, Qwen3-32B, dan Kimi K2 sudah
  **dimatikan** (Mar–Agu 2026). Yang dipakai: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `openai/gpt-oss-safeguard-20b`, `qwen/qwen3.6-27b`, `groq/compound-mini`.
* **OpenRouter** — hanya model **tanpa `expiration_date`**. Contoh yang sudah kadaluarsa dan
  sengaja tidak dipakai: `google/gemini-2.5-*` (20 Okt 2026), `qwen/qwen3.5-9b` (21 Okt),
  `poolside/laguna-*` (31 Okt), `z-ai/glm-4.5/4.7` (31 Des).
* **Aion Labs** (`https://api.aionlabs.ai/v1`) — 6 model live: `aion-3.5`, `aion-3.5-mini`,
  `aion-3.0`, `aion-3.0-mini`, `aion-2.0`, `aion-rp-llama-3.1-8b`.

Setiap karyawan punya model utama + rantai **fallback** (role → global), jadi satu model
mati tidak pernah membuat karyawan macet.

## Mesin kerja v3

Pembaruan v3 memperkuat logika internal tanpa mengganti desain UI:

* **Kontrak jawaban per jabatan dan keluaran** — engineer, QA, riset, desain, DevOps,
  resepsionis, dan role lain mendapat standar kerja berbeda; kode wajib implementabel,
  riset dilarang mengarang sumber, dan deployment wajib memikirkan rollback.
* **Quality gate lokal** — hasil dinilai tanpa panggilan model tambahan (kelengkapan,
  struktur, implementasi, pengujian, dan kebocoran reasoning). Skor dan temuan disimpan
  di task untuk audit dan pengembangan UI berikutnya.
* **Revisi benar-benar kontekstual** — catatan bos, versi hasil sebelumnya, dan riwayat
  keputusan dikirim ke karyawan agar revisi memperbaiki hasil, bukan mengulang dari nol.
* **Workflow idempotent** — klik/rerun ganda tidak lagi menggandakan API call, XP,
  statistik persetujuan, delegasi pesan, atau paket rilis.
* **Antrean berbasis prioritas** dan rekomendasi karyawan mempertimbangkan kompetensi,
  beban aktif, energi, mood, rekam jejak, serta kata kunci brief.
* **Percakapan berkelanjutan** — karyawan mengingat delapan pesan terakhir, dengan
  batas histori yang benar dan perlindungan prompt injection untuk konteks repo/pesan.
* **Persistensi schema v4** — migrasi state lama, normalisasi data rusak, statistik baru,
  penulisan atomik dengan flush ke disk, dan lock proses.

## Karyawan

| Karyawan | Jabatan | Ruang | Provider | Model |
| --- | --- | --- | --- | --- |
| Raka Danuarta | Arsitek Sistem | Ruang Kode | openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Sari Melati | Software Engineer | Ruang Kode | openrouter | `inclusionai/ling-3.1-flash` |
| Bimo Prakoso | Software Engineer | Ruang Kode | openrouter | `cohere/north-mini-code:free` |
| Nadia Kusuma | QA Engineer | Ruang QA | openrouter | `nvidia/nemotron-3-super-120b-a12b:free` |
| Ayu Larasati | Riset & Analis Pasar | Ruang Riset | openrouter | `thinkingmachines/inkling:free` |
| Fajar Nugroho | UI/UX Designer | Ruang Desain | openrouter | `google/gemma-4-31b-it:free` |
| Dinda Puspita | Content Strategist | Ruang Marketing | aion | `aion-labs/aion-3.5-mini` |
| Tomi Hartanto | DevOps Engineer | Ruang DevOps | groq | `openai/gpt-oss-120b` |
| Kenji Wirawan | Data Analyst | Ruang Data | openrouter | `nvidia/nemotron-3.5-lightning:free` |
| Lala Anindya | Resepsionis | Ruang Penerima Pesan | openrouter | `liquid/lfm-2.5-2.6b:free` |
| Gilang Ramadhan | Spesialis Konten & Keamanan | Ruang QA | groq | `openai/gpt-oss-safeguard-20b` |
| Putri Anggraini | Anak Magang | Pantry dan Ruang Santai | openrouter | `apodex/apodex-1.1-mini:free` |

Model tiap karyawan bisa diganti kapan saja dari panel **Karyawan**.

## Ruangan

Ruang Bos · Ruang Kode · Ruang Riset · Ruang Desain · Ruang Marketing ·
Ruang Penerima Pesan · Ruang QA · Ruang Data · Ruang DevOps · Pantry dan Ruang Santai.

Karakter tidak kaku: mereka **berjalan** antar ruang, **mengetik** saat bekerja,
**ngopi / main game / tidur** saat santai, berkedip, bernapas, dan memakai properti sesuai
aktivitas (laptop, cangkir, gamepad, "zzz"). Semua animasi CSS murni di dalam SVG.

Panggung dirender dua lapis: denah isometrik **SVG** sebagai lapisan dasar (selalu tergambar,
juga menjadi cadangan bila WebGL/komponen tidak termuat), dan panggung **3D** low-poly
(Three.js, gaya Two Point Hospital) yang menutupinya saat aktif.

## Alur kerja bos

1. Panel **Beri Tugas** — tulis judul + brief, pilih karyawan (ada saran otomatis berdasar
   jenis keluaran), prioritas, dan opsi konteks repo GitHub.
2. Klik **Jalankan semua antrean** (atau per tugas) — karyawan memanggil model AI
   sungguhan; hasilnya masuk antrean persetujuan.
3. Panel **Persetujuan** — baca hasil, beri catatan, **Setujui** atau **Tolak/Revisi**
   (revisi otomatis dikerjakan ulang dengan catatan Anda).
4. Hasil yang disetujui bisa dibungkus **Paket Rilis** dan diarsipkan.

## Integrasi

* **GitHub** (panel GitHub): daftar repo, commit, isu/PR, pohon berkas, baca isi file,
  membuat isu nyata bila token punya izin, plus rate-limit meter. Repo default mengikuti
  akun `amperaofficial26-beep` (Ampera-Web-Design, Ampera-Scribe, Room-Chat-Ampera-Group).
* **Aplikasi Streamlit** (panel Aplikasi Streamlit): daftarkan URL deploy, cek status hidup/mati
  dengan latensi, dan tunjuk penanggung jawab karyawan.
* **Kotak Pesan**: pesan masuk (manual / simulasi) bisa didelegasikan menjadi tugas.

## Struktur

```
app.py                  # UI Streamlit (9 panel)
office/config.py        # secrets, provider, path
office/models.py        # katalog model + probe live + migrasi model mati
office/llm.py           # pemanggil API (Groq/OpenRouter/Aion) + fallback
office/quality.py       # kontrak jawaban per role + pemeriksaan mutu lokal
office/engine.py        # alur tugas, persetujuan, aktivitas, rilis, inbox
office/roster.py        # denah ruang + roster karyawan
office/state.py         # persistensi JSON + cache
office/github.py        # REST GitHub
office/apps.py          # registri aplikasi Streamlit
office/ui/              # ikon Material, karakter SVG, panggung 3D (Three.js) + denah isometrik, tema
test/                   # pengujian otomatis (pytest)
```

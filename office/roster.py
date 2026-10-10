"""Denah kantor (ruang isometrik) dan roster karyawan AI."""
from __future__ import annotations

import time
from typing import Any

from .models import MODELS, RETIRED, ROLE_FALLBACK, migrate_model
from .models_data import EMP_IDLE, Employee, Room

# ----------------------------------------------------------------------------- denah
# Grid isometrik: TILE_W x TILE_H. Ruangan diletakkan berdampingan tanpa tumpang tindih.
TILE_W = 104
TILE_H = 52

ROOMS: dict[str, Room] = {
    r.rid: r
    for r in [
        Room(
            rid="reception",
            name="Ruang Penerima Pesan",
            icon="mark_chat_unread",
            color="#38BDF8",
            desc="Semua pesan, chat, dan permintaan masuk disortir di sini.",
            gx=0, gy=3, gw=3, gh=3,
            furniture=("desk", "monitor", "plant", "sofa"),
        ),
        Room(
            rid="code",
            name="Ruang Kode",
            icon="terminal",
            color="#22D3EE",
            desc="Insinyur menulis, mereview, dan menambal kode repo Anda.",
            gx=3, gy=0, gw=4, gh=3,
            furniture=("desk", "monitor", "whiteboard", "server"),
        ),
        Room(
            rid="research",
            name="Ruang Riset",
            icon="psychology",
            color="#A78BFA",
            desc="Riset pasar, kompetitor, dan ringkasan teknis.",
            gx=7, gy=0, gw=3, gh=3,
            furniture=("desk", "monitor", "bookshelf", "plant"),
        ),
        Room(
            rid="design",
            name="Ruang Desain",
            icon="palette",
            color="#F472B6",
            desc="UI, aset visual, dan panduan gaya produk.",
            gx=10, gy=0, gw=3, gh=3,
            furniture=("desk", "monitor", "easel", "plant"),
        ),
        Room(
            rid="marketing",
            name="Ruang Marketing",
            icon="campaign",
            color="#FB923C",
            desc="Copywriting, kampanye, dan konten media sosial.",
            gx=10, gy=3, gw=3, gh=3,
            furniture=("desk", "monitor", "sofa", "plant"),
        ),
        Room(
            rid="qa",
            name="Ruang QA",
            icon="bug_report",
            color="#F87171",
            desc="Pengujian, pencarian bug, dan laporan kualitas.",
            gx=0, gy=6, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard"),
        ),
        Room(
            rid="data",
            name="Ruang Data",
            icon="storage",
            color="#34D399",
            desc="Analisis metrik, laporan angka, dan dashboard.",
            gx=3, gy=6, gw=3, gh=3,
            furniture=("desk", "monitor", "server", "bookshelf"),
        ),
        Room(
            rid="ops",
            name="Ruang DevOps",
            icon="settings",
            color="#818CF8",
            desc="Deployment, konfigurasi, dan kesehatan layanan.",
            gx=6, gy=6, gw=3, gh=3,
            furniture=("desk", "monitor", "server"),
        ),
        Room(
            rid="break",
            name="Pantry dan Ruang Santai",
            icon="local_cafe",
            color="#FBBF24",
            desc="Kopi, camilan, dan game. Tempat karyawan memulihkan energi.",
            gx=9, gy=6, gw=3, gh=3,
            furniture=("sofa", "coffee", "arcade", "plant"),
        ),
        Room(
            rid="boss",
            name="Ruang Bos",
            icon="supervisor_account",
            color="#FACC15",
            desc="Ruang Anda. Semua persetujuan keluar dari sini.",
            gx=1, gy=0, gw=2, gh=3,
            furniture=("desk", "monitor", "plant", "trophy"),
        ),
        
        # ── Baris 1: ruang kerja pendukung ──────────────────────────
        Room(
            rid="documentation",
            name="Ruang Dokumentasi",
            icon="description",
            color="#60A5FA",
            desc="Dokumentasi teknis, README, dan panduan penggunaan.",
            gx=0, gy=9, gw=3, gh=3,
            furniture=("desk", "monitor", "bookshelf", "plant"),
        ),
        Room(
            rid="writing",
            name="Ruang Penulisan",
            icon="edit_note",
            color="#F9A8D4",
            desc="Artikel, naskah, dan penulisan profesional.",
            gx=3, gy=9, gw=3, gh=3,
            furniture=("desk", "monitor", "bookshelf", "plant"),
        ),
        Room(
            rid="ai_image",
            name="Ruang AI Image",
            icon="image",
            color="#C4B5FD",
            desc="Pembuatan gambar AI dan pengolahan aset visual.",
            gx=6, gy=9, gw=3, gh=3,
            furniture=("desk", "monitor", "easel", "plant"),
        ),
        Room(
            rid="web_research",
            name="Ruang Web Research",
            icon="travel_explore",
            color="#67E8F9",
            desc="Pencarian web, pengumpulan sumber, dan verifikasi informasi.",
            gx=9, gy=9, gw=3, gh=3,
            furniture=("desk", "monitor", "bookshelf", "whiteboard"),
        ),
        Room(
            rid="cybersecurity",
            name="Ruang Keamanan Siber",
            icon="security",
            color="#FCA5A5",
            desc="Audit keamanan aplikasi dan pemeriksaan kerentanan.",
            gx=12, gy=9, gw=3, gh=3,
            furniture=("desk", "monitor", "server", "whiteboard"),
        ),

        # ── Baris 2: infrastruktur dan pengembangan ──────────────────
        Room(
            rid="database",
            name="Ruang Database",
            icon="database",
            color="#6EE7B7",
            desc="Perancangan skema dan pengelolaan basis data.",
            gx=0, gy=12, gw=3, gh=3,
            furniture=("desk", "monitor", "server", "bookshelf"),
        ),
        Room(
            rid="automation",
            name="Ruang Otomasi",
            icon="account_tree",
            color="#93C5FD",
            desc="Workflow, integrasi, dan otomatisasi tugas.",
            gx=3, gy=12, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard", "server"),
        ),
        Room(
            rid="product",
            name="Ruang Produk",
            icon="inventory_2",
            color="#FDBA74",
            desc="Perencanaan fitur dan pengembangan produk.",
            gx=6, gy=12, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard", "sofa"),
        ),
        Room(
            rid="strategy",
            name="Ruang Strategi",
            icon="insights",
            color="#FDE68A",
            desc="Analisis arah bisnis dan perencanaan proyek.",
            gx=9, gy=12, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard", "plant"),
        ),
        Room(
            rid="meeting",
            name="Ruang Rapat",
            icon="groups",
            color="#A5B4FC",
            desc="Koordinasi tim dan pembahasan proyek.",
            gx=12, gy=12, gw=3, gh=3,
            furniture=("sofa", "whiteboard", "plant"),
        ),

        # ── Baris 3: pengetahuan, monitoring, dan AI ─────────────────
        Room(
            rid="library",
            name="Perpustakaan AI",
            icon="local_library",
            color="#D8B4FE",
            desc="Referensi, arsip, dan pengetahuan internal.",
            gx=0, gy=15, gw=3, gh=3,
            furniture=("bookshelf", "desk", "plant"),
        ),
        Room(
            rid="training",
            name="Ruang Pelatihan",
            icon="school",
            color="#86EFAC",
            desc="Pembelajaran dan peningkatan kemampuan agen.",
            gx=3, gy=15, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard"),
        ),
        Room(
            rid="monitoring",
            name="Ruang Monitoring",
            icon="monitor_heart",
            color="#7DD3FC",
            desc="Pemantauan status layanan dan aktivitas kantor.",
            gx=6, gy=15, gw=3, gh=3,
            furniture=("desk", "monitor", "server"),
        ),
        Room(
            rid="prompt_engineering",
            name="Ruang Prompt Engineering",
            icon="psychology",
            color="#E9D5FF",
            desc="Merancang, menguji, dan mengoptimalkan prompt AI.",
            gx=9, gy=15, gw=3, gh=3,
            furniture=("desk", "monitor", "whiteboard", "bookshelf"),
        ),
        Room(
            rid="ai_integration",
            name="Ruang Integrasi AI",
            icon="hub",
            color="#99F6E4",
            desc="Menghubungkan model AI, API, dan layanan eksternal.",
            gx=12, gy=15, gw=3, gh=3,
            furniture=("desk", "monitor", "server", "whiteboard"),
        ),
    ]
}


ROOM_ORDER = [
    "boss",
    "code",
    "research",
    "design",
    "marketing",
    "reception",
    "qa",
    "data",
    "ops",
    "break",
    "documentation",
    "writing",
    "ai_image",
    "web_research",
    "cybersecurity",
    "database",
    "automation",
    "product",
    "strategy",
    "meeting",
    "library",
    "training",
    "monitoring",
    "prompt_engineering",
    "ai_integration",
]

ROOM_LABEL = {rid: ROOMS[rid].name for rid in ROOMS}

# Tempat "parkir" default tiap karyawan di dalam ruangannya (koordinat grid).
DESK_SPOTS: dict[str, list[tuple[float, float]]] = {
    "boss": [(1.5, 0.8)],
    "code": [(3.7, 0.7), (5.4, 0.7), (3.7, 2.0)],
    "research": [(7.6, 0.7), (8.9, 2.0)],
    "design": [(10.6, 0.7), (11.9, 2.0)],
    "marketing": [(10.6, 3.7), (11.9, 5.0)],
    "reception": [(0.6, 3.7), (1.9, 5.0)],
    "qa": [(0.6, 6.7), (1.9, 8.0)],
    "data": [(3.6, 6.7), (4.9, 8.0)],
    "ops": [(6.6, 6.7), (7.9, 8.0)],
    "break": [(9.6, 6.8), (10.9, 7.4), (10.2, 8.2)],
    "documentation": [(0.6, 9.7), (1.9, 11.0)],
    "writing": [(3.6, 9.7), (4.9, 11.0)],
    "ai_image": [(6.6, 9.7), (7.9, 11.0)],
    "web_research": [(9.6, 9.7), (10.9, 11.0)],
    "cybersecurity": [(12.6, 9.7), (13.9, 11.0)],
    "database": [(0.6, 12.7), (1.9, 14.0)],
    "automation": [(3.6, 12.7), (4.9, 14.0)],
    "product": [(6.6, 12.7), (7.9, 14.0)],
    "strategy": [(9.6, 12.7), (10.9, 14.0)],
    "meeting": [(12.6, 12.7), (13.9, 14.0)],
    "library": [(0.6, 15.7), (1.9, 17.0)],
    "training": [(3.6, 15.7), (4.9, 17.0)],
    "monitoring": [(6.6, 15.7), (7.9, 17.0)],
    "prompt_engineering": [(9.6, 15.7), (10.9, 17.0)],
    "ai_integration": [(12.6, 15.7), (13.9, 17.0)],
}

BREAK_SPOTS = [(9.6, 6.8), (10.9, 7.4), (10.2, 8.2), (9.8, 8.4)]
BOSS_SPOT = (1.5, 0.8)


def desk_spot(room_id: str, index: int = 0) -> tuple[float, float]:
    spots = DESK_SPOTS.get(room_id) or [(0.5, 0.5)]
    return spots[index % len(spots)]


def break_spot(index: int = 0) -> tuple[float, float]:
    return BREAK_SPOTS[index % len(BREAK_SPOTS)]


def room_bounds(rid: str) -> tuple[float, float, float, float]:
    room = ROOMS[rid]
    return room.gx, room.gy, room.gx + room.gw, room.gy + room.gh


# ----------------------------------------------------------------------------- roster
def _emp(
    eid: str,
    name: str,
    role: str,
    role_label: str,
    title: str,
    model: str,
    room: str,
    personality: str,
    greeting: str,
    quirks: tuple[str, ...],
    desk_index: int = 0,
    **looks: Any,
) -> Employee:
    meta = MODELS[model]
    pos = desk_spot(room, desk_index)
    return Employee(
        eid=eid,
        name=name,
        role=role,
        role_label=role_label,
        title=title,
        provider=meta["provider"],
        model=model,
        room=room,
        personality=personality,
        greeting=greeting,
        quirks=quirks,
        desk=pos,
        pos=pos,
        hired_at=time.time(),
        **looks,
    )


ROSTER: tuple[Employee, ...] = (
    _emp(
        "raka", "Raka Danuarta", "architect", "Arsitek Sistem", "CTO / Kepala Ruang Kode",
        "nvidia/nemotron-3-ultra-550b-a55b:free", "code",
        "Tenang, sistematis, suka menggambar diagram sebelum menulis satu baris kode.",
        "Siap, Bos. Sebelum coding, saya petakan dulu arsitekturnya biar tidak bongkar ulang.",
        ("Selalu bikin diagram dulu", "Benci kode tanpa tipe data", "Ngopi tiga kali sehari"),
        desk_index=0, skin="#E8B892", hair="#1F1B16", shirt="#0F766E", accent="#FACC15",
        glasses=True, hair_style="short",
    ),
    _emp(
        "sari", "Sari Melati", "engineer", "Software Engineer", "Full-Stack Developer",
        "inclusionai/ling-3.1-flash", "code",
        "Cepat dan rapi, senang refactor diam-diam tengah malam.",
        "Bos, saya kerjakan sekarang. Nanti saya sertakan test-nya sekalian.",
        ("Refactor diam-diam", "Menulis test duluan", "Suka nama variabel panjang"),
        desk_index=1, skin="#F6C9A0", hair="#2B1D14", shirt="#7C3AED", accent="#22D3EE",
        hair_style="ponytail",
    ),
    _emp(
        "bimo", "Bimo Prakoso", "engineer", "Software Engineer", "Backend & API Developer",
        "cohere/north-mini-code:free", "code",
        "Perfeksionis soal API, tidak tahan melihat endpoint tanpa dokumentasi.",
        "Endpoint-nya saya rapikan dulu, Bos, biar tim lain tidak bingung.",
        ("Wajib dokumentasi endpoint", "Musuhan dengan magic number", "Suka PostgreSQL"),
        desk_index=2, skin="#D9A077", hair="#14100C", shirt="#1D4ED8", accent="#FB923C",
        hair_style="curly",
    ),
    _emp(
        "nadia", "Nadia Kusuma", "qa", "QA Engineer", "Kepala Pengujian",
        "nvidia/nemotron-3-super-120b-a12b:free", "qa",
        "Teliti sampai ke titik koma. Senang kalau menemukan bug sebelum rilis.",
        "Saya coba rusakkan dulu, Bos. Kalau lolos dari saya, berarti aman.",
        ("Menemukan bug adalah hobi", "Selalu cek edge case", "Punya checklist 42 poin"),
        desk_index=0, skin="#F1C0A0", hair="#3A2418", shirt="#BE123C", accent="#FDE68A",
        glasses=True, hair_style="bun",
    ),
    _emp(
        "ayu", "Ayu Larasati", "researcher", "Riset & Analis Pasar", "Kepala Riset",
        "thinkingmachines/inkling:free", "research",
        "Penasaran berlebihan, selalu menyertakan sumber di setiap klaim.",
        "Saya kumpulkan datanya dulu ya, Bos. Semua klaim nanti ada sumbernya.",
        ("Wajib sebut sumber", "Membaca 30 tab sekaligus", "Suka membuat matriks"),
        desk_index=0, skin="#F6C9A0", hair="#4A2C1B", shirt="#6D28D9", accent="#A7F3D0",
        hair_style="long",
    ),
    _emp(
        "fajar", "Fajar Nugroho", "designer", "UI/UX Designer", "Kepala Desain",
        "google/gemma-4-31b-it:free", "design",
        "Sensitif soal kontras dan jarak antar elemen, obsesif pada grid.",
        "Grid-nya saya rapikan dulu, Bos. Kontrasnya saya cek ulang.",
        ("Obsesif pada grid 8px", "Benci warna asal comot", "Suka dark mode"),
        desk_index=0, skin="#E0A878", hair="#241A12", shirt="#DB2777", accent="#FBCFE8",
        hair_style="short",
    ),
    _emp(
        "dinda", "Dinda Puspita", "marketing", "Content Strategist", "Kepala Marketing",
        "aion-labs/aion-3.5-mini", "marketing",
        "Pandai merangkai cerita, selalu punya tiga alternatif kalimat pembuka.",
        "Saya siapkan tiga versi copy-nya, Bos. Nanti Bos pilih yang paling nendang.",
        ("Selalu bikin 3 alternatif", "Suka hook di kalimat pertama", "Pakai data untuk argumen"),
        desk_index=0, skin="#F6C9A0", hair="#5A3520", shirt="#EA580C", accent="#FEF3C7",
        hair_style="long",
    ),
    _emp(
        "tomi", "Tomi Hartanto", "ops", "DevOps Engineer", "Kepala Infrastruktur",
        "openai/gpt-oss-120b", "ops",
        "Otomatisasi segalanya. Kalau dikerjakan dua kali, pasti dibuat skripnya.",
        "Saya otomatiskan, Bos. Sekali jalan, berikutnya tinggal klik.",
        ("Semua dibuat skrip", "Pantau log setiap pagi", "Suka Docker"),
        desk_index=0, skin="#D9A077", hair="#1B1512", shirt="#334155", accent="#34D399",
        glasses=True, hair_style="buzz",
    ),
    _emp(
        "kenji", "Kenji Wirawan", "analyst", "Data Analyst", "Analis Data",
        "nvidia/nemotron-3.5-lightning:free", "data",
        "Bicara lewat grafik. Tidak percaya angka tanpa konteks.",
        "Saya tarik angkanya dulu, Bos. Nanti saya sajikan dalam grafik.",
        ("Tidak percaya angka tanpa konteks", "Suka grafik garis", "Selalu hitung konversi"),
        desk_index=0, skin="#E8B892", hair="#0F0C0A", shirt="#0369A1", accent="#BAE6FD",
        glasses=True, hair_style="short",
    ),
    _emp(
        "lala", "Lala Anindya", "reception", "Resepsionis", "Penjaga Kotak Pesan",
        "liquid/lfm-2.5-2.6b:free", "reception",
        "Ramah dan gesit, tidak pernah membiarkan pesan menunggu lama.",
        "Pesan masuk sudah saya pilah, Bos. Mana yang perlu segera Bos lihat?",
        ("Membalas dalam 1 menit", "Selalu menyapa lebih dulu", "Suka merapikan label"),
        desk_index=0, skin="#F6C9A0", hair="#2E1C12", shirt="#0EA5E9", accent="#E0F2FE",
        hair_style="ponytail",
    ),
    _emp(
        "gilang", "Gilang Ramadhan", "security", "Spesialis Konten & Keamanan", "Satpam Konten",
        "openai/gpt-oss-safeguard-20b", "qa",
        "Waspada, memeriksa setiap keluaran sebelum dianggap layak tayang.",
        "Saya periksa dulu sisi amannya, Bos. Jangan sampai ada yang lolos.",
        ("Selalu cek sisi keamanan", "Tidak suka buru-buru rilis", "Punya daftar merah"),
        desk_index=1, skin="#C68863", hair="#120E0B", shirt="#1F2937", accent="#F87171",
        hair_style="buzz",
    ),
    _emp(
        "putri", "Putri Anggraini", "intern", "Anak Magang", "Serabutan Multitalenta",
        "apodex/apodex-1.1-mini:free", "break",
        "Antusias, sedikit ceroboh, tapi selalu mau belajar.",
        "Saya coba dulu ya, Bos! Kalau salah, saya perbaiki lagi.",
        ("Belajar hal baru tiap hari", "Sering bertanya", "Paling cepat akrab"),
        desk_index=0, skin="#F6C9A0", hair="#3B2416", shirt="#F59E0B", accent="#FEF9C3",
        hair_style="bun",
    ),
)

ROSTER_BY_ID: dict[str, Employee] = {e.eid: e for e in ROSTER}

ROLE_LABELS = {
    "architect": "Arsitek Sistem",
    "engineer": "Software Engineer",
    "researcher": "Riset & Analis Pasar",
    "designer": "UI/UX Designer",
    "marketing": "Content Strategist",
    "qa": "QA Engineer",
    "ops": "DevOps Engineer",
    "analyst": "Data Analyst",
    "reception": "Resepsionis",
    "security": "Spesialis Konten & Keamanan",
    "intern": "Anak Magang",
    "writer": "Penulis Konten",
}

# Karyawan yang paling cocok untuk tiap jenis tugas (dipakai fitur "sarankan karyawan").
ROLE_FOR_DELIVERABLE = {
    "kode": "engineer",
    "perbaikan bug": "qa",
    "riset": "researcher",
    "artikel": "writer",
    "konten": "marketing",
    "desain": "designer",
    "laporan": "analyst",
    "deployment": "ops",
    "balasan pesan": "reception",
    "dokumen": "engineer",
}


def suggested_employee(deliverable: str) -> str:
    role = ROLE_FOR_DELIVERABLE.get(deliverable, "engineer")
    for emp in ROSTER:
        if emp.role == role:
            return emp.eid
    return ROSTER[0].eid


def sync_employees(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Gabungkan roster bawaan dengan state tersimpan.

    - Karyawan baru dari roster otomatis ditambahkan.
    - Progres (xp, tugas selesai, mood) dipertahankan.
    - Model yang sudah mati provider otomatis dimigrasikan ke pengganti hidup.
    """
    saved = saved or {}
    merged: dict[str, Any] = {}
    for emp in ROSTER:
        data = emp.to_dict()
        old = saved.get(emp.eid)
        if isinstance(old, dict):
            for key in (
                "xp", "level", "tasks_done", "tasks_rejected", "mood", "energy",
                "state", "state_until", "target_room", "pos", "facing",
                "last_task_at", "hired_at", "room",
            ):
                if key in old:
                    data[key] = old[key]
            old_model = old.get("model", "")
            if old_model and old_model != emp.model:
                if old_model in RETIRED:
                    # model sudah dimatikan provider: wajib pindah ke pengganti hidup
                    data["model"] = migrate_model(old_model)
                elif old_model in MODELS:
                    # hormati pilihan model dari UI selama masih hidup
                    data["model"] = old_model
                else:
                    data["model"] = emp.model
                data["provider"] = MODELS.get(data["model"], {}).get("provider", emp.provider)
        data["pos"] = list(data.get("pos") or emp.pos)
        data["desk"] = list(emp.desk)
        data["fallbacks"] = ROLE_FALLBACK.get(emp.role, [])
        if data.get("state") == EMP_IDLE:
            data["target_room"] = ""
        merged[emp.eid] = data
    return merged


def employee_from_state(data: dict[str, Any]) -> Employee:
    return Employee.from_dict(data)


def roster_table() -> list[dict[str, str]]:
    """Tabel roster untuk README/panel info."""
    rows = []
    for emp in ROSTER:
        meta = MODELS[emp.model]
        rows.append(
            {
                "nama": emp.name,
                "jabatan": emp.role_label,
                "ruang": ROOMS[emp.room].name,
                "provider": meta["provider"],
                "model": emp.model,
                "label": meta["label"],
            }
        )
    return rows

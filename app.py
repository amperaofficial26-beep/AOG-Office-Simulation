"""AOG Virtual Office — game simulasi kantor berisi karyawan model AI.

Satu layar full-screen: panggung kantor memenuhi viewport, semua fitur
(tugas, pesan, persetujuan, karyawan, GitHub, aplikasi, model, pengaturan)
hidup sebagai HUD di dalam layar kantor. Di ponsel portrait, tampilan
diputar otomatis menjadi landscape.

Jalankan:  streamlit run app.py
"""
from __future__ import annotations

import time
from typing import Any

import streamlit as st

from office import apps as apps_mod
from office import engine, github as gh
from office.config import (
    APP_NAME,
    APP_TAGLINE,
    PROVIDERS,
    PROVIDER_ORDER,
    VERSION,
    get_key,
    has_key,
    read_secrets_file,
    write_secrets_file,
)
from office.icons import icon_svg, labeled, mat
from office.llm import provider_health, test_key
from office.models import (
    MODELS,
    RETIRED,
    VERIFIED_AT,
    live_models,
    models_for,
    probe_all,
)
from office.models_data import (
    EMP_ICON,
    TASK_APPROVED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_REJECTED,
    TASK_REVIEW,
    TASK_WORKING,
)
from office.roster import ROSTER, ROOMS, ROOM_ORDER, suggested_employee
from office.state import export_snapshot, load_config, load_state, reset_state, save_state, update_config
from office.ui.characters import state_label
from office.ui.office_view import render_office, room_legend
from office.ui.theme import bar, base_css, chip, progress_row, section, stat_block, theme as get_theme
from office.ui.stage3d import render_stage_3d

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="collapsed")

DELIVERABLES = [
    "kode", "perbaikan bug", "riset", "artikel", "konten",
    "desain", "laporan", "deployment", "balasan pesan", "dokumen",
]
PRIORITIES = ["rendah", "normal", "tinggi"]

TOPBAR = [
    ("tugas", "assignment", "Beri Tugas"),
    ("inbox", "mark_chat_unread", "Kotak Pesan"),
    ("approval", "approval", "Persetujuan"),
    ("karyawan", "diversity_3", "Karyawan"),
    ("github", "source", "GitHub"),
    ("apps", "rocket_launch", "Aplikasi Streamlit"),
    ("models", "hub", "Model & Provider"),
    ("settings", "settings", "Pengaturan"),
]

HUD_CSS = """
html, body { overflow: hidden !important; }
#MainMenu, footer, [data-testid="stHeader"], [data-testid="stStatusWidget"],
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
section[data-testid="stMain"] { overflow: hidden !important; height: 100vh; }
section[data-testid="stMain"] > div { overflow: hidden !important; }
div[data-testid="stMainBlockContainer"], div.block-container {
  padding: 0 !important; max-width: none !important; width: 100%; min-height: 100vh;
}
/* error jangan pernah tertutup panggung */
[data-testid="stException"], [data-testid="stAlert"][data-testid*="error"], .stError {
  position: relative; z-index: 999 !important;
}

/* Posisi HUD dipilih lewat PENANDA kelas (tahan terhadap perubahan DOM
   antar versi Streamlit), bukan urutan anak.

   Struktur DOM Streamlit (1.65): stMainBlockContainer hanya berisi SATU
   stVerticalBlock, dan setiap elemen utama terbungkus lagi dalam satu wrapper
   (stElementContainer untuk markdown, stLayoutWrapper untuk columns/fragment/
   container). Karena itu selektor di bawah menarget ANAK LANGSUNG stVerticalBlock
   (level "> div > div"), BUKAN anak langsung stMainBlockContainer. Versi lama
   yang menarget "stMainBlockContainer > div:has(style)" justru mengenai
   stVerticalBlock induk lalu menyembunyikan SELURUH aplikasi (layar hitam). */
div[data-testid="stElementContainer"][data-stale="true"] { opacity: 1 !important; transition: none !important; }
div[data-testid="stElementContainer"]:has(style),
div[data-testid="stMainBlockContainer"] > div > div:has(style) { display: none; }
div[data-testid="stMainBlockContainer"] > div > div:has(.office-wrap) {
  position: fixed; inset: 0; z-index: 1;
}
div[data-testid="stMainBlockContainer"] > div > div:has(iframe) {
  position: fixed; inset: 0; z-index: 1;
}
div[data-testid="stMainBlockContainer"] > div > div:has(iframe) iframe {
  width: 100% !important; height: 100vh !important; border: 0; display: block;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-top) {
  position: fixed; top: 0; left: 0; right: 0; z-index: 30;
  background: color-mix(in srgb, var(--bg) 78%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--line);
  padding: 6px 10px !important;
}
@keyframes hud-gradient {
  0% { background-position: 0% 50%; }
  100% { background-position: 100% 50%; }
}
/* bar bawah ala "liquid navigation": pil gelap melayang di tengah */
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) {
  position: fixed;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;

  width: fit-content;
  max-width: calc(100vw - 16px);

  /* Gradient lebih gelap dan elegan */
  background: linear-gradient(
    90deg,
    #B58A36 0%,
    #387D50 25%,
    #286F76 45%,
    #B96F48 70%,
    #A85578 100%
  );

  background-size: 200% 200%;
  animation: hud-gradient 6s ease infinite alternate;

  /* Garis tepi mengikuti bentuk kapsul */
  border: 1px solid rgba(255, 255, 255, 0.65);
  border-radius: 50px;

  /* Bayangan lebih lembut */
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.08),
    0 10px 28px rgba(0, 0, 0, 0.28);

  box-sizing: border-box;
  padding: 26px 16px 10px !important;
  overflow-x: auto;
  scrollbar-width: none;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) div[data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important; width: max-content; gap: 6px !important;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) [data-testid="stColumn"],
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) [data-testid="column"] {
  width: auto !important; min-width: 44px; flex: 0 0 auto !important;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.drawer-head) {
  position: fixed; top: 54px; right: 8px; bottom: 84px; z-index: 40;
  width: min(560px, 96%); overflow-y: auto; overflow-x: hidden;
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  backdrop-filter: blur(12px); border: 1px solid var(--line); border-radius: 16px;
  padding: 12px 14px; box-shadow: 0 18px 60px rgba(2,6,23,.5);
}
div[data-testid="stMainBlockContainer"] > div > div:has(.drawer-head) [data-testid="stVerticalBlock"] { gap: .4rem; }

/* Fallback browser tua tanpa :has() — pakai urutan anak dari stVerticalBlock.
   Urutan anak: 1,2 = blok <style> CSS (disembunyikan), 3 = panggung kantor,
   4 = bar atas, 5 = bar bawah, 6 = drawer (hanya saat terbuka). */
@supports not (selector(:has(*))) {
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(1),
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(2) { display: none; }
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(3) { position: fixed; inset: 0; z-index: 1; }
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(4) {
    position: fixed; top: 0; left: 0; right: 0; z-index: 30;
    background: color-mix(in srgb, var(--bg) 78%, transparent);
    backdrop-filter: blur(10px); border-bottom: 1px solid var(--line);
    padding: 6px 10px !important;
  }
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(5) {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 30;
    background: color-mix(in srgb, var(--bg) 78%, transparent);
    backdrop-filter: blur(10px); border-top: 1px solid var(--line);
    padding: 6px 10px !important; overflow-x: auto;
  }
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(6) {
    position: fixed; top: 54px; right: 8px; bottom: 84px; z-index: 40;
    width: min(560px, 96%); overflow-y: auto; overflow-x: hidden;
    background: color-mix(in srgb, var(--panel) 92%, transparent);
    backdrop-filter: blur(12px); border: 1px solid var(--line); border-radius: 16px;
    padding: 12px 14px;
  }
  div[data-testid="stMainBlockContainer"] > div > div:nth-child(6):empty { display: none; }
}

/* panggung memenuhi layar (wrapper DAN inner fixed, supaya tahan DOM apa pun) */
.office-wrap {
  border: none; border-radius: 0; background: transparent;
  height: 100vh; position: fixed; inset: 0; z-index: 1;
}
.office-svg { width: 100%; height: 100vh; display: block; }

/* tombol HUD bulat (pakai descendant: di Streamlit 1.65 tombol terbungkus
   span tooltip di dalam .stButton, jadi "> button" tidak akan match) */
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-top) .stButton button,
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button {
  width: 40px; height: 40px; padding: 0; border-radius: 12px;
  display: inline-flex; align-items: center; justify-content: center;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) [data-testid="stColumn"]:first-child [data-testid="stVerticalBlock"] > div:first-child {
  display: none !important;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button {
  width: 44px; height: 44px; border-radius: 50%; background: transparent;
  border: none; box-shadow: none; color: #FFFFFF; transform: translateY(-6px);
  transition: transform .35s cubic-bezier(.34,1.56,.64,1), background .25s, box-shadow .25s;
}
/* hover: ikon naik keluar dari bar, lingkaran putih mengambang terpisah */
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button:hover {
  background: #FFFFFF; color: #15151D; border: none;
  transform: translateY(-20px); box-shadow: 0 10px 18px rgba(0,0,0,.35);
}
/* item aktif: lingkaran putih seperti gelembung cair */
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button[kind="primary"],
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button[data-testid="stBaseButton-primary"] {
  background: #FFFFFF; color: #15151D; border: none;
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button[kind="primary"]:hover,
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button[data-testid="stBaseButton-primary"]:hover {
  transform: translateY(-20px);
}
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-top) p,
div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) p { margin: 0; }
.hud-bottom { height: 0; }
.brand-line { display: flex; align-items: center; gap: 8px; min-height: 40px; }
.brand-line b { font-size: 14px; letter-spacing: .01em; }

/* drawer rapi */
.drawer-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.drawer-head h3 { margin: 0; font-size: 16px; }

/* layar sempit: perkecil */
@media (max-width: 720px) {
  div[data-testid="stMainBlockContainer"] > div > div:has(.drawer-head) { top: 50px; bottom: 54px; }
  div[data-testid="stMainBlockContainer"] > div > div:has(.hud-top) .stButton button,
  div[data-testid="stMainBlockContainer"] > div > div:has(.hud-bottom) .stButton button { width: 40px; height: 40px; }
  .brand-line .tiny { display: none; }
}

/* PONSEL POTRAIT: putar paksa menjadi landscape */
@media (orientation: portrait) and (max-width: 900px) {
  html, body { overflow: hidden !important; }
  section[data-testid="stMain"] {
    position: fixed !important; top: 0; left: 100vw;
    width: 100vh; height: 100vw;
    transform: rotate(90deg); transform-origin: top left;
  }
}
"""


# ----------------------------------------------------------------------------- dasar
def css() -> None:
    cfg = load_config()
    # CSS dikirim lewat st.markdown(unsafe_allow_html=True), bukan st.html:
    # st.html menyaring HTML dengan DOMPurify dan MEMBUANG tag <style>, sehingga
    # tema & tata letak HUD tidak pernah diterapkan. Blok <style> adalah HTML
    # block mentah sehingga karakter CSS seperti "*" di [attr*="..."] aman.
    st.markdown(f"<style>{base_css(get_theme(cfg.get('theme', 'night')))}</style>", unsafe_allow_html=True)
    st.markdown(f"<style>{HUD_CSS}</style>", unsafe_allow_html=True)


def S() -> dict[str, Any]:
    if "office_state" not in st.session_state:
        st.session_state.office_state = engine.tick(load_state())
    return st.session_state.office_state


def persist() -> None:
    save_state(st.session_state.office_state)


def toast(text: str, icon_name: str = "info") -> None:
    st.toast(text, icon=mat(icon_name))


def cfg() -> dict[str, Any]:
    return load_config()


def emp_name(state: dict[str, Any], eid: str) -> str:
    emp = state.get("employees", {}).get(eid, {})
    return emp.get("name", eid)


def emp_options(state: dict[str, Any]) -> tuple[list[str], list[str]]:
    ids, labels = [], []
    for eid, emp in state.get("employees", {}).items():
        ids.append(eid)
        room = ROOMS.get(emp.get("room", ""), None)
        labels.append(f"{emp.get('name')} — {emp.get('role_label')} · {room.name if room else '-'}")
    return ids, labels


def eid_from_label(ids: list[str], labels: list[str], pick: str | None, fallback_index: int = 0) -> str:
    if pick in labels:
        return ids[labels.index(pick)]
    dipilih = st.session_state.get("selected_emp")
    if dipilih in ids:
        return dipilih
    if ids:
        return ids[min(max(fallback_index, 0), len(ids) - 1)]
    return ""


def open_drawer(name: str | None) -> None:
    st.session_state["drawer"] = name
    st.rerun()


# ----------------------------------------------------------------------------- panggung
def stage_badges(state: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for msg in state.get("inbox", []):
        if not msg.get("read"):
            out["reception"] = out.get("reception", 0) + 1
    for task in state.get("tasks", []):
        if task.get("status") == TASK_REVIEW:
            emp = state.get("employees", {}).get(task.get("assignee", ""), {})
            rid = emp.get("room") or task.get("room") or "code"
            out[rid] = out.get(rid, 0) + 1
    return out

@st.fragment(run_every=2.0)
def stage() -> None:
    state = S()
    engine.tick(state)
    render_stage_3d(
        ROOMS,
        state.get("employees", {}),
        boss_name=cfg().get("boss_name", "Bos"),
        badges=stage_badges(state),
        debug=True
    )

# ----------------------------------------------------------------------------- HUD bar
def top_bar() -> None:
    state = S()
    configuration = cfg()
    summ = engine.summary(state)
    st.markdown(
        f'<div class="brand-line hud-top">{icon_svg("apartment", 20, "var(--accent)")}'
        f'<div><b>{APP_NAME}</b><div class="tiny">{configuration.get("boss_name", "Bos")} · '
        f'hari ke-{summ["day"]} · {chip(str(summ["pending"]), "warn", "hourglass_bottom", 11)} '
        f'{chip(str(summ["inbox_unread"]), "bad" if summ["inbox_unread"] else "muted", "mark_chat_unread", 11)}</div></div></div>',
        unsafe_allow_html=True,
    )


def bottom_bar() -> None:
    """Semua tombol di bawah: fitur dulu, lalu tombol ruang."""
    summ = engine.summary(S())
    fitur = [("fitur", slug, icon_name, judul) for slug, icon_name, judul in TOPBAR]
    ruang = [("ruang", rid, ROOMS[rid].icon, ROOMS[rid].name) for rid in ROOM_ORDER]
    semua = fitur + ruang
    cols = st.columns(len(semua), gap="small", vertical_alignment="center")
    for i, (col, (jenis, kunci, icon_name, judul)) in enumerate(zip(cols, semua)):
        with col:
            if i == 0:
                st.markdown('<div class="hud-bottom"></div>', unsafe_allow_html=True)
            if jenis == "fitur":
                badge = ""
                if kunci == "approval" and summ["pending"]:
                    badge = f" ({summ['pending']})"
                if kunci == "inbox" and summ["inbox_unread"]:
                    badge = f" ({summ['inbox_unread']})"
                aktif = st.session_state.get("drawer") == kunci
                if st.button(
                    " ",
                    key=f"fb_{kunci}",
                    icon=mat(icon_name),
                    help=f"{judul}{badge}",
                    type="primary" if aktif else "secondary",
                    use_container_width=True,
                ):
                    open_drawer(None if aktif else kunci)
            else:
                aktif = st.session_state.get("selected_room") == kunci and st.session_state.get("drawer") == "kantor"
                if st.button(
                    " ",
                    key=f"bb_{kunci}",
                    icon=mat(icon_name),
                    help=judul,
                    type="primary" if aktif else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["selected_room"] = kunci
                    open_drawer("kantor")


def drawer() -> None:
    name = st.session_state.get("drawer")
    if not name:
        st.container()  # placeholder anak ke-5 supaya posisi CSS tetap
        return
    with st.container():
        judul = {slug: label for slug, _, label in TOPBAR}.get(name, "Kantor")
        c1, c2 = st.columns([6, 1])
        c1.markdown(f'<div class="drawer-head"><h3>{judul}</h3></div>', unsafe_allow_html=True)
        if c2.button(" ", icon=mat("close"), key="drawer_close", help="Tutup panel"):
            open_drawer(None)
        if name == "kantor":
            room_detail()
        elif name == "tugas":
            panel_tugas()
        elif name == "inbox":
            panel_inbox()
        elif name == "approval":
            panel_persetujuan()
        elif name == "karyawan":
            panel_karyawan()
        elif name == "github":
            panel_github()
        elif name == "apps":
            panel_apps()
        elif name == "models":
            panel_models()
        elif name == "settings":
            panel_settings()


# ----------------------------------------------------------------------------- drawer: kantor
def room_detail() -> None:
    state = S()
    rid = st.session_state.get("selected_room", "") or "code"
    room = ROOMS[rid]
    people = [e for e in state.get("employees", {}).values() if e.get("room") == rid]
    tasks = [t for t in state.get("tasks", []) if t.get("room") == rid and t.get("status") not in ("arsip",)]
    st.markdown(
        f'<div class="card accent"><div class="row between">'
        f'<div>{labeled(room.icon, f"<b>{room.name}</b>", 18)}'
        f'<div class="small" style="margin-top:4px">{room.desc}</div></div>'
        f'<div class="row">{chip(f"{len(people)} karyawan", "", "badge")}'
        f'{chip(f"{len(tasks)} tugas aktif", "", "assignment")}</div></div></div>',
        unsafe_allow_html=True,
    )
    if people:
        for emp in people:
            st.markdown(
                f'<div class="card soft" style="margin-bottom:8px">'
                f'<div class="row between"><b>{emp["name"]}</b>'
                f'{chip(state_label(emp.get("state", "")), "", EMP_ICON.get(emp.get("state", ""), "widgets"), 14)}</div>'
                f'<div class="tiny">{emp.get("role_label")} · <span class="mono">{emp.get("model")}</span></div>'
                f'{progress_row("energi", emp.get("energy", 90), "ok")}'
                f'{progress_row("mood", emp.get("mood", 80), "warn")}'
                f"</div>",
                unsafe_allow_html=True,
            )
            b1, b2, b3 = st.columns(3)
            if b1.button("Istirahatkan", icon=mat("local_cafe"), key=f"rd_break_{emp['eid']}", use_container_width=True):
                engine.send_to_break(state, emp["eid"])
                persist()
                st.rerun()
            if b2.button("Panggil", icon=mat("directions_run"), key=f"rd_call_{emp['eid']}", use_container_width=True):
                engine.recall_employee(state, emp["eid"])
                persist()
                st.rerun()
            if b3.button("Profil", icon=mat("badge"), key=f"rd_prof_{emp['eid']}", use_container_width=True):
                st.session_state["selected_emp"] = emp["eid"]
                open_drawer("karyawan")
    else:
        st.markdown('<div class="small">Ruangan ini sedang kosong.</div>', unsafe_allow_html=True)
    st.markdown(section("Log aktivitas", "timeline"), unsafe_allow_html=True)
    for row in state.get("log", [])[:8]:
        st.markdown(f'<div class="tiny" style="margin-bottom:5px">{labeled("play_arrow", row["text"], 12)}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------- beri tugas
def panel_tugas() -> None:
    state = S()
    ids, labels = emp_options(state)
    with st.form("form_tugas", clear_on_submit=False):
        a, b = st.columns([2, 1])
        title = a.text_input("Judul tugas", placeholder="mis. Perbaiki bug tombol kirim di Room Chat")
        deliverable = b.selectbox("Bentuk keluaran", DELIVERABLES, index=0)
        brief = st.text_area(
            "Brief untuk karyawan",
            height=110,
            placeholder="Jelaskan apa yang harus dikerjakan, batasan, dan hasil yang diharapkan.",
        )
        c1, c2, c3 = st.columns([2, 1, 1])
        default_emp = suggested_employee(deliverable)
        emp_idx = ids.index(default_emp) if default_emp in ids else 0
        chosen = c1.selectbox("Karyawan", labels, index=emp_idx)
        priority = c2.selectbox("Prioritas", PRIORITIES, index=1)
        room_choice = c3.selectbox("Ruang", ["(ikut karyawan)"] + [ROOMS[r].name for r in ROOM_ORDER], index=0)
        use_repo = st.checkbox("Sertakan konteks repo GitHub", value=bool(get_key("github")))
        repo_pick = ""
        files_pick = ""
        if use_repo:
            g = cfg().get("github", {})
            repos = g.get("repos", [])
            repo_pick = st.selectbox("Repo", repos or ["-"], index=0)
            files_pick = st.text_input("File dibaca (pisahkan koma)", placeholder="app.py, utils.py")
        submitted = st.form_submit_button("Kirim tugas", type="primary", icon=mat("send"), use_container_width=True)

    if submitted:
        if not title or not brief:
            st.warning("Judul dan brief wajib diisi.")
        else:
            eid = eid_from_label(ids, labels, chosen, emp_idx)
            room_map = {ROOMS[r].name: r for r in ROOM_ORDER}
            room_id = room_map.get(room_choice, "")
            context = ""
            if use_repo and repo_pick and repo_pick != "-":
                g = cfg().get("github", {})
                with st.spinner("Mengambil konteks repo dari GitHub..."):
                    try:
                        context = gh.build_context(
                            g.get("owner", ""),
                            repo_pick,
                            branch=g.get("branch", ""),
                            include_files=[f.strip() for f in files_pick.split(",") if f.strip()],
                        )
                    except Exception as exc:  # pragma: no cover
                        context = f"(konteks repo gagal diambil: {exc})"
            state, task = engine.create_task(
                state,
                title=title,
                brief=brief,
                assignee=eid,
                deliverable=deliverable,
                priority=priority,
                room=room_id,
                repo_context=context,
            )
            persist()
            toast(f"Tugas dikirim ke {emp_name(state, eid)}", "assignment")
            st.rerun()

    st.markdown(section("Antrean pekerjaan", "precision_manufacturing"), unsafe_allow_html=True)
    queue = [t for t in state.get("tasks", []) if t.get("status") in (TASK_QUEUED, TASK_WORKING)]
    if not queue:
        st.markdown('<div class="card soft"><span class="small">Tidak ada tugas berjalan.</span></div>', unsafe_allow_html=True)
    for task in queue:
        st.markdown(
            f'<div class="task-item"><div class="row between"><span class="t">{task["title"]}</span>'
            f'{chip(task["status"], "warn", task.get("state_icon", "schedule"))}</div>'
            f'<div class="tiny">{emp_name(state, task["assignee"])} · {task["deliverable"]} · {task["priority"]}</div>'
            f'{bar(task.get("progress", 0) * 100)}</div>',
            unsafe_allow_html=True,
        )
    if queue and st.button("Jalankan semua antrean", type="primary", icon=mat("play_arrow"), use_container_width=True):
        for task in queue:
            with st.spinner(f"{emp_name(state, task['assignee'])} mengerjakan: {task['title']}"):
                engine.run_task(state, task["tid"])
        persist()
        st.rerun()


# ----------------------------------------------------------------------------- inbox
def panel_inbox() -> None:
    state = S()
    ids, labels = emp_options(state)
    top = st.columns([1, 1])
    if top[0].button("Simulasi pesan masuk", icon=mat("mark_chat_unread"), use_container_width=True):
        engine.simulate_incoming(state)
        persist()
        st.rerun()
    if top[1].button("Tandai semua dibaca", icon=mat("mark_email_read"), use_container_width=True):
        for msg in state.get("inbox", []):
            msg["read"] = True
        persist()
        st.rerun()
    with st.form("pesan_manual"):
        pc = st.columns([1, 1])
        sender = pc[0].text_input("Pengirim", "Klien")
        channel = pc[1].selectbox("Kanal", ["email", "chat", "telepon", "form web"])
        subject = st.text_input("Subjek", "")
        body = st.text_area("Isi pesan", height=60)
        if st.form_submit_button("Kirim ke ruang penerima pesan", icon=mat("send"), use_container_width=True):
            engine.push_inbox(state, sender or "Anonim", subject or "(tanpa subjek)", body, channel)
            persist()
            st.rerun()

    inbox = state.get("inbox", [])
    if not inbox:
        st.info("Kotak pesan kosong. Tekan 'Simulasi pesan masuk' untuk meramaikan.")
        return
    for msg in inbox[:15]:
        subj = f"<b>{msg['subject']}</b>"
        ch_icon = "alternate_email" if msg.get("channel") == "email" else "forum"
        when = time.strftime("%d %b %H:%M", time.localtime(msg.get("at", 0)))
        st.markdown(
            f'<div class="card {"soft" if msg.get("read") else "warn"}">'
            f'<div class="row between">{labeled(ch_icon, subj, 15)}'
            f'{chip(msg.get("channel", ""), "", "language", 12)}</div>'
            f'<div class="tiny">dari {msg.get("sender")} · {when}</div>'
            f'<div class="small" style="margin-top:6px">{msg.get("body", "")}</div></div>',
            unsafe_allow_html=True,
        )
        b1, b2, b3 = st.columns([1, 2, 1])
        if b1.button("Dibaca", key=f"read_{msg['mid']}", icon=mat("check"), use_container_width=True):
            engine.mark_read(state, msg["mid"])
            persist()
            st.rerun()
        pick = b2.selectbox("Delegasikan ke", labels, key=f"deleg_{msg['mid']}", label_visibility="collapsed")
        if b3.button("Jadikan tugas", key=f"task_{msg['mid']}", icon=mat("assignment"), type="primary", use_container_width=True):
            eid = eid_from_label(ids, labels, pick)
            engine.delegate_message(state, msg["mid"], eid)
            persist()
            toast("Pesan diubah menjadi tugas", "assignment")
            st.rerun()


# ----------------------------------------------------------------------------- persetujuan
def task_card(state: dict[str, Any], task: dict[str, Any], approve_key: str) -> None:
    emp = state.get("employees", {}).get(task["assignee"], {})
    dur_chip = chip(f"{task.get('duration', 0)} dtk", "muted", "schedule", 12)
    st.markdown(
        f'<div class="task-item"><div class="row between"><span class="t">{task["title"]}</span>'
        f'{chip(task["status"], "warn" if task["status"] == TASK_REVIEW else "", task.get("state_icon", "assignment"))}</div>'
        f'<div class="row" style="margin:4px 0 8px">'
        f'{chip(emp.get("name", "-"), "", "badge", 12)}'
        f'{chip(task.get("provider_used") or "-", "muted", "hub", 12)}'
        f'{chip(task.get("model_used") or "-", "muted", "memory", 12)}'
        f'{dur_chip}</div>'
        f'<div class="tiny">Brief: {task["brief"][:220]}</div></div>',
        unsafe_allow_html=True,
    )
    if task.get("error"):
        st.error(f"Model gagal: {task['error']}")
    if task.get("result"):
        st.markdown(f'<div class="task-result">{task["result"]}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("Setujui", key=f"ok_{approve_key}", type="primary", icon=mat("task_alt"), use_container_width=True):
        engine.approve_task(state, task["tid"], st.session_state.get(f"note_{approve_key}", ""), 5)
        persist()
        toast("Tugas disetujui", "task_alt")
        st.rerun()
    if c2.button("Tolak / revisi", key=f"no_{approve_key}", icon=mat("edit"), use_container_width=True):
        note = st.session_state.get(f"note_{approve_key}", "")
        engine.reject_task(state, task["tid"], note, rerun=True)
        persist()
        toast("Dikembalikan untuk diperbaiki", "edit")
        st.rerun()
    st.text_input("Catatan untuk karyawan", key=f"note_{approve_key}", placeholder="mis. Ringkas lagi bagian instalasi")


def panel_persetujuan() -> None:
    state = S()
    pending = engine.tasks_by_status(state, TASK_REVIEW)
    st.markdown(f'<div class="small">{len(pending)} hasil kerja menunggu keputusan Anda.</div>', unsafe_allow_html=True)
    if not pending:
        st.success("Tidak ada pekerjaan yang menunggu. Kantor berjalan lancar.")
    for task in pending:
        with st.expander(f"{task['title']} — {emp_name(state, task['assignee'])}", expanded=True):
            task_card(state, task, task["tid"])

    st.markdown(section("Riwayat keputusan", "history"), unsafe_allow_html=True)
    history = engine.tasks_by_status(state, TASK_APPROVED, TASK_REJECTED, TASK_FAILED)
    if not history:
        st.markdown('<div class="card soft"><span class="small">Belum ada riwayat.</span></div>', unsafe_allow_html=True)
    for task in history[:10]:
        tone = "ok" if task["status"] == TASK_APPROVED else "bad"
        st.markdown(
            f'<div class="card soft"><div class="row between">'
            f'<span>{labeled(task.get("state_icon", "assignment"), task["title"], 14)}</span>'
            f'{chip(task["status"], tone, task.get("state_icon", ""), 12)}</div>'
            f'<div class="tiny">{emp_name(state, task["assignee"])} · '
            f'{time.strftime("%d %b %H:%M", time.localtime(task.get("decided_at") or task.get("finished_at") or 0))}'
            f'{" · " + task["boss_note"] if task.get("boss_note") else ""}</div></div>',
            unsafe_allow_html=True,
        )


# ----------------------------------------------------------------------------- karyawan
def panel_karyawan() -> None:
    state = S()
    ids, labels = emp_options(state)
    default_index = 0
    if st.session_state.get("selected_emp") in ids:
        default_index = ids.index(st.session_state["selected_emp"])
    pick = st.selectbox("Pilih karyawan", labels, index=default_index, key="emp_pick")
    eid = eid_from_label(ids, labels, pick)
    st.session_state.selected_emp = eid
    if not eid:
        st.warning("Roster belum termuat.")
        return
    emp = state["employees"][eid]
    name_html = f"<b>{emp['name']}</b>"
    level_chip = chip(f"Level {emp.get('level', 1)}", "ok", "military_tech")
    done_chip = chip(f"{emp.get('tasks_done', 0)} selesai", "", "task_alt")
    st.markdown(
        f'<div class="card accent"><div class="row between"><div>'
        f'{labeled("badge", name_html, 18)}'
        f'<div class="small">{emp.get("title")} · {ROOMS.get(emp.get("room"), None).name if ROOMS.get(emp.get("room")) else "-"}</div>'
        f'<div class="tiny" style="margin-top:4px">{emp.get("personality")}</div></div>'
        f'<div class="row">{chip(state_label(emp.get("state", "")), "", EMP_ICON.get(emp.get("state", ""), "widgets"))}'
        f'{level_chip}'
        f'{done_chip}</div></div></div>',
        unsafe_allow_html=True,
    )
    c = st.columns(3)
    c[0].markdown(progress_row("Energi", emp.get("energy", 90), "ok"), unsafe_allow_html=True)
    c[1].markdown(progress_row("Mood", emp.get("mood", 80), "warn"), unsafe_allow_html=True)
    c[2].markdown(progress_row("XP", emp.get("xp", 0) % 100, "ok"), unsafe_allow_html=True)
    st.markdown(f'<div class="small">Kebiasaan: {", ".join(emp.get("quirks", []))}</div>', unsafe_allow_html=True)

    b = st.columns(2)
    if b[0].button("Istirahatkan", icon=mat("local_cafe"), use_container_width=True):
        engine.send_to_break(state, eid)
        persist()
        st.rerun()
    if b[1].button("Panggil ke meja", icon=mat("directions_run"), use_container_width=True):
        engine.recall_employee(state, eid)
        persist()
        st.rerun()

    st.markdown(section("Model yang dipakai", "memory"), unsafe_allow_html=True)
    provider = st.selectbox(
        "Provider",
        PROVIDER_ORDER,
        index=PROVIDER_ORDER.index(emp.get("provider", "groq")) if emp.get("provider") in PROVIDER_ORDER else 0,
        key=f"prov_{eid}",
    )
    catalogue = models_for(provider)
    keys = list(catalogue)
    default_idx = keys.index(emp.get("model", "")) if emp.get("model", "") in keys else 0
    chosen = st.selectbox(
        "Model",
        keys,
        index=default_idx,
        format_func=lambda m: f"{catalogue[m]['label']} — {catalogue[m]['cost']}",
        key=f"model_{eid}",
    )
    if st.button("Terapkan model", type="primary", icon=mat("save"), use_container_width=True):
        emp["model"] = chosen
        emp["provider"] = provider
        persist()
        toast(f"{emp['name']} kini memakai {chosen}", "memory")
        st.rerun()
    st.markdown(f'<div class="small">Catatan: {catalogue[chosen]["note"]}<br>'
                f'Fallback: {", ".join(emp.get("fallbacks", [])) or "-"}</div>', unsafe_allow_html=True)

    st.markdown(section("Ajak mengobrol", "forum"), unsafe_allow_html=True)
    for row in state.get("chats", {}).get(eid, [])[-6:]:
        who = cfg().get("boss_name", "Bos") if row["who"] == "boss" else emp["name"]
        st.markdown(f'<div class="card soft"><b>{who}</b><div class="small">{row["text"]}</div></div>', unsafe_allow_html=True)
    with st.form(f"chat_{eid}"):
        text = st.text_input("Katakan sesuatu", placeholder="mis. Bagaimana progres ruang kode hari ini?")
        if st.form_submit_button("Kirim", type="primary", icon=mat("send")):
            if text:
                with st.spinner(f"{emp['name']} mengetik..."):
                    engine.chat_with_employee(state, eid, text)
                persist()
                st.rerun()


# ----------------------------------------------------------------------------- github
def panel_github() -> None:
    g = cfg().get("github", {})
    if not get_key("github"):
        st.warning("GITHUB_TOKEN belum diisi. Buka Pengaturan → 'Isi kunci langsung di sini'.")
    else:
        try:
            me = gh.whoami()
            me_title = f"<b>Terhubung sebagai {me['login'] or '?'}</b>"
            me_repos = f"{me['public_repos']} repo publik"
            st.markdown(
                f'<div class="card ok"><div class="row between">'
                f'{labeled("github", me_title, 16)}'
                f'<div class="row">{chip(me_repos, "", "folder", 12)}'
                f'{chip(me["plan"] or "akun gratis", "muted", "badge", 12)}</div></div></div>',
                unsafe_allow_html=True,
            )
        except gh.GitHubError as exc:
            st.error(f"Token terisi tapi GitHub menolak: {exc}")
    with st.form("gh_cfg"):
        c = st.columns([2, 1])
        owner = c[0].text_input("Owner / username", g.get("owner", ""))
        branch = c[1].text_input("Branch", g.get("branch", "main"))
        repos_txt = st.text_input("Repo (pisahkan koma)", ", ".join(g.get("repos", [])))
        if st.form_submit_button("Simpan konfigurasi", type="primary", icon=mat("save")):
            update_config(
                github={
                    "owner": owner.strip(),
                    "branch": branch.strip() or "main",
                    "repos": [r.strip() for r in repos_txt.split(",") if r.strip()],
                }
            )
            toast("Konfigurasi GitHub disimpan", "save")
            st.rerun()
    t1, t2 = st.columns(2)
    if t1.button("Sinkronkan repo", icon=mat("sync"), use_container_width=True):
        with st.spinner("Membaca repo dari GitHub..."):
            try:
                rows = gh.list_repos(owner, limit=100)
                update_config(github={"repos": [r["name"] for r in rows[:20]]})
                toast(f"{len(rows)} repo terbaca", "github")
            except Exception as exc:
                st.error(f"Gagal: {exc}")
        st.rerun()
    if t2.button("Cek rate limit", icon=mat("speed"), use_container_width=True):
        try:
            rl = gh.rate_limit()
            st.info(f"Sisa {rl['remaining']} dari {rl['limit']} permintaan per jam.")
        except Exception as exc:
            st.error(str(exc))

    owner_now = cfg().get("github", {}).get("owner", "")
    for repo in cfg().get("github", {}).get("repos", []):
        with st.expander(f"{owner_now}/{repo}", expanded=False):
            try:
                detail = gh.repo_detail(owner_now, repo)
                stars_chip = chip(f"{detail['stars']} bintang", "", "star")
                issues_chip = chip(f"{detail['open_issues']} isu", "warn", "bug_report")
                st.markdown(
                    f'<div class="row">{chip(detail["language"], "", "code")}'
                    f'{stars_chip}'
                    f'{issues_chip}'
                    f'{chip(detail["default_branch"], "muted", "alt_route")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**Commit terakhir**")
                for commit in gh.commits(owner_now, repo, limit=5):
                    commit_head = f"{commit['sha']} — {commit['message']}"
                    st.markdown(
                        f'<div class="card soft" style="padding:6px 10px">{labeled("commit", commit_head, 13)}'
                        f'<div class="tiny">{commit["author"]} · {commit["date"][:10]}</div></div>',
                        unsafe_allow_html=True,
                    )
                items = gh.issues(owner_now, repo, limit=5)
                if items:
                    st.markdown("**Isu & PR terbuka**")
                    for item in items:
                        icon_name = "merge_type" if item.get("is_pr") else "bug_report"
                        item_title = f"#{item['number']} {item['title']}"
                        st.markdown(f'<div class="tiny">{labeled(icon_name, item_title, 12)}</div>', unsafe_allow_html=True)
                tree = gh.file_tree(owner_now, repo, detail["default_branch"], limit=40)
                if tree:
                    st.markdown("**Berkas utama**")
                    st.dataframe(
                        [{"path": t["path"], "byte": t["size"]} for t in tree[:25]],
                        use_container_width=True,
                        hide_index=True,
                        height=180,
                    )
            except Exception as exc:
                st.error(f"Tidak bisa membaca repo ini: {exc}")


# ----------------------------------------------------------------------------- aplikasi streamlit
def panel_apps() -> None:
    rows = apps_mod.apps()
    s = apps_mod.summary(rows)
    c = st.columns(4)
    c[0].markdown(stat_block("apps", s["total"], "Total"), unsafe_allow_html=True)
    c[1].markdown(stat_block("verified", s["hidup"], "Hidup", "ok"), unsafe_allow_html=True)
    c[2].markdown(stat_block("error", s["mati"], "Bermasalah", "bad"), unsafe_allow_html=True)
    c[3].markdown(stat_block("schedule", s["belum_dicek"], "Belum dicek"), unsafe_allow_html=True)
    if rows:
        for i, row in enumerate(rows):
            st.markdown(
                f'<div class="card soft"><div class="row between"><b>{row.get("name")}</b>'
                f'{chip(row.get("status", "belum dicek"), "ok" if row.get("status") == "hidup" else ("bad" if row.get("status") not in ("belum dicek", "") else "muted"), "language", 12)}</div>'
                f'<div class="tiny mono">{row.get("url") or "tanpa URL"} · repo: {row.get("repo") or "-"} · {row.get("latency_ms", 0)} ms</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Hapus", icon=mat("close"), key=f"app_del_{i}"):
                apps_mod.remove_app(i)
                toast("Aplikasi dihapus", "close")
                st.rerun()
    with st.form("app_add"):
        c = st.columns([2, 3, 2])
        name = c[0].text_input("Nama aplikasi")
        url = c[1].text_input("URL deploy")
        repo = c[2].text_input("Repo terkait")
        if st.form_submit_button("Tambah aplikasi", type="primary", icon=mat("add"), use_container_width=True):
            if name or url:
                apps_mod.add_app(name, url, repo)
                st.rerun()
    b1, b2 = st.columns(2)
    if b1.button("Cek status semua", type="primary", icon=mat("monitor_heart"), use_container_width=True):
        with st.spinner("Memeriksa setiap aplikasi..."):
            apps_mod.check_all()
        st.rerun()
    if b2.button("Simpan perubahan", icon=mat("save"), use_container_width=True):
        toast("Daftar aplikasi disimpan", "save")


# ----------------------------------------------------------------------------- model & provider
def panel_models() -> None:
    st.markdown(
        f'<div class="small">Katalog diverifikasi {VERIFIED_AT}. Probe mengecek ulang katalog live tiap provider.</div>',
        unsafe_allow_html=True,
    )
    health = provider_health()
    for provider in PROVIDER_ORDER:
        meta = PROVIDERS[provider]
        info = health[provider]
        tone = "ok" if info["key_present"] else "bad"
        prov_title = f"<b>{meta['label']}</b>"
        catalog_chip = chip(f"{info['catalog_count']} model", "muted", "memory", 11)
        st.markdown(
            f'<div class="card" style="border-top:3px solid {meta["color"]}">'
            f'{labeled("key" if info["key_present"] else "lock", prov_title, 16)}'
            f'<div class="small" style="margin-top:4px">{meta["tagline"]}</div>'
            f'<div class="row" style="margin-top:6px">{chip(info["key_env"], tone, "key", 11)}'
            f'{catalog_chip}</div>'
            f'<div class="tiny" style="margin-top:6px">Gratis: {meta["free_tier"]}</div></div>',
            unsafe_allow_html=True,
        )
    if st.button("Probe katalog live", type="primary", icon=mat("sync"), use_container_width=True):
        with st.spinner("Memeriksa katalog tiap provider..."):
            results = probe_all(use_cache=False)
        for provider, res in results.items():
            if res["ok"]:
                st.success(
                    f"{PROVIDERS[provider]['label']}: {len(res['ids'])} model terdaftar, "
                    f"{len(res['live'])} hidup." + (f" Mati: {', '.join(res['dead'])}" if res.get("dead") else "")
                )
            else:
                st.warning(f"{PROVIDERS[provider]['label']}: {res['error'] or 'tidak bisa diverifikasi'}")

    st.markdown(section("Uji panggilan nyata", "bolt"), unsafe_allow_html=True)
    test_provider = st.selectbox("Provider", PROVIDER_ORDER, key="test_provider")
    test_model = st.selectbox("Model", list(models_for(test_provider)), key="test_model")
    if st.button("Uji sekarang", type="primary", icon=mat("bolt"), use_container_width=True):
        with st.spinner("Menghubungi model..."):
            result = test_key(test_provider, test_model)
        if result["ok"]:
            st.success(f"Berhasil dalam {result['latency']} detik. Balasan: {result['reply']}")
        else:
            st.error(result["error"])

    st.markdown(section("Katalog lengkap", "inventory_2"), unsafe_allow_html=True)
    status = live_models()
    table = []
    for mid, meta in MODELS.items():
        table.append(
            {
                "model": mid,
                "provider": PROVIDERS[meta["provider"]]["label"],
                "konteks": f"{meta['context'] // 1000}K",
                "biaya": meta["cost"],
                "live": "hidup" if status.get(mid) else "belum terverifikasi",
            }
        )
    st.dataframe(table, use_container_width=True, hide_index=True, height=300)
    with st.expander("Model yang sengaja tidak dipakai"):
        st.dataframe(
            [{"model": k, "alasan": v} for k, v in RETIRED.items()],
            use_container_width=True,
            hide_index=True,
            height=220,
        )


# ----------------------------------------------------------------------------- pengaturan
def panel_settings() -> None:
    configuration = cfg()
    with st.form("settings"):
        c = st.columns(2)
        boss = c[0].text_input("Nama bos", configuration.get("boss_name", ""))
        company = c[1].text_input("Nama perusahaan", configuration.get("company", ""))
        c2 = st.columns(2)
        theme_name = c2[0].selectbox("Tema", ["night", "day"], index=0 if configuration.get("theme") == "night" else 1)
        auto = c2[1].checkbox("Auto-refresh panggung", value=configuration.get("auto_refresh", True))
        if st.form_submit_button("Simpan", type="primary", icon=mat("save")):
            update_config(boss_name=boss, company=company, theme=theme_name, auto_refresh=auto)
            toast("Pengaturan disimpan", "save")
            st.rerun()

    st.markdown(section("Isi kunci langsung di sini", "key", "Tersimpan ke .streamlit/secrets.toml di server ini."), unsafe_allow_html=True)
    with st.form("form_secrets", clear_on_submit=True):
        sc = st.columns(2)
        g = sc[0].text_input("GROQ_API_KEY", type="password", placeholder="gsk_...")
        o = sc[0].text_input("OPENROUTER_API_KEY", type="password", placeholder="sk-or-v1-...")
        a = sc[1].text_input("AION_API_KEY", type="password", placeholder="aion_...")
        t = sc[1].text_input("GITHUB_TOKEN", type="password", placeholder="github_pat_...")
        if st.form_submit_button("Simpan kunci", type="primary", icon=mat("key"), use_container_width=True):
            written = write_secrets_file(
                {"GROQ_API_KEY": g, "OPENROUTER_API_KEY": o, "AION_API_KEY": a, "GITHUB_TOKEN": t}
            )
            if written:
                toast(f"Kunci disimpan: {', '.join(written)}", "key")
            else:
                st.info("Tidak ada kunci baru yang diisi.")
            st.rerun()

    st.markdown(section("Status kunci API", "key"), unsafe_allow_html=True)
    for provider in PROVIDER_ORDER + ["github"]:
        meta = PROVIDERS.get(provider)
        label = meta["label"] if meta else "GitHub"
        env = meta["key_env"] if meta else "GITHUB_TOKEN"
        tone = "ok" if has_key(provider) else "bad"
        st.markdown(
            f'<div class="card soft">{labeled("key" if has_key(provider) else "lock", label, 15)} '
            f'{chip("terisi" if has_key(provider) else "kosong", tone, "", 11)}'
            f'<div class="tiny mono">{env}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown(section("Data & cadangan", "storage"), unsafe_allow_html=True)
    c = st.columns(3)
    if c[0].button("Ekspor", icon=mat("download"), use_container_width=True):
        path = export_snapshot()
        toast(f"Snapshot: {path}", "download")
    if c[1].button("Muat ulang", icon=mat("refresh"), use_container_width=True):
        st.session_state.office_state = load_state()
        st.rerun()
    if c[2].button("Reset kantor", type="primary", icon=mat("restart_alt"), use_container_width=True):
        st.session_state.office_state = reset_state()
        toast("Kantor direset", "refresh")
        st.rerun()
    st.caption(f"Versi {VERSION} · state di data/office_state.json")


# ----------------------------------------------------------------------------- kerangka
def main() -> None:
    css()                      # anak 1 (style, disembunyikan CSS)
    stage()                    # anak 2: panggung full-screen
    top_bar()                  # anak 3: bar atas
    bottom_bar()               # anak 4: bar ruang
    drawer()                   # anak 5: panel fitur


main()

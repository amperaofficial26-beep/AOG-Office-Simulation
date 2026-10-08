"""AOG Virtual Office — game simulasi kantor berisi karyawan model AI.

Jalankan:  streamlit run app.py
Kunci API dibaca dari .streamlit/secrets.toml atau environment variable.
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

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")

DELIVERABLES = [
    "kode", "perbaikan bug", "riset", "artikel", "konten",
    "desain", "laporan", "deployment", "balasan pesan", "dokumen",
]
PRIORITIES = ["rendah", "normal", "tinggi"]


# ----------------------------------------------------------------------------- dasar
def css() -> None:
    cfg = load_config()
    st.markdown(f"<style>{base_css(get_theme(cfg.get('theme', 'night')))}</style>", unsafe_allow_html=True)


def S() -> dict[str, Any]:
    """State kantor tunggal per sesi."""
    if "office_state" not in st.session_state:
        st.session_state.office_state = engine.tick(load_state())
    return st.session_state.office_state


def persist() -> None:
    save_state(st.session_state.office_state)


def toast(text: str, icon_name: str = "info") -> None:
    st.toast(text, icon=mat(icon_name))
    st.session_state.setdefault("flash", []).append((icon_name, text))


def flash_bar() -> None:
    items = st.session_state.get("flash", [])
    for icon_name, text in items[-3:]:
        st.markdown(
            f'<div class="card accent fade-in" style="padding:8px 12px;margin-bottom:8px">'
            f'{labeled(icon_name, text, 16)}</div>',
            unsafe_allow_html=True,
        )
    st.session_state.flash = []


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
    """Ubah pilihan selectbox menjadi id karyawan.

    Selalu mengembalikan id yang valid: bila widget mengembalikan None (mis. saat
    diuji otomatis) dipakai karyawan terpilih di session_state, lalu indeks fallback.
    """
    if pick in labels:
        return ids[labels.index(pick)]
    dipilih = st.session_state.get("selected_emp")
    if dipilih in ids:
        return dipilih
    if ids:
        return ids[min(max(fallback_index, 0), len(ids) - 1)]
    return ""


# ----------------------------------------------------------------------------- kantor
@st.fragment(run_every=2.0)
def office_stage(selected_room: str, selected_emp: str) -> None:
    state = S()
    engine.tick(state)
    configuration = cfg()
    st.markdown(
        render_office(
            state,
            theme=configuration.get("theme", "night"),
            selected_room=selected_room,
            selected_emp=selected_emp,
        ),
        unsafe_allow_html=True,
    )


def room_buttons() -> None:
    state = S()
    cols = st.columns(5)
    for i, rid in enumerate(ROOM_ORDER):
        room = ROOMS[rid]
        unread = sum(
            1
            for m in state.get("inbox", [])
            if not m.get("read") and rid == "reception"
        ) + sum(
            1
            for t in state.get("tasks", [])
            if t.get("status") == TASK_REVIEW
            and (state.get("employees", {}).get(t.get("assignee", ""), {}) or {}).get("room") == rid
        )
        with cols[i % 5]:
            label = room.name + (f" ({unread})" if unread else "")
            if st.button(
                label,
                key=f"room_{rid}",
                icon=mat(room.icon),
                use_container_width=True,
                type="primary" if st.session_state.get("selected_room") == rid else "secondary",
            ):
                st.session_state.selected_room = rid
                st.rerun()


def room_detail() -> None:
    state = S()
    rid = st.session_state.get("selected_room", "")
    if not rid:
        st.markdown('<div class="card soft"><span class="small">Pilih salah satu ruangan untuk melihat isinya.</span></div>', unsafe_allow_html=True)
        return
    room = ROOMS[rid]
    people = [e for e in state.get("employees", {}).values() if e.get("room") == rid]
    tasks = [t for t in state.get("tasks", []) if t.get("room") == rid and t.get("status") not in ("arsip",)]
    st.markdown(
        f'<div class="card accent"><div class="row between">'
        f'<div>{labeled(room.icon, f"<b>{room.name}</b>", 20)}'
        f'<div class="small" style="margin-top:4px">{room.desc}</div></div>'
        f'<div class="row">{chip(f"{len(people)} karyawan", "", "badge")}{chip(f"{len(tasks)} tugas aktif", "", "assignment")}'
        f'{chip(f"{room.gw}x{room.gh} petak", "muted", "widgets")}</div></div></div>',
        unsafe_allow_html=True,
    )
    if people:
        cols = st.columns(min(4, len(people)))
        for i, emp in enumerate(people):
            with cols[i % len(cols)]:
                st.markdown(
                    f'<div class="card soft" style="margin-bottom:8px">'
                    f'<div class="row between"><b>{emp["name"]}</b>{chip(state_label(emp.get("state", "")), "", EMP_ICON.get(emp.get("state", ""), "widgets"), 14)}</div>'
                    f'<div class="tiny">{emp.get("role_label")}</div>'
                    f'<div class="tiny mono" style="margin:4px 0">{emp.get("model")}</div>'
                    f'{progress_row("energi", emp.get("energy", 90), "ok")}'
                    f'{progress_row("mood", emp.get("mood", 80), "warn")}'
                    f"</div>",
                    unsafe_allow_html=True,
                )
    else:
        st.markdown('<div class="small">Ruangan ini sedang kosong.</div>', unsafe_allow_html=True)
    st.markdown(room_legend([rid]), unsafe_allow_html=True)


def panel_kantor() -> None:
    state = S()
    summ = engine.summary(state)
    c = st.columns(6)
    c[0].markdown(stat_block("supervisor_account", summ["employees"], "Karyawan"), unsafe_allow_html=True)
    c[1].markdown(stat_block("hourglass_bottom", summ["pending"], "Menunggu Anda", "warn" if summ["pending"] else ""), unsafe_allow_html=True)
    c[2].markdown(stat_block("mark_chat_unread", summ["inbox_unread"], "Pesan baru", "bad" if summ["inbox_unread"] else ""), unsafe_allow_html=True)
    c[3].markdown(stat_block("task_alt", summ["stats"].get("tasks_done", 0), "Tugas selesai", "ok"), unsafe_allow_html=True)
    c[4].markdown(stat_block("api", summ["stats"].get("api_calls", 0), "Panggilan model"), unsafe_allow_html=True)
    c[5].markdown(stat_block("rocket_launch", summ["releases"], "Rilis"), unsafe_allow_html=True)

    room_buttons()
    office_stage(st.session_state.get("selected_room", ""), st.session_state.get("selected_emp", ""))
    st.markdown(room_legend(), unsafe_allow_html=True)
    room_detail()


# ----------------------------------------------------------------------------- beri tugas
def panel_tugas() -> None:
    state = S()
    ids, labels = emp_options(state)
    st.markdown(section("Beri tugas baru", "assignment", "Karyawan akan mengerjakannya dengan model AI miliknya, lalu hasilnya masuk antrean persetujuan Anda."), unsafe_allow_html=True)
    with st.form("form_tugas", clear_on_submit=False):
        a, b = st.columns([2, 1])
        title = a.text_input("Judul tugas", placeholder="mis. Perbaiki bug tombol kirim di Room Chat")
        deliverable = b.selectbox("Bentuk keluaran", DELIVERABLES, index=0)
        brief = st.text_area(
            "Brief untuk karyawan",
            height=120,
            placeholder="Jelaskan apa yang harus dikerjakan, batasan, dan hasil yang diharapkan.",
        )
        c1, c2, c3 = st.columns([2, 1, 1])
        default_emp = suggested_employee(deliverable)
        emp_idx = ids.index(default_emp) if default_emp in ids else 0
        chosen = c1.selectbox("Karyawan", labels, index=emp_idx)
        priority = c2.selectbox("Prioritas", PRIORITIES, index=1)
        room_choice = c3.selectbox("Ruang kerja", ["(ikut karyawan)"] + [ROOMS[r].name for r in ROOM_ORDER], index=0)
        use_repo = st.checkbox("Sertakan konteks repo GitHub (butuh GITHUB_TOKEN)", value=bool(get_key("github")))
        repo_pick = ""
        files_pick = ""
        if use_repo:
            g = cfg().get("github", {})
            repos = g.get("repos", [])
            repo_pick = st.selectbox("Repo", repos or ["-"], index=0)
            files_pick = st.text_input("File yang perlu dibaca (pisahkan dengan koma)", placeholder="app.py, utils.py")
        submitted = st.form_submit_button("Kirim tugas", type="primary", icon=mat("send"), use_container_width=True)

    if submitted:
        if not title or not brief:
            st.warning("Judul dan brief wajib diisi.")
            return
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
        st.session_state.setdefault("queue", []).append(task["tid"])
        st.rerun()

    st.markdown(section("Antrean pekerjaan", "precision_manufacturing"), unsafe_allow_html=True)
    queue = [t for t in state.get("tasks", []) if t.get("status") in (TASK_QUEUED, TASK_WORKING)]
    if not queue:
        st.markdown('<div class="card soft"><span class="small">Tidak ada tugas yang sedang berjalan.</span></div>', unsafe_allow_html=True)
    for task in queue:
        st.markdown(
            f'<div class="task-item"><div class="row between"><span class="t">{task["title"]}</span>'
            f'{chip(task["status"], "warn", task.get("state_icon", "schedule"))}</div>'
            f'<div class="tiny">{emp_name(state, task["assignee"])} · {task["deliverable"]} · {task["priority"]}</div>'
            f'{bar(task.get("progress", 0) * 100)}</div>',
            unsafe_allow_html=True,
        )
    if st.button("Jalankan semua antrean sekarang", type="primary", icon=mat("play_arrow")):
        for task in queue:
            with st.spinner(f"{emp_name(state, task['assignee'])} mengerjakan: {task['title']}"):
                engine.run_task(state, task["tid"])
        persist()
        st.rerun()


# ----------------------------------------------------------------------------- inbox
def panel_inbox() -> None:
    state = S()
    ids, labels = emp_options(state)
    top = st.columns([1, 1, 3])
    if top[0].button("Simulasi pesan masuk", icon=mat("mark_chat_unread"), use_container_width=True):
        engine.simulate_incoming(state)
        persist()
        st.rerun()
    if top[1].button("Tandai semua dibaca", icon=mat("mark_email_read"), use_container_width=True):
        for msg in state.get("inbox", []):
            msg["read"] = True
        persist()
        st.rerun()
    with top[2].form("pesan_manual"):
        pc = st.columns([1, 1, 2])
        sender = pc[0].text_input("Pengirim", "Klien")
        channel = pc[1].selectbox("Kanal", ["email", "chat", "telepon", "form web"])
        subject = pc[2].text_input("Subjek", "")
        body = st.text_area("Isi pesan", height=70)
        if st.form_submit_button("Kirim ke ruang penerima pesan", icon=mat("send"), use_container_width=True):
            engine.push_inbox(state, sender or "Anonim", subject or "(tanpa subjek)", body, channel)
            persist()
            st.rerun()

    inbox = state.get("inbox", [])
    if not inbox:
        st.info("Kotak pesan masih kosong. Tekan 'Simulasi pesan masuk' untuk meramaikan.")
        return
    for msg in inbox[:25]:
        tone = "" if msg.get("read") else "warn"
        with st.container(border=False):
            st.markdown(
                f'<div class="card {"soft" if msg.get("read") else "warn"}">'
                f'<div class="row between">{labeled("alternate_email" if msg.get("channel") == "email" else "forum", f"<b>{msg["subject"]}</b>", 16)}'
                f'{chip(msg.get("channel", ""), tone, "language", 13)}</div>'
                f'<div class="tiny">dari {msg.get("sender")} · {time.strftime("%d %b %H:%M", time.localtime(msg.get("at", 0)))}</div>'
                f'<div class="small" style="margin-top:6px">{msg.get("body", "")}</div></div>',
                unsafe_allow_html=True,
            )
            b1, b2, b3 = st.columns([1, 2, 1])
            if b1.button("Tandai dibaca", key=f"read_{msg['mid']}", icon=mat("check"), use_container_width=True):
                engine.mark_read(state, msg["mid"])
                persist()
                st.rerun()
            pick = b2.selectbox(
                "Delegasikan ke",
                labels,
                key=f"deleg_{msg['mid']}",
                label_visibility="collapsed",
            )
            if b3.button("Jadikan tugas", key=f"task_{msg['mid']}", icon=mat("assignment"), use_container_width=True, type="primary"):
                eid = eid_from_label(ids, labels, pick)
                engine.delegate_message(state, msg["mid"], eid)
                persist()
                toast("Pesan diubah menjadi tugas", "assignment")
                st.rerun()


# ----------------------------------------------------------------------------- persetujuan
def task_card(state: dict[str, Any], task: dict[str, Any], approve_key: str) -> None:
    emp = state.get("employees", {}).get(task["assignee"], {})
    st.markdown(
        f'<div class="task-item"><div class="row between"><span class="t">{task["title"]}</span>'
        f'{chip(task["status"], "warn" if task["status"] == TASK_REVIEW else "", task.get("state_icon", "assignment"))}</div>'
        f'<div class="row" style="margin:4px 0 8px">'
        f'{chip(emp.get("name", "-"), "", "badge", 13)}'
        f'{chip(task.get("provider_used") or "-", "muted", "hub", 13)}'
        f'{chip(task.get("model_used") or "-", "muted", "memory", 13)}'
        f'{chip(f"{task.get('duration', 0)} dtk", "muted", "schedule", 13)}'
        f'{chip(f"{task.get('tokens_out', 0)} token keluar", "muted", "functions", 13)}'
        f'</div>'
        f'<div class="tiny">Brief: {task["brief"][:260]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if task.get("error"):
        st.error(f"Model gagal: {task['error']}")
    if task.get("result"):
        st.markdown(f'<div class="task-result">{task["result"]}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 2])
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
    c3.text_input("Catatan untuk karyawan", key=f"note_{approve_key}", placeholder="mis. Ringkas lagi bagian instalasi")


def panel_persetujuan() -> None:
    state = S()
    pending = engine.tasks_by_status(state, TASK_REVIEW)
    st.markdown(
        section("Menunggu persetujuan Anda", "approval", f"{len(pending)} hasil kerja menunggu keputusan bos."),
        unsafe_allow_html=True,
    )
    if not pending:
        st.success("Tidak ada pekerjaan yang menunggu. Kantor berjalan lancar.")
    for task in pending:
        with st.expander(f"{task['title']} — {emp_name(state, task['assignee'])}", expanded=len(pending) == 1):
            task_card(state, task, task["tid"])

    st.markdown(section("Riwayat keputusan", "history"), unsafe_allow_html=True)
    history = engine.tasks_by_status(state, TASK_APPROVED, TASK_REJECTED, TASK_FAILED)
    if not history:
        st.markdown('<div class="card soft"><span class="small">Belum ada riwayat.</span></div>', unsafe_allow_html=True)
    for task in history[:12]:
        tone = "ok" if task["status"] == TASK_APPROVED else "bad"
        st.markdown(
            f'<div class="card soft"><div class="row between">'
            f'<span>{labeled(task.get("state_icon", "assignment"), task["title"], 15)}</span>'
            f'{chip(task["status"], tone, task.get("state_icon", ""), 13)}</div>'
            f'<div class="tiny">{emp_name(state, task["assignee"])} · {time.strftime("%d %b %H:%M", time.localtime(task.get("decided_at") or task.get("finished_at") or 0))}'
            f'{" · catatan: " + task["boss_note"] if task.get("boss_note") else ""}</div></div>',
            unsafe_allow_html=True,
        )


# ----------------------------------------------------------------------------- karyawan
def panel_karyawan() -> None:
    state = S()
    st.markdown(section("Tim Anda", "diversity_3", "Setiap karyawan memakai model AI sendiri. Anda bisa mengganti modelnya kapan saja."), unsafe_allow_html=True)
    ids, labels = emp_options(state)
    default_index = 0
    if st.session_state.get("selected_emp") in ids:
        default_index = ids.index(st.session_state["selected_emp"])
    pick = st.selectbox("Pilih karyawan", labels, index=default_index, key="emp_pick")
    eid = eid_from_label(ids, labels, pick)
    st.session_state.selected_emp = eid
    if not eid:
        st.warning("Roster belum termuat. Muat ulang halaman atau reset kantor dari panel Pengaturan.")
        return
    emp = state["employees"][eid]
    st.markdown(
        f'<div class="card accent"><div class="row between"><div>'
        f'{labeled("badge", f"<b>{emp['name']}</b>", 20)}'
        f'<div class="small">{emp.get("title")} · {ROOMS.get(emp.get("room"), None).name if ROOMS.get(emp.get("room")) else "-"}</div>'
        f'<div class="tiny" style="margin-top:4px">{emp.get("personality")}</div></div>'
        f'<div class="row">{chip(state_label(emp.get("state", "")), "", EMP_ICON.get(emp.get("state", ""), "widgets"))}'
        f'{chip(f"Level {emp.get('level', 1)}", "ok", "military_tech")}{chip(f"{emp.get('tasks_done', 0)} tugas selesai", "", "task_alt")}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    c = st.columns(3)
    c[0].markdown(progress_row("Energi", emp.get("energy", 90), "ok"), unsafe_allow_html=True)
    c[1].markdown(progress_row("Mood", emp.get("mood", 80), "warn"), unsafe_allow_html=True)
    c[2].markdown(progress_row(f"XP ke level berikutnya", (emp.get("xp", 0) % 100), "ok"), unsafe_allow_html=True)
    st.markdown(f'<div class="small">Kebiasaan: {", ".join(emp.get("quirks", []))}</div>', unsafe_allow_html=True)

    b = st.columns(4)
    if b[0].button("Istirahatkan", icon=mat("local_cafe"), use_container_width=True):
        engine.send_to_break(state, eid)
        persist()
        st.rerun()
    if b[1].button("Panggil ke meja", icon=mat("directions_run"), use_container_width=True):
        engine.recall_employee(state, eid)
        persist()
        st.rerun()
    if b[2].button("Sapa", icon=mat("waving_hand"), use_container_width=True):
        engine.push_inbox(state, cfg().get("boss_name", "Bos"), f"Halo {emp['name']}", "Semangat kerja hari ini ya.", "chat")
        persist()
        st.rerun()
    if b[3].button("Tugaskan cepat", type="primary", icon=mat("assignment"), use_container_width=True):
        st.session_state.selected_emp = eid
        st.session_state.page = "Beri Tugas"
        st.rerun()

    st.markdown(section("Model yang dipakai", "memory"), unsafe_allow_html=True)
    provider = st.selectbox(
        "Provider",
        PROVIDER_ORDER,
        index=PROVIDER_ORDER.index(emp.get("provider", "groq")) if emp.get("provider") in PROVIDER_ORDER else 0,
        key=f"prov_{eid}",
    )
    catalogue = models_for(provider)
    current = emp.get("model", "")
    keys = list(catalogue)
    default_idx = keys.index(current) if current in keys else 0
    chosen = st.selectbox(
        "Model",
        keys,
        index=default_idx,
        format_func=lambda m: f"{catalogue[m]['label']} — {catalogue[m]['cost']}",
        key=f"model_{eid}",
    )
    if st.button("Terapkan model", type="primary", icon=mat("save")):
        emp["model"] = chosen
        emp["provider"] = provider
        persist()
        toast(f"{emp['name']} sekarang memakai {chosen}", "memory")
        st.rerun()
    st.markdown(f'<div class="small">Catatan model: {catalogue[chosen]["note"]}<br>'
                f'Fallback otomatis bila gagal: {", ".join(emp.get("fallbacks", [])) or "-"}</div>', unsafe_allow_html=True)

    st.markdown(section("Ajak mengobrol", "forum", "Karyawan menjawab dengan model miliknya."), unsafe_allow_html=True)
    log = state.get("chats", {}).get(eid, [])
    for row in log[-8:]:
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
    st.markdown(section("Integrasi GitHub", "github", "Repo Anda dibaca langsung dari API GitHub. Token hanya dipakai di sisi server."), unsafe_allow_html=True)
    if not get_key("github"):
        st.warning("GITHUB_TOKEN belum diisi. Isi lewat form 'Isi kunci langsung di sini' di panel Pengaturan, atau sunting `.streamlit/secrets.toml`.")
    else:
        try:
            me = gh.whoami()
            st.markdown(
                f'<div class="card ok"><div class="row between">'
                f'{labeled("github", f"<b>Terhubung sebagai {me['login'] or '?'}</b>", 18)}'
                f'<div class="row">{chip(f"{me['public_repos']} repo publik", "", "folder", 13)}'
                f'{chip(me["plan"] or "akun gratis", "muted", "badge", 13)}</div></div>'
                f'<div class="tiny" style="margin-top:4px">Token aktif — repo, commit, isu, dan PR dibaca live.</div></div>',
                unsafe_allow_html=True,
            )
        except gh.GitHubError as exc:
            st.error(f"Token terisi tapi GitHub menolak: {exc}")
    with st.form("gh_cfg"):
        c = st.columns(3)
        owner = c[0].text_input("Owner / username", g.get("owner", ""))
        branch = c[1].text_input("Branch default", g.get("branch", "main"))
        repos_txt = c[2].text_input("Repo (pisahkan koma)", ", ".join(g.get("repos", [])))
        if st.form_submit_button("Simpan konfigurasi", type="primary", icon=mat("save")):
            update_config(
                github={
                    "owner": owner.strip(),
                    "branch": branch.strip() or "main",
                    "repos": [r.strip() for r in repos_txt.split(",") if r.strip()],
                }
            )
            st.rerun()

    t1, t2 = st.columns(2)
    if t1.button("Sinkronkan semua repo", icon=mat("sync"), use_container_width=True):
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
                st.markdown(
                    f'<div class="row">{chip(detail["language"], "", "code")}'
                    f'{chip(f"{detail['stars']} bintang", "", "star")}'
                    f'{chip(f"{detail['open_issues']} issue terbuka", "warn", "bug_report")}'
                    f'{chip(detail["default_branch"], "muted", "alt_route")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**Commit terakhir**")
                for commit in gh.commits(owner_now, repo, limit=6):
                    st.markdown(
                        f'<div class="card soft" style="padding:6px 10px">{labeled("commit", f"{commit['sha']} — {commit['message']}", 14)}'
                        f'<div class="tiny">{commit["author"]} · {commit["date"][:10]}</div></div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("**Isu & PR terbuka**")
                items = gh.issues(owner_now, repo, limit=6)
                if not items:
                    st.markdown('<div class="tiny">Tidak ada isu terbuka.</div>', unsafe_allow_html=True)
                for item in items:
                    icon_name = "merge_type" if item.get("is_pr") else "bug_report"
                    st.markdown(f'<div class="tiny">{labeled(icon_name, f"#{item["number"]} {item["title"]}", 13)}</div>', unsafe_allow_html=True)
                st.markdown("**Berkas utama**")
                tree = gh.file_tree(owner_now, repo, detail["default_branch"], limit=60)
                if tree:
                    st.dataframe(
                        [{"path": t["path"], "ukuran (byte)": t["size"]} for t in tree[:40]],
                        use_container_width=True,
                        hide_index=True,
                        height=220,
                    )
            except Exception as exc:
                st.error(f"Tidak bisa membaca repo ini: {exc}")


# ----------------------------------------------------------------------------- aplikasi streamlit
def panel_apps() -> None:
    st.markdown(section("Aplikasi Streamlit Anda", "rocket_launch", "Daftarkan URL deploy-nya, lalu karyawan bisa memantau mana yang hidup."), unsafe_allow_html=True)
    rows = apps_mod.apps()
    if rows:
        for i, row in enumerate(rows):
            c = st.columns([2, 3, 1.6, 1])
            c[0].text_input("Nama aplikasi", row.get("name", ""), key=f"app_name_{i}", label_visibility="collapsed", placeholder="Nama aplikasi")
            c[1].text_input("URL deploy", row.get("url", ""), key=f"app_url_{i}", label_visibility="collapsed", placeholder="https://nama-app.streamlit.app")
            c[2].text_input("Repo terkait", row.get("repo", ""), key=f"app_repo_{i}", label_visibility="collapsed", placeholder="nama repo")
            if c[3].button("Hapus", key=f"app_del_{i}", icon=mat("close"), use_container_width=True):
                rows = apps_mod.remove_app(i)
                toast("Aplikasi dihapus", "close")
                st.rerun()
            tone = "ok" if row.get("status") == "hidup" else ("bad" if row.get("status") not in ("belum dicek", "") else "muted")
            st.markdown(
                f'<div class="row">{chip(row.get("status", "belum dicek"), tone, "language", 13)}'
                f'{chip(f"{row.get('latency_ms', 0)} ms", "muted", "speed", 13)}'
                f'{chip(row.get("owner", "") or "tanpa penanggung jawab", "muted", "badge", 13)}</div>',
                unsafe_allow_html=True,
            )
    with st.form("app_add"):
        c = st.columns([2, 3, 2])
        name = c[0].text_input("Nama aplikasi")
        url = c[1].text_input("URL deploy")
        repo = c[2].text_input("Repo terkait")
        if st.form_submit_button("Tambah aplikasi", type="primary", icon=mat("add")):
            if name or url:
                apps_mod.add_app(name, url, repo)
                st.rerun()
    b1, b2 = st.columns(2)
    if b1.button("Cek status semua", use_container_width=True, type="primary", icon=mat("monitor_heart")):
        with st.spinner("Memeriksa setiap aplikasi..."):
            rows = apps_mod.check_all()
        st.rerun()
    if b2.button("Simpan perubahan", use_container_width=True, icon=mat("save")):
        updated = []
        for i, row in enumerate(rows):
            updated.append(
                {
                    **row,
                    "name": st.session_state.get(f"app_name_{i}", row.get("name")),
                    "url": st.session_state.get(f"app_url_{i}", row.get("url")),
                    "repo": st.session_state.get(f"app_repo_{i}", row.get("repo")),
                }
            )
        apps_mod.save_apps(updated)
        toast("Daftar aplikasi disimpan", "save")
        st.rerun()
    s = apps_mod.summary(rows)
    c = st.columns(5)
    c[0].markdown(stat_block("apps", s["total"], "Total app"), unsafe_allow_html=True)
    c[1].markdown(stat_block("verified", s["hidup"], "Hidup", "ok"), unsafe_allow_html=True)
    c[2].markdown(stat_block("error", s["mati"], "Bermasalah", "bad"), unsafe_allow_html=True)
    c[3].markdown(stat_block("link", s["tanpa_url"], "Tanpa URL", "warn"), unsafe_allow_html=True)
    c[4].markdown(stat_block("schedule", s["belum_dicek"], "Belum dicek"), unsafe_allow_html=True)


# ----------------------------------------------------------------------------- model & provider
def panel_models() -> None:
    st.markdown(
        section("Model & provider", "hub", f"Katalog diverifikasi pada {VERIFIED_AT}. Tombol probe memeriksa ulang katalog live."),
        unsafe_allow_html=True,
    )
    health = provider_health()
    cols = st.columns(len(PROVIDER_ORDER))
    for i, provider in enumerate(PROVIDER_ORDER):
        meta = PROVIDERS[provider]
        info = health[provider]
        with cols[i]:
            tone = "ok" if info["key_present"] else "bad"
            st.markdown(
                f'<div class="card" style="border-top:3px solid {meta["color"]}">'
                f'{labeled("key" if info["key_present"] else "lock", f"<b>{meta['label']}</b>", 18)}'
                f'<div class="small" style="margin-top:4px">{meta["tagline"]}</div>'
                f'<div class="tiny mono" style="margin:6px 0">{info["base_url"]}</div>'
                f'<div class="row">{chip(info["key_env"], tone, "key", 12)}'
                f'{chip(f"{info['catalog_count']} model", "muted", "memory", 12)}</div>'
                f'<div class="tiny" style="margin-top:6px">Batas gratis: {meta["free_tier"]}</div></div>',
                unsafe_allow_html=True,
            )
    if st.button("Probe katalog live sekarang", type="primary", icon=mat("sync")):
        with st.spinner("Memeriksa katalog tiap provider..."):
            results = probe_all(use_cache=False)
        for provider, res in results.items():
            if res["ok"]:
                st.success(
                    f"{PROVIDERS[provider]['label']}: {len(res['ids'])} model terdaftar, "
                    f"{len(res['live'])} dari katalog kita hidup."
                    + (f" Mati: {', '.join(res['dead'])}" if res.get("dead") else "")
                )
            else:
                st.warning(f"{PROVIDERS[provider]['label']}: {res['error'] or 'tidak bisa diverifikasi'}")
        st.rerun()

    st.markdown(section("Uji panggilan nyata", "bolt", "Kirim satu permintaan kecil untuk memastikan kunci + model benar-benar jalan."), unsafe_allow_html=True)
    test_provider = st.selectbox("Provider", PROVIDER_ORDER, key="test_provider")
    test_model = st.selectbox("Model", list(models_for(test_provider)), key="test_model")
    if st.button("Uji sekarang", type="primary", icon=mat("bolt")):
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
                "nama": meta["label"],
                "provider": PROVIDERS[meta["provider"]]["label"],
                "konteks": f"{meta['context'] // 1000}K",
                "biaya": meta["cost"],
                "verifikasi live": "hidup" if status.get(mid) else "belum terverifikasi",
                "catatan": meta["note"],
            }
        )
    st.dataframe(table, use_container_width=True, hide_index=True, height=360)

    st.markdown(section("Model yang sengaja tidak dipakai", "block", "Sudah dimatikan provider atau mendekati tanggal kedaluwarsa."), unsafe_allow_html=True)
    st.dataframe(
        [{"model": k, "alasan": v} for k, v in RETIRED.items()],
        use_container_width=True,
        hide_index=True,
        height=260,
    )


# ----------------------------------------------------------------------------- pengaturan
def panel_settings() -> None:
    configuration = cfg()
    st.markdown(section("Pengaturan kantor", "settings"), unsafe_allow_html=True)
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

    st.markdown(section("Isi kunci langsung di sini", "key", "Tersimpan ke .streamlit/secrets.toml di server ini. Kolom bertopeng, nilai lama tidak ditampilkan."), unsafe_allow_html=True)
    with st.form("form_secrets", clear_on_submit=True):
        sc = st.columns(2)
        g = sc[0].text_input("GROQ_API_KEY", type="password", placeholder="gsk_...")
        o = sc[0].text_input("OPENROUTER_API_KEY", type="password", placeholder="sk-or-v1-...")
        a = sc[1].text_input("AION_API_KEY", type="password", placeholder="aion_...")
        t = sc[1].text_input("GITHUB_TOKEN", type="password", placeholder="github_pat_...")
        if st.form_submit_button("Simpan kunci", type="primary", icon=mat("save")):
            written = write_secrets_file(
                {
                    "GROQ_API_KEY": g,
                    "OPENROUTER_API_KEY": o,
                    "AION_API_KEY": a,
                    "GITHUB_TOKEN": t,
                }
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
            f'<div class="card soft">{labeled("key" if has_key(provider) else "lock", label, 16)} '
            f'{chip("terisi" if has_key(provider) else "kosong", tone, "", 12)}'
            f'<div class="tiny mono">{env}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="card soft"><b>Contoh .streamlit/secrets.toml</b>'
        '<pre class="mono">GROQ_API_KEY = "gsk_..."\nOPENROUTER_API_KEY = "sk-or-..."\n'
        'AION_API_KEY = "aion_..."\nGITHUB_TOKEN = "github_pat_..."</pre></div>',
        unsafe_allow_html=True,
    )

    st.markdown(section("Data & cadangan", "storage"), unsafe_allow_html=True)
    c = st.columns(3)
    if c[0].button("Ekspor snapshot", icon=mat("download"), use_container_width=True):
        path = export_snapshot()
        toast(f"Snapshot disimpan di {path}", "download")
    if c[1].button("Muat ulang state dari disk", icon=mat("refresh"), use_container_width=True):
        st.session_state.office_state = load_state()
        st.rerun()
    if c[2].button("Reset kantor", use_container_width=True, type="primary", icon=mat("restart_alt")):
        st.session_state.office_state = reset_state()
        toast("Kantor direset", "refresh")
        st.rerun()
    st.caption(f"Versi {VERSION} · state disimpan di data/office_state.json")


# ----------------------------------------------------------------------------- kerangka
def sidebar() -> None:
    state = S()
    configuration = cfg()
    summ = engine.summary(state)
    st.markdown(
        f'<div style="padding:6px 0 10px">{labeled("apartment", f"<b>{APP_NAME}</b>", 22)}'
        f'<div class="tiny">{APP_TAGLINE}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="card soft">{labeled("supervisor_account", configuration.get("boss_name", "Bos"), 16)}'
        f'<div class="tiny">{configuration.get("company", "")} · hari ke-{summ["day"]}</div>'
        f'<div class="row" style="margin-top:6px">{chip(f"{summ['pending']} menunggu", "warn", "hourglass_bottom", 12)}'
        f'{chip(f"{summ['inbox_unread']} pesan", "bad" if summ["inbox_unread"] else "muted", "mark_chat_unread", 12)}</div></div>',
        unsafe_allow_html=True,
    )
    if not any(has_key(p) for p in PROVIDER_ORDER):
        st.markdown(
            f'<div class="card bad">{labeled("lock", "Belum ada API key", 15)}'
            '<div class="tiny">Isi GROQ_API_KEY / OPENROUTER_API_KEY / AION_API_KEY di secrets agar karyawan bisa bekerja sungguhan.</div></div>',
            unsafe_allow_html=True,
        )
    pages = ["Kantor", "Beri Tugas", "Kotak Pesan", "Persetujuan", "Karyawan", "GitHub", "Aplikasi Streamlit", "Model & Provider", "Pengaturan"]
    icons = ["apartment", "assignment", "mark_chat_unread", "approval", "diversity_3", "github", "rocket_launch", "hub", "settings"]
    st.session_state.setdefault("page", "Kantor")
    for page, icon_name in zip(pages, icons):
        badge = ""
        if page == "Persetujuan" and summ["pending"]:
            badge = f"  ({summ['pending']})"
        if page == "Kotak Pesan" and summ["inbox_unread"]:
            badge = f"  ({summ['inbox_unread']})"
        if st.button(
            f"{page}{badge}",
            key=f"nav_{page}",
            icon=mat(icon_name),
            use_container_width=True,
            type="primary" if st.session_state.page == page else "secondary",
        ):
            st.session_state.page = page
            st.rerun()

    st.markdown(section("Aktivitas kantor", "timeline"), unsafe_allow_html=True)
    for row in state.get("log", [])[:10]:
        st.markdown(
            f'<div class="tiny" style="margin-bottom:6px">'
            f'{labeled("play_arrow", row["text"], 12)}</div>',
            unsafe_allow_html=True,
        )


def main() -> None:
    css()
    flash_bar()
    sidebar()
    page = st.session_state.get("page", "Kantor")
    st.markdown(f"<h2 style='margin-bottom:2px'>{page}</h2>", unsafe_allow_html=True)
    if page == "Kantor":
        panel_kantor()
    elif page == "Beri Tugas":
        panel_tugas()
    elif page == "Kotak Pesan":
        panel_inbox()
    elif page == "Persetujuan":
        panel_persetujuan()
    elif page == "Karyawan":
        panel_karyawan()
    elif page == "GitHub":
        panel_github()
    elif page == "Aplikasi Streamlit":
        panel_apps()
    elif page == "Model & Provider":
        panel_models()
    else:
        panel_settings()


main()

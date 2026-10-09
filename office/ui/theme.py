"""Tema, CSS, dan komponen HTML kecil (tanpa emoji, semua ikon Material inline)."""
from __future__ import annotations

from ..icons import icon_svg

THEME = {
    "night": {
        "bg": "#0B1020",
        "panel": "#131A2E",
        "panel2": "#1B2440",
        "line": "#26314F",
        "text": "#E7ECF7",
        "muted": "#93A0BF",
        "accent": "#38BDF8",
        "accent2": "#FACC15",
        "ok": "#22C55E",
        "warn": "#FBBF24",
        "bad": "#F87171",
        "floor": "#151D33",
        "grid": "#20293F",
    },
    "day": {
        "bg": "#F4F7FC",
        "panel": "#FFFFFF",
        "panel2": "#EEF3FB",
        "line": "#DCE4F0",
        "text": "#0F172A",
        "muted": "#5B6B87",
        "accent": "#0284C7",
        "accent2": "#D97706",
        "ok": "#16A34A",
        "warn": "#D97706",
        "bad": "#DC2626",
        "floor": "#E7EDF7",
        "grid": "#D6DFEE",
    },
}


def theme(name: str = "night") -> dict[str, str]:
    return THEME.get(name, THEME["night"])


def base_css(t: dict[str, str]) -> str:
    """CSS inti aplikasi + seluruh keyframe animasi karakter."""
    return f"""
:root {{
  --bg: {t['bg']}; --panel: {t['panel']}; --panel2: {t['panel2']}; --line: {t['line']};
  --text: {t['text']}; --muted: {t['muted']}; --accent: {t['accent']};
  --accent2: {t['accent2']}; --ok: {t['ok']}; --warn: {t['warn']}; --bad: {t['bad']};
}}
html, body, [data-testid="stAppViewContainer"] {{ background: var(--bg) !important; }}
[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stAppViewContainer"] {{ font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif; color: var(--text); }}
[data-testid="stSidebar"] {{ background: var(--panel); border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] * {{ color: var(--text); }}
h1, h2, h3, h4 {{ color: var(--text) !important; letter-spacing: -0.01em; }}
p, span, li, label, div {{ color: inherit; }}
.small {{ color: var(--muted); font-size: 12px; line-height: 1.5; }}
.tiny {{ color: var(--muted); font-size: 11px; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}

/* ---------- kartu & panel ---------- */
.card {{
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 14px 16px; margin-bottom: 12px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.02) inset, 0 6px 18px rgba(2,6,23,0.25);
}}
.card.soft {{ background: var(--panel2); box-shadow: none; }}
.card.accent {{ border-left: 3px solid var(--accent); }}
.card.ok {{ border-left: 3px solid var(--ok); }}
.card.warn {{ border-left: 3px solid var(--warn); }}
.card.bad {{ border-left: 3px solid var(--bad); }}
.card h3 {{ margin: 0 0 6px; font-size: 15px; }}
.row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.row.between {{ justify-content: space-between; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }}
.grid3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}

/* ---------- badge & chip ---------- */
.chip {{
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 999px;
  background: var(--panel2); border: 1px solid var(--line); font-size: 12px; color: var(--text);
  white-space: nowrap;
}}
.chip.ok {{ color: var(--ok); border-color: color-mix(in srgb, var(--ok) 45%, transparent); }}
.chip.warn {{ color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, transparent); }}
.chip.bad {{ color: var(--bad); border-color: color-mix(in srgb, var(--bad) 45%, transparent); }}
.chip.muted {{ color: var(--muted); }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); display: inline-block; }}
.dot.ok {{ background: var(--ok); }} .dot.warn {{ background: var(--warn); }} .dot.bad {{ background: var(--bad); }}

/* ---------- statistik ---------- */
.stat {{ display: flex; gap: 10px; align-items: center; }}
.stat .num {{ font-size: 22px; font-weight: 700; line-height: 1.1; }}
.stat .lbl {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}

/* ---------- progress ---------- */
.bar {{ height: 6px; border-radius: 999px; background: var(--panel2); overflow: hidden; }}
.bar > i {{ display: block; height: 100%; background: var(--accent); border-radius: 999px;
  transition: width .5s ease; }}
.bar.thin {{ height: 4px; }}

/* ---------- tombol ---------- */
/* Pakai descendant selector: di Streamlit 1.65 tombol terbungkus span tooltip
   di dalam .stButton, sehingga ".stButton > button" tidak match. */
.stButton button, .stFormSubmitButton button {{
  border-radius: 10px; border: 1px solid var(--line); background: var(--panel2);
  color: var(--text); font-weight: 600; padding: 6px 14px;
}}
.stButton button:hover {{ border-color: var(--accent); color: var(--accent); }}
.stButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"] {{
  background: var(--accent); border-color: var(--accent); color: #06121f;
}}
div[data-testid="stMetricValue"] {{ font-size: 20px; }}

/* ---------- input ---------- */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {{
  background: var(--panel2) !important; color: var(--text) !important;
  border: 1px solid var(--line) !important; border-radius: 10px;
}}
[data-baseweb="select"] svg {{ fill: var(--muted); }}

/* ---------- panggung kantor ---------- */
.office-wrap {{
  width: 100%; overflow: hidden; border-radius: 16px; border: 1px solid var(--line);
  background: radial-gradient(120% 100% at 50% 0%, var(--panel2) 0%, var(--bg) 70%);
}}
.office-svg {{ width: 100%; height: auto; display: block; }}
.room-hit {{ fill: transparent; cursor: pointer; }}
.room-hit:hover {{ fill: rgba(56,189,248,0.10); }}
.char {{ cursor: pointer; }}
.char:hover .char-body {{ filter: brightness(1.12); }}
.nametag {{ font: 600 10px ui-sans-serif, system-ui, sans-serif; }}
.room-label {{ font: 700 12px ui-sans-serif, system-ui, sans-serif; letter-spacing: .04em; }}
.room-sub {{ font: 500 9px ui-sans-serif, system-ui, sans-serif; }}

/* ---------- animasi karakter ---------- */
@keyframes bob {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-1.6px); }} }}
@keyframes breathe {{ 0%,100% {{ transform: scaleY(1); }} 50% {{ transform: scaleY(1.035); }} }}
@keyframes blink {{ 0%,92%,100% {{ transform: scaleY(1); }} 96% {{ transform: scaleY(0.08); }} }}
@keyframes legSwing {{ 0%,100% {{ transform: rotate(17deg); }} 50% {{ transform: rotate(-17deg); }} }}
@keyframes armSwing {{ 0%,100% {{ transform: rotate(-14deg); }} 50% {{ transform: rotate(14deg); }} }}
@keyframes typeTap {{ 0%,100% {{ transform: rotate(-24deg); }} 50% {{ transform: rotate(-44deg); }} }}
@keyframes headNod {{ 0%,100% {{ transform: rotate(-2deg); }} 50% {{ transform: rotate(2deg); }} }}
@keyframes napTilt {{ 0%,100% {{ transform: rotate(-9deg) translateY(1px); }} 50% {{ transform: rotate(9deg) translateY(1px); }} }}
@keyframes zzz {{ 0% {{ opacity: 0; transform: translate(0,0) scale(.7); }}
  35% {{ opacity: 1; }} 100% {{ opacity: 0; transform: translate(9px,-16px) scale(1.1); }} }}
@keyframes sip {{ 0%,60%,100% {{ transform: rotate(-26deg); }} 75% {{ transform: rotate(-52deg); }} }}
@keyframes padPush {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(1.6px); }} }}
@keyframes talk {{ 0%,100% {{ transform: scale(1); opacity:.95; }} 50% {{ transform: scale(1.07); opacity: 1; }} }}
@keyframes glowPulse {{ 0%,100% {{ opacity: .35; }} 50% {{ opacity: .9; }} }}
@keyframes steamUp {{ 0% {{ opacity: .0; transform: translateY(0) scaleX(1); }}
  40% {{ opacity: .55; }} 100% {{ opacity: 0; transform: translateY(-10px) scaleX(1.5); }} }}
@keyframes screenFlicker {{ 0%,100% {{ opacity: .82; }} 50% {{ opacity: 1; }} }}
@keyframes codeScroll {{ 0% {{ transform: translateY(0); }} 100% {{ transform: translateY(-9px); }} }}
@keyframes statusPulse {{ 0%,100% {{ opacity: .25; r: 5; }} 50% {{ opacity: .8; r: 9; }} }}
@keyframes fadeSlide {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}

.char-body {{ animation: bob 2.6s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
.st-idle .char-body {{ animation: bob 3.4s ease-in-out infinite; }}
.st-work .char-body {{ animation: bob 1.1s ease-in-out infinite; }}
.st-walk .char-body {{ animation: bob .42s ease-in-out infinite; }}
.st-nap .char-body {{ animation: napTilt 3.6s ease-in-out infinite; }}
.st-coffee .char-body {{ animation: bob 3s ease-in-out infinite; }}
.st-game .char-body {{ animation: bob 1.4s ease-in-out infinite; }}

.torso {{ animation: breathe 3.2s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
.eye {{ animation: blink 5.2s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 50%; }}
.head {{ animation: headNod 4.4s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
.st-walk .head {{ animation: none; }}
.leg {{ transform-box: fill-box; transform-origin: 50% 0%; }}
.arm {{ transform-box: fill-box; transform-origin: 50% 8%; }}
.st-walk .leg.l1 {{ animation: legSwing .42s ease-in-out infinite; }}
.st-walk .leg.l2 {{ animation: legSwing .42s ease-in-out infinite reverse; }}
.st-walk .arm.a1 {{ animation: armSwing .42s ease-in-out infinite reverse; }}
.st-walk .arm.a2 {{ animation: armSwing .42s ease-in-out infinite; }}
.st-work .arm.a1 {{ animation: typeTap .34s ease-in-out infinite; }}
.st-work .arm.a2 {{ animation: typeTap .34s ease-in-out infinite .17s; }}
.st-coffee .arm.a1 {{ animation: sip 3.2s ease-in-out infinite; }}
.st-game .arm.a1 {{ animation: padPush .7s ease-in-out infinite; }}
.st-game .arm.a2 {{ animation: padPush .7s ease-in-out infinite .35s; }}
.zzz {{ animation: zzz 2.6s ease-in-out infinite; }}
.zzz.z2 {{ animation-delay: .9s; }} .zzz.z3 {{ animation-delay: 1.8s; }}
.steam {{ animation: steamUp 3s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
.steam.s2 {{ animation-delay: 1s; }} .steam.s3 {{ animation-delay: 2s; }}
.screen {{ animation: screenFlicker 2.8s ease-in-out infinite; }}
.codeline {{ animation: codeScroll 3.4s linear infinite; }}
.pulse {{ animation: statusPulse 1.8s ease-in-out infinite; }}
.bubble {{ animation: talk 2.2s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
.fade-in {{ animation: fadeSlide .35s ease-out both; }}

/* ---------- tugas ---------- */
.task-item {{ border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; margin-bottom: 8px;
  background: var(--panel2); }}
.task-item .t {{ font-weight: 600; font-size: 14px; }}
.task-result {{ background: var(--bg); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 12px; max-height: 340px; overflow: auto; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }}

/* ---------- tabel ---------- */
[data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}

/* ---------- scrollbar ---------- */
::-webkit-scrollbar {{ width: 9px; height: 9px; }}
::-webkit-scrollbar-thumb {{ background: var(--line); border-radius: 9px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
"""


def chip(text: str, tone: str = "", icon_name: str = "", size: int = 13) -> str:
    cls = f"chip {tone}".strip()
    ic = icon_svg(icon_name, size=size) if icon_name else ""
    return f'<span class="{cls}">{ic}<span>{text}</span></span>'


def stat_block(icon_name: str, value, label: str, tone: str = "") -> str:
    color = {"ok": "var(--ok)", "warn": "var(--warn)", "bad": "var(--bad)"}.get(tone, "var(--text)")
    return (
        '<div class="card soft" style="margin-bottom:0">'
        '<div class="stat">'
        f'<span style="color:{color}">{icon_svg(icon_name, 22)}</span>'
        f'<div><div class="num" style="color:{color}">{value}</div>'
        f'<div class="lbl">{label}</div></div></div></div>'
    )


def bar(pct: float, color: str = "var(--accent)", thin: bool = False) -> str:
    pct = max(0.0, min(100.0, float(pct)))
    cls = "bar thin" if thin else "bar"
    return f'<div class="{cls}"><i style="width:{pct:.0f}%;background:{color}"></i></div>'


def section(title: str, icon_name: str = "", sub: str = "") -> str:
    ic = icon_svg(icon_name, 17, color="var(--accent)") if icon_name else ""
    sub_html = f'<div class="tiny">{sub}</div>' if sub else ""
    return (
        f'<div style="display:flex;align-items:center;gap:8px;margin:16px 0 8px">'
        f"{ic}<h3 style=\"margin:0;font-size:15px\">{title}</h3></div>{sub_html}"
    )


def progress_row(label: str, pct: float, tone: str = "") -> str:
    color = {"ok": "var(--ok)", "warn": "var(--warn)", "bad": "var(--bad)"}.get(tone, "var(--accent)")
    return (
        f'<div style="margin-bottom:8px"><div class="row between" style="margin-bottom:4px">'
        f'<span class="tiny">{label}</span><span class="tiny">{pct:.0f}%</span></div>{bar(pct, color, thin=True)}</div>'
    )

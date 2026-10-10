"""Panggung kantor 3D (Three.js) untuk AOG Virtual Office.

Pengganti panggung SVG isometrik: ruangan, furnitur, dan karyawan digambar sebagai
objek 3D low-poly kartun dengan kamera orthographic miring (gaya Two Point Hospital).

Pemakaian di app.py (tidak berubah):

    from office.ui.stage3d import render_stage_3d
    render_stage_3d(ROOMS, employees_state, height=640)

- ``ROOMS``            : dict ``rid -> Room`` dari ``office/roster.py``
- ``employees_state``  : dict ``eid -> dict`` (hasil ``sync_employees``) atau daftar ``Employee``
- ``quality``          : "high" (bayangan lembut) atau "low" (tanpa bayangan, untuk perangkat lemah)

CARA KERJA (anti kedip)
-----------------------
Versi lama mengirim ulang seluruh HTML tiap fragmen dijalankan (2 detik). Begitu isi HTML
berubah sedikit saja, Streamlit memasang ulang iframe, Three.js dibuat ulang, dan layar berkedip.

Sekarang panggung dipasang sebagai *komponen Streamlit dua arah* (``declare_component``):
iframe dipasang SEKALI, lalu tiap tick Python hanya mengirim data terbaru lewat
``postMessage``; skrip di dalam iframe memperbarui target jalan, aktivitas, dan badge tanpa
memuat ulang. Iframe baru dimuat ulang hanya bila tata letak/penampilan karyawan berubah
(``sig`` berbeda), misalnya setelah reset kantor.

Bila komponen gagal dibuat (mis. folder tidak bisa ditulis), otomatis kembali ke mode lama
(``st.iframe`` bila ada, atau ``components.html`` di Streamlit versi lama).

Pratinjau tanpa Streamlit (membuat berkas HTML yang bisa dibuka di browser):

    python -m office.ui.stage3d
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any, Mapping

try:  # nilai state asli dari proyek
    from ..models_data import EMP_COFFEE, EMP_GAMING, EMP_IDLE, EMP_NAP, EMP_WALKING
except Exception:  # pragma: no cover - modul dipakai terpisah
    EMP_COFFEE = EMP_GAMING = EMP_IDLE = EMP_NAP = EMP_WALKING = None

THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
STAGE3D_VERSION = "v2-komponen"
_log = logging.getLogger("aog.stage3d")
_announced: set[str] = set()

COMPONENT_NAME = "aog_stage_3d"
COMPONENT_KEY = "aog_stage_3d"

DEFAULT_LOOKS: dict[str, Any] = {
    "skin": "#F6C9A0",
    "hair": "#2B1D14",
    "shirt": "#2563EB",
    "accent": "#FDE68A",
    "glasses": False,
    "hair_style": "short",
}

# Kata kunci pada ``state`` karyawan -> aktivitas visual. Sesuaikan dengan konstanta EMP_*
# di office/models_data.py bila nilainya berbeda.
_SLEEP_WORDS = ("sleep", "tidur", "zzz")
_REST_WORDS = ("break", "rest", "relax", "santai", "istirahat", "kopi", "coffee",
               "ngopi", "game", "bermain", "gaming", "pantry")
_WORK_WORDS = ("work", "kerja", "busy", "sibuk", "task", "tugas", "think", "mikir",
               "type", "ketik", "running", "proses", "progress")

ACTIVITY_LABEL = {
    "work": "Sedang bekerja",
    "rest": "Istirahat",
    "sleep": "Tidur",
    "idle": "Siaga di meja",
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _items(items: Any) -> list[Any]:
    if items is None:
        return []
    if isinstance(items, Mapping):
        return list(items.values())
    return list(items)


def activity_of(state: Any, target_room: str = "") -> str:
    """Petakan state karyawan ke aktivitas visual: work / rest / sleep / idle."""
    if EMP_IDLE is not None:
        if state == EMP_NAP:
            return "sleep"
        if state in (EMP_COFFEE, EMP_GAMING):
            return "rest"
        if state == EMP_WALKING:
            return "rest" if target_room == "break" else "work"
        if state == EMP_IDLE:
            return "idle"
        return "work"  # state lain (mengetik/bekerja) = bekerja
    s = str(state or "").lower()
    if any(w in s for w in _SLEEP_WORDS):
        return "sleep"
    if any(w in s for w in _REST_WORDS):
        return "rest"
    if any(w in s for w in _WORK_WORDS):
        return "work"
    return "idle"


def _xy(value: Any, default: tuple[float, float] = (0.5, 0.5)) -> tuple[float, float]:
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return default


def _r3(v: float) -> float:
    """Bulatkan ke 3 desimal supaya noise float tidak membuat payload 'berubah'."""
    return round(float(v), 3)


def _roster_helpers():
    """Ambil helper denah dari roster; kembalikan (desk_spots, desk_spot, break_spot)."""
    try:
        from ..roster import DESK_SPOTS, break_spot, desk_spot

        return DESK_SPOTS, desk_spot, break_spot
    except Exception:  # pragma: no cover - dipakai bila modul dijalankan terpisah
        return {}, None, None


def _signature(out_rooms: list[dict[str, Any]], out_emps: list[dict[str, Any]], quality: str) -> tuple[str, dict[str, str]]:
    """Sidik jari bagian yang menuntut scene DIBANGUN ULANG: denah ruangan + penampilan karyawan.

    Nama, ruangan, posisi meja, aktivitas, target jalan, model, dan badge sengaja TIDAK ikut:
    semuanya dikirim lewat pesan dan diterapkan tanpa muat ulang iframe.
    Mengembalikan (sidik jari gabungan, sidik jari per bagian) - bagian dipakai untuk diagnosis.
    """
    def h(obj: Any) -> str:
        raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]

    parts = {
        "kualitas": h(quality),
        "denah": h([
            {k: r[k] for k in ("rid", "name", "color", "gx", "gy", "gw", "gh", "furniture", "spots", "lounge")}
            for r in out_rooms
        ]),
        "karyawan": h([
            {k: e[k] for k in ("eid", "skin", "hair", "shirt", "accent", "glasses", "hair_style")}
            for e in out_emps
        ]),
    }
    return h(parts), parts


def build_payload(
    rooms: Any,
    employees: Any,
    quality: str = "high",
    boss_name: str | None = None,
    badges: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Ubah data Room/Employee menjadi JSON sederhana untuk scene 3D."""
    desk_spots, desk_spot, break_spot = _roster_helpers()
    room_list = _items(rooms)
    room_ids = {_get(r, "rid") for r in room_list}

    out_rooms = []
    for r in room_list:
        rid = _get(r, "rid")
        out_rooms.append(
            {
                "rid": rid,
                "name": _get(r, "name", rid),
                "color": _get(r, "color", "#38BDF8"),
                "gx": int(_get(r, "gx", 0)),
                "gy": int(_get(r, "gy", 0)),
                "gw": int(_get(r, "gw", 3)),
                "gh": int(_get(r, "gh", 3)),
                "furniture": list(_get(r, "furniture", ()) or ()),
                "spots": [list(map(float, s)) for s in desk_spots.get(rid, [])],
                "lounge": rid in ("break", "atrium"),
                "badge": int((badges or {}).get(rid, 0)),
            }
        )

    out_emps = []
    rest_states = (EMP_COFFEE, EMP_GAMING, EMP_NAP) if EMP_IDLE is not None else ()
    for idx, e in enumerate(_items(employees)):
        eid = _get(e, "eid", f"e{idx}")
        looks = {k: _get(e, k, v) or v for k, v in DEFAULT_LOOKS.items()}
        looks["glasses"] = bool(_get(e, "glasses", False))
        room = _get(e, "room", "")
        state = _get(e, "state", "")
        desk = _xy(_get(e, "desk"))
        target_room = _get(e, "target_room", "") or ""
        slot = sum(map(ord, str(eid))) % 4  # stabil antar proses (hash() tidak stabil)
        target, face = desk, 0.0  # idle/bekerja: di meja sendiri
        if state in rest_states and break_spot:
            target = break_spot(slot)
        elif target_room and target_room in room_ids and (EMP_WALKING is None or state == EMP_WALKING):
            if target_room == "break" and break_spot:
                target = break_spot(slot)
            elif target_room == room:
                target = desk
            elif desk_spot:
                sx, sy = desk_spot(target_room, slot % 3)
                target, face = (sx, sy + 1.3), 3.14159  # tamu: berdiri di depan meja
        activity = activity_of(state, target_room)
        tx, tz = _r3(target[0]), _r3(target[1])
        out_emps.append(
            {
                "eid": eid,
                "name": _get(e, "name", "Karyawan"),
                "role": _get(e, "role_label", "") or _get(e, "role", ""),
                "model": _get(e, "model", ""),
                "activity": activity,
                "label": ACTIVITY_LABEL[activity],
                "room": room,
                "x": tx, "z": tz,
                "tx": tx, "tz": tz,
                "deskx": _r3(desk[0]), "deskz": _r3(desk[1]),
                "face": face,
                **looks,
            }
        )
    if boss_name:
        bx, bz = (desk_spots.get("boss") or [(1.5, 0.8)])[0]
        out_emps.append(
            {
                "eid": "boss", "name": boss_name, "role": "Bos", "model": "",
                "activity": "idle", "label": "Memantau kantor", "room": "boss",
                "x": bx, "z": bz, "tx": bx, "tz": bz, "deskx": bx, "deskz": bz, "face": 0.0,
                "skin": "#E8B892", "hair": "#1B1512", "shirt": "#1F2937", "accent": "#FACC15",
                "glasses": False, "hair_style": "short",
            }
        )
    q = "low" if quality == "low" else "high"
    sig, parts = _signature(out_rooms, out_emps, q)
    return {
        "rooms": out_rooms,
        "employees": out_emps,
        "quality": q,
        "badges": {r["rid"]: r["badge"] for r in out_rooms},
        "sig": sig,
        "parts": parts,
    }


def build_html(payload: dict[str, Any], height: int = 640) -> str:
    """HTML mandiri (data tertanam). Dipakai untuk mode cadangan dan pratinjau."""
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        _TEMPLATE.replace("__THREE__", THREE_URL)
        .replace("__HEIGHT__", str(int(height)))
        .replace("__DATA__", data)
    )


def _component_html() -> str:
    """HTML untuk komponen dua arah: tanpa data tertanam, menunggu pesan dari Streamlit."""
    return (
        _TEMPLATE.replace("__THREE__", THREE_URL)
        .replace("__HEIGHT__", "700")
        .replace("__DATA__", "null")
    )


# ----------------------------------------------------------------------------- komponen Streamlit
_component_func: Any = None  # None = belum dicoba, False = gagal, selain itu = fungsi komponen


def _announce(mode: str, detail: str = "") -> None:
    """Catat SEKALI per proses mode yang dipakai, supaya mudah dilihat di log."""
    if mode in _announced:
        return
    _announced.add(mode)
    print(f"[stage3d {STAGE3D_VERSION}] mode={mode} {detail}".rstrip(), flush=True)


def _get_component() -> Any:
    """Buat (sekali) komponen Streamlit dua arah dari template; None bila tidak bisa."""
    global _component_func
    if _component_func is not None:
        return _component_func or None
    try:
        import streamlit.components.v1 as components

        html = _component_html()
        candidates = [
            Path(__file__).with_name("_stage3d_component"),
            Path(tempfile.gettempdir()) / "aog_stage3d_component",
        ]
        folder = None
        for cand in candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                target = cand / "index.html"
                if not target.exists() or target.read_text(encoding="utf-8") != html:
                    target.write_text(html, encoding="utf-8")
                folder = cand
                break
            except OSError as exc:
                _log.warning("stage3d: folder %s tidak bisa ditulis: %s", cand, exc)
        if folder is None:
            _component_func = False
            return None
        _component_func = components.declare_component(COMPONENT_NAME, path=str(folder))
    except Exception:  # pragma: no cover
        _log.warning("stage3d: komponen gagal dibuat:\n%s", traceback.format_exc())
        _component_func = False
    return _component_func or None


def _show_html(html: str, height: int) -> None:
    """Mode cadangan: HTML mandiri lewat st.iframe (components.html hanya untuk Streamlit lama)."""
    import streamlit as st

    if hasattr(st, "iframe"):
        _announce("cadangan-st.iframe")
        st.iframe(html, height=height)
        return
    import streamlit.components.v1 as components

    _announce("cadangan-components.html")
    components.html(html, height=height, scrolling=False)


def render_stage_3d(
    rooms: Any,
    employees: Any,
    *,
    boss_name: str | None = None,
    badges: Mapping[str, int] | None = None,
    height: int = 700,
    quality: str = "high",
    debug: bool = False,
) -> None:
    """Gambar panggung 3D di halaman Streamlit tanpa memuat ulang iframe tiap tick.

    ``debug=True`` (atau env ``AOG_STAGE3D_DEBUG=1``) menampilkan penghitung kecil di pojok kiri
    bawah panggung: ``boot`` naik = iframe dimuat ulang (penyebab kedip), ``upd`` naik = pembaruan normal.
    """
    payload = build_payload(rooms, employees, quality, boss_name, badges)
    payload["height"] = int(height)
    payload["debug"] = bool(debug or os.environ.get("AOG_STAGE3D_DEBUG"))
    payload["version"] = STAGE3D_VERSION

    comp = _get_component()
    if comp is not None:
        try:
            # key tetap => Streamlit TIDAK memasang ulang iframe saat argumen berubah;
            # iframe hanya menerima pesan 'render' baru.
            comp(payload=payload, key=COMPONENT_KEY, default=None)
            _announce("komponen")
            return
        except Exception:  # pragma: no cover
            _log.warning("stage3d: pemanggilan komponen gagal:\n%s", traceback.format_exc())
    _show_html(build_html(payload, height), height)


# ----------------------------------------------------------------------------- template
_TEMPLATE = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;height:100%;background:#17202b;overflow:hidden;
  font-family:"Trebuchet MS","Segoe UI",system-ui,sans-serif}
#wrap{position:relative;width:100%;height:100vh;touch-action:none;background:#17202b}
canvas{display:block;cursor:grab}
#tip{position:absolute;pointer-events:none;display:none;background:#FFF6D8;color:#3A2E1C;
  border:2px solid #3A2E1C;border-radius:10px;padding:6px 10px;font-size:12px;line-height:1.4;
  box-shadow:0 3px 0 rgba(0,0,0,.28);max-width:230px;z-index:3}
#tip b{font-size:13px}
#hud{position:absolute;right:10px;top:64px;display:flex;gap:6px;z-index:2}
#hud button{font:700 14px "Trebuchet MS",system-ui,sans-serif;color:#3A2E1C;background:#FFE9A8;
  border:2px solid #3A2E1C;border-radius:9px;min-width:36px;height:34px;padding:0 10px;
  box-shadow:0 3px 0 rgba(0,0,0,.3);cursor:pointer}
#hud button:active{transform:translateY(2px);box-shadow:0 1px 0 rgba(0,0,0,.3)}
#hud button:focus-visible{outline:3px solid #38BDF8;outline-offset:2px}
#dbg{position:absolute;left:8px;bottom:8px;z-index:5;display:none;font:11px monospace;color:#FFE9A8;background:rgba(0,0,0,.55);padding:3px 7px;border-radius:6px;pointer-events:none}
#err{display:none;position:absolute;inset:0;color:#FFE9A8;padding:24px;font-size:15px;z-index:4}
</style></head>
<body>
<div id="wrap">
  <div id="hud">
    <button id="zin" aria-label="Perbesar">+</button>
    <button id="zout" aria-label="Perkecil">&minus;</button>
    <button id="zreset">Pusat</button>
  </div>
  <div id="tip"></div>
  <div id="err"></div>
  <div id="dbg"></div>
</div>
<script src="__THREE__"></script>
<script>
(function(){
"use strict";
/* EMBED = data tertanam (mode cadangan/pratinjau). null = mode komponen: data datang lewat pesan. */
var EMBED=__DATA__;
var booted=false,bootSig=null,bootParts=null,applyFn=null,nUpd=0,nBoot=0,dbgOn=false,dbgVer="",dbgWhy="";
function showDbg(){var d=document.getElementById("dbg");if(!d)return;d.style.display=dbgOn?"block":"none";if(dbgOn)d.textContent=dbgVer+" | boot "+nBoot+" | upd "+nUpd+(dbgWhy?" | muat ulang: "+dbgWhy:"");}
function showErr(m){var e=document.getElementById("err");e.textContent=m;e.style.display="block";}

function boot(D){
if(typeof THREE==="undefined"){showErr("Three.js gagal dimuat. Periksa koneksi internet lalu muat ulang.");return;}

var wrap=document.getElementById("wrap");
var W=wrap.clientWidth||800,H=wrap.clientHeight||600;
var SH=D.quality==="high";
var renderer;
try{renderer=new THREE.WebGLRenderer({antialias:true});}
catch(err){showErr("WebGL tidak tersedia di browser ini.");return;}
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,SH?2:1));
renderer.setSize(W,H);
renderer.shadowMap.enabled=SH;
renderer.shadowMap.type=THREE.PCFSoftShadowMap;
wrap.insertBefore(renderer.domElement,wrap.firstChild);

var scene=new THREE.Scene();
scene.background=new THREE.Color("#17202b");

/* ---------- grid ---------- */
var rooms=D.rooms,emps=D.employees;
var GW=0,GH=0;
rooms.forEach(function(r){GW=Math.max(GW,r.gx+r.gw);GH=Math.max(GH,r.gy+r.gh);});
var occ=[];
for(var yy=0;yy<GH;yy++){occ.push(new Array(GW).fill(null));}
rooms.forEach(function(r){for(var j=0;j<r.gh;j++)for(var i=0;i<r.gw;i++)occ[r.gy+j][r.gx+i]=r.rid;});
function inGrid(x,y){return x>=0&&y>=0&&x<GW&&y<GH;}
var WH=1.5,WT=0.14;

/* ---------- helpers ---------- */
function mix(a,b,t){return new THREE.Color(a).lerp(new THREE.Color(b),t);}
var matCache={};
function mat(c){
  var col=(c&&c.isColor)?c:new THREE.Color(c);
  var k=col.getHexString();
  if(!matCache[k])matCache[k]=new THREE.MeshLambertMaterial({color:col.clone()});
  return matCache[k];
}
function mesh(geo,c,x,y,z,p){
  var m=new THREE.Mesh(geo,mat(c));
  m.position.set(x,y,z);m.castShadow=SH;m.receiveShadow=SH;
  (p||scene).add(m);return m;
}
function box(w,h,d,c,x,y,z,p){return mesh(new THREE.BoxGeometry(w,h,d),c,x,y,z,p);}
function cyl(rt,rb,h,c,x,y,z,p,seg){return mesh(new THREE.CylinderGeometry(rt,rb,h,seg||10),c,x,y,z,p);}
function sph(r,c,x,y,z,p,sx,sy,sz){
  var m=mesh(new THREE.SphereGeometry(r,14,10),c,x,y,z,p);
  m.scale.set(sx||1,sy||1,sz||1);return m;
}
function glow(w,h,c,x,y,z,p){
  var m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({color:new THREE.Color(c)}));
  m.position.set(x,y,z);if(p)p.add(m);return m;
}
function rr(ctx,x,y,w,h,r){
  ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();
}
var FONT='"Trebuchet MS","Segoe UI",system-ui,sans-serif';
var screens=[],leds=[];

/* ---------- lantai ---------- */
var maxAniso=Math.min(4,renderer.capabilities.getMaxAnisotropy?renderer.capabilities.getMaxAnisotropy():1);
function floorTex(c1,c2,line,rx,ry){
  var c=document.createElement("canvas");c.width=128;c.height=128;
  var x=c.getContext("2d");
  x.fillStyle=c1.getStyle();x.fillRect(0,0,128,128);
  x.fillStyle=c2.getStyle();x.fillRect(0,0,64,64);x.fillRect(64,64,64,64);
  x.fillStyle=line.getStyle();
  x.fillRect(0,0,128,3);x.fillRect(0,64,128,3);x.fillRect(0,0,3,128);x.fillRect(64,0,3,128);
  var t=new THREE.CanvasTexture(c);
  t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(rx,ry);t.anisotropy=maxAniso;
  return t;
}
var CREAM=new THREE.Color("#EDE5A8"),CREAM2=new THREE.Color("#E4DA98"),LINE=new THREE.Color("#CDC27C");
(function buildFloors(){
  var slab=box(GW+0.3,0.3,GH+0.3,"#8F6B43",GW/2,-0.16,GH/2);slab.castShadow=false;
  var hall=new THREE.Mesh(new THREE.PlaneGeometry(GW,GH),
    new THREE.MeshLambertMaterial({map:floorTex(CREAM,CREAM2,LINE,GW,GH)}));
  hall.rotation.x=-Math.PI/2;hall.position.set(GW/2,0.005,GH/2);hall.receiveShadow=SH;scene.add(hall);
  rooms.forEach(function(r){
    var base=mix(CREAM,r.color,0.22),alt=mix(CREAM2,r.color,0.30),ln=mix(LINE,r.color,0.40);
    var f=new THREE.Mesh(new THREE.PlaneGeometry(r.gw,r.gh),
      new THREE.MeshLambertMaterial({map:floorTex(base,alt,ln,r.gw,r.gh)}));
    f.rotation.x=-Math.PI/2;f.position.set(r.gx+r.gw/2,0.015,r.gy+r.gh/2);f.receiveShadow=SH;scene.add(f);
  });
})();

/* ---------- dinding ---------- */
var GOLD="#E2B33C";
function signTex(text,color,badge){
  var c=document.createElement("canvas");c.width=512;c.height=96;
  var x=c.getContext("2d");
  rr(x,6,6,500,84,26);x.fillStyle=mix(color,"#FFFFFF",0.3).getStyle();x.fill();
  x.lineWidth=6;x.strokeStyle="#3A2E1C";x.stroke();
  var size=46;x.font="bold "+size+"px "+FONT;
  while(x.measureText(text).width>440&&size>20){size-=2;x.font="bold "+size+"px "+FONT;}
  x.fillStyle="#2A2216";x.textAlign="center";x.textBaseline="middle";x.fillText(text,256,50);
  if(badge>0){
    x.beginPath();x.arc(488,20,19,0,Math.PI*2);x.fillStyle="#EF4444";x.fill();x.lineWidth=4;x.strokeStyle="#FFFFFF";x.stroke();
    x.fillStyle="#FFFFFF";x.font="bold 24px "+FONT;x.fillText(String(badge),488,21);
  }
  return new THREE.CanvasTexture(c);
}
function wallPiece(len,h,c,x,y,z,alongX,thick,p){
  var m=alongX?box(len,h,WT,c,x,y,z,p):box(WT,h,len,c,x,y,z,p);
  if(thick){if(alongX)m.scale.z=thick;else m.scale.x=thick;}
  return m;
}
function buildWalls(r){
  var wallC=mix("#EEF1F4",r.color,0.32),baseC=mix(r.color,"#1B2433",0.4),capC="#FFFFFF";
  // dinding utara (sepanjang x) dan barat (sepanjang z)
  [true,false].forEach(function(alongX){
    var n=alongX?r.gw:r.gh,mid=Math.floor(n/2),doorIdx=-1;
    var nx=alongX?r.gx+mid:r.gx-1,ny=alongX?r.gy-1:r.gy+mid;
    if(inGrid(nx,ny))doorIdx=mid;
    for(var i=0;i<n;i++){
      var cx=alongX?r.gx+i+0.5:r.gx,cz=alongX?r.gy:r.gy+i+0.5;
      if(i===doorIdx){
        var lh=WH-1.05;
        wallPiece(1,lh,wallC,cx,1.05+lh/2,cz,alongX,1);
        wallPiece(1,0.07,GOLD,cx,1.05,cz,alongX,1.5);
        var off=0.47;
        if(alongX){box(0.08,1.05,WT+0.05,GOLD,cx-off,0.525,cz);box(0.08,1.05,WT+0.05,GOLD,cx+off,0.525,cz);}
        else{box(WT+0.05,1.05,0.08,GOLD,cx,0.525,cz-off);box(WT+0.05,1.05,0.08,GOLD,cx,0.525,cz+off);}
      }else{
        wallPiece(1,WH,wallC,cx,WH/2,cz,alongX,1);
        wallPiece(1,0.15,baseC,cx,0.075,cz,alongX,1.3);
        wallPiece(1,0.06,capC,cx,WH+0.03,cz,alongX,1.25);
      }
    }
  });
  box(WT+0.07,WH+0.08,WT+0.07,mix(r.color,"#1B2433",0.2),r.gx,(WH+0.08)/2,r.gy);
  // papan nama di dinding utara (disimpan agar badge bisa diperbarui tanpa muat ulang)
  var sign=new THREE.Mesh(new THREE.PlaneGeometry(1.7,0.32),
    new THREE.MeshBasicMaterial({map:signTex(r.name,r.color,r.badge||0)}));
  sign.position.set(r.gx+r.gw/2,1.3,r.gy+WT/2+0.012);scene.add(sign);
  r._sign=sign;
}
rooms.forEach(buildWalls);

function redrawSign(r){
  if(!r._sign)return;
  var old=r._sign.material.map;
  r._sign.material.map=signTex(r.name,r.color,r.badge||0);
  r._sign.material.needsUpdate=true;
  if(old&&old.dispose)old.dispose();
}

/* ---------- furnitur ---------- */
var WOOD="#C9965E",WOOD_D="#8F6538";
function makeDesk(color){
  var g=new THREE.Group();
  box(1.0,0.06,0.55,WOOD,0,0.45,0,g);
  box(0.05,0.42,0.5,WOOD_D,-0.45,0.21,0,g);box(0.05,0.42,0.5,WOOD_D,0.45,0.21,0,g);
  box(0.84,0.3,0.04,WOOD_D,0,0.3,-0.24,g);
  box(0.16,0.03,0.1,"#2B2F38",0,0.495,-0.12,g);box(0.04,0.1,0.04,"#2B2F38",0,0.55,-0.12,g);
  box(0.5,0.31,0.035,"#1F2630",0,0.72,-0.12,g);
  var s=glow(0.44,0.25,mix(color,"#FFFFFF",0.25),0,0.72,-0.1,g);screens.push({m:s.material,base:s.material.color.clone()});
  box(0.34,0.015,0.11,"#E5E7EB",0,0.485,0.12,g);
  cyl(0.04,0.035,0.07,"#FFFFFF",0.36,0.51,0.08,g,8);
  var paper=box(0.2,0.01,0.28,"#FFFFFF",-0.33,0.485,0.02,g);paper.rotation.y=0.25;
  return g;
}
function makeChair(c){
  var g=new THREE.Group(),col=mix(c,"#FFFFFF",0.1);
  box(0.36,0.06,0.36,col,0,0.2,0,g);box(0.34,0.38,0.05,col,0,0.42,-0.17,g);
  cyl(0.03,0.03,0.18,"#444444",0,0.1,0,g,6);cyl(0.17,0.17,0.03,"#333333",0,0.015,0,g,8);
  return g;
}
function makePlant(){
  var g=new THREE.Group();
  cyl(0.14,0.1,0.2,"#B4694A",0,0.1,0,g);cyl(0.13,0.13,0.02,"#4A3426",0,0.2,0,g);
  sph(0.17,"#3FA45B",0,0.42,0,g,1,1.15,1);sph(0.12,"#58BD72",0.1,0.55,0.05,g);sph(0.11,"#2E8B57",-0.1,0.5,-0.04,g);
  return g;
}
function makeSofa(c){
  var g=new THREE.Group(),d=mix(c,"#000000",0.25),l=mix(c,"#FFFFFF",0.15);
  box(1.3,0.22,0.55,d,0,0.18,0,g);box(1.3,0.42,0.14,c,0,0.4,-0.2,g);
  box(0.14,0.32,0.55,c,-0.62,0.3,0,g);box(0.14,0.32,0.55,c,0.62,0.3,0,g);
  box(0.5,0.12,0.42,l,-0.28,0.35,0.04,g);box(0.5,0.12,0.42,l,0.28,0.35,0.04,g);
  return g;
}
function makeWhiteboard(){
  var g=new THREE.Group();
  box(0.95,0.6,0.03,"#D9DDE3",0,0.85,0,g);box(0.9,0.55,0.02,"#FAFAFA",0,0.85,0.012,g);
  [["#EF4444",-0.2,0.98,0.4],["#3B82F6",-0.15,0.88,0.5],["#10B981",-0.2,0.78,0.3]].forEach(function(s){
    box(s[3],0.025,0.01,s[0],s[1],s[2],0.026,g);});
  box(0.9,0.03,0.07,"#B8BEC8",0,0.55,0.03,g);
  return g;
}
function makeServer(){
  var g=new THREE.Group();
  box(0.55,1.1,0.42,"#2B3340",0,0.55,0,g);
  for(var i=0;i<5;i++){
    box(0.46,0.12,0.02,"#3D4757",0,0.2+i*0.18,0.215,g);
    var led=glow(0.04,0.04,"#34D399",0.18,0.2+i*0.18,0.227,g);leds.push({m:led.material,ph:i*1.3});
  }
  return g;
}
function makeBookshelf(){
  var g=new THREE.Group(),cols=["#EF4444","#3B82F6","#F59E0B","#10B981","#8B5CF6","#EC4899","#14B8A6"];
  box(0.95,1.15,0.3,WOOD_D,0,0.575,0,g);
  for(var row=0;row<3;row++){
    box(0.9,0.03,0.3,WOOD,0,0.2+row*0.36,0.02,g);
    var x=-0.4;
    for(var b=0;b<8;b++){
      var w=0.05+((b*7+row*3)%4)*0.012,h=0.2+((b*5+row)%3)*0.04;
      box(w,h,0.2,cols[(b+row*2)%cols.length],x+w/2,0.2+row*0.36+0.015+h/2,0.04,g);x+=w+0.01;
    }
  }
  return g;
}
function makeEasel(){
  var g=new THREE.Group();
  [[-0.2,-0.08],[0.2,-0.08],[0,-0.3]].forEach(function(p,i){
    var l=cyl(0.015,0.015,0.9,WOOD_D,p[0],0.45,p[1],g,5);l.rotation.z=i===2?0:p[0]*-0.3;});
  var cv=box(0.55,0.65,0.03,"#FFFFFF",0,0.72,0,g);cv.rotation.x=-0.1;
  box(0.4,0.2,0.012,"#F472B6",-0.02,0.82,0.022,g).rotation.x=-0.1;
  box(0.3,0.16,0.012,"#38BDF8",0.04,0.62,0.022,g).rotation.x=-0.1;
  return g;
}
function makeCoffee(){
  var g=new THREE.Group();
  box(0.9,0.5,0.4,"#6B4A31",0,0.25,0,g);box(0.94,0.04,0.44,"#E6DCC6",0,0.52,0,g);
  box(0.3,0.36,0.26,"#B91C1C",-0.2,0.72,-0.04,g);box(0.2,0.04,0.2,"#7F1D1D",-0.2,0.92,-0.04,g);
  cyl(0.04,0.035,0.07,"#FFFFFF",0.2,0.575,0.05,g,8);cyl(0.04,0.035,0.07,"#FFFFFF",0.32,0.575,0.0,g,8);
  return g;
}
function makeArcade(c){
  var g=new THREE.Group(),col=mix(c,"#7C3AED",0.4);
  box(0.55,1.0,0.45,col,0,0.5,0,g);box(0.55,0.18,0.3,mix(col,"#FFFFFF",0.2),0,1.06,-0.04,g);
  glow(0.42,0.3,"#7DD3FC",0,0.78,0.226,g);
  box(0.55,0.08,0.3,"#222222",0,0.55,0.18,g);
  sph(0.03,"#EF4444",-0.1,0.62,0.2,g);sph(0.03,"#FACC15",0.05,0.6,0.22,g);sph(0.03,"#22C55E",0.15,0.6,0.2,g);
  return g;
}
function makeTrophy(){
  var g=new THREE.Group();
  box(0.3,0.45,0.3,WOOD_D,0,0.225,0,g);
  cyl(0.06,0.06,0.04,GOLD,0,0.47,0,g,10);cyl(0.13,0.06,0.2,GOLD,0,0.6,0,g,12);
  sph(0.05,GOLD,-0.14,0.62,0,g);sph(0.05,GOLD,0.14,0.62,0,g);
  return g;
}
var BUILD={plant:makePlant,sofa:makeSofa,whiteboard:makeWhiteboard,server:makeServer,bookshelf:makeBookshelf,
  easel:makeEasel,coffee:makeCoffee,arcade:makeArcade,trophy:makeTrophy};
var WALL_ITEMS={whiteboard:0.02,server:0.22,bookshelf:0.17,coffee:0.22,arcade:0.25,trophy:0.2};
var FLOOR_ITEMS={plant:[0.3,0.35],sofa:[0.8,0.7],easel:[0.45,0.45]};

function freeSpot(r,need,inset,obs){
  for(var x=r.gx+r.gw-inset;x>=r.gx+inset;x-=0.5){
    for(var z=r.gy+r.gh-0.5;z>=r.gy+0.9;z-=0.5){
      var ok=true;
      for(var k=0;k<obs.length;k++){if(Math.hypot(obs[k][0]-x,obs[k][1]-z)<obs[k][2]+need){ok=false;break;}}
      if(ok)return[x,z];
    }
  }
  return null;
}
function furnish(r){
  var obs=[];
  r.spots.forEach(function(s){
    if(r.lounge){obs.push([s[0],s[1],0.5]);return;}
    var d=makeDesk(r.color);d.position.set(s[0],0,s[1]+0.55);d.rotation.y=Math.PI;scene.add(d);
    var ch=makeChair(r.color);ch.position.set(s[0],0,s[1]);scene.add(ch);
    obs.push([s[0],s[1]+0.5,0.7]);
  });
  var n=r.gw,mid=Math.floor(n/2),hasDoor=inGrid(r.gx+mid,r.gy-1),tiles=[];
  for(var i=0;i<n;i++){if(!(hasDoor&&i===mid))tiles.push(i);}
  var floorList=[];
  r.furniture.forEach(function(f){
    if(f==="desk"||f==="monitor")return;
    if(WALL_ITEMS[f]!==undefined&&tiles.length){
      var t=tiles.shift(),g=BUILD[f](r.color),cx=r.gx+t+0.5;
      g.position.set(cx,0,r.gy+WT/2+WALL_ITEMS[f]+0.01);scene.add(g);obs.push([cx,r.gy+0.4,0.4]);
    }else if(FLOOR_ITEMS[f]){floorList.push(f);}
  });
  floorList.forEach(function(f){
    var sz=FLOOR_ITEMS[f],p=freeSpot(r,sz[0],Math.max(0.5,sz[0]*0.75),obs);
    if(!p)return;
    var g=BUILD[f](r.color);g.position.set(p[0],0,p[1]);scene.add(g);obs.push([p[0],p[1],sz[1]]);
  });
}
rooms.forEach(furnish);

/* ---------- lobi: logo AOG perak ---------- */
(function lobby(){
  var atrium = rooms.find(function(r) {
    return r.rid === "atrium";
  });
  var cx = atrium ? atrium.gx + atrium.gw / 2 : GW / 2;
  var cz = atrium ? atrium.gy + atrium.gh / 2 : GH / 2;
  var c=document.createElement("canvas");c.width=c.height=512;var x=c.getContext("2d");
  var gr=x.createRadialGradient(200,190,20,256,256,250);
  gr.addColorStop(0,"#FAFBFC");gr.addColorStop(0.6,"#B9C1CA");gr.addColorStop(1,"#8E98A4");
  x.beginPath();x.arc(256,256,248,0,Math.PI*2);x.fillStyle=gr;x.fill();
  x.lineWidth=14;x.strokeStyle="#5B6572";x.stroke();
  x.beginPath();x.arc(256,256,214,0,Math.PI*2);x.lineWidth=5;x.strokeStyle="#E8ECF0";x.stroke();
  x.font="bold 190px "+FONT;x.textAlign="center";x.textBaseline="middle";
  x.fillStyle="#4A5360";x.fillText("AOG",258,262);x.fillStyle="#F4F6F8";x.fillText("AOG",252,254);
  var disc=new THREE.Mesh(new THREE.CircleGeometry(1.25,40),new THREE.MeshLambertMaterial({map:new THREE.CanvasTexture(c)}));
  disc.rotation.x=-Math.PI/2;disc.rotation.z=-Math.PI/4;disc.position.set(cx,0.025,cz);disc.receiveShadow=SH;scene.add(disc);
  [[3.55,3.55],[GW-3.55,GH-3.55]].forEach(function(p){var pl=makePlant();pl.position.set(p[0],0,p[1]);scene.add(pl);});
})();

/* ---------- karakter ---------- */
function bubbleTex(){
  var c=document.createElement("canvas");c.width=128;c.height=80;var x=c.getContext("2d");
  rr(x,6,6,116,50,22);x.fillStyle="#FFFFFF";x.fill();x.lineWidth=4;x.strokeStyle="#3A2E1C";x.stroke();
  x.beginPath();x.moveTo(52,54);x.lineTo(64,74);x.lineTo(74,54);x.closePath();x.fillStyle="#FFFFFF";x.fill();x.stroke();
  x.fillStyle="#3A2E1C";[40,64,88].forEach(function(px){x.beginPath();x.arc(px,31,6,0,Math.PI*2);x.fill();});
  return new THREE.CanvasTexture(c);
}
var BUBBLE=bubbleTex();

function hairCap(r,sy,color,parent,tilt){
  var m=new THREE.Mesh(new THREE.SphereGeometry(r,16,12,0,Math.PI*2,0,Math.PI*sy),mat(color));
  m.castShadow=SH;m.rotation.x=tilt;m.position.set(0,0.01,0);parent.add(m);return m;
}
function makeChar(e){
  var g=new THREE.Group(),root=new THREE.Group();g.add(root);
  var pants="#34425E",shoe="#222222",hip=0.26;
  var legs=[new THREE.Group(),new THREE.Group()];
  legs.forEach(function(l,i){
    l.position.set(i?0.075:-0.075,hip,0);root.add(l);
    cyl(0.055,0.05,0.24,pants,0,-0.12,0,l,8);box(0.1,0.05,0.15,shoe,0,-0.255,0.025,l);
  });
  cyl(0.14,0.13,0.3,e.shirt,0,hip+0.15,0,root,12);
  box(0.07,0.09,0.015,e.accent,0.06,hip+0.19,0.135,root);
  var arms=[new THREE.Group(),new THREE.Group()];
  arms.forEach(function(a,i){
    a.position.set(i?0.185:-0.185,hip+0.27,0);root.add(a);
    cyl(0.04,0.04,0.24,e.shirt,0,-0.12,0,a,8);sph(0.045,e.skin,0,-0.26,0,a);
  });
  var cup=cyl(0.035,0.03,0.06,"#FFFFFF",0,-0.3,0.05,arms[1],8);cup.visible=false;
  var head=new THREE.Group();head.position.set(0,0.72,0);root.add(head);
  sph(0.18,e.skin,0,0,0,head,1,0.96,1);
  var eyes=[-0.065,0.065].map(function(ex){return sph(0.022,"#1B1B1B",ex,0.01,0.165,head,1,1.2,0.6);});
  [-0.1,0.1].forEach(function(cx){sph(0.03,"#F9A8A8",cx,-0.04,0.14,head,1,0.7,0.5);});
  var hs2=e.hair_style,hc=e.hair;
  if(hs2==="buzz"){hairCap(0.185,0.5,hc,head,-0.15);}
  else{hairCap(0.195,0.56,hc,head,-0.3);}
  if(hs2==="long"){box(0.34,0.34,0.1,hc,0,-0.08,-0.14,head);}
  if(hs2==="ponytail"){sph(0.08,hc,0,0.02,-0.2,head);box(0.05,0.2,0.05,hc,0,-0.1,-0.22,head);}
  if(hs2==="bun"){sph(0.085,hc,0,0.2,-0.06,head);}
  if(hs2==="curly"){for(var k=0;k<7;k++){var a=k/7*Math.PI*2;sph(0.075,hc,Math.cos(a)*0.14,0.12,Math.sin(a)*0.14-0.02,head);}sph(0.09,hc,0,0.2,-0.02,head);}
  if(e.glasses){
    [-0.068,0.068].forEach(function(gx){
      var t=mesh(new THREE.TorusGeometry(0.05,0.009,6,16),"#222222",gx,0.012,0.172,head);t.castShadow=false;});
    box(0.05,0.01,0.01,"#222222",0,0.02,0.178,head).castShadow=false;
  }
  var bub=new THREE.Sprite(new THREE.SpriteMaterial({map:BUBBLE,transparent:true}));
  bub.scale.set(0.5,0.31,1);bub.position.set(0,1.28,0);bub.visible=false;g.add(bub);
  var hit=new THREE.Mesh(new THREE.SphereGeometry(0.5,8,6),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));
  hit.position.set(0,0.5,0);g.add(hit);
  scene.add(g);
  var c={e:e,g:g,root:root,legs:legs,arms:arms,head:head,eyes:eyes,cup:cup,bub:bub,hit:hit,
    x:e.x,z:e.z,tx:e.tx,tz:e.tz,yaw:e.face||0,phase:Math.random()*6,seed:Math.random()*6};
  hit.userData.c=c;g.position.set(c.x,0,c.z);g.rotation.y=c.yaw;
  return c;
}
var store=null,saved={};
try{store=window.sessionStorage;saved=JSON.parse(store.getItem("aog3d")||"{}")||{};}catch(err){store=null;saved={};}
var sp=saved.chars||{};
emps.forEach(function(e){if(sp[e.eid]){e.x=sp[e.eid][0];e.z=sp[e.eid][1];}});
var chars=emps.map(makeChar);
function saveView(){
  if(!store)return;
  try{
    var o={zoom:zoom,tg:tg,chars:{}};
    chars.forEach(function(c){o.chars[c.e.eid]=[+c.x.toFixed(3),+c.z.toFixed(3)];});
    store.setItem("aog3d",JSON.stringify(o));
  }catch(err){}
}

/* Perbarui data dinamis (aktivitas, target jalan, model, badge) TANPA membangun ulang scene. */
function applyDyn(P){
  var map={};
  (P.employees||[]).forEach(function(n){map[n.eid]=n;});
  chars.forEach(function(c){
    var n=map[c.e.eid];if(!n)return;
    var e=c.e;
    e.activity=n.activity;e.label=n.label;e.model=n.model;e.role=n.role;e.face=n.face;
    e.name=n.name;e.room=n.room;e.deskx=n.deskx;e.deskz=n.deskz;
    e.tx=n.tx;e.tz=n.tz;c.tx=n.tx;c.tz=n.tz;
  });
  var b=P.badges||{};
  rooms.forEach(function(r){
    var nb=b[r.rid]||0;
    if(nb!==(r.badge||0)){r.badge=nb;redrawSign(r);}
  });
}
applyFn=applyDyn;

function animChar(c,dt,t){
  var e=c.e,dx=c.tx-c.x,dz=c.tz-c.z,dist=Math.hypot(dx,dz),moving=dist>0.04,want;
  if(moving){
    var st=Math.min(dist,1.15*dt);c.x+=dx/dist*st;c.z+=dz/dist*st;want=Math.atan2(dx,dz);c.phase+=dt*9;
  }else{want=e.face||0;}
  var d=want-c.yaw;d=Math.atan2(Math.sin(d),Math.cos(d));c.yaw+=d*Math.min(1,dt*8);
  c.g.position.set(c.x,0,c.z);c.g.rotation.y=c.yaw;
  var R=c.root,H=c.head,L=c.legs,A=c.arms,act=e.activity;
  var sit=!moving&&act!=="rest"&&Math.hypot(c.x-e.deskx,c.z-e.deskz)<0.2;
  R.position.y=0;R.rotation.x=0;H.rotation.set(0,0,0);
  L[0].rotation.x=L[1].rotation.x=0;A[0].rotation.set(0,0,0);A[1].rotation.set(0,0,0);
  c.cup.visible=false;
  c.eyes.forEach(function(m){m.scale.y=(act==="sleep"&&!moving)?0.15:1.2;});
  if(moving){
    var s=Math.sin(c.phase);
    L[0].rotation.x=s*0.7;L[1].rotation.x=-s*0.7;A[0].rotation.x=-s*0.6;A[1].rotation.x=s*0.6;
    R.position.y=Math.abs(Math.cos(c.phase))*0.035;H.rotation.z=s*0.04;
  }else if(sit){
    R.position.y=-0.03;L[0].rotation.x=L[1].rotation.x=-1.45;
    if(act==="work"){
      A[0].rotation.x=-1.2+Math.sin(t*13+c.seed)*0.1;A[1].rotation.x=-1.2+Math.sin(t*13+c.seed+1.7)*0.12;
      H.rotation.x=0.12+Math.sin(t*2+c.seed)*0.03;R.rotation.x=0.06;
    }else if(act==="sleep"){
      A[0].rotation.x=A[1].rotation.x=-0.9;H.rotation.x=0.55;
    }else{
      A[0].rotation.x=A[1].rotation.x=-0.95+Math.sin(t*1.2+c.seed)*0.03;H.rotation.y=Math.sin(t*0.6+c.seed)*0.35;
    }
  }else{
    if(act==="rest"){
      A[1].rotation.x=-2.3+Math.sin(t*1.5+c.seed)*0.08;c.cup.visible=true;
      R.position.y=Math.sin(t*2+c.seed)*0.01;H.rotation.y=Math.sin(t*0.5+c.seed)*0.3;
    }else if(act==="sleep"){
      H.rotation.x=0.5;R.position.y=Math.sin(t*1.2+c.seed)*0.008;
    }else if(act==="work"){
      A[0].rotation.x=-0.5+Math.sin(t*9+c.seed)*0.12;A[1].rotation.x=-0.5+Math.sin(t*9+c.seed+1.5)*0.12;
    }else{
      R.position.y=Math.sin(t*1.8+c.seed)*0.008;H.rotation.y=Math.sin(t*0.5+c.seed)*0.3;
    }
  }
  c.bub.visible=(act==="work"&&!moving);
  if(c.bub.visible){c.bub.position.y=1.26+Math.sin(t*3+c.seed)*0.02;c.bub.material.opacity=0.75+0.25*Math.sin(t*4+c.seed);}
}

/* ---------- cahaya & kamera ---------- */
scene.add(new THREE.HemisphereLight("#FFF4D6","#7A6A58",0.78));
var sun=new THREE.DirectionalLight("#FFFFFF",0.62);
sun.position.set(GW/2+4,18,GH/2+9);sun.target.position.set(GW/2,0,GH/2);
sun.castShadow=SH;sun.shadow.mapSize.set(2048,2048);
var sc=Math.max(GW,GH)*0.8;
sun.shadow.camera.left=-sc;sun.shadow.camera.right=sc;sun.shadow.camera.top=sc;sun.shadow.camera.bottom=-sc;
sun.shadow.camera.near=1;sun.shadow.camera.far=60;sun.shadow.bias=-0.0006;
scene.add(sun);scene.add(sun.target);

var cam=new THREE.OrthographicCamera(-1,1,1,-1,0.1,200);
var EL=0.70,AZ=Math.PI/4,zoom=saved.zoom||1,tg=saved.tg||{x:GW/2,y:0.4,z:GH/2},hh=10;
function updateCam(){
  var aspect=W/H,span=(GW+GH)*Math.SQRT1_2;
  var vw=span+2.2,vh=(span*Math.sin(EL)+WH*Math.cos(EL)+2.6)*1.16;
  hh=Math.max(vw/aspect,vh)/2/zoom;
  cam.left=-hh*aspect;cam.right=hh*aspect;cam.top=hh;cam.bottom=-hh;cam.updateProjectionMatrix();
  var d=40;
  cam.position.set(tg.x+d*Math.cos(EL)*Math.sin(AZ),tg.y+d*Math.sin(EL),tg.z+d*Math.cos(EL)*Math.cos(AZ));
  cam.lookAt(new THREE.Vector3(tg.x,tg.y,tg.z));cam.updateMatrixWorld();
}
function resize(){
  W=wrap.clientWidth||W;H=wrap.clientHeight||H;renderer.setSize(W,H);updateCam();
}
window.addEventListener("resize",resize);
updateCam();

/* ---------- interaksi ---------- */
var el=renderer.domElement,tip=document.getElementById("tip");
var dragging=false,lx=0,ly=0;
function clampTarget(){tg.x=Math.max(0,Math.min(GW,tg.x));tg.z=Math.max(0,Math.min(GH,tg.z));}
el.addEventListener("pointerdown",function(ev){
  dragging=true;lx=ev.clientX;ly=ev.clientY;el.style.cursor="grabbing";
  try{el.setPointerCapture(ev.pointerId);}catch(err){}
});
el.addEventListener("pointermove",function(ev){
  if(dragging){
    var k=(2*hh)/H,dx=ev.clientX-lx,dy=ev.clientY-ly;lx=ev.clientX;ly=ev.clientY;
    var rx=Math.SQRT1_2,rz=-Math.SQRT1_2;
    var ux=-Math.sin(EL)*Math.sin(AZ),uy=Math.cos(EL),uz=-Math.sin(EL)*Math.cos(AZ);
    tg.x+=-dx*k*rx+dy*k*ux;tg.y+=dy*k*uy;tg.z+=-dx*k*rz+dy*k*uz;
    tg.y=Math.max(-2,Math.min(3,tg.y));clampTarget();updateCam();tip.style.display="none";return;
  }
  hover(ev);
});
function endDrag(){dragging=false;el.style.cursor="grab";}
el.addEventListener("pointerup",endDrag);el.addEventListener("pointercancel",endDrag);
el.addEventListener("pointerleave",function(){tip.style.display="none";});
el.addEventListener("wheel",function(ev){
  ev.preventDefault();zoom=Math.max(0.6,Math.min(3.5,zoom*Math.exp(-ev.deltaY*0.001)));updateCam();
},{passive:false});
function setZoom(f){zoom=Math.max(0.6,Math.min(3.5,zoom*f));updateCam();}
document.getElementById("zin").addEventListener("click",function(){setZoom(1.25);});
document.getElementById("zout").addEventListener("click",function(){setZoom(0.8);});
document.getElementById("zreset").addEventListener("click",function(){zoom=1;tg={x:GW/2,y:0.4,z:GH/2};updateCam();});

var ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
var hits=chars.map(function(c){return c.hit;});
function hover(ev){
  var rect=el.getBoundingClientRect();
  mouse.x=((ev.clientX-rect.left)/rect.width)*2-1;mouse.y=-((ev.clientY-rect.top)/rect.height)*2+1;
  ray.setFromCamera(mouse,cam);
  var h=ray.intersectObjects(hits,false);
  if(!h.length){tip.style.display="none";el.style.cursor="grab";return;}
  var e=h[0].object.userData.c.e;
  tip.textContent="";
  var b=document.createElement("b");b.textContent=e.name;tip.appendChild(b);
  [e.role,e.label,e.model].forEach(function(t){
    if(!t)return;tip.appendChild(document.createElement("br"));tip.appendChild(document.createTextNode(t));});
  tip.style.display="block";el.style.cursor="pointer";
  var x=ev.clientX-rect.left+14,y=ev.clientY-rect.top+14;
  if(x>W-240)x=ev.clientX-rect.left-240;
  tip.style.left=x+"px";tip.style.top=y+"px";
}

/* ---------- loop ---------- */
var last=0,lastSave=0;
function frame(ms){
  var t=ms/1000,dt=Math.min(0.05,last?t-last:0.016);last=t;
  if(wrap.clientWidth&&wrap.clientHeight&&(wrap.clientWidth!==W||wrap.clientHeight!==H))resize();
  chars.forEach(function(c){animChar(c,dt,t);});
  if(t-lastSave>0.5){lastSave=t;saveView();}
  screens.forEach(function(s,i){s.m.color.copy(s.base).multiplyScalar(0.82+0.18*Math.sin(t*2.2+i));});
  leds.forEach(function(l){l.m.color.set(Math.sin(t*5+l.ph)>-0.2?"#34D399":"#14532D");});
  renderer.render(scene,cam);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
}/* akhir boot */

/* ---------- penghubung ke Streamlit (mode komponen) ---------- */
function setFrameHeight(h){
  try{window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:setFrameHeight",height:h||700},"*");}catch(err){}
}
function safeReload(){
  /* cegah loop muat-ulang bila sidik jari terus berubah */
  var ok=true;
  try{
    var now=Date.now(),prev=+(window.sessionStorage.getItem("aog3d_rl")||0);
    if(now-prev<4000)ok=false;else window.sessionStorage.setItem("aog3d_rl",String(now));
  }catch(err){}
  if(ok){try{window.location.reload();}catch(err){}}
  return ok;
}
window.addEventListener("message",function(ev){
  var m=ev.data;
  if(!m||m.type!=="streamlit:render")return;
  var P=m.args&&m.args.payload;
  if(!P)return;
  setFrameHeight(P.height);
  dbgOn=!!P.debug;dbgVer=P.version||"";
  if(!booted){
    booted=true;bootSig=P.sig;bootParts=P.parts||{};
    try{dbgWhy=window.sessionStorage.getItem("aog3d_why")||"";}catch(err){dbgWhy="";}
    try{nBoot=(+window.sessionStorage.getItem("aog3d_boots")||0)+1;window.sessionStorage.setItem("aog3d_boots",String(nBoot));}catch(err){nBoot=1;}
    boot(P);showDbg();return;
  }
  if(P.sig!==bootSig){
    var diff=[];Object.keys(P.parts||{}).forEach(function(k){if((bootParts||{})[k]!==P.parts[k])diff.push(k);});
    try{window.sessionStorage.setItem("aog3d_why",diff.join(",")||"sig");}catch(err){}
    if(safeReload())return;
  }
  nUpd++;showDbg();
  if(applyFn)applyFn(P);
});
if(EMBED){booted=true;boot(EMBED);}
else{
  try{window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:componentReady",apiVersion:1},"*");}catch(err){}
}
})();
</script>
</body></html>
"""


def _preview() -> None:  # pragma: no cover
    from ..roster import ROOMS, ROSTER

    demo_states = ["working", "working", "idle", "working", "working", "idle",
                   "working", "working", "idle", "working", "idle", "rest"]
    people = []
    for i, emp in enumerate(ROSTER):
        d = emp.to_dict()
        d["state"] = demo_states[i % len(demo_states)]
        people.append(d)
    out = Path("data") / "stage3d_preview.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(build_html(build_payload(ROOMS, people)), encoding="utf-8")
    print(f"Tersimpan: {out} - buka di browser (butuh internet untuk memuat Three.js).")


if __name__ == "__main__":  # pragma: no cover
    _preview()

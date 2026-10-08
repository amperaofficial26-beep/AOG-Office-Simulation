"""Regenerasi pratinjau PNG panggung kantor (butuh cairosvg + pillow)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from office.roster import sync_employees
from office.state import empty_state
from office.ui.office_view import render_office


def main() -> None:
    state = empty_state()
    state["employees"] = sync_employees({})
    state["employees"]["sari"]["state"] = "bekerja"
    state["employees"]["ayu"]["state"] = "ngopi"
    state["employees"]["ayu"]["room"] = "break"
    state["employees"]["putri"]["state"] = "main game"
    state["employees"]["putri"]["room"] = "break"
    state["employees"]["raka"]["state"] = "istirahat"
    state["employees"]["raka"]["room"] = "break"
    state["employees"]["lala"]["state"] = "mengobrol"

    html = render_office(state)
    svg = html[html.find("<svg") : html.rfind("</svg>") + len("</svg>")]
    css = (
        "<style>.char-body{animation:none}.nametag{font:600 10px sans-serif}"
        ".room-label{font:700 12px sans-serif}.room-sub{font:500 9px sans-serif}</style>"
    )
    i = svg.find(">") + 1
    svg = svg[:i] + css + svg[i:]
    svg = svg.replace('<svg class="office-svg"', '<svg xmlns="http://www.w3.org/2000/svg"', 1)

    import cairosvg

    out = Path(__file__).resolve().parent.parent / "data" / "pratinjau_kantor.png"
    cairosvg.svg2png(
        bytestring=svg.encode(),
        write_to=str(out),
        output_width=1600,
        background_color="#0B1020",
    )
    print(f"PNG ditulis ke {out}")


if __name__ == "__main__":
    main()

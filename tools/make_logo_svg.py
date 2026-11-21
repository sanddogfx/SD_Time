"""Build the SD Time app logo (SVG) from the vector artwork in logo.ai.

The .ai file is PDF-compatible: its vector paths are read with PyMuPDF, normalized,
and placed in white on a circle filled with the app accent colour.

    python tools/make_logo_svg.py "C:\\_WORK_\\_STOCK_\\logos\\logo.ai" assets/logo.svg [--set white|black]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sd_time.theme import C  # noqa: E402

SIZE = 256          # viewBox side
FACE_WIDTH = 0.62   # face width as a fraction of the circle diameter
# Small variant: the face takes more of the circle, and the green is a bit deeper so
# white reads better (contrast 3.0:1 instead of 2.3:1) while staying the app's hue.
SMALL_FACE_WIDTH = 0.66
SMALL_CIRCLE = "#77a12d"
SMALL_OUTLINE = 12.0   # thin and soft: keeps the gaps readable without a heavy halo
OUTLINE_DARKEN = 0.74  # contour = circle colour × this (same hue, a bit darker)


def drawings(ai_path: Path, color_set: str) -> list[dict]:
    # PyMuPDF goes by extension, so open a .pdf copy of the .ai file.
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "logo.pdf"
        shutil.copyfile(ai_path, pdf)
        doc = pymupdf.open(pdf)
        target = (1.0, 1.0, 1.0) if color_set == "white" else (0.0, 0.0, 0.0)
        found = [d for d in doc[0].get_drawings()
                 if d.get("fill") and tuple(round(c, 3) for c in d["fill"]) == target]
        doc.close()
    if not found:
        raise SystemExit(f"No {color_set} shapes found in {ai_path}")
    return found


def path_data(d: dict, sx: float, ox: float, oy: float) -> str:
    """PyMuPDF items -> SVG path data, transformed into the icon's coordinates."""
    def pt(p) -> str:
        return f"{(p.x - ox) * sx:.2f} {(p.y - oy) * sx:.2f}"

    out: list[str] = []
    start = cur = None
    for item in d["items"]:
        kind, p0 = item[0], item[1]
        if cur is None or abs(p0.x - cur.x) > 1e-3 or abs(p0.y - cur.y) > 1e-3:
            if start is not None:
                out.append("Z")
            out.append(f"M{pt(p0)}")
            start = p0
        if kind == "l":
            out.append(f"L{pt(item[2])}")
            cur = item[2]
        elif kind == "c":
            out.append(f"C{pt(item[2])} {pt(item[3])} {pt(item[4])}")
            cur = item[4]
        elif kind == "re":
            r = item[1]
            out[-1:] = [f"M{pt(r.tl)}", f"L{pt(r.tr)}", f"L{pt(r.br)}", f"L{pt(r.bl)}"]
            cur = r.tl
        else:
            raise ValueError(f"Unsupported path item {kind!r}")
    out.append("Z")
    return " ".join(out)


def darker(hex_color: str, factor: float = OUTLINE_DARKEN) -> str:
    """Same hue, darker: used for the contour around the white face."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c * factor) for c in (r, g, b))


def build_svg(shapes: list[dict], circle: str, face: str, face_width: float = FACE_WIDTH,
              outline: float = 0.0, rim: float = 0.0) -> str:
    """outline > 0: a darker-green contour is drawn *under* the white shapes, so only its
    outer half shows — the face keeps its size, its edges get a dark halo, and the thin
    gaps between brow, face and chin become dark lines instead of disappearing.
    rim > 0: a darker ring on the circle's edge, separating the icon from its backdrop.
    Elements carry ids (bg, rim, outline) so the app can recolour them per state."""
    x0 = min(d["rect"].x0 for d in shapes)
    y0 = min(d["rect"].y0 for d in shapes)
    x1 = max(d["rect"].x1 for d in shapes)
    y1 = max(d["rect"].y1 for d in shapes)
    w, h = x1 - x0, y1 - y0
    scale = SIZE * face_width / w
    # centre the face in the circle (optically a touch lower: the ears are light)
    ox = x0 - (SIZE - w * scale) / 2 / scale
    oy = y0 - (SIZE - h * scale) / 2 / scale - SIZE * 0.015 / scale
    paths = "\n    ".join(
        f'<path fill-rule="{"evenodd" if d.get("even_odd") else "nonzero"}" '
        f'd="{path_data(d, scale, ox, oy)}"/>' for d in shapes)
    dark = darker(circle)
    parts = [f'<circle id="bg" cx="{SIZE / 2}" cy="{SIZE / 2}" r="{SIZE / 2}" fill="{circle}"/>']
    if rim > 0:
        parts.append(f'<circle id="rim" cx="{SIZE / 2}" cy="{SIZE / 2}" r="{SIZE / 2 - rim / 2:g}" '
                     f'fill="none" stroke="{dark}" stroke-width="{rim:g}"/>')
    if outline > 0:
        parts.append(f'<g id="outline" fill="{dark}" stroke="{dark}" stroke-width="{outline:g}" '
                     f'stroke-linejoin="round">\n    {paths}\n  </g>')
    parts.append(f'<g fill="{face}">\n    {paths}\n  </g>')
    body = "\n  ".join(parts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">
  <title>SD Time</title>
  {body}
</svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ai", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--set", default="white", choices=("white", "black"),
                    help="which copy of the artwork in the file to use")
    ap.add_argument("--circle", default=None, help="circle colour (default: theme green)")
    ap.add_argument("--face", default="#ffffff")
    ap.add_argument("--small", action="store_true",
                    help="small-size variant (<=32 px): dark contour, slightly bigger face, "
                         "deeper green")
    ap.add_argument("--outline", type=float, default=None, help="contour width (units of 256)")
    ap.add_argument("--rim", type=float, default=0.0, help="dark ring on the circle edge")
    ap.add_argument("--face-width", type=float, default=None)
    args = ap.parse_args()
    shapes = drawings(args.ai, args.set)
    if args.small:
        svg = build_svg(shapes, args.circle or SMALL_CIRCLE, args.face,
                        face_width=args.face_width or SMALL_FACE_WIDTH,
                        outline=SMALL_OUTLINE if args.outline is None else args.outline,
                        rim=args.rim)
    else:
        svg = build_svg(shapes, args.circle or C["accent_text"], args.face,
                        face_width=args.face_width or FACE_WIDTH,
                        outline=args.outline or 0.0, rim=args.rim)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()

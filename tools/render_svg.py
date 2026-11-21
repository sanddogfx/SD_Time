"""Render SVG files to PNG previews (optionally on a background colour).

    python tools/render_svg.py out.png 512 "#37393b" a.svg [b.svg ...]
"""
import sys

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication(sys.argv)
out, size, bg, files = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:]
pad = size // 8
img = QImage(len(files) * (size + pad) + pad, size + 2 * pad, QImage.Format.Format_ARGB32)
img.fill(QColor(bg))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
for i, f in enumerate(files):
    r = QSvgRenderer(f)
    if not r.isValid():
        raise SystemExit(f"invalid SVG: {f}")
    r.render(p, QRectF(pad + i * (size + pad), pad, size, size))
p.end()
img.save(out)
print(out)

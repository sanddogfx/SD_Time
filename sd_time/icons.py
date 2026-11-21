"""App icons: the SVG logo (assets/logo.svg) tinted per state, with a painted fallback."""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import C

RUN_COLOR = C["accent_text"]   # same green as the logo
SMALL_RUN_COLOR = "#77a12d"    # a touch deeper at small sizes so the white face reads
IDLE_COLOR = "#6b6b6b"
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def assets_dir() -> Path:
    # PyInstaller unpacks data next to sys._MEIPASS; in the repo it's ../assets.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets"


SMALL_MAX = 32   # up to this many pixels the small-size artwork (logo_small.svg) is used


def _darker(hex_color: str, factor: float = 0.74) -> str:
    """Contour colour: same hue as the circle, darker (matches tools/make_logo_svg.py)."""
    c = QColor(hex_color)
    return QColor(round(c.red() * factor), round(c.green() * factor),
                  round(c.blue() * factor)).name()


@lru_cache(maxsize=None)
def _logo_renderer(circle_color: str, small: bool = False) -> QSvgRenderer | None:
    path = assets_dir() / ("logo_small.svg" if small else "logo.svg")
    try:
        svg = path.read_text(encoding="utf-8")
    except OSError:
        return _logo_renderer(circle_color, False) if small else None
    # Recolour per state: background circle, and the darker contour / rim (same hue,
    # darker) of the small variant. The face stays white.
    if small and circle_color == RUN_COLOR:
        circle_color = SMALL_RUN_COLOR
    dark = _darker(circle_color)
    svg = re.sub(r'(<circle id="bg"[^>]*\bfill=")[^"]*(")', rf"\g<1>{circle_color}\g<2>", svg)
    svg = re.sub(r'(<circle id="rim"[^>]*\bstroke=")[^"]*(")', rf"\g<1>{dark}\g<2>", svg)
    svg = re.sub(r'(<g id="outline" fill=")[^"]*(" stroke=")[^"]*(")',
                 rf"\g<1>{dark}\g<2>{dark}\g<3>", svg)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    return renderer if renderer.isValid() else None


def logo_pixmap(size: int, circle_color: str = RUN_COLOR,
                small: bool | None = None) -> QPixmap | None:
    """small=None picks the artwork by pixel size; pass it explicitly when the pixmap
    is rendered at a high-DPI multiple of a small logical size."""
    if small is None:
        small = size <= SMALL_MAX
    renderer = _logo_renderer(circle_color, small)
    if renderer is None:
        return None
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def make_icon(running: bool) -> QIcon:
    """Green logo while the timer runs, grey when it's stopped."""
    color = RUN_COLOR if running else IDLE_COLOR
    icon = QIcon()
    for size in SIZES:
        pm = logo_pixmap(size, color) or _painted_clock(size, color)
        icon.addPixmap(pm)
    return icon


def _painted_clock(size: int, color: str) -> QPixmap:
    """Fallback if assets/logo.svg is missing: a simple clock face."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.05
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(m, m, size - 2 * m, size - 2 * m))
    pen = QPen(QColor("white"), max(1.6, size * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    c = QPointF(size / 2, size / 2)
    p.drawLine(c, QPointF(size / 2, size * 0.22))
    p.drawLine(c, QPointF(size * 0.72, size / 2))
    p.end()
    return pm


# ------------------------------------------------------------ sidebar icons
# Line icons on a 24×24 grid, one stroke width, so they read as one family.
_NAV_SVG = {
    "tracker": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/>'
                '<path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "timesheet": '<rect x="3.5" y="4" width="17" height="16" rx="2"/>'
                 '<path d="M3.5 9h17M3.5 14.5h17M9.5 9v11"/>',
    "reports": '<path d="M4 20h16"/><path d="M7.5 16.5v-4M12 16.5V7M16.5 16.5v-7"/>',
    "projects": '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.8l2 2h7.2a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2'
                'h-13a2 2 0 0 1-2-2z"/>',
    "clients": '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20c1.3-3.8 4.2-5.8 7.5-5.8'
               's6.2 2 7.5 5.8"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/>'
                '<circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/>'
                '<circle cx="17" cy="17" r="2"/>',
    "plus": '<circle cx="12" cy="12" r="8.5"/><path d="M12 8.2v7.6M8.2 12h7.6"/>',
    "add": '<path d="M12 5.5v13M5.5 12h13"/>',
    "pencil": '<path d="M5 19h4L19 9l-4-4L5 15z"/>',
    "skip": '<path d="M6 6.5l8 5.5-8 5.5zM17.5 6v12"/>',
    "chevron": '<path d="M9 6l6 6-6 6"/>',
    "close": '<path d="M7 7l10 10M17 7L7 17"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "left": '<path d="M15 6l-6 6 6 6"/>',
    "download": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
    "gap": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/><path d="M4 4l3 3"/>',
    "play": '<path d="M8.5 6.2v11.6c0 .6.6.9 1.1.6l9-5.8c.5-.3.5-1 0-1.3l-9-5.8c-.5-.3-1.1 0-1.1.7z"/>',
    "more": '<circle cx="12" cy="6" r=".9"/><circle cx="12" cy="12" r=".9"/>'
            '<circle cx="12" cy="18" r=".9"/>',
    # Tomato: slightly wide body open at the top, two leaf arcs and a short curled stem.
    "tomato": '<path d="M8.3 8.7C5.7 9.7 4 11.9 4 14.4 4 18 7.6 20.5 12 20.5s8-2.5 8-6.1'
              'c0-2.5-1.7-4.7-4.3-5.7"/>'
              '<path d="M12 10c-1.1-1.9-3.1-2.6-5.2-1.9M12 10c1.1-1.9 3.1-2.6 5.2-1.9"/>'
              '<path d="M12 10V5.2c0-.9.8-1.6 2-1.7"/>',
}
NAV_ICON_COLOR = "#bdbdbd"


def _render_line_icon(body: str, color: str, size: int) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
           f'stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


# Colour tomato (same silhouette as the line one): red body with a soft shine, green
# calyx and stem. The red has almost the same luminance as the green "on" button
# (1.09:1), so a dark outline behind body and calyx carries the silhouette there.
TOMATO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <g fill="#141414" stroke="#141414" stroke-width="2.2" stroke-linejoin="round">
    <path d="M4 14.4C4 11.3 7.3 8.6 12 8.6s8 2.7 8 5.8c0 3.6-3.6 6.1-8 6.1s-8-2.5-8-6.1z"/>
    <path d="M12 10.3 9.2 11l.9-1.9-2.8-.6 2.8-.9L12 5.9l1.9 1.7 2.8.9-2.8.6.9 1.9z"/>
  </g>
  <path d="M4 14.4C4 11.3 7.3 8.6 12 8.6s8 2.7 8 5.8c0 3.6-3.6 6.1-8 6.1s-8-2.5-8-6.1z"
        fill="#e5483f" stroke="#a8261f" stroke-width="0.9"/>
  <path d="M7 12.6c.7-1.1 1.8-1.8 3.1-2.1" fill="none" stroke="#ffffff" stroke-opacity="0.6"
        stroke-width="1.3" stroke-linecap="round"/>
  <path d="M12 10.3 9.2 11l.9-1.9-2.8-.6 2.8-.9L12 5.9l1.9 1.7 2.8.9-2.8.6.9 1.9z"
        fill="#5aa53a" stroke="#3d7a24" stroke-width="0.6" stroke-linejoin="round"/>
  <path d="M12 7V4.6c0-.7.7-1.2 1.8-1.3" fill="none" stroke="#3d7a24" stroke-width="1.5"
        stroke-linecap="round"/>
</svg>"""


def tomato_pixmap(size: int, dpr: float = 1.0) -> QPixmap:
    px = max(size, int(round(size * dpr)))
    renderer = QSvgRenderer(QByteArray(TOMATO_SVG.encode("utf-8")))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(px / size)
    return pm


_FILLED_SVG = {
    "play": '<path d="M8 5.6v12.8c0 .8.9 1.3 1.6.8l10-6.4c.6-.4.6-1.2 0-1.6l-10-6.4C8.9 4.3 8 4.8 8 5.6z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
}


def filled_pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    """Solid glyph (play / stop) for the round timer button."""
    px = max(size, int(round(size * dpr)))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}">'
           f'{_FILLED_SVG[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(px / size)
    return pm


def line_pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    """A single line icon as a crisp pixmap (for labels)."""
    px = max(size, int(round(size * dpr)))
    pm = _render_line_icon(_NAV_SVG[name], color, px)
    pm.setDevicePixelRatio(px / size)
    return pm


@lru_cache(maxsize=None)
def inline_icon_html(name: str, color: str, size: int = 15, dpr: float = 1.0) -> str:
    """<img> tag with a line icon for rich-text labels (rendered at device pixels)."""
    import base64
    from PySide6.QtCore import QBuffer, QIODevice
    px = max(size, int(round(size * dpr)))
    pm = _render_line_icon(_NAV_SVG[name], color, px)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    data = base64.b64encode(bytes(buf.data())).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" width="{size}" height="{size}" align="middle">'


@lru_cache(maxsize=None)   # shared by every list row: render each icon once
def hover_icon(name: str, dpr: float = 1.0, size: int = 20, normal: str = NAV_ICON_COLOR,
               hover: str | None = None) -> QIcon:
    """For flat icon buttons: grey normally, accent green under the mouse."""
    icon = QIcon()
    icon.addPixmap(line_pixmap(name, normal, size, dpr), QIcon.Mode.Normal)
    icon.addPixmap(line_pixmap(name, hover or C["accent_text"], size, dpr), QIcon.Mode.Active)
    icon.addPixmap(line_pixmap(name, "#555555", size, dpr), QIcon.Mode.Disabled)
    return icon


def toggle_icon(name: str, dpr: float = 1.0, size: int = 20) -> QIcon:
    """For checkable buttons: grey when off, white when on (on the green fill)."""
    icon = QIcon()
    for state, color in ((QIcon.State.Off, NAV_ICON_COLOR), (QIcon.State.On, "#ffffff")):
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active):
            icon.addPixmap(line_pixmap(name, color, size, dpr), mode, state)
    return icon


def nav_icon(name: str, dpr: float = 1.0, size: int = 20) -> QIcon:
    """Grey icon normally, accent green when the menu item is selected."""
    icon = QIcon()
    px = max(size, int(round(size * dpr)))
    for mode, color in ((QIcon.Mode.Normal, NAV_ICON_COLOR),
                        (QIcon.Mode.Active, NAV_ICON_COLOR),
                        (QIcon.Mode.Selected, C["accent_text"])):
        pm = _render_line_icon(_NAV_SVG[name], color, px)
        pm.setDevicePixelRatio(px / size)
        icon.addPixmap(pm, mode)
    return icon


def color_icon(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.25, size * 0.25)
    p.end()
    return QIcon(pm)

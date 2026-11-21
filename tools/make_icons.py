"""Export assets/logo.ico (multi-size, for Windows shortcuts / a future .exe) and PNGs
of the running/idle tray icons from assets/logo.svg.

    python tools/make_icons.py
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
app = QGuiApplication(sys.argv)
from sd_time.icons import IDLE_COLOR, RUN_COLOR, assets_dir, logo_pixmap  # noqa: E402

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(size: int, color: str) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    logo_pixmap(size, color).save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, color: str) -> None:
    """ICO with PNG-compressed images (supported since Windows Vista)."""
    images = [png_bytes(s, color) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(ICO_SIZES, images):
        dim = 0 if size >= 256 else size          # 0 means 256 in ICO
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(images))


out = assets_dir()
write_ico(out / "logo.ico", RUN_COLOR)
for name, color in (("tray_running", RUN_COLOR), ("tray_idle", IDLE_COLOR)):
    logo_pixmap(64, color).save(str(out / f"{name}.png"))
for f in sorted(out.iterdir()):
    print(f"{f.name:<18} {f.stat().st_size:>7,} bytes")

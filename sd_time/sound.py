"""Chime sounds synthesized into WAV files (no bundled audio), played asynchronously."""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 22050   # plenty for a chime, and half the synthesis work

# (frequency Hz, start s) — soft bell-like notes
CHIMES = {
    "focus_done": [(659.25, 0.00), (783.99, 0.16), (1046.50, 0.32), (1046.50, 0.75)],  # E5 G5 C6 C6
    "break_done": [(1046.50, 0.00), (783.99, 0.18), (1046.50, 0.42)],                   # C6 G5 C6
}


def _render(notes: list[tuple[float, float]], length: float = 1.6) -> bytes:
    n = int(RATE * length)
    buf = [0.0] * n
    for freq, start in notes:
        s0 = int(start * RATE)
        for i in range(n - s0):
            t = i / RATE
            env = math.exp(-t * 4.2) * min(1.0, t * 200)          # quick attack, bell decay
            # fundamental + soft overtones give a bell timbre
            v = (math.sin(2 * math.pi * freq * t)
                 + 0.35 * math.sin(2 * math.pi * freq * 2.0 * t) * math.exp(-t * 3)
                 + 0.12 * math.sin(2 * math.pi * freq * 3.01 * t) * math.exp(-t * 6))
            buf[s0 + i] += v * env
    peak = max(abs(x) for x in buf) or 1.0
    scale = 0.55 * 32767 / peak
    return b"".join(struct.pack("<h", int(x * scale)) for x in buf)


def chime_path(kind: str, folder: Path) -> Path:
    path = folder / f"chime_{kind}.wav"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(_render(CHIMES[kind]))
        tmp.replace(path)   # never leave a half-written file that would play as noise
    return path


def prepare_in_background(folder: Path) -> None:
    """Synthesize missing chimes off the UI thread (first run only)."""
    import threading
    missing = [k for k in CHIMES if not (folder / f"chime_{k}.wav").exists()]
    if missing:
        threading.Thread(target=lambda: [chime_path(k, folder) for k in missing],
                         daemon=True).start()


def play(kind: str, folder: Path) -> None:
    try:
        path = chime_path(kind, folder)
    except OSError:
        path = None
    if sys.platform == "win32" and path is not None:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return
    from PySide6.QtWidgets import QApplication
    QApplication.beep()

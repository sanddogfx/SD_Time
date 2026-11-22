"""Render README screenshots on a throw-away database filled with made-up demo data.

    .venv\\Scripts\\python.exe tools\\make_screenshots.py

Writes docs/screenshots/*.png. Nothing touches your real data (%APPDATA%\\SD_Time).
All clients, projects and descriptions below are invented for illustration.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_SCALE_FACTOR", "1.25")  # crisp images; 1280x800 still fits a 1080p screen
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
app = QApplication(sys.argv)

from demo import close_window, make_db_and_settings, pump, seed, start_demo_timer  # noqa: E402
from sd_time.main_window import MainWindow  # noqa: E402
from sd_time.theme import apply_theme  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
apply_theme(app)
db, settings = make_db_and_settings()
projects, task_ids = seed(db)

w = MainWindow(db, settings)
w.resize(1280, 800)
w.show()


def shot(name: str, widget=None) -> None:
    pump()
    path = OUT / f"{name}.png"
    (widget or w).grab().save(str(path))
    print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")


start_demo_timer(w, db, projects, task_ids)

w.go(w.tracker)
w.set_mini_visible(True)
shot("tracker")
shot("mini", w.mini)
w.set_mini_visible(False)

w.go(w.pages[1])
shot("week")
wk = w.pages[1]
wk._set_mode("month")
shot("month")
wk._set_mode("week")

w.go(w.pages[2])
shot("timesheet")

rp = w.pages[3]
w.go(rp)
rp._set_kind("month")
shot("insights")

w.go(w.pages[4])
shot("projects")

w.go(w.pages[6])
# The real data path would show the Windows user name; show where a normal install keeps it.
w.pages[6].data_dir.setText(r"%APPDATA%\SD_Time")
shot("settings")


# Focus timer flavours: a small banner for the README, built from real widgets and icons.
def timers_banner():
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
    from sd_time.icons import timer_pixmap
    from sd_time.pomodoro import KINDS
    tint = {"tomato": "#f2a59f", "potato": "#e3c48f", "cucumber": "#addb92"}
    use = {"tomato": "The classic", "potato": "Deep work", "cucumber": "Quick sprints"}
    root = QWidget()
    root.setObjectName("TimersBanner")       # not "Banner": that name is the gap finder's style
    root.setStyleSheet("#TimersBanner { background: #161616; }")
    row = QHBoxLayout(root)
    row.setContentsMargins(18, 18, 18, 18)
    row.setSpacing(14)
    dpr = root.devicePixelRatioF()
    for k in KINDS.values():
        box = QFrame()
        box.setObjectName("Card")
        box.setFixedWidth(300)
        col = QVBoxLayout(box)
        col.setContentsMargins(22, 20, 22, 20)
        col.setSpacing(4)
        icon = QLabel()
        icon.setPixmap(timer_pixmap(k.key, 56, dpr))
        name = QLabel(k.name)
        name.setStyleSheet("font-size: 15pt; font-weight: 600;")
        lengths = QLabel(f"{k.focus} / {k.short_break}")
        lengths.setStyleSheet(f"font-size: 24pt; font-weight: 600; color: {tint[k.key]};")
        unit = QLabel("min focus / break")
        unit.setObjectName("Muted")
        note = QLabel(f"{use[k.key]} · long break {k.long_break} min every {k.long_every}")
        note.setObjectName("Small")
        col.addWidget(icon, 0, _Qt.AlignmentFlag.AlignLeft)
        col.addSpacing(6)
        col.addWidget(name)
        col.addWidget(lengths)
        col.addWidget(unit)
        col.addSpacing(6)
        col.addWidget(note)
        row.addWidget(box)
    root.adjustSize()
    root.show()
    return root


banner = timers_banner()
shot("timers", banner)
banner.close()

# Pomodoro "focus done" prompt, shown on its own
w.pomo.end = int(time.time()) - 1
w.on_tick()
pump()
if w._prompt is not None:
    shot("pomodoro", w._prompt)
    w._close_prompt()

close_window(w, db)

"""Render README screenshots on a throw-away database filled with made-up demo data.

    .venv\\Scripts\\python.exe tools\\make_screenshots.py

Writes docs/screenshots/*.png. Nothing touches your real data (%APPDATA%\\SD_Time).
All clients, projects and descriptions below are invented for illustration.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_SCALE_FACTOR", "1.5")   # crisp, high-DPI images
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QLocale, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
app = QApplication(sys.argv)

from sd_time.db import Database, day_start_ts  # noqa: E402
from sd_time.main_window import MainWindow  # noqa: E402
from sd_time.theme import apply_theme  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
apply_theme(app)
tmp = Path(tempfile.mkdtemp(prefix="sd_time_shots_"))
db = Database(tmp / "demo.db")
settings = QSettings(str(tmp / "settings.ini"), QSettings.Format.IniFormat)
settings.setValue("hotkey", "")
settings.setValue("pomodoro/sound", False)
settings.setValue("tray_hint_shown", True)

# ------------------------------------------------------------------ demo data
db.set_setting("currency", "USD")
db.set_setting("default_rate", 35)
northwind = db.add_client("Northwind Studio", rate=60)
bluefin = db.add_client("Bluefin Games", rate=75)
lumen = db.add_client("Lumen Coffee", rate=50)

projects = {
    "brand": (db.add_project("Brand Refresh", northwind, "#2196f3"),
              ["Logo animation", "Style frames", "Client review"]),
    "web": (db.add_project("Website Motion", northwind, "#26a69a"),
            ["Hero loop", "Micro-interactions"]),
    "trailer": (db.add_project("Launch Trailer", bluefin, "#ab47bc"),
                ["Storyboard", "Edit", "Color grade", "Sound pass"]),
    "capsules": (db.add_project("Store Capsules", bluefin, "#ec407a"), ["Key art", "Variants"]),
    "promo": (db.add_project("Spring Promo", lumen, "#ff9800"), ["Social cuts", "Stills"]),
    "internal": (db.add_project("Internal", None, "#8d6e63"), ["Planning", "Inbox"]),
    "stock": (db.add_project("Stock Footage", None, "#7cb342", rate=25), ["Upload & tagging"]),
}
task_ids = {key: [db.add_task(pid, name) for name in names] for key, (pid, names) in projects.items()}
db.update_task(task_ids["trailer"][2], rate=90)   # colour grading billed higher

DESCRIPTIONS = {
    "brand": ["Logo reveal v3", "Type animation", "Feedback round 2", ""],
    "web": ["Hero loop polish", "Button hover states", ""],
    "trailer": ["Shot 12-18 rough cut", "Grade pass", "Music sync", "Storyboard frames"],
    "capsules": ["Capsule 616x353", "Main capsule variants", ""],
    "promo": ["Reels 9:16 cuts", "Product stills"],
    "internal": ["Weekly planning", "Email & invoices", "Client call"],
    "stock": ["Upload batch", "Keywords"],
}
WEIGHTS = {"brand": 5, "web": 2, "trailer": 6, "capsules": 2, "promo": 3, "internal": 2, "stock": 1}

random.seed(7)
today = date.today()
for back in range(16, 0, -1):          # past days (today is filled separately)
    d = today - timedelta(days=back)
    if d.weekday() >= 5:
        continue
    t = day_start_ts(d, 8, random.choice([30, 45, 0]))
    end_of_day = day_start_ts(d, 18, random.choice([0, 30]))
    while t < end_of_day - 1800:
        key = random.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
        pid, _ = projects[key]
        dur = random.choice([1800, 2700, 3600, 5400, 7200])
        db.add_entry(t, min(t + dur, end_of_day), pid, random.choice(task_ids[key]),
                     random.choice(DESCRIPTIONS[key]))
        t += dur + random.choice([0, 600, 900, 1800])

# today: a few finished entries, then a running timer with a Pomodoro focus session
now = int(time.time())
start = min(day_start_ts(today, 9), now - 5 * 3600)
for key, task, desc, dur in (("internal", 0, "Weekly planning", 1800),
                             ("trailer", 1, "Shot 12-18 rough cut", 5400),
                             ("brand", 0, "Logo reveal v3", 3600)):
    db.add_entry(start, start + dur, projects[key][0], task_ids[key][task], desc)
    start += dur + 900

# ------------------------------------------------------------------ window
w = MainWindow(db, settings)
w.resize(1280, 800)
w.show()


def pump(n: int = 8) -> None:
    for _ in range(n):
        app.processEvents()
        time.sleep(0.04)


def shot(name: str, widget=None) -> None:
    pump()
    path = OUT / f"{name}.png"
    (widget or w).grab().save(str(path))
    print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")


# Running timer in Pomodoro mode, 12 minutes into a focus session
settings.setValue("pomodoro/enabled", True)
w.start(projects["trailer"][0], task_ids["trailer"][2], "Grade pass")
r = db.running_entry()
db.update_entry(r["id"], start_ts=now - 12 * 60)
w.pomo.end = now - 12 * 60 + w.pomo.config.focus
w.notify()

w.go(w.tracker)
shot("tracker")

cal = w.pages[1]
w.go(cal)
pump()
cal.scroll.verticalScrollBar().setValue(int(7.5 * cal.view.hour_h))
shot("calendar")

w.go(w.pages[2])
shot("timesheet")

rp = w.pages[3]
w.go(rp)
rp.period.setCurrentIndex(rp.period.findData("last_week"))
shot("reports")

w.go(w.pages[4])
shot("projects")

w.go(w.pages[6])
shot("settings")

# Pomodoro "focus done" prompt, shown on its own
w.pomo.end = int(time.time()) - 1
w.on_tick()
pump()
if w._prompt is not None:
    shot("pomodoro", w._prompt)
    w._close_prompt()

w._really_quit = True
w.tray.hide()
w.close()
db.close()

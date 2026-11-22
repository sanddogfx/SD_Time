"""Made-up demo data and a ready main window, shared by make_screenshots.py and preview.py.

Everything lives in a throw-away folder: your real data (%APPDATA%\\SD_Time) is never touched.
Create the QApplication (and set QT_* environment variables) before importing this module.
All clients, projects and descriptions are invented for illustration.
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sd_time.db import Database, day_start_ts  # noqa: E402


def make_db_and_settings() -> tuple[Database, QSettings]:
    """Empty database + settings in a temp folder; hotkeys, sounds and update checks off."""
    tmp = Path(tempfile.mkdtemp(prefix="sd_time_demo_"))
    db = Database(tmp / "demo.db")
    settings = QSettings(str(tmp / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("hotkey", "")          # the real app may hold Ctrl+Alt+T / M
    settings.setValue("mini_hotkey", "")
    settings.setValue("pomodoro/sound", False)
    settings.setValue("tray_hint_shown", True)
    settings.setValue("updates/auto", False)
    settings.setValue("updates/last_check", int(time.time()))
    return db, settings


def seed(db: Database) -> tuple[dict, dict]:
    """Fill db with 12 weeks of plausible work. Returns (projects, task_ids) keyed by short name:
    projects[key] = (project_id, [task names]), task_ids[key] = [task ids]."""
    db.set_setting("currency", "USD")
    db.set_setting("default_rate", 35)
    db.set_currencies(["USD", "EUR", "GBP"], "USD")
    northwind = db.add_client("Northwind Studio", rate=60)
    bluefin = db.add_client("Bluefin Games", rate=75)
    lumen = db.add_client("Lumen Coffee", rate=45, currency="EUR")

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

    descriptions = {
        "brand": ["Logo reveal v3", "Type animation", "Feedback round 2", ""],
        "web": ["Hero loop polish", "Button hover states", ""],
        "trailer": ["Shot 12-18 rough cut", "Grade pass", "Music sync", "Storyboard frames"],
        "capsules": ["Capsule 616x353", "Main capsule variants", ""],
        "promo": ["Reels 9:16 cuts", "Product stills"],
        "internal": ["Weekly planning", "Email & invoices", "Client call"],
        "stock": ["Upload batch", "Keywords"],
    }
    weights = {"brand": 5, "web": 2, "trailer": 6, "capsules": 2, "promo": 3, "internal": 2, "stock": 1}

    random.seed(7)
    today = date.today()
    for back in range(84, 0, -1):          # 12 weeks back (today is filled separately)
        d = today - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        t = day_start_ts(d, 8, random.choice([30, 45, 0]))
        end_of_day = day_start_ts(d, 18, random.choice([0, 30]))
        while t < end_of_day - 1800:
            key = random.choices(list(weights), weights=list(weights.values()))[0]
            pid, _ = projects[key]
            dur = random.choice([1800, 2700, 3600, 5400, 7200])
            db.add_entry(t, min(t + dur, end_of_day), pid, random.choice(task_ids[key]),
                         random.choice(descriptions[key]))
            if dur >= 3600 and random.random() < 0.6:      # a Pomodoro focus inside longer blocks
                db.log_focus(t, t + 1500, None, "break" if random.random() < 0.8 else "skip")
            t += dur + random.choice([0, 600, 900, 1800])

    # today: a few finished entries (the running timer is started by start_demo_timer)
    now = int(time.time())
    start = min(day_start_ts(today, 9), now - 5 * 3600)
    for key, task, desc, dur in (("internal", 0, "Weekly planning", 1800),
                                 ("trailer", 1, "Shot 12-18 rough cut", 5400),
                                 ("brand", 0, "Logo reveal v3", 3600)):
        db.add_entry(start, start + dur, projects[key][0], task_ids[key][task], desc)
        start += dur + 900
    return projects, task_ids


def start_demo_timer(w, db: Database, projects: dict, task_ids: dict) -> None:
    """Running timer in Pomodoro mode, 12 minutes into a focus session."""
    now = int(time.time())
    w.settings.setValue("pomodoro/enabled", True)
    w.start(projects["trailer"][0], task_ids["trailer"][2], "Grade pass")
    r = db.running_entry()
    db.update_entry(r["id"], start_ts=now - 12 * 60)
    w.pomo.end = now - 12 * 60 + w.pomo.config.focus
    w.notify()


def pump(n: int = 8) -> None:
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()
        time.sleep(0.04)


def close_window(w, db: Database) -> None:
    w._really_quit = True
    w.tray.hide()
    w.close()
    db.close()

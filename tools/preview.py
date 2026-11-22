"""Render one or more SD Time screens to PNG, off screen, on throw-away demo data.

    .venv\\Scripts\\python.exe tools\\preview.py tracker week
    .venv\\Scripts\\python.exe tools\\preview.py all --size 1000x640      (the smallest window the app allows)
    .venv\\Scripts\\python.exe tools\\preview.py tracker --empty --idle

Screens: tracker, mini, week, month, timesheet, insights, projects, clients, settings,
entry (edit-entry dialog), project (project dialog), pomodoro (focus-done prompt), or all.
Writes previews/<screen>.png (git-ignored). Nothing appears on screen, no hotkeys are taken
and your real data (%APPDATA%\\SD_Time) is never touched, so it runs next to the real app.
For quick design checks after a change; README images come from make_screenshots.py.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ["tracker", "mini", "week", "month", "timesheet", "insights", "projects", "clients",
           "settings", "entry", "project", "pomodoro"]

ap = argparse.ArgumentParser(description="Render SD Time screens to PNG.")
ap.add_argument("screens", nargs="+", choices=SCREENS + ["all"], metavar="SCREEN",
                help=", ".join(SCREENS) + ", all")
ap.add_argument("--size", default="1320x840", help="window size WxH (default 1320x840, as the app opens; minimum 1000x640)")
ap.add_argument("--scale", default="1", help="Qt scale factor (default 1; README uses 1.25)")
ap.add_argument("--empty", action="store_true", help="no demo data: empty states")
ap.add_argument("--idle", action="store_true", help="no running timer")
ap.add_argument("--out", default=str(ROOT / "previews"), help="output folder")
ap.add_argument("--show", action="store_true", help="real window instead of off screen")
args = ap.parse_args()

if not args.show:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # the offscreen platform has no fonts of its own; FreeType text differs a hair from DirectWrite
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ["QT_SCALE_FACTOR"] = args.scale
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
app = QApplication(sys.argv)

import sd_time.main_window as mw  # noqa: E402
from demo import close_window, make_db_and_settings, pump, seed, start_demo_timer  # noqa: E402
from sd_time.dialogs import EntryDialog, ProjectDialog  # noqa: E402
from sd_time.theme import apply_theme  # noqa: E402

mw.show_error = lambda *a, **k: print("show_error:", a[1:] if len(a) > 1 else a)  # no modal boxes

apply_theme(app)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
width, height = (int(v) for v in args.size.lower().split("x"))
screens = SCREENS if "all" in args.screens else list(dict.fromkeys(args.screens))

db, settings = make_db_and_settings()
projects, task_ids = ({}, {}) if args.empty else seed(db)
w = mw.MainWindow(db, settings)
w.resize(width, height)
w.show()
if not args.empty and not args.idle:
    start_demo_timer(w, db, projects, task_ids)


def save(name: str, widget) -> None:
    pump()
    path = out / f"{name}.png"
    widget.grab().save(str(path))
    print(f"{path}  {widget.width()}x{widget.height()}")


def dialog(name: str, dlg) -> None:
    dlg.show()
    save(name, dlg)
    dlg.reject()


for name in screens:
    if name == "tracker":
        w.go(w.tracker)
        save(name, w)
    elif name == "mini":
        w.set_mini_visible(True)
        save(name, w.mini)
        w.set_mini_visible(False)
    elif name in ("week", "month"):
        w.go(w.pages[1])
        w.pages[1]._set_mode(name)
        save(name, w)
        w.pages[1]._set_mode("week")
    elif name == "timesheet":
        w.go(w.pages[2])
        save(name, w)
    elif name == "insights":
        w.go(w.pages[3])
        w.pages[3]._set_kind("month")
        save(name, w)
    elif name in ("projects", "clients", "settings"):
        page = w.pages[{"projects": 4, "clients": 5, "settings": 6}[name]]
        w.go(page)
        if name == "settings":
            page.data_dir.setText(r"%APPDATA%\SD_Time")
        save(name, w)
    elif name == "entry":
        entries = db.entries(0, int(time.time()) + 86400)
        dialog(name, EntryDialog(db, w, entry=entries[-1], on_delete=lambda: False)
               if entries else EntryDialog(db, w))
    elif name == "project":
        pid = projects["trailer"][0] if projects else None
        dialog(name, ProjectDialog(db, w, project=db.get_project(pid)) if pid else ProjectDialog(db, w))
    elif name == "pomodoro":
        settings.setValue("pomodoro/enabled", True)
        if db.running_entry() is None:
            w.start(None, None, "Focus")
        w.pomo.end = int(time.time()) - 1
        w.on_tick()
        pump()
        if w._prompt is not None:
            save(name, w._prompt)
            w._close_prompt()
        else:
            print("pomodoro: prompt did not appear")

close_window(w, db)

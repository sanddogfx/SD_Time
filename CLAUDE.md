# SD Time — notes for Claude

Desktop time tracker for Windows. Python 3 + PySide6, SQLite, tray app with global hotkeys.
The user writes in Russian; UI text, code, comments, commits and repo docs stay in English.

## Run, test, build
- Run from source: `SD_Time.bat` (uses `.venv\Scripts\pythonw.exe SD_Time.pyw`). Single instance via QLocalServer.
- Tests: `.venv\Scripts\python.exe -m unittest discover tests` (stdlib unittest, `Database(":memory:")`).
- Build: `.\build.ps1` (PyInstaller + Inno Setup → `dist\`) runs `--selftest`. Only at release time, not after every change.
- App flags: `--hidden` (start in the tray), `--selftest=FILE` (throw-away DB, writes OK/error, exits).
- Data: `%APPDATA%\SD_Time\sd_time.db` + `settings.ini` (QSettings, INI). Never touch the real data; use temp dirs.

## Map (`sd_time/`)
- `app.py` is the entry point: single instance, settings, startup.
- `main_window.py` has the sidebar, pages, tray, hotkeys and the controller (start/stop logic).
- `db.py` holds the schema (`SCHEMA_VERSION`, migrations) and all queries. clients ← projects ← tasks; entries hold Unix ts; running entry = `end_ts IS NULL`; the rate is inherited task → project → client → default.
- `pages/`: `today.py` Tracker (ring timer, today ribbon), `week.py` calendar with drag, `ledger.py` Timesheet + gap finder, `insights.py` reports/export (openpyxl), `manage.py` Projects / Clients / Settings / About.
- `mini.py` is the always-on-top mini timer. It shares the draft with Tracker.
- `pomodoro.py` is a pure state machine for focus flavours (Pomodoro / Potato / Cucumber).
- `theme.py` has the colour dict `C`, one QSS stylesheet and the design rules. `widgets.py` holds shared widgets, `dialogs.py` the entry/client/project dialogs.
- `icons.py` tints the SVG logo, `sound.py` synthesizes chimes, `hotkey.py` wraps RegisterHotKey, `autostart.py` writes the HKCU Run key, `updates.py` does the GitHub release check, `util.py` formats time and money.
- `tools/` holds asset and screenshot generators (`make_screenshots.py` uses a fake demo DB). `packaging/` holds the .spec and installer.iss.

## Design rules (user is picky about these)
- All controls are `CTRL_H` tall. Radii: cards 8, controls 5, inner bits 3. One fill and one outline for controls.
- Dark theme, olive-green accent, Segoe UI. Watch for clipped text, uneven sizes and low icon contrast.
- For visual changes, check before reporting: `.venv\Scripts\python.exe tools\preview.py <screen...>` renders off screen on demo data to `previews\<screen>.png` (screens: tracker mini week month timesheet insights projects clients settings entry project pomodoro all; `--size 1000x640` for the minimum window, `--empty`, `--idle`). Safe to run next to the user's app. Render only the screens you touched.
- Demo data lives in `tools/demo.py` (shared with `make_screenshots.py`, which makes the README images).

## Rules
- Commit, push, tag and release only when the user says so. Commit messages: UTF-8 file without BOM, `git commit -F`.
- Release: bump `sd_time/__init__.py` + CHANGELOG + README badge → `build.ps1` → commit, tag `vX.Y.Z`, `push --follow-tags` → `gh release create` (gh at `C:\Program Files\GitHub CLI\gh.exe`, notes via `--notes-file` in UTF-8).
- Add user-facing changes to CHANGELOG `[Unreleased]` as you go.
- The user's own SD Time is often running and holds Ctrl+Alt+T/M. Never kill their python processes. Smoke tests must stub `show_error` (a modal box hangs them).
- The installer test uses the real AppId. Run it only when SD Time is not installed (check the HKCU Uninstall key).
- Python one-liners through PowerShell break on quotes. Put scripts in the scratchpad instead.

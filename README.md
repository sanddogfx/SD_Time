# SD Time

Desktop time tracker for Windows: timer in the system tray, clients → projects → tasks,
hourly rates, calendar, timesheet and reports with Excel export.

## Install

Run `SD_Time_Setup_<version>.exe` (from `dist\` after a build). No admin rights needed:
it installs for the current user, adds a Start menu shortcut, and optionally a desktop
shortcut and "Start with Windows". Running a newer installer updates in place.
Uninstall from Settings → Apps; your time data stays unless you choose to delete it.

## Build the installer

```powershell
.\build.ps1
```

Builds `dist\SD Time\SD Time.exe` (PyInstaller, no Python needed to run it), self-tests it,
then `dist\SD_Time_Setup_<version>.exe` (Inno Setup 6: `winget install JRSoftware.InnoSetup`).
`.\build.ps1 -NoInstaller` builds only the app folder.

## Run from source

Double-click `SD_Time.bat`. Start hidden in the tray: `SD_Time.bat --hidden`.

First setup on a new machine:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Pages

- **Time Tracker**: type what you're working on, pick a project (and task), press START.
  Entries below are grouped by week and day; edit the description or project in place,
  click the time range to edit times, ▷ continues an activity, ⋮ duplicates or deletes.
  ＋ adds time manually.
- **Calendar**: week or day grid. Drag on empty space to add time, click an entry to edit,
  double-click for a one-hour entry. − / + zoom.
- **Timesheet**: one row per project/task, one column per day. Double-click a cell and type
  `1:30` or `1.5`: more time adds an entry, less time trims the latest entries.
- **Reports**: period, client and project filters; stacked bar chart by day (by month for long
  periods); grouping Project › Task, Project › Description, Client › Project, Description; donut
  chart; amounts. Export to Excel (Summary + Detailed sheets) or CSV.
- **Projects / Clients**: create, edit, archive, delete. A project's dialog also manages its tasks.
- **Settings**: currency, default hourly rate, global hotkey, close-to-tray.

## Pomodoro

The 🍅 button next to START turns Pomodoro mode on. START then runs a focus session (25 min by
default) with a countdown. When it ends a chime plays and a window asks: **Take a break** (the entry
stops exactly at the focus end, the break counts down untracked) or **Skip, keep working** (the
entry keeps running and a new focus session starts). Closing that window counts as a break. When a
break ends you're asked to start the next focus. Every 4th break is long. Lengths, auto-start and
sound are in Settings.

A timer stopped within 5 seconds of starting is treated as a misclick and not saved.

## Rates

A rate is inherited: **task → project → client → default rate**. Leave a rate empty to inherit.
Amounts are calculated from the current rates when shown or exported.

## Hotkey and tray

`Ctrl+Alt+T` works from any app: it stops the running timer, or starts what's typed in the timer
bar, or continues the last entry. Left-click the tray icon to show/hide the window; right-click for
start/stop, recent activities and quit. Closing the window keeps SD Time running in the tray.

## Data

Everything is in `%APPDATA%\SD_Time\`: `sd_time.db` (SQLite) and `settings.ini`.
Copy that folder to back up. Deleting a client keeps its projects; deleting a project or task
keeps its time entries (without the project/task).

## Versions

The version is in `sd_time/__init__.py` (shown in Settings); changes are listed in
[CHANGELOG.md](CHANGELOG.md). Releases are git tags `vMAJOR.MINOR.PATCH`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

# Changelog

Versions follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
New features bump MINOR, fixes bump PATCH. The version lives in `sd_time/__init__.py`.

## [Unreleased]

## [0.3.0] - 2026-11-21

A new look of its own.

### Changed
- Icon rail instead of the wide text menu; sentence-case labels, rounded cards,
  monospaced digits, projects as tinted chips.
- Tracker: a ring timer (shows Pomodoro progress), round start/stop, "Start again"
  with recent activities, "Today" as a time ribbon with compact lines; earlier days fold
  into one line each.
- Calendar → Week: days are rows and hours run left to right, with Day / Week / Month.
  Drag to create, move (also to another day) and resize; Esc cancels.
- Reports → Insights: KPI cards (tracked with change, billable, per workday, focus
  sessions), a 12-week heatmap, ranked projects / clients / tasks, a by-client strip.
  Excel / CSV export kept.
- Timesheet: a ledger of day pills filled by hours, day totals with load bars.

### Added
- Gap finder on the Timesheet: untracked time between entries, filled in one click.
- Pomodoro focus sessions are recorded (database schema v4) and counted in Insights.

## [0.2.1] - 2026-11-21

### Fixed
- Timesheet: "Add new row" shows the line plus icon instead of a font glyph.
- Reports: group titles no longer truncated next to the donut chart.

### Added
- README with screenshots; `tools/make_screenshots.py` renders them on demo data.

## [0.2.0] - 2026-11-21

### Added
- Windows installer (`SD_Time_Setup_<version>.exe`, Inno Setup): per-user install without
  admin rights, Start menu shortcut, optional desktop shortcut and autostart, listed in
  Apps & features, uninstaller that keeps your data unless you choose to delete it.
- Standalone build (PyInstaller): runs without Python installed.
- Settings: "Start SD Time when Windows starts".
- `build.ps1`: one-command build with a self-test of the built app (`--selftest`).
- Version shown in Settings.

## [0.1.0] - 2026-11-21

First version.

### Added
- Timer in the system tray with a global start/stop hotkey (`Ctrl+Alt+T` by default).
- Clients → projects → tasks; client and task are optional.
- Hourly rates inherited task → project → client → default rate; amounts everywhere.
- Time Tracker page: timer bar with autocomplete, entries grouped by week and day,
  inline editing, continue, duplicate, delete, manual entries.
- Calendar (week/day): drag to create, drag to move between days, drag edges to resize.
- Timesheet: weekly grid, type `1:30` or `1.5` into a cell.
- Reports: filters, stacked bar chart by day/month, grouping, donut chart,
  Excel (Summary + Detailed) and CSV export.
- Pomodoro mode: focus countdown, chime, "take a break / keep working" prompt,
  long break every N sessions, settings.
- Dark grey theme with an olive-green accent, own line icons, raccoon logo
  (with a small-size variant for the tray and menu).
- SQLite storage in `%APPDATA%\SD_Time`, automatic migration from the first schema.

### Fixed (during the first QA pass)
- Report donut crashed on an empty database.
- Duplicating a 0-second entry crashed; misclick start/stop (<5 s) no longer saves entries.
- Deleting a client could leave two client-less projects with the same name.
- First-run chime synthesis froze the UI; tables filled in quadratic time.

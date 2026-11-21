# Changelog

Versions follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
New features bump MINOR, fixes bump PATCH. The version lives in `sd_time/__init__.py`.

## [Unreleased]

## [0.5.0] - 2026-11-21

Stay up to date.

### Added
- **Update check**: once a day SD Time asks GitHub for the latest release number. A newer
  version shows a tray notification and an *Update to …* item in the tray menu; both open
  the release page. Nothing is downloaded or installed on its own, and only the version
  question is sent. Each version is announced once.
- **Settings → About**: version, links to the GitHub page, releases and issues, *Check for
  updates* and the automatic-check switch.

### Changed
- Settings: *Save* moved to the page header; the page scrolls on short windows.
- Self-test of the built app also checks that HTTPS (Qt TLS plugin) is bundled.

## [0.4.0] - 2026-11-21

Tasks in plain sight, flatter look.

### Added
- **Focus timer flavours**: 🍅 Pomodoro (25 / 5, long 15 every 4), 🥔 Potato (50 / 10,
  long 20 every 3) and 🥒 Cucumber (15 / 3, long 10 every 4). The chip above the ring is
  now a menu: pick a flavour or *Off*. Each flavour keeps its own lengths (Settings →
  Focus timer); the old Pomodoro lengths carry over. Its icon shows on the chip, in the
  mini timer and in the break prompt.
- **Mini timer**: a small always-on-top window with the description, project · task,
  the time and START/STOP. It shares the draft with the Tracker page, follows the
  running entry (edits go to it), shows the Pomodoro countdown, can be dragged anywhere
  and remembers its place and whether it was open. Open it with `Ctrl+Alt+M`
  (configurable in Settings), *Mini timer* in the tray menu, or the button next to
  *Add time*. Right-click it for more.
- Projects page shows each project's tasks underneath it, with the task's rate (own or
  inherited), tracked time and amount. Projects fold and unfold; folding is remembered.
- "+ Add task" row under every active project, and a small task window (name + rate).
- Double-click a task to edit it; right-click for archive / restore and delete.
- Search on the Projects page also finds tasks.
- Project picker (timer, entry window): "+ Add task" under every project, and
  "+ New client" next to "+ New project" (client first, then its first project).
  Type a task name that does not exist yet and every project offers
  "+ Add task “name”": one click creates it and picks it.

### Fixed (picker)
- Search results in the project picker open their projects, so matching tasks show
  without an extra click.

### Changed
- Numbers (timers, totals, KPIs) use Segoe UI instead of a monospace font.
- Smaller corner radii everywhere: cards, buttons, inputs, chips, calendar
  blocks, charts. The start/stop buttons are now rounded squares.
- One height (36 px) for every control: buttons, arrows, inputs, drop-downs,
  segmented switches and header figures line up in every page header.
- Buttons, arrows and switches share one fill and outline; hover lightens the fill.
- Checkboxes are visible on the dark background and turn green when checked.
- Insights: "By client" sits right under the bars instead of at the card bottom.

### Fixed
- The Day / Week / Month switch no longer clips its highlighted option
  (the checked label was bolder, so wider, than the space reserved for it).
- The Export button shows its drop-down arrow in the right place.
- "Start again" no longer flashes a lighter background while it refreshes.

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

"""SQLite storage for SD Time.

Model (single user):
    clients  <- projects (client optional) <- tasks
    entries: description + optional project + optional task + start/end

Times are Unix timestamps (seconds). An entry belongs to the day it started.
The running timer is the entry with end_ts IS NULL (at most one at a time).

Hourly rate is inherited: task -> project -> client -> default rate (meta table).
NULL rate means "inherit".
"""
from __future__ import annotations

import os
import sqlite3
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

SCHEMA_VERSION = 4

CLIENTS_DDL = """
CREATE TABLE IF NOT EXISTS clients (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    rate     REAL,
    archived INTEGER NOT NULL DEFAULT 0,
    created  INTEGER NOT NULL
)"""
PROJECTS_DDL = """
CREATE TABLE {name} (
    id        INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    name      TEXT    NOT NULL,
    color     TEXT    NOT NULL DEFAULT '#4a90d9',
    rate      REAL,
    archived  INTEGER NOT NULL DEFAULT 0,
    created   INTEGER NOT NULL
)"""
TASKS_DDL = """
CREATE TABLE {name} (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    rate       REAL,
    archived   INTEGER NOT NULL DEFAULT 0,
    created    INTEGER NOT NULL
)"""
ENTRIES_DDL = """
CREATE TABLE {name} (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    description TEXT    NOT NULL DEFAULT '',
    start_ts    INTEGER NOT NULL,
    end_ts      INTEGER
)"""
META_DDL = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
# v4: finished Pomodoro focus sessions (for Insights). outcome: "break" | "skip".
FOCUS_DDL = """
CREATE TABLE IF NOT EXISTS focus_sessions (
    id       INTEGER PRIMARY KEY,
    start_ts INTEGER NOT NULL,
    end_ts   INTEGER NOT NULL,
    entry_id INTEGER,
    outcome  TEXT    NOT NULL DEFAULT 'break'
)"""
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_entries_start   ON entries(start_ts);
CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_task    ON entries(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project   ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_id);
"""

PALETTE = [
    "#2196f3", "#ab47bc", "#7cb342", "#ff9800", "#ef5350",
    "#26a69a", "#ffca28", "#5c6bc0", "#ec407a", "#8d6e63",
]

ENTRY_SELECT = """
SELECT e.id, e.project_id, e.task_id, e.description, e.start_ts, e.end_ts,
       p.name  AS project_name,
       p.color AS project_color,
       t.name  AS task_name,
       c.id    AS client_id,
       c.name  AS client_name,
       COALESCE(t.rate, p.rate, c.rate) AS own_rate
FROM entries e
LEFT JOIN projects p ON p.id = e.project_id
LEFT JOIN tasks    t ON t.id = e.task_id
LEFT JOIN clients  c ON c.id = p.client_id
"""

_UNSET = object()
NO_COLOR = "#9a9a9a"
MIN_ENTRY = 5   # seconds; a timer run shorter than this is treated as a misclick


class DuplicateNameError(ValueError):
    pass


def default_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "SD_Time"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now(now: int | None) -> int:
    return int(time.time()) if now is None else int(now)


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name cannot be empty")
    return name


def _clean_rate(rate) -> float | None:
    if rate is None or rate == "":
        return None
    rate = float(rate)
    if rate < 0:
        raise ValueError("Rate cannot be negative")
    return rate


def _check_unique(rows, name: str, exclude_id: int | None, what: str) -> None:
    # Python casefold() handles any alphabet; SQLite NOCASE only handles ASCII.
    key = name.casefold()
    for row in rows:
        if row["id"] != exclude_id and row["name"].casefold() == key:
            raise DuplicateNameError(f'{what} "{name}" already exists')


def money(seconds: float, rate: float | None) -> float:
    return 0.0 if not rate else seconds / 3600 * rate


def day_start_ts(d: date, hour: int = 0, minute: int = 0) -> int:
    return int(datetime.combine(d, dtime(hour, minute)).timestamp())


class Database:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = default_data_dir() / "sd_time.db"
        self.path = path
        self._meta: dict | None = None
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._migrate()
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    # ================================================================ schema
    def _columns(self, table: str) -> list[str]:
        return [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]

    def _migrate(self) -> None:
        if self.conn.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
            return
        # Foreign keys must be off while tables are rebuilt (SQLite ALTER procedure).
        self.conn.execute("PRAGMA foreign_keys = OFF")
        old_projects = self._columns("projects")
        if old_projects and "client_id" not in old_projects:
            self._migrate_from_v1()
        self.conn.execute(CLIENTS_DDL)
        self.conn.execute(PROJECTS_DDL.format(name="IF NOT EXISTS projects"))
        self.conn.execute(TASKS_DDL.format(name="IF NOT EXISTS tasks"))
        self.conn.execute(ENTRIES_DDL.format(name="IF NOT EXISTS entries"))
        self.conn.execute(META_DDL)
        self.conn.execute(FOCUS_DDL)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_focus_start ON focus_sessions(start_ts)")
        self.conn.executescript(INDEXES)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def _migrate_from_v1(self) -> None:
        """v1: projects/tasks/entries(task_id, note) without clients and rates."""
        c = self.conn
        c.execute(CLIENTS_DDL)
        c.execute(PROJECTS_DDL.format(name="projects_new"))
        c.execute(TASKS_DDL.format(name="tasks_new"))
        c.execute(ENTRIES_DDL.format(name="entries_new"))
        c.execute("""INSERT INTO projects_new (id, client_id, name, color, archived, created)
                     SELECT id, NULL, name, color, archived, created FROM projects""")
        c.execute("""INSERT INTO tasks_new (id, project_id, name, archived, created)
                     SELECT id, project_id, name, archived, created FROM tasks""")
        c.execute("""INSERT INTO entries_new (id, project_id, task_id, description, start_ts, end_ts)
                     SELECT e.id, t.project_id, e.task_id, e.note, e.start_ts, e.end_ts
                     FROM entries e LEFT JOIN tasks t ON t.id = e.task_id""")
        for table in ("entries", "tasks", "projects"):
            c.execute(f"DROP TABLE {table}")
        for table in ("projects", "tasks", "entries"):
            c.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
        c.commit()

    # ================================================================== meta
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        # Cached: currency/default rate are read for every entry shown.
        if self._meta is None:
            self._meta = dict(self.conn.execute("SELECT key, value FROM meta").fetchall())
        value = self._meta.get(key)
        return default if value is None else value

    def set_setting(self, key: str, value) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, None if value is None else str(value)))
        self._meta = None

    @property
    def currency(self) -> str:
        return self.get_setting("currency", "USD") or ""

    @property
    def default_rate(self) -> float | None:
        value = self.get_setting("default_rate")
        return float(value) if value not in (None, "") else None

    def rate_of(self, entry) -> float | None:
        rate = entry["own_rate"]
        return rate if rate is not None else self.default_rate

    # =============================================================== clients
    def clients(self, include_archived: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM clients"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY archived, name COLLATE NOCASE"
        return self.conn.execute(sql).fetchall()

    def get_client(self, client_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()

    def add_client(self, name: str, rate: float | None = None) -> int:
        name = _clean_name(name)
        _check_unique(self.clients(True), name, None, "Client")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO clients (name, rate, created) VALUES (?, ?, ?)",
                (name, _clean_rate(rate), _now(None)))
        return cur.lastrowid

    def update_client(self, client_id: int, *, name: str | None = None, rate=_UNSET,
                      archived: bool | None = None) -> None:
        fields: dict = {}
        if name is not None:
            name = _clean_name(name)
            _check_unique(self.clients(True), name, client_id, "Client")
            fields["name"] = name
        if rate is not _UNSET:
            fields["rate"] = _clean_rate(rate)
        if archived is not None:
            fields["archived"] = int(archived)
        self._update("clients", client_id, fields)

    def delete_client(self, client_id: int) -> None:
        """Projects of the client are kept, without a client. A project whose name would
        clash with an existing client-less project gets the client's name appended."""
        client = self.get_client(client_id)
        if client is None:
            return
        taken = {p["name"].casefold() for p in self.projects(None, include_archived=True)}
        with self.conn:
            for p in self.projects(client_id, include_archived=True):
                name = p["name"]
                if name.casefold() in taken:
                    base = f"{name} ({client['name']})"
                    name, n = base, 2
                    while name.casefold() in taken:
                        name, n = f"{base} {n}", n + 1
                    self.conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, p["id"]))
                taken.add(name.casefold())
            self.conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))

    # ============================================================== projects
    _PROJECT_SELECT = """
        SELECT p.*, c.name AS client_name, c.rate AS client_rate,
               COALESCE(p.rate, c.rate) AS own_rate
        FROM projects p LEFT JOIN clients c ON c.id = p.client_id"""

    def projects(self, client_id=_UNSET, include_archived: bool = False) -> list[sqlite3.Row]:
        sql = self._PROJECT_SELECT + " WHERE 1 = 1"
        args: list = []
        if client_id is not _UNSET:
            if client_id is None:
                sql += " AND p.client_id IS NULL"
            else:
                sql += " AND p.client_id = ?"
                args.append(client_id)
        if not include_archived:
            sql += " AND p.archived = 0"
        sql += " ORDER BY p.archived, p.name COLLATE NOCASE"
        return self.conn.execute(sql, args).fetchall()

    def get_project(self, project_id: int) -> sqlite3.Row | None:
        return self.conn.execute(self._PROJECT_SELECT + " WHERE p.id = ?",
                                 (project_id,)).fetchone()

    def add_project(self, name: str, client_id: int | None = None, color: str | None = None,
                    rate: float | None = None) -> int:
        name = _clean_name(name)
        _check_unique(self.projects(client_id, True), name, None, "Project")
        if color is None:
            count = self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            color = PALETTE[count % len(PALETTE)]
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO projects (client_id, name, color, rate, created)
                   VALUES (?, ?, ?, ?, ?)""",
                (client_id, name, color, _clean_rate(rate), _now(None)))
        return cur.lastrowid

    def update_project(self, project_id: int, *, name: str | None = None, client_id=_UNSET,
                       color: str | None = None, rate=_UNSET,
                       archived: bool | None = None) -> None:
        current = self.get_project(project_id)
        if current is None:
            return
        fields: dict = {}
        new_client = current["client_id"] if client_id is _UNSET else client_id
        new_name = current["name"] if name is None else _clean_name(name)
        if name is not None or client_id is not _UNSET:
            _check_unique(self.projects(new_client, True), new_name, project_id, "Project")
            fields["name"] = new_name
            fields["client_id"] = new_client
        if color is not None:
            fields["color"] = color
        if rate is not _UNSET:
            fields["rate"] = _clean_rate(rate)
        if archived is not None:
            fields["archived"] = int(archived)
        self._update("projects", project_id, fields)

    def delete_project(self, project_id: int) -> None:
        """Tasks are deleted; time entries are kept without a project."""
        with self.conn:
            self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    # ================================================================= tasks
    def tasks(self, project_id: int, include_archived: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM tasks WHERE project_id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY archived, name COLLATE NOCASE"
        return self.conn.execute(sql, (project_id,)).fetchall()

    def get_task(self, task_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT t.*, p.name AS project_name, p.color AS project_color, p.client_id,
                      c.name AS client_name,
                      COALESCE(p.rate, c.rate) AS inherited_rate,
                      COALESCE(t.rate, p.rate, c.rate) AS own_rate
               FROM tasks t
               JOIN projects p ON p.id = t.project_id
               LEFT JOIN clients c ON c.id = p.client_id
               WHERE t.id = ?""", (task_id,)).fetchone()

    def add_task(self, project_id: int, name: str, rate: float | None = None) -> int:
        name = _clean_name(name)
        _check_unique(self.tasks(project_id, True), name, None, "Task")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tasks (project_id, name, rate, created) VALUES (?, ?, ?, ?)",
                (project_id, name, _clean_rate(rate), _now(None)))
        return cur.lastrowid

    def update_task(self, task_id: int, *, name: str | None = None, rate=_UNSET,
                    archived: bool | None = None) -> None:
        fields: dict = {}
        if name is not None:
            name = _clean_name(name)
            task = self.get_task(task_id)
            if task is not None:
                _check_unique(self.tasks(task["project_id"], True), name, task_id, "Task")
            fields["name"] = name
        if rate is not _UNSET:
            fields["rate"] = _clean_rate(rate)
        if archived is not None:
            fields["archived"] = int(archived)
        self._update("tasks", task_id, fields)

    def delete_task(self, task_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def _update(self, table: str, row_id: int, fields: dict) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?",
                              (*fields.values(), row_id))

    def count_entries(self, *, client_id: int | None = None, project_id: int | None = None,
                      task_id: int | None = None) -> int:
        sql = "SELECT COUNT(*) FROM entries e LEFT JOIN projects p ON p.id = e.project_id"
        if task_id is not None:
            sql, args = sql + " WHERE e.task_id = ?", (task_id,)
        elif project_id is not None:
            sql, args = sql + " WHERE e.project_id = ?", (project_id,)
        elif client_id is not None:
            sql, args = sql + " WHERE p.client_id = ?", (client_id,)
        else:
            args = ()
        return self.conn.execute(sql, args).fetchone()[0]

    # =============================================================== entries
    def running_entry(self) -> sqlite3.Row | None:
        return self.conn.execute(
            ENTRY_SELECT + " WHERE e.end_ts IS NULL ORDER BY e.start_ts DESC LIMIT 1"
        ).fetchone()

    def last_entry(self) -> sqlite3.Row | None:
        return self.conn.execute(
            ENTRY_SELECT + " ORDER BY e.start_ts DESC, e.id DESC LIMIT 1").fetchone()

    def start(self, project_id: int | None = None, task_id: int | None = None,
              description: str = "", now: int | None = None) -> int:
        """Start a timer; a running timer is stopped first."""
        now = _now(now)
        with self.conn:
            # Switching within a few seconds: the previous run was a misclick, drop it.
            self.conn.execute(
                "DELETE FROM entries WHERE end_ts IS NULL AND ? - start_ts < ?", (now, MIN_ENTRY))
            self.conn.execute(
                "UPDATE entries SET end_ts = MAX(start_ts, ?) WHERE end_ts IS NULL", (now,))
            cur = self.conn.execute(
                """INSERT INTO entries (project_id, task_id, description, start_ts, end_ts)
                   VALUES (?, ?, ?, ?, NULL)""",
                (project_id, task_id, (description or "").strip(), now))
        return cur.lastrowid

    def stop(self, now: int | None = None) -> int | None:
        """Stop the running timer. Returns its id, or None if nothing ran or the run was
        shorter than MIN_ENTRY seconds (an accidental click: the entry is discarded)."""
        running = self.running_entry()
        if running is None:
            return None
        now = max(_now(now), running["start_ts"])
        with self.conn:
            if now - running["start_ts"] < MIN_ENTRY:
                self.conn.execute("DELETE FROM entries WHERE id = ?", (running["id"],))
                return None
            self.conn.execute("UPDATE entries SET end_ts = ? WHERE id = ?", (now, running["id"]))
        return running["id"]

    def get_entry(self, entry_id: int) -> sqlite3.Row | None:
        return self.conn.execute(ENTRY_SELECT + " WHERE e.id = ?", (entry_id,)).fetchone()

    def add_entry(self, start_ts: int, end_ts: int, project_id: int | None = None,
                  task_id: int | None = None, description: str = "") -> int:
        if end_ts <= start_ts:
            raise ValueError("End must be after start")
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO entries (project_id, task_id, description, start_ts, end_ts)
                   VALUES (?, ?, ?, ?, ?)""",
                (project_id, task_id, (description or "").strip(), int(start_ts), int(end_ts)))
        return cur.lastrowid

    def update_entry(self, entry_id: int, **fields) -> None:
        """Fields: project_id, task_id, description, start_ts, end_ts."""
        allowed = {"project_id", "task_id", "description", "start_ts", "end_ts"}
        unknown = set(fields) - allowed
        if unknown:
            raise TypeError(f"Unknown fields: {unknown}")
        current = self.get_entry(entry_id)
        if current is None:
            return
        start = fields.get("start_ts", current["start_ts"])
        end = fields.get("end_ts", current["end_ts"])
        if end is not None and end <= start:
            raise ValueError("End must be after start")
        if "description" in fields:
            fields["description"] = (fields["description"] or "").strip()
        self._update("entries", entry_id, fields)

    def delete_entry(self, entry_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def entries(self, t0: int, t1: int, client_id=_UNSET, project_id=_UNSET,
                include_running: bool = True) -> list[sqlite3.Row]:
        """Entries that started within [t0, t1). client_id/project_id None = 'without'."""
        sql = ENTRY_SELECT + " WHERE e.start_ts >= ? AND e.start_ts < ?"
        args: list = [t0, t1]
        for column, value in (("p.client_id", client_id), ("e.project_id", project_id)):
            if value is _UNSET:
                continue
            if value is None:
                sql += f" AND {column} IS NULL"
            else:
                sql += f" AND {column} = ?"
                args.append(value)
        if not include_running:
            sql += " AND e.end_ts IS NOT NULL"
        sql += " ORDER BY e.start_ts"
        return self.conn.execute(sql, args).fetchall()

    @staticmethod
    def duration(entry, now: int | None = None) -> int:
        end = entry["end_ts"] if entry["end_ts"] is not None else _now(now)
        return max(0, end - entry["start_ts"])

    def amount(self, entry, now: int | None = None) -> float:
        return money(self.duration(entry, now), self.rate_of(entry))

    def recent_activities(self, limit: int = 10) -> list[sqlite3.Row]:
        """Distinct recent (project, task, description) combinations for quick start."""
        return self.conn.execute(
            f"""SELECT * FROM ({ENTRY_SELECT}) x
                WHERE x.id IN (
                    SELECT MAX(e.id) FROM entries e
                    LEFT JOIN projects p ON p.id = e.project_id
                    WHERE p.id IS NULL OR p.archived = 0
                    GROUP BY e.project_id, e.task_id, e.description)
                ORDER BY x.start_ts DESC LIMIT ?""", (limit,)).fetchall()

    def totals_by_project(self, now: int | None = None) -> dict[int | None, dict]:
        """All-time tracked seconds and amount per project."""
        now = _now(now)
        default = self.default_rate
        out: dict[int | None, dict] = {}
        # Aggregate in SQL per (project, task): the rate is the same within a task.
        rows = self.conn.execute(
            """SELECT e.project_id,
                      COALESCE(t.rate, p.rate, c.rate) AS own_rate,
                      SUM(MAX(0, COALESCE(e.end_ts, ?) - e.start_ts)) AS seconds
               FROM entries e
               LEFT JOIN projects p ON p.id = e.project_id
               LEFT JOIN tasks    t ON t.id = e.task_id
               LEFT JOIN clients  c ON c.id = p.client_id
               GROUP BY e.project_id, e.task_id""", (now,)).fetchall()
        for r in rows:
            item = out.setdefault(r["project_id"], {"seconds": 0, "amount": 0.0})
            rate = r["own_rate"] if r["own_rate"] is not None else default
            item["seconds"] += r["seconds"]
            item["amount"] += money(r["seconds"], rate)
        return out

    def totals_by_task(self, now: int | None = None) -> dict[int, dict]:
        """All-time tracked seconds and amount per task."""
        now = _now(now)
        default = self.default_rate
        rows = self.conn.execute(
            """SELECT e.task_id,
                      COALESCE(t.rate, p.rate, c.rate) AS own_rate,
                      SUM(MAX(0, COALESCE(e.end_ts, ?) - e.start_ts)) AS seconds
               FROM entries e
               JOIN tasks         t ON t.id = e.task_id
               LEFT JOIN projects p ON p.id = t.project_id
               LEFT JOIN clients  c ON c.id = p.client_id
               GROUP BY e.task_id""", (now,)).fetchall()
        out: dict[int, dict] = {}
        for r in rows:
            rate = r["own_rate"] if r["own_rate"] is not None else default
            out[r["task_id"]] = {"seconds": r["seconds"], "amount": money(r["seconds"], rate)}
        return out

    # ======================================================= focus sessions
    def log_focus(self, start_ts: int, end_ts: int, entry_id: int | None,
                  outcome: str = "break") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO focus_sessions (start_ts, end_ts, entry_id, outcome) VALUES (?, ?, ?, ?)",
                (int(start_ts), int(end_ts), entry_id, outcome))

    def focus_sessions(self, t0: int, t1: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM focus_sessions WHERE end_ts >= ? AND end_ts < ? ORDER BY end_ts",
            (t0, t1)).fetchall()

    # ================================================================= gaps
    def find_gaps(self, d0: date, d1: date, min_gap: int = 30 * 60) -> list[dict]:
        """Untracked stretches inside a working day: between the end of one finished entry
        and the start of the next one on the same day, at least `min_gap` seconds long.
        Time before the first and after the last entry of a day is not a gap."""
        gaps: list[dict] = []
        d = d0
        while d <= d1:
            t0, t1 = day_start_ts(d), day_start_ts(d + timedelta(days=1))
            rows = [e for e in self.entries(t0, t1) if e["end_ts"] is not None]
            rows.sort(key=lambda e: e["start_ts"])
            reach = None          # latest end so far (handles overlapping entries)
            before = None
            for e in rows:
                if reach is not None and e["start_ts"] - reach >= min_gap:
                    gaps.append({"day": d, "start": reach, "end": e["start_ts"],
                                 "before": before, "after": e})
                if reach is None or e["end_ts"] > reach:
                    reach, before = e["end_ts"], e
            d += timedelta(days=1)
        return gaps

    # ============================================================= timesheet
    def set_day_total(self, d: date, project_id: int | None, task_id: int | None,
                      seconds: int) -> None:
        """Make the tracked time of (project, task) on day d equal `seconds`.

        More time: a new entry is appended after the last entry of that row/day
        (or at 09:00). Less time: the latest finished entries are shortened or
        deleted. A running entry is never touched.
        """
        t0, t1 = day_start_ts(d), day_start_ts(d + timedelta(days=1))
        rows = [e for e in self.entries(t0, t1)
                if e["project_id"] == project_id and e["task_id"] == task_id]
        current = sum(self.duration(e) for e in rows)
        diff = int(seconds) - current
        if diff > 0:
            finished = [e for e in rows if e["end_ts"] is not None]
            start = max((e["end_ts"] for e in finished), default=day_start_ts(d, 9))
            self.add_entry(start, start + diff, project_id, task_id)
        elif diff < 0:
            remaining = -diff
            for e in sorted((e for e in rows if e["end_ts"] is not None),
                            key=lambda e: e["start_ts"], reverse=True):
                dur = self.duration(e)
                if dur <= remaining:
                    self.delete_entry(e["id"])
                    remaining -= dur
                else:
                    self.update_entry(e["id"], end_ts=e["end_ts"] - remaining)
                    remaining = 0
                if remaining <= 0:
                    break

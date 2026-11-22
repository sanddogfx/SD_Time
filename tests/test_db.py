import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sd_time.db import Database, DuplicateNameError, day_start_ts  # noqa: E402
from sd_time.util import (day_bounds, fmt_hm, fmt_hms, fmt_hours, fmt_money,  # noqa: E402
                          parse_clock, parse_duration, parse_rate, period_dates)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.c = self.db.add_client("Acme", rate=50)
        self.p = self.db.add_project("Website", self.c)
        self.t1 = self.db.add_task(self.p, "Layout")
        self.t2 = self.db.add_task(self.p, "Animation")

    def test_totals_by_task(self):
        self.db.update_task(self.t2, rate=80)
        self.db.add_entry(0, 3600, self.p, self.t1)          # client rate 50
        self.db.add_entry(4000, 5800, self.p, self.t2)       # own rate 80, half an hour
        self.db.add_entry(6000, 9600, self.p, None)          # no task: not in the result
        totals = self.db.totals_by_task(now=10_000)
        self.assertEqual(set(totals), {self.t1, self.t2})
        self.assertEqual(totals[self.t1], {"seconds": 3600, "amount": {"USD": 50.0}})
        self.assertEqual(totals[self.t2], {"seconds": 1800, "amount": {"USD": 40.0}})

    def test_start_stop(self):
        eid = self.db.start(self.p, self.t1, "first pass", now=1000)
        running = self.db.running_entry()
        self.assertEqual(running["id"], eid)
        self.assertEqual(running["client_name"], "Acme")
        self.assertEqual(running["task_name"], "Layout")
        self.assertEqual(self.db.stop(now=1600), eid)
        self.assertIsNone(self.db.running_entry())
        self.assertEqual(self.db.get_entry(eid)["end_ts"], 1600)
        self.assertIsNone(self.db.stop(now=2000))

    def test_misclick_runs_are_discarded(self):
        self.db.start(self.p, self.t1, now=1000)
        self.assertIsNone(self.db.stop(now=1003))           # 3 s: misclick
        self.assertEqual(self.db.count_entries(), 0)
        self.db.start(self.p, self.t1, now=2000)
        self.db.start(self.p, self.t2, now=2002)            # switched right away
        self.assertEqual(self.db.count_entries(), 1)
        self.assertEqual(self.db.running_entry()["task_id"], self.t2)
        self.assertIsNotNone(self.db.stop(now=2010))        # 8 s: kept
        self.assertEqual(self.db.count_entries(), 1)

    def test_entry_without_project(self):
        eid = self.db.start(description="emails", now=1000)
        e = self.db.running_entry()
        self.assertEqual(e["id"], eid)
        self.assertIsNone(e["project_name"])
        self.assertIsNone(self.db.rate_of(e))
        self.db.set_setting("default_rate", 30)
        self.assertEqual(self.db.rate_of(e), 30)

    def test_start_switches(self):
        a = self.db.start(self.p, self.t1, now=1000)
        b = self.db.start(self.p, self.t2, now=1300)
        self.assertEqual(self.db.get_entry(a)["end_ts"], 1300)
        self.assertEqual(self.db.running_entry()["id"], b)

    def test_rate_inheritance(self):
        def rate(tid):
            return self.db.get_task(tid)["own_rate"]
        self.assertEqual(rate(self.t1), 50)
        self.db.update_project(self.p, rate=60)
        self.assertEqual(rate(self.t1), 60)
        self.db.update_task(self.t1, rate=80)
        self.assertEqual(rate(self.t1), 80)
        self.assertEqual(rate(self.t2), 60)
        self.db.update_project(self.p, rate=None)
        self.assertEqual(rate(self.t2), 50)
        self.db.update_client(self.c, rate=None)
        self.assertIsNone(rate(self.t2))

    def test_amounts(self):
        self.db.update_task(self.t2, rate=100)
        a = self.db.add_entry(1000, 4600, self.p, self.t1)   # 1h at 50
        self.db.start(self.p, self.t2, now=7000)             # running 0.25h at 100
        self.assertAlmostEqual(self.db.amount(self.db.get_entry(a)), 50.0)
        self.assertAlmostEqual(self.db.amount(self.db.running_entry(), now=7900), 25.0)
        totals = self.db.totals_by_project(now=7900)
        self.assertEqual(totals[self.p]["seconds"], 3600 + 900)
        self.assertAlmostEqual(totals[self.p]["amount"]["USD"], 75.0)

    def test_currency_follows_the_rate(self):
        self.db.set_currencies(["USD", "EUR", "gbp"], "USD")
        self.assertEqual(self.db.currencies, ["USD", "EUR", "GBP"])
        self.db.update_client(self.c, currency="EUR")                # client: 50 EUR
        self.db.update_task(self.t2, rate=100, currency="GBP")       # task: 100 GBP
        t1, t2 = self.db.get_task(self.t1), self.db.get_task(self.t2)
        self.assertEqual((t1["own_rate"], t1["own_currency"]), (50, "EUR"))
        self.assertEqual((t2["own_rate"], t2["own_currency"]), (100, "GBP"))
        self.assertEqual(t2["inherited_currency"], "EUR")
        self.db.update_project(self.p, rate=60)                      # project rate, no currency
        self.assertIsNone(self.db.get_project(self.p)["own_currency"])
        a = self.db.add_entry(0, 3600, self.p, self.t1)              # 60 in the default USD
        self.db.add_entry(3600, 5400, self.p, self.t2)               # 50 GBP
        self.db.add_entry(5400, 9000, None, None)                    # no rate: nothing
        self.assertEqual(self.db.currency_of(self.db.get_entry(a)), "USD")
        entries = self.db.entries(0, 10_000)
        self.assertEqual(self.db.amounts(entries), {"USD": 60.0, "GBP": 50.0})
        self.assertEqual(self.db.totals_by_project(now=10_000)[self.p]["amount"],
                         {"USD": 60.0, "GBP": 50.0})
        self.assertEqual(self.db.currencies_in_use(), {"USD", "EUR", "GBP"})
        self.db.set_currencies(["EUR", "USD"], "EUR")                # new default
        self.assertEqual(self.db.currencies, ["EUR", "USD"])
        # the project's 60 was saved without a currency, i.e. in USD: it stays USD
        self.assertEqual(self.db.get_project(self.p)["own_currency"], "USD")
        self.assertEqual(self.db.currency_of(self.db.get_entry(a)), "USD")
        e = self.db.get_entry(self.db.add_entry(9000, 9600, None, None))
        self.db.set_setting("default_rate", 30)                      # default rate: new default
        self.assertEqual(self.db.currency_of(e), "EUR")
        with self.assertRaises(ValueError):
            self.db.update_task(self.t1, currency="US DOLLAR")

    def test_v4_database_gets_currency_columns(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            con = sqlite3.connect(path)
            con.executescript("""
                CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL, rate REAL,
                    archived INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
                INSERT INTO clients VALUES (1, 'Old', 40, 0, 0);
                PRAGMA user_version = 4;""")
            con.close()
            db = Database(path)
            self.assertIsNone(db.get_client(1)["currency"])
            db.update_client(1, currency="EUR")
            self.assertEqual(db.get_client(1)["currency"], "EUR")
            db.close()

    def test_entries_filters(self):
        other = self.db.add_project("Stock")  # no client
        self.db.add_entry(100, 200, self.p, self.t1)
        self.db.add_entry(300, 400, other)
        self.db.add_entry(500, 600)
        self.assertEqual(len(self.db.entries(0, 300)), 1)
        self.assertEqual(len(self.db.entries(0, 1000)), 3)
        self.assertEqual(len(self.db.entries(0, 1000, client_id=self.c)), 1)
        self.assertEqual(len(self.db.entries(0, 1000, client_id=None)), 2)
        self.assertEqual(len(self.db.entries(0, 1000, project_id=None)), 1)

    def test_validation_and_uniqueness(self):
        with self.assertRaises(ValueError):
            self.db.add_entry(500, 500)
        with self.assertRaises(ValueError):
            self.db.add_client("   ")
        with self.assertRaises(ValueError):
            self.db.add_client("Neg", rate=-1)
        with self.assertRaises(DuplicateNameError):
            self.db.add_client("acme")
        with self.assertRaises(DuplicateNameError):
            self.db.add_task(self.p, "LAYOUT")
        with self.assertRaises(DuplicateNameError):
            self.db.update_task(self.t2, name="layout")
        c2 = self.db.add_client("Клиент")
        with self.assertRaises(DuplicateNameError):
            self.db.add_client("КЛИЕНТ")
        self.db.add_project("Website", c2)      # same name, other client: ok
        self.db.add_project("Website")          # same name, no client: ok
        with self.assertRaises(DuplicateNameError):
            self.db.add_project("website")
        with self.assertRaises(DuplicateNameError):
            self.db.update_project(self.p, client_id=c2)  # would clash under c2

    def test_delete_keeps_entries(self):
        e = self.db.add_entry(100, 200, self.p, self.t1)
        self.db.delete_client(self.c)
        self.assertIsNone(self.db.get_project(self.p)["client_id"])
        self.db.delete_project(self.p)
        entry = self.db.get_entry(e)
        self.assertIsNone(entry["project_id"])
        self.assertIsNone(entry["task_id"])
        self.assertEqual(self.db.count_entries(), 1)

    def test_delete_client_resolves_name_clash(self):
        loose = self.db.add_project("Website")            # client-less project, same name
        self.db.delete_client(self.c)
        names = sorted(p["name"] for p in self.db.projects(None))
        self.assertEqual(names, ["Website", "Website (Acme)"])
        # both can still be saved without a duplicate error
        self.db.update_project(self.p, name=self.db.get_project(self.p)["name"], client_id=None)
        self.db.update_project(loose, name="Website", client_id=None)

    def test_recent_activities(self):
        self.db.add_entry(100, 200, self.p, self.t1, "a")
        self.db.add_entry(300, 400, self.p, self.t1, "a")
        self.db.add_entry(500, 600, self.p, self.t2, "b")
        rows = self.db.recent_activities()
        self.assertEqual([(r["task_id"], r["description"]) for r in rows],
                         [(self.t2, "b"), (self.t1, "a")])
        self.db.update_project(self.p, archived=True)
        self.assertEqual(self.db.recent_activities(), [])

    def test_set_day_total(self):
        d = date(2026, 11, 20)
        nine = day_start_ts(d, 9)
        self.db.set_day_total(d, self.p, self.t1, 3600)
        rows = self.db.entries(*day_bounds(d))
        self.assertEqual([(r["start_ts"], r["end_ts"]) for r in rows], [(nine, nine + 3600)])
        self.db.set_day_total(d, self.p, self.t1, 5400)   # +30 min appended
        rows = self.db.entries(*day_bounds(d))
        self.assertEqual(sum(Database.duration(r) for r in rows), 5400)
        self.assertEqual(rows[1]["start_ts"], nine + 3600)
        self.db.set_day_total(d, self.p, self.t1, 1200)   # shrink: delete + trim
        rows = self.db.entries(*day_bounds(d))
        self.assertEqual(len(rows), 1)
        self.assertEqual(Database.duration(rows[0]), 1200)
        self.db.set_day_total(d, self.p, self.t1, 0)
        self.assertEqual(self.db.entries(*day_bounds(d)), [])
        self.db.set_day_total(d, None, None, 600)         # row without project
        self.assertIsNone(self.db.entries(*day_bounds(d))[0]["project_id"])

    def test_find_gaps(self):
        d = date(2026, 11, 19)
        at = lambda h, m=0: day_start_ts(d, h, m)   # noqa: E731
        self.db.add_entry(at(9), at(10), self.p, self.t1, "a")
        self.db.add_entry(at(10, 10), at(11), self.p, self.t1, "b")       # 10 min gap: ignored
        self.db.add_entry(at(12, 30), at(13), self.p, self.t2, "c")       # 1h30 gap before
        self.db.add_entry(at(12, 40), at(14), self.p, self.t2, "d")       # overlaps c
        self.db.add_entry(at(15), at(16), self.p, self.t1, "e")           # 1h gap after d
        gaps = self.db.find_gaps(d, d)
        self.assertEqual([(g["start"], g["end"]) for g in gaps],
                         [(at(11), at(12, 30)), (at(14), at(15))])
        self.assertEqual(gaps[0]["before"]["description"], "b")
        self.assertEqual(gaps[1]["before"]["description"], "d")   # the one reaching furthest
        self.assertEqual(self.db.find_gaps(d, d, min_gap=2 * 3600), [])
        self.db.start(self.p, self.t1, now=at(17))   # running entries are not gap bounds
        self.assertEqual(len(self.db.find_gaps(d, d)), 2)

    def test_focus_sessions(self):
        self.db.log_focus(1000, 2500, None, "break")
        self.db.log_focus(3000, 4500, None, "skip")
        rows = self.db.focus_sessions(0, 4000)
        self.assertEqual([r["outcome"] for r in rows], ["break"])
        self.assertEqual(len(self.db.focus_sessions(0, 10_000)), 2)

    def test_settings(self):
        self.assertEqual(self.db.currency, "USD")
        self.db.set_setting("currency", "EUR")
        self.db.set_setting("currency", "RUB")
        self.assertEqual(self.db.currency, "RUB")
        self.assertIsNone(self.db.default_rate)


class MigrationTest(unittest.TestCase):
    def test_v1_database_is_migrated(self):
        path = Path(tempfile.mkdtemp()) / "old.db"
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#4a90d9', archived INTEGER NOT NULL DEFAULT 0,
                created INTEGER NOT NULL);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
            CREATE TABLE entries (id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                start_ts INTEGER NOT NULL, end_ts INTEGER, note TEXT NOT NULL DEFAULT '');
            INSERT INTO projects VALUES (1, 'Old project', '#ff0000', 0, 0);
            INSERT INTO tasks VALUES (1, 1, 'Old task', 0, 0);
            INSERT INTO entries VALUES (1, 1, 100, 3700, 'old note');
        """)
        old.commit()
        old.close()

        db = Database(path)
        e = db.get_entry(1)
        self.assertEqual((e["project_name"], e["task_name"], e["description"]),
                         ("Old project", "Old task", "old note"))
        self.assertIsNone(e["client_id"])
        # Foreign keys point at the right tables after the rebuild.
        c = db.add_client("New client")
        db.update_project(1, client_id=c)
        db.delete_task(1)
        self.assertIsNone(db.get_entry(1)["task_id"])
        db.delete_project(1)
        self.assertIsNone(db.get_entry(1)["project_id"])
        db.close()
        Database(path).close()  # reopening is a no-op


class UtilTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(fmt_hms(3725), "1:02:05")
        self.assertEqual(fmt_hm(3725), "1:02")
        self.assertEqual(fmt_hours(5400), "1.50")
        self.assertEqual(fmt_money(1234.5, "USD"), "1,234.50 USD")

    def test_parse(self):
        self.assertIsNone(parse_rate("  "))
        self.assertEqual(parse_rate("45,5"), 45.5)
        self.assertEqual(parse_rate("1 200"), 1200)
        with self.assertRaises(ValueError):
            parse_rate("abc")
        for text, hm in (("1245", (12, 45)), ("930", (9, 30)), ("0930", (9, 30)), ("9", (9, 0)),
                         ("12", (12, 0)), ("12:45", (12, 45)), ("12.45", (12, 45)),
                         ("7:05", (7, 5)), (" 23:59 ", (23, 59)), ("0", (0, 0))):
            self.assertEqual(parse_clock(text), hm, text)
        for bad in ("", "2460", "25", "12:60", "12345", "ab", "12:3:4", "1:234"):
            with self.assertRaises(ValueError, msg=bad):
                parse_clock(bad)
        self.assertEqual(parse_duration("1:30"), 5400)
        self.assertEqual(parse_duration("1:30:15"), 5415)
        self.assertEqual(parse_duration("1.5"), 5400)
        self.assertEqual(parse_duration("90m"), 5400)
        self.assertEqual(parse_duration(""), 0)
        with self.assertRaises(ValueError):
            parse_duration("x")

    def test_periods(self):
        d = date(2026, 11, 21)  # Saturday
        self.assertEqual(period_dates("week", d), (date(2026, 11, 16), date(2026, 11, 22)))
        self.assertEqual(period_dates("last_week", d), (date(2026, 11, 9), date(2026, 11, 15)))
        self.assertEqual(period_dates("month", d), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(period_dates("last_month", d), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(period_dates("year", d), (date(2026, 1, 1), date(2026, 12, 31)))
        t0, t1 = day_bounds(d)
        self.assertEqual(t1 - t0, 86400)


if __name__ == "__main__":
    unittest.main()

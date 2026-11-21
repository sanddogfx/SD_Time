"""Reports page: filters, stacked bar chart by day, grouped table, donut, export."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QScrollArea,
    QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..charts import DonutChart, StackedBarChart
from ..db import NO_COLOR, PALETTE, day_start_ts
from ..icons import color_icon
from ..theme import C
from ..util import fmt_clock, fmt_date, fmt_money, fmt_time, period_dates, range_bounds
from ..widgets import button, card, label, show_error

PERIODS = [("week", "This week"), ("last_week", "Last week"), ("month", "This month"),
           ("last_month", "Last month"), ("year", "This year"), ("custom", "Custom")]
GROUPINGS = [("project_task", "Project › Task"), ("project_desc", "Project › Description"),
             ("client_project", "Client › Project"), ("desc_project", "Description › Project")]
ALL, NONE = "__all__", "__none__"


class ReportsPage(QWidget):
    title = "Reports"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self.entries: list = []

        self.period = QComboBox()
        for key, text in PERIODS:
            self.period.addItem(text, key)
        self.from_edit = QDateEdit(calendarPopup=True, displayFormat="MMM d, yyyy")
        self.to_edit = QDateEdit(calendarPopup=True, displayFormat="MMM d, yyyy")
        self.client_combo = QComboBox()
        self.project_combo = QComboBox()
        self.group_combo = QComboBox()
        for key, text in GROUPINGS:
            self.group_combo.addItem(text, key)
        for combo in (self.client_combo, self.project_combo):
            combo.setMinimumWidth(160)

        filters = card()
        fl = QHBoxLayout(filters)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.addWidget(self.period)
        fl.addWidget(self.from_edit)
        fl.addWidget(label("–", "Muted"))
        fl.addWidget(self.to_edit)
        fl.addSpacing(16)
        fl.addWidget(label("Client", "Muted"))
        fl.addWidget(self.client_combo)
        fl.addWidget(label("Project", "Muted"))
        fl.addWidget(self.project_combo)
        fl.addStretch(1)

        self.total_label = label("", "Big")
        self.amount_label = label("", "Big")
        excel_btn = button("Export Excel…", self.export_excel)
        csv_btn = button("Export CSV…", self.export_csv)
        summary = QWidget()
        summary.setObjectName("CardHeader")
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(14, 10, 14, 10)
        sl.addWidget(label("Total:", "Small"))
        sl.addWidget(self.total_label)
        sl.addSpacing(24)
        sl.addWidget(label("Amount:", "Small"))
        sl.addWidget(self.amount_label)
        sl.addStretch(1)
        sl.addWidget(excel_btn)
        sl.addWidget(csv_btn)

        self.bars = StackedBarChart()
        chart_card = card()
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(0, 0, 0, 12)
        cl.addWidget(summary)
        cl.addWidget(self.bars)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Title", "Duration", "Amount", "Share"])
        self.tree.setAlternatingRowColors(False)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.donut = DonutChart()
        self.donut.setMaximumWidth(420)   # leave the width to the table, so titles aren't cut

        group_bar = QHBoxLayout()
        group_bar.addWidget(label("Group by:", "Small"))
        group_bar.addWidget(self.group_combo)
        group_bar.addStretch(1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(group_bar)
        ll.addWidget(self.tree, 1)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.donut)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setMinimumHeight(320)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(16)
        root.addWidget(filters)
        root.addWidget(chart_card)
        root.addWidget(split, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.period.currentIndexChanged.connect(self._on_period)
        self.from_edit.dateChanged.connect(self._on_dates)
        self.to_edit.dateChanged.connect(self._on_dates)
        self.client_combo.currentIndexChanged.connect(self._on_client)
        self.project_combo.currentIndexChanged.connect(self.refresh_data)
        self.group_combo.currentIndexChanged.connect(self.refresh_data)
        self._set_dates(*period_dates("week"))

    # --------------------------------------------------------------- filters
    def _set_dates(self, d0: date, d1: date) -> None:
        for edit, d in ((self.from_edit, d0), (self.to_edit, d1)):
            edit.blockSignals(True)
            edit.setDate(QDate(d.year, d.month, d.day))
            edit.blockSignals(False)

    def _on_period(self) -> None:
        key = self.period.currentData()
        if key != "custom":
            self._set_dates(*period_dates(key))
        self.refresh_data()

    def _on_dates(self) -> None:
        self.period.blockSignals(True)
        self.period.setCurrentIndex(self.period.findData("custom"))
        self.period.blockSignals(False)
        self.refresh_data()

    def _fill_filters(self) -> None:
        current = self.client_combo.currentData()
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("All clients", ALL)
        self.client_combo.addItem("Without client", NONE)
        for c in self.db.clients(include_archived=True):
            self.client_combo.addItem(c["name"], c["id"])
        idx = self.client_combo.findData(current)
        self.client_combo.setCurrentIndex(max(0, idx))
        self.client_combo.blockSignals(False)
        self._fill_projects()

    def _fill_projects(self) -> None:
        current = self.project_combo.currentData()
        client = self.client_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("All projects", ALL)
        if client in (ALL, None):
            self.project_combo.addItem("Without project", NONE)
        for p in self.db.projects(include_archived=True):
            if client == NONE and p["client_id"] is not None:
                continue
            if client not in (ALL, NONE, None) and p["client_id"] != client:
                continue
            self.project_combo.addItem(color_icon(p["color"]), p["name"], p["id"])
        idx = self.project_combo.findData(current)
        self.project_combo.setCurrentIndex(max(0, idx))
        self.project_combo.blockSignals(False)

    def _on_client(self) -> None:
        self._fill_projects()
        self.refresh_data()

    def _range(self) -> tuple[date, date]:
        d0 = self.from_edit.date().toPython()
        d1 = self.to_edit.date().toPython()
        return (d0, d1) if d0 <= d1 else (d1, d0)

    def _query(self) -> list:
        d0, d1 = self._range()
        t0, t1 = range_bounds(d0, d1)
        kwargs = {}
        for name, combo in (("client_id", self.client_combo), ("project_id", self.project_combo)):
            value = combo.currentData()
            if value == NONE:
                kwargs[name] = None
            elif value not in (ALL, None):
                kwargs[name] = value
        return self.db.entries(t0, t1, **kwargs)

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self._fill_filters()
        self.refresh_data()

    def refresh_data(self) -> None:
        self.entries = self._query()
        total = sum(self.db.duration(e) for e in self.entries)
        amount = sum(self.db.amount(e) for e in self.entries)
        self.total_label.setText(fmt_clock(total))
        self.amount_label.setText(fmt_money(amount, self.db.currency))
        self._fill_bars()
        self._fill_tree(total)

    def _fill_bars(self) -> None:
        d0, d1 = self._range()
        days = (d1 - d0).days + 1
        by_month = days > 31
        buckets: dict = {}
        order: list = []
        if by_month:
            d = d0.replace(day=1)
            while d <= d1:
                order.append(d)
                d = (d + timedelta(days=32)).replace(day=1)
        else:
            order = [d0 + timedelta(days=i) for i in range(days)]
        for key in order:
            buckets[key] = {}
        for e in self.entries:
            d = datetime.fromtimestamp(e["start_ts"]).date()
            key = d.replace(day=1) if by_month else d
            if key not in buckets:
                continue
            pk = e["project_id"]
            item = buckets[key].setdefault(pk, [0, e["project_color"] or NO_COLOR,
                                                e["project_name"] or "No project"])
            item[0] += self.db.duration(e)
        bars = []
        for key in order:
            text = f"{key:%b %Y}" if by_month else f"{key:%a}, {key:%b} {key.day}"
            stack = sorted((tuple(v) for v in buckets[key].values()), key=lambda s: s[2].lower())
            bars.append((text, stack))
        self.bars.set_data(bars)

    def _group_keys(self, e) -> tuple[tuple, str, str, tuple, str]:
        """-> (l1 key, l1 name, l1 color, l2 key, l2 name)"""
        mode = self.group_combo.currentData()
        project = e["project_name"] or "No project"
        color = e["project_color"] or NO_COLOR
        if mode == "client_project":
            client = e["client_name"] or "Without client"
            return (e["client_id"],), client, "", (e["project_id"],), project
        if mode == "desc_project":
            desc = e["description"] or "(no description)"
            return (desc,), desc, "", (e["project_id"],), project
        if mode == "project_desc":
            desc = e["description"] or "(no description)"
            return (e["project_id"],), project, color, (desc,), desc
        task = e["task_name"] or "(no task)"
        return (e["project_id"],), project, color, (e["task_id"],), task

    def _groups(self) -> list[dict]:
        groups: dict = {}
        for e in self.entries:
            k1, n1, col, k2, n2 = self._group_keys(e)
            g = groups.setdefault(k1, {"name": n1, "color": col, "seconds": 0, "amount": 0.0,
                                       "children": {}})
            sec, amt = self.db.duration(e), self.db.amount(e)
            g["seconds"] += sec
            g["amount"] += amt
            ch = g["children"].setdefault(k2, {"name": n2, "seconds": 0, "amount": 0.0})
            ch["seconds"] += sec
            ch["amount"] += amt
        result = sorted(groups.values(), key=lambda g: -g["seconds"])
        for i, g in enumerate(result):
            if not g["color"]:
                g["color"] = PALETTE[i % len(PALETTE)]
            g["children"] = sorted(g["children"].values(), key=lambda c: -c["seconds"])
        return result

    def _fill_tree(self, total: int) -> None:
        self.tree.clear()
        cur = self.db.currency
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        bold = QFont(self.tree.font())
        bold.setBold(True)
        groups = self._groups()
        for g in groups:
            share = f"{g['seconds'] / total:.0%}" if total else ""
            top = QTreeWidgetItem([g["name"], fmt_clock(g["seconds"]),
                                   fmt_money(g["amount"], cur) if g["amount"] else "—", share])
            top.setIcon(0, color_icon(g["color"], 10))
            top.setForeground(0, QColor(g["color"]))
            for col in (1, 2, 3):
                top.setTextAlignment(col, right)
                top.setFont(col, bold)
            for ch in g["children"]:
                item = QTreeWidgetItem([ch["name"], fmt_clock(ch["seconds"]),
                                        fmt_money(ch["amount"], cur) if ch["amount"] else "—",
                                        f"{ch['seconds'] / total:.0%}" if total else ""])
                for col in (1, 2, 3):
                    item.setTextAlignment(col, right)
                top.addChild(item)
            self.tree.addTopLevelItem(top)
        if not groups:
            empty = QTreeWidgetItem(["No time entries for these filters"])
            empty.setForeground(0, QColor(C["muted"]))
            self.tree.addTopLevelItem(empty)
            empty.setFirstColumnSpanned(True)   # don't squeeze the message into column 1
        self.donut.set_data([(g["seconds"], g["color"], g["name"]) for g in groups],
                            fmt_clock(total))

    # ---------------------------------------------------------------- export
    def _file_name(self, ext: str) -> str:
        d0, d1 = self._range()
        return f"SD_Time_report_{d0:%Y-%m-%d}_{d1:%Y-%m-%d}.{ext}"

    def _detail_rows(self) -> list[list]:
        rows = []
        for e in self.entries:
            sec = self.db.duration(e)
            rate = self.db.rate_of(e)
            rows.append([
                fmt_date(e["start_ts"]), fmt_time(e["start_ts"]),
                fmt_time(e["end_ts"]) if e["end_ts"] is not None else "running",
                sec, e["client_name"] or "", e["project_name"] or "", e["task_name"] or "",
                e["description"], rate, self.db.amount(e),
            ])
        return rows

    DETAIL_HEADER = ["Date", "Start", "End", "Duration", "Client", "Project", "Task",
                     "Description", "Rate", "Amount"]

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", self._file_name("csv"),
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(self.DETAIL_HEADER[:4] + ["Hours"] + self.DETAIL_HEADER[4:])
                for r in self._detail_rows():
                    sec = r[3]
                    w.writerow(r[:3] + [fmt_clock(sec), f"{sec / 3600:.2f}"] + r[4:8]
                               + ["" if r[8] is None else f"{r[8]:.2f}", f"{r[9]:.2f}"])
        except OSError as exc:
            show_error(self, exc)
            return
        QMessageBox.information(self, "SD Time", f"Saved:\n{path}")

    def export_excel(self) -> None:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            show_error(self, "openpyxl is not installed. Run: pip install openpyxl")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", self._file_name("xlsx"),
                                              "Excel workbook (*.xlsx)")
        if not path:
            return
        cur = self.db.currency
        wb = Workbook()
        head_font = Font(bold=True, color="FFFFFF")
        head_fill = PatternFill("solid", fgColor="2B2B2B")

        def header(ws, cols):
            ws.append(cols)
            for cell in ws[1]:
                cell.font = head_font
                cell.fill = head_fill

        ws = wb.active
        ws.title = "Summary"
        d0, d1 = self._range()
        header(ws, ["Group", "Item", "Duration", "Hours", f"Amount, {cur}"])
        for g in self._groups():
            ws.append([g["name"], "", g["seconds"] / 86400, round(g["seconds"] / 3600, 2),
                       round(g["amount"], 2)])
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
            for ch in g["children"]:
                ws.append(["", ch["name"], ch["seconds"] / 86400,
                           round(ch["seconds"] / 3600, 2), round(ch["amount"], 2)])
        total = sum(self.db.duration(e) for e in self.entries)
        amount = sum(self.db.amount(e) for e in self.entries)
        ws.append(["Total", f"{d0:%Y-%m-%d} – {d1:%Y-%m-%d}", total / 86400,
                   round(total / 3600, 2), round(amount, 2)])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
        for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
            row[0].number_format = "[h]:mm:ss"
        for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
            row[0].number_format = "#,##0.00"
        for col, width in zip("ABCDE", (32, 36, 12, 10, 14)):
            ws.column_dimensions[col].width = width

        ws2 = wb.create_sheet("Detailed")
        header(ws2, ["Date", "Start", "End", "Duration", "Hours", "Client", "Project", "Task",
                     "Description", f"Rate, {cur}/h", f"Amount, {cur}"])
        for r in self._detail_rows():
            sec = r[3]
            ws2.append(r[:3] + [sec / 86400, round(sec / 3600, 2)] + r[4:8]
                       + [r[8], round(r[9], 2)])
        for row in ws2.iter_rows(min_row=2, min_col=4, max_col=4):
            row[0].number_format = "[h]:mm:ss"
        for col, width in zip("ABCDEFGHIJK", (11, 7, 8, 10, 8, 18, 20, 18, 40, 10, 12)):
            ws2.column_dimensions[col].width = width
        try:
            wb.save(path)
        except OSError as exc:
            show_error(self, exc)
            return
        QMessageBox.information(self, "SD Time", f"Saved:\n{path}")

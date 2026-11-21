"""Timesheet page: week grid, rows = project/task, editable day cells."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ..db import NO_COLOR, day_start_ts
from ..icons import color_icon
from ..theme import C
from ..util import fmt_clock, parse_duration, week_start
from ..widgets import ProjectPopup, button, confirm, label, show_error

ROLE = Qt.ItemDataRole.UserRole


class TimesheetPage(QWidget):
    title = "Timesheet"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self.week = week_start(date.today())
        self.extra_rows: dict[date, set] = {}
        self._loading = False

        self.range_label = label("", "Big")
        top = QHBoxLayout()
        top.addWidget(label("Timesheet", "H1"))
        top.addStretch(1)
        top.addWidget(button("This week", self._this_week))
        top.addWidget(button("‹", lambda: self._shift(-1)))
        top.addWidget(self.range_label)
        top.addWidget(button("›", lambda: self._shift(1)))

        self.table = QTableWidget(0, 10)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 10):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, 96)
        self.table.setColumnWidth(9, 40)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.cellClicked.connect(self._cell_clicked)

        self.add_btn = button("⊕  Add new row", self._add_row)
        copy_btn = button("Copy last week's rows", self._copy_last_week)
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_btn)
        bottom.addWidget(copy_btn)
        bottom.addStretch(1)
        bottom.addWidget(label("Double-click a cell and type 1:30 or 1.5 to set the time.",
                               "Small"))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(14)
        root.addLayout(top)
        root.addWidget(self.table, 1)
        root.addLayout(bottom)

    # ----------------------------------------------------------- navigation
    def _this_week(self) -> None:
        self.week = week_start(date.today())
        self.refresh()

    def _shift(self, step: int) -> None:
        self.week += timedelta(weeks=step)
        self.refresh()

    def _days(self) -> list[date]:
        return [self.week + timedelta(days=i) for i in range(7)]

    # ----------------------------------------------------------------- data
    def _collect(self) -> tuple[list, dict]:
        days = self._days()
        t0 = day_start_ts(days[0])
        t1 = day_start_ts(days[-1] + timedelta(days=1))
        cells: dict[tuple, dict[date, int]] = {}
        for e in self.db.entries(t0, t1):
            key = (e["project_id"], e["task_id"])
            d = datetime.fromtimestamp(e["start_ts"]).date()
            cells.setdefault(key, {})
            cells[key][d] = cells[key].get(d, 0) + self.db.duration(e)
        for key in self.extra_rows.get(self.week, set()):
            cells.setdefault(key, {})
        rows = sorted(cells, key=lambda k: self._row_title(k).lower())
        return rows, cells

    def _row_title(self, key) -> str:
        project_id, task_id = key
        if project_id is None:
            return "~No project"
        p = self.db.get_project(project_id)
        t = self.db.get_task(task_id) if task_id else None
        text = p["name"] + (f": {t['name']}" if t else "")
        if p["client_name"]:
            text += f"  -  {p['client_name']}"
        return text

    def refresh(self) -> None:
        self._loading = True
        days = self._days()
        we = days[-1]
        self.range_label.setText(
            "This week" if self.week == week_start(date.today())
            else f"{self.week:%b} {self.week.day} - {we:%b} {we.day}")
        today = date.today()
        self.table.setHorizontalHeaderLabels(
            ["Projects"] + [f"{d:%a}, {d:%b} {d.day}" for d in days] + ["Total", ""])
        for i, d in enumerate(days, start=1):
            item = self.table.horizontalHeaderItem(i)
            item.setForeground(QColor(C["accent_text"] if d == today else C["muted"]))

        rows, cells = self._collect()
        self.rows = rows
        self.table.setRowCount(len(rows) + 1)
        bold = QFont(self.table.font())
        bold.setBold(True)
        right = Qt.AlignmentFlag.AlignCenter
        day_totals = [0] * 7
        for r, key in enumerate(rows):
            project_id, _ = key
            p = self.db.get_project(project_id) if project_id else None
            title = QTableWidgetItem(self._row_title(key).lstrip("~"))
            title.setFlags(Qt.ItemFlag.ItemIsEnabled)
            title.setIcon(color_icon(p["color"] if p else NO_COLOR, 10))
            if p is None:
                title.setForeground(QColor(C["muted"]))
            self.table.setItem(r, 0, title)
            row_total = 0
            for c, d in enumerate(days, start=1):
                sec = cells[key].get(d, 0)
                row_total += sec
                day_totals[c - 1] += sec
                item = QTableWidgetItem(fmt_clock(sec) if sec else "")
                item.setTextAlignment(right)
                item.setData(ROLE, (key, d))
                item.setToolTip("Double-click to edit")
                self.table.setItem(r, c, item)
            total = QTableWidgetItem(fmt_clock(row_total))
            total.setFlags(Qt.ItemFlag.ItemIsEnabled)
            total.setTextAlignment(right)
            total.setFont(bold)
            self.table.setItem(r, 8, total)
            remove = QTableWidgetItem("✕")
            remove.setFlags(Qt.ItemFlag.ItemIsEnabled)
            remove.setTextAlignment(right)
            remove.setForeground(QColor(C["muted"]))
            remove.setToolTip("Remove row (deletes this row's time for the week)")
            self.table.setItem(r, 9, remove)

        last = len(rows)
        footer = QTableWidgetItem("Total:")
        footer.setFlags(Qt.ItemFlag.ItemIsEnabled)
        footer.setFont(bold)
        self.table.setItem(last, 0, footer)
        for c, sec in enumerate(day_totals, start=1):
            item = QTableWidgetItem(fmt_clock(sec))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setTextAlignment(right)
            item.setFont(bold)
            self.table.setItem(last, c, item)
        grand = QTableWidgetItem(fmt_clock(sum(day_totals)))
        grand.setFlags(Qt.ItemFlag.ItemIsEnabled)
        grand.setTextAlignment(right)
        grand.setFont(bold)
        self.table.setItem(last, 8, grand)
        blank = QTableWidgetItem("")
        blank.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(last, 9, blank)
        for c in range(10):
            it = self.table.item(last, c)
            if it:
                it.setBackground(QColor(C["header"]))
        self._loading = False

    # -------------------------------------------------------------- editing
    def _cell_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        data = item.data(ROLE)
        if not data:
            return
        (project_id, task_id), d = data
        try:
            seconds = parse_duration(item.text())
        except ValueError as exc:
            show_error(self, exc)
            self.refresh()
            return
        if seconds > 16 * 3600:
            show_error(self, "That's more than 16 hours in one day.")
            self.refresh()
            return
        running = self.ctl.running
        if running is not None and running["project_id"] == project_id \
                and running["task_id"] == task_id \
                and datetime.fromtimestamp(running["start_ts"]).date() == d:
            show_error(self, "The timer is running on this row. Stop it before editing the day.")
            self.refresh()
            return
        self.db.set_day_total(d, project_id, task_id, seconds)
        self.ctl.notify()

    def _cell_clicked(self, row: int, col: int) -> None:
        if col != 9 or row >= len(self.rows):
            return
        key = self.rows[row]
        days = self._days()
        has_time = any(self.table.item(row, c).text() for c in range(1, 8))
        if has_time and not confirm(self, "Remove row",
                                    f"Delete all time of “{self._row_title(key).lstrip('~')}” "
                                    "in this week?"):
            return
        running = self.ctl.running
        for d in days:
            if running is not None and (running["project_id"], running["task_id"]) == key \
                    and datetime.fromtimestamp(running["start_ts"]).date() == d:
                continue
            self.db.set_day_total(d, key[0], key[1], 0)
        self.extra_rows.get(self.week, set()).discard(key)
        self.ctl.notify()

    def _add_row(self) -> None:
        popup = ProjectPopup(self.db, self.window())
        popup.chosen.connect(self._row_chosen)
        popup.move(self.add_btn.mapToGlobal(QPoint(0, -popup.minimumHeight() - 4)))
        popup.show()

    def _row_chosen(self, project_id, task_id) -> None:
        self.extra_rows.setdefault(self.week, set()).add((project_id, task_id))
        self.refresh()

    def _copy_last_week(self) -> None:
        prev = self.week - timedelta(weeks=1)
        t0, t1 = day_start_ts(prev), day_start_ts(self.week)
        keys = {(e["project_id"], e["task_id"]) for e in self.db.entries(t0, t1)}
        if not keys:
            show_error(self, "Last week has no time entries.")
            return
        self.extra_rows.setdefault(self.week, set()).update(keys)
        self.refresh()

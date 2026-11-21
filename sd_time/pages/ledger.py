"""Timesheet page: a week ledger with day pills, plus a gap finder.

Rows = project/task, columns = days. Double-click a pill and type 1:30 or 1.5. The gap finder
spots untracked time between entries on the same day and offers to fill it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .. import theme
from ..db import NO_COLOR, day_start_ts
from ..icons import hover_icon, line_pixmap
from ..theme import C
from ..util import fmt_hm, fmt_time, fmt_words, parse_duration, week_start
from ..widgets import ProjectPopup, button, chip_colors, confirm, label, show_error

ROLE = Qt.ItemDataRole.UserRole
SECS = Qt.ItemDataRole.UserRole + 1
KIND = Qt.ItemDataRole.UserRole + 2     # "project" | "day" | "total" | "remove" | "foot" | "foot_total"
PROJ = Qt.ItemDataRole.UserRole + 3
MIN_GAP = 30 * 60


class LedgerDelegate(QStyledItemDelegate):
    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table

    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setFont(theme.mono(10))
        ed.setPlaceholderText("1:30")
        ed.setStyleSheet(f"border-radius: 10px; border: 1px solid {C['accent_text']};")
        return ed

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(4, 8, -4, -8))

    def paint(self, p: QPainter, option, index) -> None:
        kind = index.data(KIND)
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if kind == "project":
            info = index.data(PROJ) or {}
            bg, fg = chip_colors(info.get("color"))
            f = QFont(option.font)
            fm = QFontMetrics(f)
            text = info.get("name", "")
            w = min(fm.horizontalAdvance(text) + 22, r.width() - 12)
            top = r.top() + 7 if info.get("sub") else r.center().y() - 12   # centre when no client
            chip = QRectF(r.left() + 4, top, w, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(bg))
            p.drawRoundedRect(chip, 12, 12)
            p.setPen(QColor(fg))
            p.setFont(f)
            p.drawText(chip.adjusted(11, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(text, Qt.TextElideMode.ElideRight, int(chip.width() - 19)))
            sub = info.get("sub", "")
            if sub:
                f2 = QFont(option.font)
                f2.setPointSizeF(8.5)
                p.setFont(f2)
                p.setPen(QColor(C["muted"]))
                p.drawText(QRectF(r.left() + 6, chip.bottom() + 2, r.width() - 12, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(f2).elidedText(sub, Qt.TextElideMode.ElideRight, int(r.width() - 12)))
        elif kind == "day":
            secs = index.data(SECS) or 0
            pill = r.adjusted(5, 9, -5, -9)
            if secs:
                a = 0.18 + min(secs / 3600 / 3, 1) * 0.5
                fill = QColor(141, 184, 55, int(a * 255))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawRoundedRect(pill, 10, 10)
                p.setPen(QColor("#f2f7e8"))
                text = fmt_hm(secs)
            else:
                pen = QPen(QColor("#333333"), 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(pill, 10, 10)
                p.setPen(QColor("#666666"))
                text = "–"
            if option.state & option.state.__class__.State_Selected:
                p.setPen(QPen(QColor(C["accent_text"]), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(pill, 10, 10)
                p.setPen(QColor("#f2f7e8") if secs else QColor("#888888"))
            p.setFont(theme.mono(9.5))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        elif kind in ("total", "foot_total"):
            p.setFont(theme.mono(10, True))
            p.setPen(QColor(C["accent_soft_text"] if kind == "foot_total" else C["text"]))
            p.drawText(r.adjusted(0, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fmt_hm(index.data(SECS) or 0))
        elif kind == "foot":
            secs = index.data(SECS) or 0
            p.setFont(theme.mono(9.5, True))
            p.setPen(QColor(C["text"]))
            p.drawText(QRectF(r.left(), r.top() + 6, r.width(), 20), Qt.AlignmentFlag.AlignCenter,
                       fmt_hm(secs) if secs else "–")
            track = QRectF(r.center().x() - 27, r.top() + 32, 54, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2a2a2a"))
            p.drawRoundedRect(track, 3, 3)
            if secs:
                p.setBrush(QColor(C["accent_text"]))
                p.drawRoundedRect(QRectF(track.left(), track.top(), 54 * min(secs / (8 * 3600), 1), 6), 3, 3)
        elif kind == "foot_label":
            p.setPen(QColor(C["muted"]))
            f = QFont(option.font)
            f.setPointSizeF(9)
            p.setFont(f)
            p.drawText(r.adjusted(6, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "Day total · bar = share of 8h")
        elif kind == "remove":
            pm = line_pixmap("close", "#8a8a8a", 16, self.table.devicePixelRatioF())
            p.drawPixmap(int(r.center().x() - 8), int(r.center().y() - 8), pm)
        p.restore()


class TimesheetPage(QWidget):
    title = "Timesheet"

    def __init__(self, ctl):
        super().__init__()
        self.ctl, self.db = ctl, ctl.db
        self.week = week_start(date.today())
        self.extra_rows: dict[date, set] = {}
        self.rows: list = []
        self._loading = False
        self.gaps: list[dict] = []
        self.gap_index = 0
        dpr = self.devicePixelRatioF()

        self.title_label = label("", "H1")
        nav = []
        for icon, tip, step in (("left", "Previous week", -1), ("chevron", "Next week", 1)):
            b = QToolButton()
            b.setObjectName("RoundSmall")
            b.setFixedSize(40, 40)
            b.setStyleSheet("QToolButton#RoundSmall { border-radius: 12px; }")
            b.setIcon(hover_icon(icon, dpr, 16, normal="#c9c9c9"))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=step: self._shift(s))
            nav.append(b)
        this_week = button("This week", self._this_week)
        copy_btn = button("Copy last week", self._copy_last_week)
        self.add_btn = button("Add row", self._add_row)
        self.add_btn.setIcon(hover_icon("add", dpr, 16))
        self.add_btn.setIconSize(QSize(16, 16))
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self.title_label, 1)
        header.addWidget(nav[0])
        header.addWidget(nav[1])
        header.addWidget(this_week)
        header.addWidget(copy_btn)
        header.addWidget(self.add_btn)

        # ---- gap finder banner
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        icon = label()
        icon.setPixmap(line_pixmap("gap", C["accent_soft_text"], 20, dpr))
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: #2a3a18; border-radius: 12px;")
        self.gap_title = label("", "H3")
        self.gap_text = label("", "Small")
        self.gap_text.setStyleSheet("color: #b5c79a;")
        self.gap_text.setTextFormat(Qt.TextFormat.RichText)
        self.gap_text.linkActivated.connect(lambda _: self._next_gap())
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.gap_title)
        texts.addWidget(self.gap_text)
        self.fill_btn = button("", self._fill_gap, "Primary")
        pick_btn = button("Pick project", self._pick_for_gap)
        pick_btn.setStyleSheet("QPushButton { background: transparent; border: 1px solid #3d4d27; "
                               "color: #c9d9ae; }")
        dismiss = QToolButton()
        dismiss.setObjectName("Icon")
        dismiss.setIcon(hover_icon("close", dpr, 16, normal="#9fb07f"))
        dismiss.setIconSize(QSize(16, 16))
        dismiss.setToolTip("Ignore this gap")
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.clicked.connect(self._dismiss_gap)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 12, 12, 12)
        bl.setSpacing(14)
        bl.addWidget(icon)
        bl.addLayout(texts, 1)
        bl.addWidget(self.fill_btn)
        bl.addWidget(pick_btn)
        bl.addWidget(dismiss)

        # ---- ledger
        self.table = QTableWidget(0, 10)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setItemDelegate(LedgerDelegate(self.table))
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 10):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, 86)
        self.table.setColumnWidth(8, 84)
        self.table.setColumnWidth(9, 40)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.cellClicked.connect(self._cell_clicked)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(16)
        root.addLayout(header)
        root.addWidget(self.banner)
        root.addWidget(self.table, 1)
        root.addWidget(label("Double-click a day and type 1:30 or 1.5. More time adds an entry, "
                             "less time trims the latest ones.", "Small"))

    # ------------------------------------------------------------ navigation
    def _this_week(self) -> None:
        self.week = week_start(date.today())
        self.refresh()

    def _shift(self, step: int) -> None:
        self.week += timedelta(weeks=step)
        self.refresh()

    def _days(self) -> list[date]:
        return [self.week + timedelta(days=i) for i in range(7)]

    # ------------------------------------------------------------ data
    def _collect(self) -> tuple[list, dict]:
        days = self._days()
        cells: dict[tuple, dict[date, int]] = {}
        for e in self.db.entries(day_start_ts(days[0]), day_start_ts(days[-1] + timedelta(days=1))):
            key = (e["project_id"], e["task_id"])
            d = datetime.fromtimestamp(e["start_ts"]).date()
            cells.setdefault(key, {})
            cells[key][d] = cells[key].get(d, 0) + self.db.duration(e)
        for key in self.extra_rows.get(self.week, set()):
            cells.setdefault(key, {})
        rows = sorted(cells, key=lambda k: self._row_info(k)["name"].lower().replace("no project", "~"))
        return rows, cells

    def _row_info(self, key) -> dict:
        project_id, task_id = key
        if project_id is None:
            return {"name": "No project", "sub": "", "color": NO_COLOR}
        p = self.db.get_project(project_id)
        t = self.db.get_task(task_id) if task_id else None
        name = p["name"] + (f" · {t['name']}" if t else "")
        return {"name": name, "sub": p["client_name"] or "", "color": p["color"]}

    def refresh(self) -> None:
        self._loading = True
        days = self._days()
        we = days[-1]
        self.title_label.setText(f"Timesheet · {self.week.day} – {we.day} {we:%b}" if self.week.month == we.month
                                 else f"Timesheet · {self.week.day} {self.week:%b} – {we.day} {we:%b}")
        today = date.today()
        self.table.setHorizontalHeaderLabels(["Project"] + [f"{d:%a} {d.day}" for d in days] + ["Total", ""])
        for i, d in enumerate(days, start=1):
            item = self.table.horizontalHeaderItem(i)
            item.setForeground(QColor(C["accent_soft_text"] if d == today else C["muted"]))
        self.table.horizontalHeaderItem(8).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        rows, cells = self._collect()
        self.rows = rows
        self.table.setRowCount(len(rows) + 1)
        day_totals = [0] * 7
        for r, key in enumerate(rows):
            info = self._row_info(key)
            it = QTableWidgetItem()
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setData(KIND, "project")
            it.setData(PROJ, info)
            it.setToolTip(info["name"] + (f" — {info['sub']}" if info["sub"] else ""))
            self.table.setItem(r, 0, it)
            row_total = 0
            for c, d in enumerate(days, start=1):
                sec = cells[key].get(d, 0)
                row_total += sec
                day_totals[c - 1] += sec
                item = QTableWidgetItem(fmt_hm(sec) if sec else "")
                item.setData(KIND, "day")
                item.setData(SECS, sec)
                item.setData(ROLE, (key, d))
                item.setToolTip("Double-click to edit")
                self.table.setItem(r, c, item)
            tot = QTableWidgetItem()
            tot.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tot.setData(KIND, "total")
            tot.setData(SECS, row_total)
            self.table.setItem(r, 8, tot)
            rm = QTableWidgetItem()
            rm.setFlags(Qt.ItemFlag.ItemIsEnabled)
            rm.setData(KIND, "remove")
            rm.setToolTip("Remove row (deletes this row's time for the week)")
            self.table.setItem(r, 9, rm)
        last = len(rows)
        foot = QTableWidgetItem()
        foot.setFlags(Qt.ItemFlag.ItemIsEnabled)
        foot.setData(KIND, "foot_label")
        self.table.setItem(last, 0, foot)
        for c, sec in enumerate(day_totals, start=1):
            it = QTableWidgetItem()
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setData(KIND, "foot")
            it.setData(SECS, sec)
            self.table.setItem(last, c, it)
        grand = QTableWidgetItem()
        grand.setFlags(Qt.ItemFlag.ItemIsEnabled)
        grand.setData(KIND, "foot_total")
        grand.setData(SECS, sum(day_totals))
        self.table.setItem(last, 8, grand)
        blank = QTableWidgetItem()
        blank.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.setItem(last, 9, blank)
        self._loading = False
        self._refresh_gaps()

    # ------------------------------------------------------------ gaps
    def _ignored(self) -> set[str]:
        raw = self.ctl.settings.value("gaps/ignored", "", type=str) or ""
        return {x for x in raw.split(",") if x}

    def _refresh_gaps(self) -> None:
        days = self._days()
        last = min(days[-1], date.today())
        ignored = self._ignored()
        self.gaps = [] if last < days[0] else [
            g for g in self.db.find_gaps(days[0], last, MIN_GAP) if f"{g['start']}-{g['end']}" not in ignored]
        self.gap_index = min(self.gap_index, max(0, len(self.gaps) - 1))
        self._show_gap()

    def _show_gap(self) -> None:
        if not self.gaps:
            self.banner.hide()
            return
        g = self.gaps[self.gap_index]
        self.banner.show()
        b, a = g["before"], g["after"]
        day = g["day"]
        when = "Today" if day == date.today() else f"{day:%A}"
        self.gap_title.setText(f"{when} has {fmt_words(g['end'] - g['start'])} untracked")
        bn = b["project_name"] or b["description"] or "an entry"
        an = a["project_name"] or a["description"] or "the next entry"
        text = f"Between {bn} (until {fmt_time(g['start'])}) and {an} (from {fmt_time(g['end'])})."
        others = len(self.gaps) - 1
        if others:
            text += f' <a href="#next" style="color:{C["accent_soft_text"]}">{others} more gap' \
                    f'{"s" if others > 1 else ""} this week</a>'
        self.gap_text.setText(text)
        target = b if b["project_id"] else a
        self.fill_btn.setText(f"Fill with {target['project_name']}" if target["project_id"] else "Fill gap")

    def _next_gap(self) -> None:
        if self.gaps:
            self.gap_index = (self.gap_index + 1) % len(self.gaps)
            self._show_gap()

    def _fill(self, project_id, task_id, description: str = "") -> None:
        g = self.gaps[self.gap_index]
        try:
            self.db.add_entry(g["start"], g["end"], project_id, task_id, description)
        except ValueError as exc:
            show_error(self, exc)
            return
        self.ctl.notify()

    def _fill_gap(self) -> None:
        if not self.gaps:
            return
        g = self.gaps[self.gap_index]
        src = g["before"] if g["before"]["project_id"] else g["after"]
        self._fill(src["project_id"], src["task_id"], src["description"] if src["project_id"] else "")

    def _pick_for_gap(self) -> None:
        if not self.gaps:
            return
        popup = ProjectPopup(self.db, self.window())
        popup.chosen.connect(lambda pid, tid: self._fill(pid, tid))
        popup.move(self.fill_btn.mapToGlobal(QPoint(0, self.fill_btn.height() + 4)))
        popup.show()

    def _dismiss_gap(self) -> None:
        if not self.gaps:
            return
        g = self.gaps[self.gap_index]
        ignored = self._ignored() | {f"{g['start']}-{g['end']}"}
        self.ctl.settings.setValue("gaps/ignored", ",".join(sorted(ignored)[-200:]))
        self._refresh_gaps()

    # ------------------------------------------------------------ editing
    def _cell_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.data(KIND) != "day":
            return
        (project_id, task_id), d = item.data(ROLE)
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
        if running is not None and running["project_id"] == project_id and running["task_id"] == task_id \
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
        has_time = any((self.table.item(row, c).data(SECS) or 0) for c in range(1, 8))
        if has_time and not confirm(self, "Remove row",
                                    f"Delete all time of “{self._row_info(key)['name']}” in this week?"):
            return
        running = self.ctl.running
        for d in self._days():
            if running is not None and (running["project_id"], running["task_id"]) == key \
                    and datetime.fromtimestamp(running["start_ts"]).date() == d:
                continue
            self.db.set_day_total(d, key[0], key[1], 0)
        self.extra_rows.get(self.week, set()).discard(key)
        self.ctl.notify()

    def _add_row(self) -> None:
        popup = ProjectPopup(self.db, self.window())
        popup.chosen.connect(self._row_chosen)
        popup.move(self.add_btn.mapToGlobal(QPoint(-200, self.add_btn.height() + 4)))
        popup.show()

    def _row_chosen(self, project_id, task_id) -> None:
        self.extra_rows.setdefault(self.week, set()).add((project_id, task_id))
        self.refresh()

    def _copy_last_week(self) -> None:
        prev = self.week - timedelta(weeks=1)
        keys = {(e["project_id"], e["task_id"])
                for e in self.db.entries(day_start_ts(prev), day_start_ts(self.week))}
        if not keys:
            show_error(self, "Last week has no time entries.")
            return
        self.extra_rows.setdefault(self.week, set()).update(keys)
        self.refresh()

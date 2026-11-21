"""Time Tracker page: timer bar on top, entries grouped by week and day."""
from __future__ import annotations

import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from PySide6.QtCore import QSize, QStringListModel, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCompleter, QFrame, QHBoxLayout, QLineEdit, QMenu, QScrollArea, QToolButton, QVBoxLayout,
    QWidget,
)

from ..db import day_start_ts
from ..icons import hover_icon, tomato_pixmap
from ..pomodoro import BREAK, FOCUS
from ..theme import C
from ..util import day_title, fmt_clock, fmt_money, fmt_time, week_start
from ..widgets import ProjectPicker, button, card, label, vsep


def icon_button(icon: str, tooltip: str, slot=None, size: int = 18,
                dpr: float = 1.0) -> QToolButton:
    """Flat button with a line icon (grey, green on hover)."""
    b = QToolButton(toolTip=tooltip)
    b.setObjectName("Icon")
    b.setIcon(hover_icon(icon, dpr, size))
    b.setIconSize(QSize(size, size))
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def repolish(widget: QWidget, name: str) -> None:
    if widget.objectName() != name:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class EntryRow(QFrame):
    def __init__(self, page: "TrackerPage", entry):
        super().__init__()
        self.page = page
        self.ctl = page.ctl
        self.entry = entry
        db = self.ctl.db
        self.setObjectName("EntryRow")

        self.desc = QLineEdit(entry["description"], placeholderText="Add description")
        self.desc.setObjectName("Flat")
        self.desc.setMinimumWidth(240)
        self.desc.editingFinished.connect(self._save_description)
        self.picker = ProjectPicker(db, self)
        self.picker.set_entry(entry)
        self.picker.changed.connect(self._save_project)

        amount = db.amount(entry)
        self.amount = label(fmt_money(amount, db.currency) if amount else "", "Muted")
        time_btn = button(f"{fmt_time(entry['start_ts'])}  -  {fmt_time(entry['end_ts'])}",
                          lambda: self.ctl.edit_entry(entry["id"]), "Time")
        time_btn.setToolTip("Edit time")
        duration = label(fmt_clock(db.duration(entry)), "Duration")
        duration.setMinimumWidth(90)
        duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        dpr = page.devicePixelRatioF()
        play = icon_button("play", "Continue this activity",
                           lambda: self.ctl.start(entry["project_id"], entry["task_id"],
                                                  entry["description"]), 16, dpr)
        more = icon_button("more", "More", lambda: self._show_menu(more), 18, dpr)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 8, 6)
        lay.setSpacing(10)
        lay.addWidget(self.desc, 3)
        lay.addWidget(self.picker, 2)
        lay.addStretch(1)
        lay.addWidget(self.amount)
        lay.addWidget(vsep())
        lay.addWidget(time_btn)
        lay.addWidget(vsep())
        lay.addWidget(duration)
        lay.addWidget(play)
        lay.addWidget(more)

    def _show_menu(self, anchor: QWidget) -> None:
        # Built on demand: one menu per row up front made the list slow to build.
        eid = self.entry["id"]
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self.ctl.edit_entry(eid))
        menu.addAction("Duplicate", lambda: self.ctl.duplicate_entry(eid))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.ctl.delete_entry(eid))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        menu.deleteLater()

    def _save_description(self) -> None:
        text = self.desc.text().strip()
        if text != self.entry["description"]:
            self.ctl.db.update_entry(self.entry["id"], description=text)
            self.entry = self.ctl.db.get_entry(self.entry["id"])
            self.ctl.notify(origin=self.page)

    def _save_project(self, project_id, task_id) -> None:
        self.ctl.db.update_entry(self.entry["id"], project_id=project_id, task_id=task_id)
        QTimer.singleShot(0, self.ctl.notify)


class TrackerPage(QWidget):
    title = "Time Tracker"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self.weeks = 2   # more via "Load more"; each row is real widgets, keep the first build fast

        # ---- timer bar
        bar = QFrame()
        bar.setObjectName("TopBar")
        self.desc = QLineEdit(placeholderText="What are you working on?")
        self.desc.setObjectName("BigInput")
        # Autocomplete from earlier descriptions; picking one also fills its project/task.
        self._activities: dict[str, tuple] = {}
        self._completer_model = QStringListModel(self)
        completer = QCompleter(self._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated[str].connect(self._activity_chosen)
        self.desc.setCompleter(completer)
        self.picker = ProjectPicker(self.db, self)
        self.amount_label = label("", "Muted")
        self.time_label = label("00:00:00", "Big")
        self.time_label.setMinimumWidth(110)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_btn = button("START", self.toggle, "Primary")
        self.start_btn.setFixedWidth(120)
        manual_btn = icon_button("add", "Add time manually", lambda: self.ctl.new_entry(), 20,
                                 self.devicePixelRatioF())
        manual_btn.setFixedSize(36, self.start_btn.sizeHint().height())

        self.pomo_btn = QToolButton()
        self.pomo_btn.setObjectName("Pomo")
        # Red tomato in both states; the button's fill (grey / green) shows on or off.
        self.pomo_btn.setIcon(QIcon(tomato_pixmap(26, self.devicePixelRatioF())))
        self.pomo_btn.setIconSize(QSize(26, 26))
        # Same height as START next to it.
        self.pomo_btn.setFixedSize(56, self.start_btn.sizeHint().height())
        self.pomo_btn.setCheckable(True)
        self.pomo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pomo_btn.setToolTip("Pomodoro mode: START runs a focus session, then a break.\n"
                                 "Lengths are in Settings.")
        self.pomo_btn.setChecked(self.ctl.pomodoro_enabled())
        self.pomo_btn.toggled.connect(self.ctl.set_pomodoro_enabled)
        self.pomo_label = label("", "Small")
        self.pomo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skip_btn = button("Skip break", self.ctl.skip_break, "Link")
        self.skip_btn.setVisible(False)
        clock = QVBoxLayout()
        clock.setSpacing(0)
        clock.addWidget(self.pomo_label)
        clock.addWidget(self.time_label)

        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(10, 10, 10, 10)
        bar_lay.setSpacing(12)
        bar_lay.addWidget(self.desc, 1)
        bar_lay.addWidget(self.picker)
        bar_lay.addWidget(vsep())
        bar_lay.addWidget(self.amount_label)
        bar_lay.addWidget(self.skip_btn)
        bar_lay.addLayout(clock)
        bar_lay.addWidget(self.pomo_btn)
        bar_lay.addWidget(self.start_btn)
        bar_lay.addWidget(manual_btn)

        # ---- list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.list_layout = QVBoxLayout(self.content)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(0)
        self.scroll.setWidget(self.content)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(16)
        root.addWidget(bar)
        root.addWidget(self.scroll, 1)

        self.desc.returnPressed.connect(self._desc_enter)
        self.desc.editingFinished.connect(self._desc_done)
        self.picker.changed.connect(self._picker_changed)

    # ------------------------------------------------------------ timer bar
    def toggle(self) -> None:
        if self.ctl.running is not None:
            self._desc_done()
            self.ctl.stop()
        else:
            self.ctl.start(self.picker.project_id, self.picker.task_id, self.desc.text())

    def _reload_completions(self) -> None:
        self._activities = {}
        for a in self.db.recent_activities(300):
            if a["description"] and a["description"] not in self._activities:
                self._activities[a["description"]] = (a["project_id"], a["task_id"])
        self._completer_model.setStringList(list(self._activities))

    def _activity_chosen(self, text: str) -> None:
        project_id, task_id = self._activities.get(text, (None, None))
        if project_id and (self.ctl.running is None or self.picker.project_id is None):
            self.picker.set_value(project_id, task_id)
            self._picker_changed(project_id, task_id)

    def draft(self) -> tuple:
        return self.picker.project_id, self.picker.task_id, self.desc.text().strip()

    def _desc_enter(self) -> None:
        if self.ctl.running is None:
            self.toggle()
        else:
            self._desc_done()

    def _desc_done(self) -> None:
        running = self.ctl.running
        if running is not None and self.desc.text().strip() != running["description"]:
            self.db.update_entry(running["id"], description=self.desc.text())
            self.ctl.notify(origin=self)

    def _picker_changed(self, project_id, task_id) -> None:
        running = self.ctl.running
        if running is not None:
            self.db.update_entry(running["id"], project_id=project_id, task_id=task_id)
            self.ctl.notify(origin=self)
            self.tick()

    def sync_top(self) -> None:
        running = self.ctl.running
        self.pomo_btn.blockSignals(True)
        self.pomo_btn.setChecked(self.ctl.pomodoro_enabled())
        self.pomo_btn.blockSignals(False)
        if running is not None:
            if not self.desc.hasFocus():
                self.desc.setText(running["description"])
            self.picker.set_value(running["project_id"], running["task_id"])
            self.start_btn.setText("STOP")
            repolish(self.start_btn, "Stop")
        else:
            self.start_btn.setText("START")
            repolish(self.start_btn, "Primary")
            self.amount_label.setText("")
        self.tick()

    def clear_draft(self) -> None:
        self.desc.clear()
        self.picker.set_value(None, None)

    def set_draft(self, project_id, task_id, description: str) -> None:
        """Pre-fill the bar so one START continues the same activity (after a pomodoro)."""
        if self.ctl.running is None:
            self.desc.setText(description or "")
            self.picker.set_value(project_id, task_id)

    def tick(self) -> None:
        running = self.ctl.running
        pomo = self.ctl.pomo
        enabled = self.ctl.pomodoro_enabled()
        now = int(time.time())
        self.skip_btn.setVisible(pomo.phase == BREAK)
        self.pomo_label.setVisible(enabled)
        self.pomo_label.setText(pomo.label() if enabled else "")
        if pomo.phase in (FOCUS, BREAK):
            # Countdown; green while focusing, muted text during a break.
            self.time_label.setText(fmt_clock(pomo.remaining(now)))
            self.time_label.setStyleSheet(
                f"color: {C['accent_text'] if pomo.phase == FOCUS else C['muted']};")
        elif running is not None:
            self.time_label.setText(fmt_clock(self.db.duration(running)))
            self.time_label.setStyleSheet("")
        else:
            self.time_label.setText(fmt_clock(pomo.config.focus) if enabled else "00:00:00")
            self.time_label.setStyleSheet("")
        if running is not None:
            amount = self.db.amount(running)
            self.amount_label.setText(fmt_money(amount, self.db.currency) if amount else "")

    # ----------------------------------------------------------------- list
    def refresh(self) -> None:
        self.sync_top()
        self.rebuild_list()
        self._reload_completions()

    def _new_list_widget(self) -> None:
        """Build the list into a fresh widget; swapping it in later deletes the old one in
        one go (much faster than detaching rows one by one, and no overlap/flicker)."""
        self.content = QWidget()
        self.list_layout = QVBoxLayout(self.content)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(0)

    def rebuild_list(self) -> None:
        scroll_pos = self.scroll.verticalScrollBar().value()
        self._new_list_widget()
        today = date.today()
        first_week = week_start(today) - timedelta(weeks=self.weeks - 1)
        t0 = day_start_ts(first_week)
        t1 = day_start_ts(today + timedelta(days=1))
        entries = self.db.entries(t0, t1, include_running=False)

        weeks: "OrderedDict[date, OrderedDict[date, list]]" = OrderedDict()
        for e in sorted(entries, key=lambda e: e["start_ts"], reverse=True):
            d = datetime.fromtimestamp(e["start_ts"]).date()
            weeks.setdefault(week_start(d), OrderedDict()).setdefault(d, []).append(e)

        if not weeks:
            empty = label("No time entries yet.\nType what you're working on above and press "
                          "START, or add time manually with ＋.", "Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 60, 0, 0)
            self.list_layout.addWidget(empty)

        this_week = week_start(today)
        for ws, days in weeks.items():
            if ws == this_week:
                title = "This week"
            elif ws == this_week - timedelta(weeks=1):
                title = "Last week"
            else:
                we = ws + timedelta(days=6)
                title = f"{ws:%b} {ws.day} - {we:%b} {we.day}"
            week_total = sum(self.db.duration(e) for ds in days.values() for e in ds)
            head = QWidget()
            hl = QHBoxLayout(head)
            hl.setContentsMargins(2, 18, 2, 10)
            hl.addWidget(label(title))
            hl.addStretch(1)
            hl.addWidget(label("Week total:", "Small"))
            hl.addWidget(label(fmt_clock(week_total), "Big"))
            self.list_layout.addWidget(head)
            for d, items in days.items():
                self.list_layout.addWidget(self._day_card(d, items))
                self.list_layout.addSpacing(14)

        older = self.db.conn.execute("SELECT 1 FROM entries WHERE start_ts < ? LIMIT 1",
                                     (t0,)).fetchone()
        if older:
            more = button("Load more", self._load_more)
            more.setFixedWidth(160)
            self.list_layout.addWidget(more, 0, Qt.AlignmentFlag.AlignHCenter)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.content)   # deletes the previous list widget
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_pos))

    def _day_card(self, d: date, entries: list) -> QWidget:
        box = card()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        header = QWidget()
        header.setObjectName("CardHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 8, 14, 8)
        hl.addWidget(label(day_title(d), "Small"))
        hl.addStretch(1)
        amount = sum(self.db.amount(e) for e in entries)
        if amount:
            hl.addWidget(label(fmt_money(amount, self.db.currency), "Muted"))
            hl.addSpacing(12)
        hl.addWidget(label("Total:", "Small"))
        hl.addWidget(label(fmt_clock(sum(self.db.duration(e) for e in entries)), "Big"))
        lay.addWidget(header)
        for e in entries:
            lay.addWidget(EntryRow(self, e))
        return box

    def _load_more(self) -> None:
        self.weeks += 2
        self.rebuild_list()

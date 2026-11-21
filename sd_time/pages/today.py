"""Tracker page: the "Now" card with a ring timer, quick restarts, and Today with a time ribbon.

Earlier days are folded into one line each ("Yesterday · 7h 55m · 373 USD") and open on click.
"""
from __future__ import annotations

import html
import math
import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, QStringListModel, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea,
    QSizePolicy, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from .. import theme
from ..db import NO_COLOR, day_start_ts
from ..icons import color_icon, filled_pixmap, hover_icon, line_pixmap, timer_pixmap
from ..pomodoro import ASK, BREAK, FOCUS, KINDS
from ..theme import C
from ..util import day_title, fmt_clock, fmt_hm, fmt_money, fmt_time, fmt_words, week_start
from ..widgets import ProjectPicker, button, card, clear_layout, label


def repolish(widget: QWidget, name: str) -> None:
    if widget.objectName() != name:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def icon_button(icon: str, tooltip: str, slot=None, size: int = 18, dpr: float = 1.0) -> QToolButton:
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


def short_money(value: float, currency: str) -> str:
    return f"{value:,.0f} {currency}".strip() if value >= 100 else fmt_money(value, currency)


# ------------------------------------------------------------------ painted widgets
class RingTimer(QWidget):
    """Circular timer: a track, a progress arc and the time in the middle."""

    def __init__(self, size: int = 216):
        super().__init__()
        self.setFixedSize(size, size)
        self.progress = 0.0
        self.color = C["accent_text"]
        self.big = "0:00:00"
        self.small = ""

    def set(self, progress: float, color: str, big: str, small: str) -> None:
        self.progress, self.color, self.big, self.small = max(0.0, min(1.0, progress)), color, big, small
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = 12
        r = QRectF(w / 2 + 2, w / 2 + 2, self.width() - w - 4, self.height() - w - 4)
        pen = QPen(QColor("#2a2a2a"), w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(r)
        if self.progress > 0:
            pen.setColor(QColor(self.color))
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -int(360 * 16 * self.progress))
        p.setPen(QColor(C["text"]))
        size = 28 if len(self.big) <= 5 else 23
        p.setFont(theme.mono(size, True))
        p.drawText(QRectF(0, self.height() / 2 - 34, self.width(), 48), Qt.AlignmentFlag.AlignCenter, self.big)
        f = self.font()
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(0, self.height() / 2 + 14, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.small)


class DayRibbon(QWidget):
    """Today as one horizontal strip: coloured blocks for entries, a marker for now."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)
        self.setMouseTracking(True)
        self.segments: list[tuple[float, float, str, bool, str]] = []
        self.h0, self.h1, self.now_h = 8.0, 19.0, None
        self._hits: list[tuple[QRectF, str]] = []

    def set(self, segments, h0: float, h1: float, now_h: float | None) -> None:
        self.segments, self.h0, self.h1, self.now_h = segments, h0, h1, now_h
        self.update()

    def _x(self, h: float) -> float:
        return (h - self.h0) / max(0.01, self.h1 - self.h0) * self.width()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#181818"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 40), 4, 4)
        self._hits = []
        for start, end, color, running, tip in self.segments:
            x0, x1 = self._x(max(start, self.h0)), self._x(min(end, self.h1))
            rect = QRectF(x0, 7, max(3.0, x1 - x0 - 1.5), 26)
            p.setPen(QPen(QColor(C["accent_text"]), 2) if running else Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(rect, 3, 3)
            self._hits.append((rect, tip))
        if self.now_h is not None and self.h0 <= self.now_h <= self.h1:
            x = self._x(self.now_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["accent_text"]))
            p.drawRoundedRect(QRectF(x - 1, 0, 2, 40), 1, 1)
        p.setFont(theme.mono(8))
        p.setPen(QColor("#8a8a8a"))
        h = math.ceil(self.h0)
        while h <= self.h1:
            if h % 2 == 0:
                x = min(max(0.0, self._x(h) - 2), self.width() - 18)   # keep edge labels inside
                p.drawText(QRectF(x, 44, 40, 16), Qt.AlignmentFlag.AlignLeft, f"{h:02d}")
            h += 1

    def mouseMoveEvent(self, event) -> None:
        for rect, tip in self._hits:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()


# ------------------------------------------------------------------ list widgets
class EntryLine(QFrame):
    """One entry: time · description · project chip · duration · amount · ▷ · ⋮"""

    def __init__(self, page: "TrackerPage", entry, running: bool = False):
        super().__init__()
        self.page, self.ctl, self.entry = page, page.ctl, entry
        db = self.ctl.db
        self.setObjectName("EntryLine")
        dpr = page.devicePixelRatioF()

        end = "now" if running else fmt_time(entry["end_ts"])
        self.time_btn = button(f"{fmt_time(entry['start_ts'])} – {end}",
                               lambda: self.ctl.edit_entry(entry["id"]), "Time")
        self.time_btn.setToolTip("Edit time")
        self.time_btn.setFixedWidth(116)
        if running:
            self.time_btn.setStyleSheet(f"color: {C['accent_soft_text']};")
        self.desc = QLineEdit(entry["description"], placeholderText="Add description")
        self.desc.setObjectName("Flat")
        self.desc.setMinimumWidth(110)
        self.desc.setCursorPosition(0)          # show the start of long descriptions
        self.desc.editingFinished.connect(self._save_description)
        if running:
            f = self.desc.font()
            f.setBold(True)
            self.desc.setFont(f)
        self.picker = ProjectPicker(db, self)
        self.picker.set_entry(entry)
        self.picker.setMaximumWidth(230)
        self.picker.changed.connect(self._save_project)
        self.duration = label(fmt_hm(db.duration(entry)), "Mono")
        self.duration.setFixedWidth(52)
        self.duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        amount = db.amount(entry)
        self.amount = label(short_money(amount, db.currency) if amount else "", "Muted")
        self.amount.setFixedWidth(72)
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        play = icon_button("play", "Continue this activity",
                           lambda: self.ctl.start(entry["project_id"], entry["task_id"],
                                                  entry["description"]), 15, dpr)
        play.setVisible(not running)
        more = icon_button("more", "More", lambda: self._show_menu(more), 17, dpr)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 5, 2, 5)
        lay.setSpacing(10)
        lay.addWidget(self.time_btn)
        lay.addWidget(self.desc, 1)
        lay.addWidget(self.picker)
        lay.addWidget(self.duration)
        lay.addWidget(self.amount)
        lay.addWidget(play)
        lay.addWidget(more)
        if running:
            lay.setStretchFactor(self.desc, 1)

    def _show_menu(self, anchor: QWidget) -> None:
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


class DayGroup(QWidget):
    """A folded day: "› Thu, Nov 19        6h 56m · 373 USD"; opens to its entries."""

    def __init__(self, page: "TrackerPage", d: date, entries: list):
        super().__init__()
        self.page, self.d, self.entries = page, d, entries
        self.setObjectName("DayGroup")
        db = page.db
        self.head = QPushButton()
        self.head.setObjectName("GroupHead")
        self.head.setCursor(Qt.CursorShape.PointingHandCursor)
        self.head.setFixedHeight(42)
        self.chevron = QLabel()
        self._set_chevron(False)
        title = label(day_title(d))
        total = sum(db.duration(e) for e in entries)
        amount = sum(db.amount(e) for e in entries)
        summary = label(fmt_words(total) + (f" · {short_money(amount, db.currency)}" if amount else ""),
                        "MonoMuted")
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(8, 0, 10, 0)
        hl.setSpacing(10)
        for w in (self.chevron, title, summary):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hl.addWidget(self.chevron)
        hl.addWidget(title, 1)
        hl.addWidget(summary)
        self.body = QWidget()
        self.body.setVisible(False)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(22, 0, 0, 6)
        self.body_lay.setSpacing(0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.head)
        lay.addWidget(self.body)
        self.head.clicked.connect(self.toggle)
        self._built = False

    def _set_chevron(self, open_: bool) -> None:
        self.chevron.setPixmap(line_pixmap("chevron-down" if open_ else "chevron", "#bdbdbd", 16,
                                           self.page.devicePixelRatioF()))

    def toggle(self) -> None:
        if not self._built:   # build rows on first open only
            for e in sorted(self.entries, key=lambda e: e["start_ts"], reverse=True):
                self.body_lay.addWidget(EntryLine(self.page, e))
            self._built = True
        show = not self.body.isVisible()
        self.body.setVisible(show)
        self._set_chevron(show)
        self.page.open_days.add(self.d) if show else self.page.open_days.discard(self.d)


# ------------------------------------------------------------------ the page
class TrackerPage(QWidget):
    title = "Tracker"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self.days_back = 14
        self.open_days: set[date] = set()
        self._running_line: EntryLine | None = None
        self._today_done = 0
        self._today_amount = 0.0
        self._ribbon_segments: list = []
        dpr = self.devicePixelRatioF()

        # ---- header
        self.title_label = label("", "H1")
        self.subtitle = label("", "Muted")
        add_btn = button("Add time", lambda: self.ctl.new_entry())
        add_btn.setIcon(hover_icon("add", dpr, 16))
        add_btn.setIconSize(QSize(16, 16))
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(self.title_label)
        head_text.addWidget(self.subtitle)
        self.mini_btn = QToolButton()
        self.mini_btn.setObjectName("Nav")
        self.mini_btn.setCheckable(True)
        self.mini_btn.setFixedSize(theme.CTRL_H, theme.CTRL_H)
        self.mini_btn.setIcon(hover_icon("mini", dpr, 18, normal="#c9c9c9"))
        self.mini_btn.setIconSize(QSize(18, 18))
        self.mini_btn.setToolTip("Mini timer: a small window that stays on top")
        self.mini_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mini_btn.clicked.connect(lambda: self.ctl.toggle_mini())
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(head_text, 1)
        header.addWidget(self.mini_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # ---- Now card
        now = card()
        now.setFixedWidth(380)
        self.pomo_btn = QToolButton()
        self.pomo_btn.setObjectName("PomoChip")
        self.pomo_btn.setCheckable(True)          # shows "on"; the menu changes it
        self.pomo_btn.setIconSize(QSize(18, 18))
        self.pomo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.pomo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pomo_btn.setToolTip("Focus timer: START runs a focus session, then a break")
        self.pomo_btn.setChecked(self.ctl.pomodoro_enabled())
        self.pomo_menu = QMenu(self.pomo_btn)
        self.pomo_menu.aboutToShow.connect(self._fill_pomo_menu)
        self.pomo_btn.setMenu(self.pomo_menu)
        self.pomo_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._pomo_kind_shown = None
        self.pomo_label = label("", "Small")
        top = QHBoxLayout()
        top.addWidget(self.pomo_btn)
        top.addStretch(1)
        top.addWidget(self.pomo_label)

        self.ring = RingTimer(184)
        self.desc = QLineEdit(placeholderText="What are you working on?")
        self.desc.setObjectName("NowInput")
        self.desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._activities: dict[str, tuple] = {}
        self._completer_model = QStringListModel(self)
        completer = QCompleter(self._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated[str].connect(self._activity_chosen)
        self.desc.setCompleter(completer)
        self.picker = ProjectPicker(self.db, self)
        self.info = label("", "Small")
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.left_btn = QToolButton()
        self.left_btn.setObjectName("RoundSmall")
        self.left_btn.setFixedSize(48, 48)
        self.left_btn.setIconSize(QSize(20, 20))
        self.left_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.left_btn.clicked.connect(self._left_action)
        self.start_btn = QToolButton()
        self.start_btn.setObjectName("RoundStart")
        self.start_btn.setFixedSize(68, 68)
        self.start_btn.setIconSize(QSize(24, 24))
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle)
        self.edit_btn = QToolButton()
        self.edit_btn.setObjectName("RoundSmall")
        self.edit_btn.setFixedSize(48, 48)
        self.edit_btn.setIconSize(QSize(20, 20))
        self.edit_btn.setIcon(hover_icon("pencil", dpr, 20, normal="#c9c9c9"))
        self.edit_btn.setToolTip("Edit the running entry")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.ctl.running and self.ctl.edit_entry(self.ctl.running["id"]))
        buttons = QHBoxLayout()
        buttons.setSpacing(16)
        buttons.addStretch(1)
        buttons.addWidget(self.left_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.edit_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        buttons.addStretch(1)

        picker_row = QHBoxLayout()
        picker_row.addStretch(1)
        picker_row.addWidget(self.picker)
        picker_row.addStretch(1)
        nl = QVBoxLayout(now)
        nl.setContentsMargins(20, 16, 20, 18)
        nl.setSpacing(10)
        nl.addLayout(top)
        nl.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignHCenter)
        nl.addWidget(self.desc)
        nl.addLayout(picker_row)
        nl.addWidget(self.info)
        nl.addSpacing(4)
        nl.addLayout(buttons)

        # ---- Start again card
        again = card()
        again.setFixedWidth(380)
        self.again_lay = QVBoxLayout(again)
        self.again_lay.setContentsMargins(20, 16, 20, 18)
        self.again_lay.setSpacing(8)

        # The left column scrolls when the window is short, instead of squeezing the ring.
        left_box = QWidget()
        left = QVBoxLayout(left_box)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(16)
        left.addWidget(now)
        left.addWidget(again)
        left.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFixedWidth(392)
        left_scroll.setWidget(left_box)

        # ---- Today card
        today = card()
        self.pill_total = label("", "Pill")
        self.pill_amount = label("", "Pill")
        self.pill_focus = label("", "PillAccent")
        th = QHBoxLayout()
        th.setSpacing(8)
        th.addWidget(label("Today", "H2"), 1)
        th.addWidget(self.pill_total)
        th.addWidget(self.pill_amount)
        th.addWidget(self.pill_focus)
        self.ribbon = DayRibbon()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        tl = QVBoxLayout(today)
        tl.setContentsMargins(22, 20, 22, 14)
        tl.setSpacing(14)
        tl.addLayout(th)
        tl.addWidget(self.ribbon)
        tl.addWidget(self.scroll, 1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(left_scroll)
        body.addWidget(today, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 22)
        root.setSpacing(20)
        root.addLayout(header)
        root.addLayout(body, 1)

        self.desc.returnPressed.connect(self._desc_enter)
        self.desc.editingFinished.connect(self._desc_done)
        self.picker.changed.connect(self._picker_changed)

    # ------------------------------------------------------------ timer controls
    def toggle(self) -> None:
        if self.ctl.running is not None:
            self._desc_done()
            self.ctl.stop()
        else:
            self.ctl.start(self.picker.project_id, self.picker.task_id, self.desc.text())

    def _left_action(self) -> None:
        if self.ctl.pomo.phase == BREAK:
            self.ctl.skip_break()
        else:
            self.ctl.new_entry()

    def _fill_pomo_menu(self) -> None:
        menu, dpr = self.pomo_menu, self.devicePixelRatioF()
        menu.clear()
        on, current = self.ctl.pomodoro_enabled(), self.ctl.pomodoro_kind()
        for kind in KINDS.values():
            m = self.ctl.timer_lengths(kind.key)
            act = menu.addAction(QIcon(timer_pixmap(kind.key, 18, dpr)),
                                 f"{kind.name}   {m['focus_min']} / {m['short_break_min']} min")
            act.setCheckable(True)
            act.setChecked(on and kind.key == current)
            act.setToolTip(kind.blurb)
            act.triggered.connect(lambda _=False, k=kind.key: self.ctl.set_pomodoro_kind(k))
        menu.addSeparator()
        off = menu.addAction("Off: plain timer")
        off.setCheckable(True)
        off.setChecked(not on)
        off.triggered.connect(lambda: self.ctl.set_pomodoro_enabled(False))
        menu.setToolTipsVisible(True)

    def sync_mini_button(self, on: bool) -> None:
        self.mini_btn.setChecked(on)

    def draft(self) -> tuple:
        return self.picker.project_id, self.picker.task_id, self.desc.text().strip()

    def clear_draft(self) -> None:
        self.desc.clear()
        self.picker.set_value(None, None)

    def set_draft(self, project_id, task_id, description: str) -> None:
        """Pre-fill so one START continues the same activity (after a pomodoro)."""
        if self.ctl.running is None:
            self.desc.setText(description or "")
            self.picker.set_value(project_id, task_id)

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
            self.ctl.notify()

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

    # ------------------------------------------------------------ state → widgets
    def sync_top(self) -> None:
        running = self.ctl.running
        dpr = self.devicePixelRatioF()
        self.pomo_btn.blockSignals(True)
        self.pomo_btn.setChecked(self.ctl.pomodoro_enabled())
        self.pomo_btn.blockSignals(False)
        if running is not None:
            if not self.desc.hasFocus():
                self.desc.setText(running["description"])
            self.picker.set_value(running["project_id"], running["task_id"])
            repolish(self.start_btn, "RoundStop")
            self.start_btn.setIcon(QIcon(filled_pixmap("stop", "#ffffff", 24, dpr)))
            self.start_btn.setToolTip("Stop")
        else:
            repolish(self.start_btn, "RoundStart")
            self.start_btn.setIcon(QIcon(filled_pixmap("play", "#ffffff", 26, dpr)))
            self.start_btn.setToolTip("Start")
        self.edit_btn.setEnabled(running is not None)
        if self.ctl.pomo.phase == BREAK:
            self.left_btn.setIcon(hover_icon("skip", dpr, 20, normal="#c9c9c9"))
            self.left_btn.setToolTip("Skip the break")
        else:
            self.left_btn.setIcon(hover_icon("add", dpr, 20, normal="#c9c9c9"))
            self.left_btn.setToolTip("Add time manually")
        self.tick()

    def tick(self) -> None:
        running = self.ctl.running
        pomo = self.ctl.pomo
        enabled = self.ctl.pomodoro_enabled()
        now = int(time.time())
        cfg = pomo.config
        # Pomodoro chip and status
        if self._pomo_kind_shown != cfg.kind:
            self._pomo_kind_shown = cfg.kind
            self.pomo_btn.setIcon(QIcon(timer_pixmap(cfg.kind, 18, self.devicePixelRatioF())))
            self.pomo_btn.setProperty("kind", cfg.kind)      # tint of the "on" chip
            self.pomo_btn.style().unpolish(self.pomo_btn)
            self.pomo_btn.style().polish(self.pomo_btn)
        self.pomo_btn.setText(pomo.label().replace("/", " of ") if enabled else "Focus timer")
        if not enabled:
            hk = self.ctl.hotkey_text()
            self.pomo_label.setText(f"{hk} starts / stops" if hk else "")
        elif pomo.phase == FOCUS:
            self.pomo_label.setText(f"Break in {max(1, math.ceil(pomo.remaining(now) / 60))} min")
        elif pomo.phase == BREAK:
            self.pomo_label.setText("Break")
        elif pomo.phase == ASK:
            self.pomo_label.setText("Focus done")
        else:
            self.pomo_label.setText(f"{cfg.focus // 60}-min focus")
        # Ring
        if pomo.phase == FOCUS:
            left = pomo.remaining(now)
            self.ring.set(1 - left / max(1, cfg.focus), C["accent_text"],
                          self._mmss(left), f"left of {self._mmss(cfg.focus)}")
        elif pomo.phase == BREAK:
            left = pomo.remaining(now)
            length = cfg.long_break if pomo.long else cfg.short_break
            self.ring.set(1 - left / max(1, length), "#7aa7c7", self._mmss(left), "break")
        elif running is not None:
            elapsed = self.db.duration(running)
            done = pomo.phase == ASK
            self.ring.set(1.0 if done else (elapsed % 3600) / 3600, C["accent_text"],
                          fmt_clock(elapsed) if elapsed >= 3600 else self._mmss(elapsed),
                          "focus done · keep going?" if done else "elapsed")
        else:
            self.ring.set(0, C["accent_text"], self._mmss(cfg.focus) if enabled else "00:00",
                          "focus length" if enabled else "ready")
        # Info line under the project chip
        if running is not None:
            amount = self.db.amount(running)
            parts = [running["client_name"] or "", (fmt_money(amount, self.db.currency) + " so far")
                     if amount else ""]
            self.info.setText(" · ".join(p for p in parts if p))
        else:
            self.info.setText("")
        # Live bits of the Today card
        if running is not None and self._running_line is not None:
            self._running_line.duration.setText(fmt_hm(self.db.duration(running)))
            amount = self.db.amount(running)
            self._running_line.amount.setText(short_money(amount, self.db.currency) if amount else "")
        total = self._today_done + (self.db.duration(running) if running is not None
                                    and self._started_today(running) else 0)
        amount = self._today_amount + (self.db.amount(running) if running is not None
                                       and self._started_today(running) else 0)
        self.pill_total.setText(fmt_words(total))
        self.pill_amount.setText(short_money(amount, self.db.currency))
        self.pill_amount.setVisible(amount > 0)
        if running is not None and self._ribbon_segments:
            self._update_ribbon()

    @staticmethod
    def _mmss(seconds: int) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def _started_today(e) -> bool:
        return datetime.fromtimestamp(e["start_ts"]).date() == date.today()

    # ------------------------------------------------------------ data → lists
    def refresh(self) -> None:
        today = date.today()
        self.title_label.setText(f"{today:%A}, {today.day} {today:%B}")
        ws = week_start(today)
        week = self.db.entries(day_start_ts(ws), day_start_ts(today + timedelta(days=1)))
        week_total = sum(self.db.duration(e) for e in week)
        week_amount = sum(self.db.amount(e) for e in week)
        sub = f"Week {today.isocalendar()[1]} · {fmt_words(week_total)} tracked"
        if week_amount:
            sub += f" · {short_money(week_amount, self.db.currency)}"
        self.subtitle.setText(sub)
        self._rebuild_again()
        self._rebuild_list()
        self._reload_completions()
        self.sync_top()

    def _rebuild_again(self) -> None:
        clear_layout(self.again_lay)
        self.again_lay.addWidget(label("Start again", "H3"))
        recent = self.db.recent_activities(3)
        if not recent:
            self.again_lay.addWidget(label("Your recent activities will appear here.", "Small"))
        for a in recent:
            text = a["description"] or a["project_name"] or "No description"
            sub = a["project_name"] if a["description"] and a["project_name"] else ""
            b = QPushButton()
            b.setObjectName("Chip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(color_icon(a["project_color"] or NO_COLOR, 9))
            b.setIconSize(QSize(9, 9))
            b.setText(f"  {text}" + (f"   ·   {sub}" if sub else ""))
            b.setToolTip("Start this again")
            b.clicked.connect(lambda _=False, a=a: self.ctl.start(a["project_id"], a["task_id"],
                                                                  a["description"]))
            self.again_lay.addWidget(b)

    def _rebuild_list(self) -> None:
        scroll_pos = self.scroll.verticalScrollBar().value()
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(0)
        today = date.today()
        first = today - timedelta(days=self.days_back)
        entries = self.db.entries(day_start_ts(first), day_start_ts(today + timedelta(days=1)))
        by_day: dict[date, list] = {}
        for e in entries:
            by_day.setdefault(datetime.fromtimestamp(e["start_ts"]).date(), []).append(e)

        todays = sorted(by_day.pop(today, []), key=lambda e: e["start_ts"], reverse=True)
        self._running_line = None
        self._today_done = sum(self.db.duration(e) for e in todays if e["end_ts"] is not None)
        self._today_amount = sum(self.db.amount(e) for e in todays if e["end_ts"] is not None)
        for e in todays:
            line = EntryLine(self, e, running=e["end_ts"] is None)
            if e["end_ts"] is None:
                self._running_line = line
            lay.addWidget(line)
        if not todays:
            empty = label("Nothing tracked today yet. Type what you're working on and press start.",
                          "Muted")
            empty.setContentsMargins(4, 18, 4, 18)
            lay.addWidget(empty)
        focus_today = self.db.focus_sessions(day_start_ts(today), day_start_ts(today + timedelta(days=1)))
        self.pill_focus.setText(f"{len(focus_today)} focus done")
        self.pill_focus.setVisible(bool(focus_today))

        if by_day:
            lay.addSpacing(14)
            lay.addWidget(label("Earlier", "Small"))
        for d in sorted(by_day, reverse=True):
            group = DayGroup(self, d, by_day[d])
            lay.addWidget(group)
            if d in self.open_days:
                group.toggle()
        older = self.db.conn.execute("SELECT 1 FROM entries WHERE start_ts < ? LIMIT 1",
                                     (day_start_ts(first),)).fetchone()
        if older:
            more = button("Show more days", self._load_more, "Link")
            lay.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(1)
        self.scroll.setWidget(content)       # replaces (and deletes) the previous list
        self.content = content
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_pos))

        # ribbon segments for today
        self._ribbon_segments = [
            (e, e["project_color"] or NO_COLOR) for e in sorted(todays, key=lambda e: e["start_ts"])]
        self._update_ribbon()

    def _update_ribbon(self) -> None:
        today0 = day_start_ts(date.today())
        now = time.time()
        segs = []
        lo, hi = 8.0, 19.0
        for e, color in self._ribbon_segments:
            end_ts = e["end_ts"] if e["end_ts"] is not None else now
            s, t = (e["start_ts"] - today0) / 3600, (end_ts - today0) / 3600
            lo, hi = min(lo, math.floor(s)), max(hi, math.ceil(t))
            tip = " · ".join(x for x in (e["description"], e["project_name"]) if x) or "No description"
            end_txt = fmt_time(e["end_ts"]) if e["end_ts"] is not None else "now"
            segs.append((s, t, color, e["end_ts"] is None,
                         f"{tip}\n{fmt_time(e['start_ts'])} – {end_txt}"))
        now_h = (now - today0) / 3600
        hi = max(hi, math.ceil(now_h)) if self.ctl.running is not None else hi
        self.ribbon.set(segs, max(0.0, lo), min(24.0, hi), now_h)

    def _load_more(self) -> None:
        self.days_back += 14
        self._rebuild_list()

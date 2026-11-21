"""Mini timer: a small always-on-top window with the timer, what you are doing and START/STOP.

It shares state with the Tracker page: while the timer is stopped, what is typed here is the
Tracker's draft (and the other way round); while it runs, edits go to the running entry.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from .icons import filled_pixmap, hover_icon, timer_pixmap
from .pomodoro import ASK, BREAK, FOCUS
from .theme import C, CTRL_H
from .util import fmt_clock
from .widgets import ProjectPicker, label

MARGIN = 24        # default distance from the screen corner


def _repolish(widget: QWidget, name: str) -> None:
    if widget.objectName() != name:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class MiniTimer(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.ctl, self.db = ctl, ctl.db
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("SD Time")
        self.setWindowIcon(ctl.windowIcon())
        self.setFixedWidth(430)
        dpr = self.devicePixelRatioF()
        self._dpr = dpr

        self.dot = QLabel()
        self.dot.setFixedSize(18, 18)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc = QLineEdit(placeholderText="What are you working on?")
        self.desc.setObjectName("MiniInput")
        tracker = ctl.tracker
        completer = QCompleter(tracker._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated[str].connect(self._activity_chosen)
        self.desc.setCompleter(completer)
        self.time = QLabel("00:00:00")
        self.time.setObjectName("MiniTime")
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.start_btn = QToolButton()
        self.start_btn.setObjectName("MiniStart")
        self.start_btn.setFixedSize(CTRL_H, CTRL_H)
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle)

        self.picker = ProjectPicker(self.db, self)
        self.picker.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)   # never clipped
        self.status = label("", "Small")
        self.open_btn = self._icon_button("expand", "Open SD Time", ctl.show_window)
        self.close_btn = self._icon_button("close", "Hide the mini timer",
                                           lambda: ctl.set_mini_visible(False))

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.dot)
        top.addWidget(self.desc, 1)
        top.addWidget(self.time)
        top.addWidget(self.start_btn)
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        bottom.setContentsMargins(22, 0, 0, 0)    # under the description, past the dot
        bottom.addWidget(self.picker)
        bottom.addStretch(1)
        bottom.addWidget(self.status)
        bottom.addWidget(self.open_btn)
        bottom.addWidget(self.close_btn)

        card = QFrame()
        card.setObjectName("MiniCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 10, 8)
        cl.setSpacing(6)
        cl.addLayout(top)
        cl.addLayout(bottom)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        self.desc.textEdited.connect(self._desc_edited)
        self.desc.returnPressed.connect(self._desc_enter)
        self.desc.editingFinished.connect(self._desc_done)
        self.picker.changed.connect(self._picker_changed)
        self.setToolTip("Drag to move · right-click for options")

    def _icon_button(self, icon: str, tip: str, slot) -> QToolButton:
        b = QToolButton(toolTip=tip)
        b.setObjectName("Icon")
        b.setIcon(hover_icon(icon, self._dpr, 15))
        b.setIconSize(QSize(15, 15))
        b.setAutoRaise(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ------------------------------------------------------------ state
    def sync(self) -> None:
        """Data changed: show the running entry, or the Tracker's draft when stopped."""
        running = self.ctl.running
        if running is not None:
            if not self.desc.hasFocus():
                self.desc.setText(running["description"])
            self.picker.set_value(running["project_id"], running["task_id"])
            _repolish(self.start_btn, "MiniStop")
            self.start_btn.setIcon(QIcon(filled_pixmap("stop", "#ffffff", 16, self._dpr)))
            self.start_btn.setToolTip("Stop")
        else:
            project_id, task_id, desc = self.ctl.tracker.draft()
            if not self.desc.hasFocus():
                self.desc.setText(desc)
            self.picker.set_value(project_id, task_id)
            _repolish(self.start_btn, "MiniStart")
            self.start_btn.setIcon(QIcon(filled_pixmap("play", "#ffffff", 17, self._dpr)))
            self.start_btn.setToolTip("Start")
        if not self.desc.hasFocus():
            self.desc.setCursorPosition(0)       # long text: show its start, not its end
        self.tick()

    def tick(self) -> None:
        running = self.ctl.running
        pomo = self.ctl.pomo
        now = int(time.time())
        color = (running["project_color"] if running is not None else None) or C["accent_text"]
        if pomo.phase == FOCUS and running is not None:
            self.time.setText(fmt_clock(pomo.remaining(now)))
            # Short: the vegetable already says "focus"; the full label is in the tooltip.
            self.status.setText(f"break in {max(1, math.ceil(pomo.remaining(now) / 60))} min")
            self.status.setToolTip(pomo.label().replace("/", " of "))
        elif pomo.phase == BREAK and running is None:
            self.time.setText(fmt_clock(pomo.remaining(now)))
            self.status.setText("Break")
            color = C["muted"]
        elif pomo.phase == ASK:
            self.time.setText("00:00")
            self.status.setText("Focus done")
        elif running is not None:
            self.time.setText(fmt_clock(self.db.duration(running)))
            self.status.setText("")
        else:
            self.time.setText("00:00:00")
            self.status.setText("")
        self.time.setStyleSheet(f"color: {C['text'] if running is not None else C['faint']};")
        if self.ctl.pomodoro_enabled() and pomo.phase in (FOCUS, BREAK, ASK):
            self.dot.setPixmap(timer_pixmap(pomo.config.kind, 16, self._dpr))
        else:
            self.dot.setPixmap(filled_pixmap("dot", color if running is not None else "#4a4a4a",
                                             10, self._dpr))

    # ------------------------------------------------------------ actions
    def toggle(self) -> None:
        if self.ctl.running is not None:
            self._desc_done()
            self.ctl.stop()
        else:
            self.ctl.start(self.picker.project_id, self.picker.task_id, self.desc.text().strip())
        self.desc.clearFocus()

    def _desc_edited(self, text: str) -> None:
        if self.ctl.running is None:
            self.ctl.tracker.desc.setText(text)

    def _desc_enter(self) -> None:
        if self.ctl.running is None:
            self.toggle()
        else:
            self._desc_done()
            self.desc.clearFocus()

    def _desc_done(self) -> None:
        running = self.ctl.running
        if running is not None and self.desc.text().strip() != running["description"]:
            self.db.update_entry(running["id"], description=self.desc.text())
            self.ctl.notify()

    def _picker_changed(self, project_id, task_id) -> None:
        running = self.ctl.running
        if running is not None:
            self.db.update_entry(running["id"], project_id=project_id, task_id=task_id)
            self.ctl.notify()
        else:
            self.ctl.tracker.picker.set_value(project_id, task_id)

    def _activity_chosen(self, text: str) -> None:
        pt = self.ctl.tracker._activities.get(text)
        if pt is not None:
            self._picker_changed(*pt)
            self.picker.set_value(*pt)
        self._desc_edited(text)

    # ------------------------------------------------------------ window
    def default_pos(self) -> QPoint:
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        return QPoint(area.right() - self.width() - MARGIN, area.bottom() - self.height() - MARGIN)

    def place(self, pos: QPoint | None) -> None:
        """Move to pos if it is on a screen (monitors change), else to the default corner."""
        self.adjustSize()
        if pos is not None:
            for screen in QGuiApplication.screens():
                if screen.availableGeometry().contains(pos + QPoint(40, 20)):
                    self.move(pos)
                    return
        self.move(self.default_pos())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.windowHandle() is not None:
            self.windowHandle().startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.isVisible():
            self.ctl.settings.setValue("mini/pos", self.pos())

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("Open SD Time", self.ctl.show_window)
        menu.addAction("Add time…", lambda: self.ctl.new_entry())
        menu.addSeparator()
        reset = QAction("Move to the corner", menu)
        reset.triggered.connect(lambda: self.move(self.default_pos()))
        menu.addAction(reset)
        menu.addAction("Hide mini timer", lambda: self.ctl.set_mini_visible(False))
        menu.exec(event.globalPos())

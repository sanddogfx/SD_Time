"""Projects, Clients and Settings pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel,
    QSpinBox,
    QLineEdit, QMenu, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import __version__, autostart
from ..dialogs import ClientDialog, ProjectDialog
from ..icons import color_icon, tomato_pixmap
from ..theme import C
from ..util import fmt_clock, fmt_money, fmt_rate
from ..widgets import RateEdit, Stepper, bulk_fill, button, card, confirm, label, show_error

ROLE = Qt.ItemDataRole.UserRole


def make_table(headers: list[str], stretch_col: int = 0) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(42)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    t.setShowGrid(False)
    h = t.horizontalHeader()
    for i in range(len(headers)):
        h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i == stretch_col
                               else QHeaderView.ResizeMode.ResizeToContents)
    return t


def cell(text: str, align_right: bool = False, muted: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if muted:
        item.setForeground(QColor(C["muted"]))
    return item


# ================================================================== projects
class ProjectsPage(QWidget):
    title = "Projects"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db

        self.search = QLineEdit(placeholderText="Search by name")
        self.search.setFixedWidth(260)
        self.show_archived = QCheckBox("Show archived")
        top = QHBoxLayout()
        top.addWidget(label("Projects", "H1"))
        top.addStretch(1)
        top.addWidget(button("Create new project", self.create, "Primary"))

        bar = QHBoxLayout()
        bar.addWidget(self.search)
        bar.addWidget(self.show_archived)
        bar.addStretch(1)

        self.table = make_table(["Name", "Client", "Rate", "Tracked", "Amount", "Tasks", "Status"])
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.table.customContextMenuRequested.connect(self._menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(14)
        root.addLayout(top)
        root.addLayout(bar)
        root.addWidget(self.table, 1)
        root.addWidget(label("Double-click a project to edit it and its tasks. "
                             "Right-click for more actions.", "Small"))
        self.search.textChanged.connect(self.refresh)
        self.show_archived.toggled.connect(self.refresh)

    def refresh(self) -> None:
        query = self.search.text().strip().casefold()
        totals = self.db.totals_by_project()
        cur = self.db.currency
        default = self.db.default_rate
        rows = [p for p in self.db.projects(include_archived=self.show_archived.isChecked())
                if not query or query in p["name"].casefold()
                or query in (p["client_name"] or "").casefold()]
        task_counts = dict(self.db.conn.execute(
            "SELECT project_id, COUNT(*) FROM tasks WHERE archived = 0 GROUP BY project_id"))
        with bulk_fill(self.table):
            self._fill(rows, totals, task_counts, cur, default)

    def _fill(self, rows, totals, task_counts, cur, default) -> None:
        self.table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            name = cell(p["name"])
            name.setIcon(color_icon(p["color"], 10))
            name.setForeground(QColor(p["color"]))
            name.setData(ROLE, p["id"])
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, cell(p["client_name"] or "—", muted=not p["client_name"]))
            if p["rate"] is not None:
                rate = cell(fmt_rate(p["rate"], cur), True)
            elif p["client_rate"] is not None:
                rate = cell(f"{fmt_rate(p['client_rate'], cur)} (client)", True, muted=True)
            else:
                rate = cell(f"{fmt_rate(default, cur)} (default)" if default else "—", True,
                            muted=True)
            self.table.setItem(r, 2, rate)
            t = totals.get(p["id"], {"seconds": 0, "amount": 0.0})
            self.table.setItem(r, 3, cell(fmt_clock(t["seconds"]), True))
            self.table.setItem(r, 4, cell(fmt_money(t["amount"], cur) if t["amount"] else "—", True))
            self.table.setItem(r, 5, cell(str(task_counts.get(p["id"], 0)), True))
            self.table.setItem(r, 6, cell("Archived" if p["archived"] else "Active",
                                          muted=bool(p["archived"])))

    def _selected(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.db.get_project(self.table.item(row, 0).data(ROLE))

    def create(self) -> None:
        if ProjectDialog(self.db, self).exec():
            self.ctl.notify()

    def edit(self) -> None:
        p = self._selected()
        if p and ProjectDialog(self.db, self, project=p).exec():
            self.ctl.notify()

    def _menu(self, pos: QPoint) -> None:
        p = self._selected()
        if p is None:
            return
        menu = QMenu(self)
        menu.addAction("Edit…", self.edit)
        menu.addAction("Restore" if p["archived"] else "Archive", self.toggle_archive)
        menu.addSeparator()
        menu.addAction("Delete…", self.delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def toggle_archive(self) -> None:
        p = self._selected()
        if p:
            self.db.update_project(p["id"], archived=not p["archived"])
            self.ctl.notify()

    def delete(self) -> None:
        p = self._selected()
        if p is None:
            return
        n = self.db.count_entries(project_id=p["id"])
        text = f"Delete project “{p['name']}” and its tasks?"
        if n:
            text += f"\n\n{n} time entries will be kept without a project. " \
                    "Archive the project instead to keep them grouped."
        if confirm(self, "Delete project", text):
            self.db.delete_project(p["id"])
            self.ctl.notify()


# =================================================================== clients
class ClientsPage(QWidget):
    title = "Clients"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db

        self.new_name = QLineEdit(placeholderText="Add new client")
        self.new_rate = RateEdit(None, "Hourly rate (optional)")
        self.new_rate.setFixedWidth(180)
        add_btn = button("ADD", self.add, "Primary")
        self.new_name.returnPressed.connect(self.add)
        self.show_archived = QCheckBox("Show archived")

        add_card = card()
        al = QHBoxLayout(add_card)
        al.setContentsMargins(12, 10, 12, 10)
        al.addWidget(self.new_name, 1)
        al.addWidget(self.new_rate)
        al.addWidget(add_btn)

        self.table = make_table(["Name", "Rate", "Projects", "Tracked", "Amount", "Status"])
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.table.customContextMenuRequested.connect(self._menu)

        top = QHBoxLayout()
        top.addWidget(label("Clients", "H1"))
        top.addStretch(1)
        top.addWidget(self.show_archived)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(14)
        root.addLayout(top)
        root.addWidget(add_card)
        root.addWidget(self.table, 1)
        root.addWidget(label("A client's rate applies to all its projects unless a project or "
                             "task has its own rate.", "Small"))
        self.show_archived.toggled.connect(self.refresh)

    def refresh(self) -> None:
        totals = self.db.totals_by_project()
        cur = self.db.currency
        default = self.db.default_rate
        clients = self.db.clients(include_archived=self.show_archived.isChecked())
        with bulk_fill(self.table):
            self._fill(clients, totals, cur, default)

    def _fill(self, clients, totals, cur, default) -> None:
        self.table.setRowCount(len(clients))
        for r, c in enumerate(clients):
            name = cell(c["name"])
            name.setData(ROLE, c["id"])
            self.table.setItem(r, 0, name)
            if c["rate"] is not None:
                self.table.setItem(r, 1, cell(fmt_rate(c["rate"], cur), True))
            else:
                self.table.setItem(r, 1, cell(f"{fmt_rate(default, cur)} (default)"
                                              if default else "—", True, muted=True))
            projects = self.db.projects(c["id"], include_archived=True)
            seconds = sum(totals.get(p["id"], {}).get("seconds", 0) for p in projects)
            amount = sum(totals.get(p["id"], {}).get("amount", 0.0) for p in projects)
            self.table.setItem(r, 2, cell(str(len(projects)), True))
            self.table.setItem(r, 3, cell(fmt_clock(seconds), True))
            self.table.setItem(r, 4, cell(fmt_money(amount, cur) if amount else "—", True))
            self.table.setItem(r, 5, cell("Archived" if c["archived"] else "Active",
                                          muted=bool(c["archived"])))

    def add(self) -> None:
        try:
            self.db.add_client(self.new_name.text(), self.new_rate.value())
        except ValueError as exc:
            show_error(self, exc)
            return
        self.new_name.clear()
        self.new_rate.clear()
        self.ctl.notify()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.db.get_client(self.table.item(row, 0).data(ROLE))

    def edit(self) -> None:
        c = self._selected()
        if c and ClientDialog(self.db, self, client=c).exec():
            self.ctl.notify()

    def _menu(self, pos: QPoint) -> None:
        c = self._selected()
        if c is None:
            return
        menu = QMenu(self)
        menu.addAction("Edit…", self.edit)
        menu.addAction("Restore" if c["archived"] else "Archive", self.toggle_archive)
        menu.addSeparator()
        menu.addAction("Delete…", self.delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def toggle_archive(self) -> None:
        c = self._selected()
        if c:
            self.db.update_client(c["id"], archived=not c["archived"])
            self.ctl.notify()

    def delete(self) -> None:
        c = self._selected()
        if c is None:
            return
        n = len(self.db.projects(c["id"], include_archived=True))
        text = f"Delete client “{c['name']}”?"
        if n:
            text += f"\n\nIts {n} project(s) and their time will be kept, without a client."
        if confirm(self, "Delete client", text):
            self.db.delete_client(c["id"])
            self.ctl.notify()


# ================================================================== settings
class SettingsPage(QWidget):
    title = "Settings"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db

        self.currency = QLineEdit()
        self.currency.setMaxLength(8)
        self.currency.setFixedWidth(120)
        self.default_rate = RateEdit(None, "No default rate")
        self.default_rate.setFixedWidth(200)
        self.hotkey = QKeySequenceEdit()
        self.hotkey.setMaximumSequenceLength(1)
        self.hotkey.setFixedWidth(200)
        self.close_to_tray = QCheckBox("Closing the window keeps SD Time running in the tray")
        self.autostart = QCheckBox("Start SD Time when Windows starts (in the tray)")
        self.data_dir = label("", "Muted")
        self.data_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        box = card()
        form = QFormLayout(box)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(14)
        form.addRow("Currency", self.currency)
        form.addRow("Default hourly rate", self.default_rate)
        form.addRow("", label("Used when neither the task, project nor client has a rate.",
                              "Small"))
        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hotkey)
        hk_row.addWidget(button("Clear", self.hotkey.clear))
        hk_row.addStretch(1)
        form.addRow("Start/stop hotkey", hk_row)
        form.addRow("", label("Works from any app. Starts what is typed in the timer bar, "
                              "or continues the last entry.", "Small"))
        form.addRow("", self.close_to_tray)
        form.addRow("", self.autostart)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.data_dir)
        dir_row.addWidget(button("Open folder", self._open_dir))
        dir_row.addStretch(1)
        form.addRow("Data folder", dir_row)
        form.addRow("Version", label(f"SD Time {__version__}", "Muted"))

        # ---- Pomodoro
        self.pomo_focus = Stepper(1, 180, " min")
        self.pomo_short = Stepper(1, 60, " min")
        self.pomo_long = Stepper(1, 120, " min")
        self.pomo_every = Stepper(1, 12, " sessions")
        self.pomo_auto = QCheckBox("Start the next focus session automatically after a break")
        self.pomo_sound = QCheckBox("Play a sound when a focus session or break ends")
        pomo_box = card()
        pf = QFormLayout(pomo_box)
        pf.setContentsMargins(20, 20, 20, 20)
        pf.setSpacing(14)
        pomo_icon = label()
        pomo_icon.setPixmap(tomato_pixmap(26, self.devicePixelRatioF()))
        pomo_title = QHBoxLayout()
        pomo_title.setSpacing(8)
        pomo_title.addWidget(pomo_icon)
        pomo_title.addWidget(label("Pomodoro", "Big"))
        pomo_title.addStretch(1)
        pf.addRow(pomo_title)
        pf.addRow("Focus", self.pomo_focus)
        pf.addRow("Short break", self.pomo_short)
        pf.addRow("Long break", self.pomo_long)
        pf.addRow("Long break after", self.pomo_every)
        pf.addRow("", self.pomo_auto)
        pf.addRow("", self.pomo_sound)
        pf.addRow("", label("Turn it on with the tomato button next to START. Only focus time is "
                            "tracked; when it ends the entry stops and the break starts.", "Small"))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(14)
        root.addWidget(label("Settings", "H1"))
        cards = QHBoxLayout()
        cards.setSpacing(14)
        cards.addWidget(box, 3)
        cards.addWidget(pomo_box, 2)
        root.addLayout(cards)
        for hint in self.findChildren(QLabel, "Small"):
            hint.setWordWrap(True)
        save_row = QHBoxLayout()
        save_row.addWidget(button("Save", self.save, "Primary"))
        save_row.addStretch(1)
        root.addLayout(save_row)
        root.addStretch(1)

    def refresh(self) -> None:
        self.currency.setText(self.db.currency)
        rate = self.db.default_rate
        self.default_rate.setText("" if rate is None else f"{rate:g}")
        self.hotkey.setKeySequence(QKeySequence(self.ctl.hotkey_text()))
        self.close_to_tray.setChecked(self.ctl.settings.value("close_to_tray", True, type=bool))
        self.autostart.setChecked(autostart.is_enabled())
        self.data_dir.setText(str(Path(self.ctl.settings.fileName()).parent))
        cfg = self.ctl.pomodoro_config()
        self.pomo_focus.setValue(cfg.focus // 60)
        self.pomo_short.setValue(cfg.short_break // 60)
        self.pomo_long.setValue(cfg.long_break // 60)
        self.pomo_every.setValue(cfg.long_every)
        self.pomo_auto.setChecked(cfg.auto_next)
        self.pomo_sound.setChecked(cfg.sound)

    def _open_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.data_dir.text()))

    def save(self) -> None:
        try:
            rate = self.default_rate.value()
        except ValueError as exc:
            show_error(self, exc)
            return
        self.db.set_setting("currency", self.currency.text().strip() or "USD")
        self.db.set_setting("default_rate", rate)
        self.ctl.settings.setValue("close_to_tray", self.close_to_tray.isChecked())
        try:
            autostart.set_enabled(self.autostart.isChecked())
        except OSError as exc:
            show_error(self, f"Couldn't change autostart: {exc}")
        s = self.ctl.settings
        s.setValue("pomodoro/focus_min", self.pomo_focus.value())
        s.setValue("pomodoro/short_break_min", self.pomo_short.value())
        s.setValue("pomodoro/long_break_min", self.pomo_long.value())
        s.setValue("pomodoro/long_every", self.pomo_every.value())
        s.setValue("pomodoro/auto_next", self.pomo_auto.isChecked())
        s.setValue("pomodoro/sound", self.pomo_sound.isChecked())
        self.ctl.reload_pomodoro_config()
        hotkey = self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if self.ctl.set_hotkey(hotkey):
            self.ctl.toast("Settings saved")
        self.ctl.notify(origin=self)

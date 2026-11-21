"""Dialogs: time entry, client, project (with tasks)."""
from __future__ import annotations

import time

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .db import PALETTE, Database
from .icons import tomato_pixmap
from .widgets import ProjectPicker, RateEdit, button, confirm, label, show_error
from .util import fmt_hms, fmt_money, fmt_rate, parse_rate

ROLE = Qt.ItemDataRole.UserRole


def _buttons(dialog: QDialog, ok_text: str = "Save") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                           | QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


# ===================================================================== entry
class EntryDialog(QDialog):
    """Create or edit a time entry."""

    def __init__(self, db: Database, parent: QWidget | None = None, entry=None,
                 start_ts: int | None = None, end_ts: int | None = None,
                 project_id: int | None = None, task_id: int | None = None,
                 description: str = ""):
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.setWindowTitle("Edit time entry" if entry else "Add time entry")
        self.setMinimumWidth(460)

        now = int(time.time()) // 60 * 60
        if entry is not None:
            description = entry["description"]
            project_id, task_id = entry["project_id"], entry["task_id"]
            start_ts = entry["start_ts"]
            end_ts = entry["end_ts"] if entry["end_ts"] is not None else max(now, start_ts + 60)
        if start_ts is None:
            end_ts, start_ts = now, now - 3600
        if end_ts is None:
            end_ts = start_ts + 3600

        self.desc_edit = QLineEdit(description, placeholderText="What did you work on?")
        self.picker = ProjectPicker(db, self)
        self.picker.set_value(project_id, task_id)
        self.start_edit = QDateTimeEdit(QDateTime.fromSecsSinceEpoch(start_ts),
                                        calendarPopup=True, displayFormat="ddd, MMM d yyyy   HH:mm")
        self.end_edit = QDateTimeEdit(QDateTime.fromSecsSinceEpoch(end_ts),
                                      calendarPopup=True, displayFormat="ddd, MMM d yyyy   HH:mm")
        self.running_check = QCheckBox("Timer is still running")
        self.running_check.setChecked(entry is not None and entry["end_ts"] is None)
        self.running_check.setVisible(entry is not None and entry["end_ts"] is None)
        self.duration_edit = QLineEdit()
        self.duration_edit.setPlaceholderText("1:30")
        self.amount_label = label("", "Muted")

        form = QFormLayout(self)
        form.setSpacing(10)
        form.addRow("Description", self.desc_edit)
        form.addRow("Project", self.picker)
        form.addRow("Start", self.start_edit)
        form.addRow("End", self.end_edit)
        form.addRow("", self.running_check)
        form.addRow("Duration", self.duration_edit)
        form.addRow("Amount", self.amount_label)
        form.addRow(_buttons(self))

        self.start_edit.dateTimeChanged.connect(self._sync_duration)
        self.end_edit.dateTimeChanged.connect(self._sync_duration)
        self.running_check.toggled.connect(self._sync_duration)
        self.duration_edit.editingFinished.connect(self._duration_edited)
        self.picker.changed.connect(lambda *_: self._sync_duration())
        self._sync_duration()

    def _start(self) -> int:
        return self.start_edit.dateTime().toSecsSinceEpoch()

    def _end(self) -> int | None:
        if self.running_check.isVisible() and self.running_check.isChecked():
            return None
        return self.end_edit.dateTime().toSecsSinceEpoch()

    def _rate(self) -> float | None:
        if self.picker.task_id:
            rate = self.db.get_task(self.picker.task_id)["own_rate"]
        elif self.picker.project_id:
            rate = self.db.get_project(self.picker.project_id)["own_rate"]
        else:
            rate = None
        return rate if rate is not None else self.db.default_rate

    def _sync_duration(self) -> None:
        end = self._end()
        self.end_edit.setEnabled(end is not None)
        self.duration_edit.setEnabled(end is not None)
        seconds = (end if end is not None else int(time.time())) - self._start()
        self.duration_edit.setText(fmt_hms(seconds) if seconds > 0 else "")
        rate = self._rate()
        if rate and seconds > 0:
            self.amount_label.setText(
                f"{fmt_money(seconds / 3600 * rate, self.db.currency)}   "
                f"({fmt_rate(rate, self.db.currency)})")
        else:
            self.amount_label.setText("—")

    def _duration_edited(self) -> None:
        from .util import parse_duration
        try:
            seconds = parse_duration(self.duration_edit.text())
        except ValueError as exc:
            show_error(self, exc)
            return
        if seconds > 0:
            self.end_edit.setDateTime(QDateTime.fromSecsSinceEpoch(self._start() + seconds))

    def accept(self) -> None:
        end = self._end()
        if end is not None and end <= self._start():
            show_error(self, "End must be after start.")
            return
        if end is not None and end - self._start() > 16 * 3600:
            if not confirm(self, "SD Time", f"This entry is {fmt_hms(end - self._start())} long. "
                                            "Is that right?"):
                return
        super().accept()

    def values(self) -> dict:
        return {
            "description": self.desc_edit.text().strip(),
            "project_id": self.picker.project_id,
            "task_id": self.picker.task_id,
            "start_ts": self._start(),
            "end_ts": self._end(),
        }


# ==================================================================== client
class ClientDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None = None, client=None, name: str = ""):
        super().__init__(parent)
        self.db = db
        self.client = client
        self.client_id = client["id"] if client else None
        self.setWindowTitle("Edit client" if client else "New client")
        self.setMinimumWidth(380)

        self.name_edit = QLineEdit(client["name"] if client else name)
        default = db.default_rate
        self.rate_edit = RateEdit(client["rate"] if client else None,
                                  f"Default ({fmt_rate(default, db.currency)})")
        form = QFormLayout(self)
        form.addRow("Name", self.name_edit)
        form.addRow(f"Hourly rate, {db.currency}", self.rate_edit)
        form.addRow(_buttons(self, "Save" if client else "Create"))

    def accept(self) -> None:
        try:
            rate = self.rate_edit.value()
            if self.client_id:
                self.db.update_client(self.client_id, name=self.name_edit.text(), rate=rate)
            else:
                self.client_id = self.db.add_client(self.name_edit.text(), rate)
        except ValueError as exc:
            show_error(self, exc)
            return
        super().accept()


# =================================================================== project
class ProjectDialog(QDialog):
    """Project settings and its tasks. Task edits are applied on Save."""

    NEW_CLIENT = -1

    def __init__(self, db: Database, parent: QWidget | None = None, project=None,
                 name: str = "", client_id: int | None = None):
        super().__init__(parent)
        self.db = db
        self.project = project
        self.project_id = project["id"] if project else None
        self.setWindowTitle("Edit project" if project else "Create new project")
        self.setMinimumSize(520, 520)

        count = db.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        self.color = project["color"] if project else PALETTE[count % len(PALETTE)]

        self.name_edit = QLineEdit(project["name"] if project else name)
        self.client_combo = QComboBox()
        self._fill_clients(project["client_id"] if project else client_id)
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(60)
        self.color_btn.clicked.connect(self._pick_color)
        self._render_color()
        self.rate_edit = RateEdit(project["rate"] if project else None)

        self.tasks_table = QTableWidget(0, 3)
        self.tasks_table.setHorizontalHeaderLabels(["Task", f"Rate, {db.currency}/h", "Status"])
        self.tasks_table.verticalHeader().setVisible(False)
        header = self.tasks_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tasks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._deleted_tasks: list[int] = []
        if project:
            for t in db.tasks(project["id"], include_archived=True):
                self._add_task_row(t["name"], t["rate"], bool(t["archived"]), t["id"])
        self._update_rate_placeholder()

        form = QFormLayout()
        form.addRow("Project name", self.name_edit)
        form.addRow("Client", self.client_combo)
        form.addRow("Color", self.color_btn)
        form.addRow(f"Hourly rate, {db.currency}", self.rate_edit)

        task_buttons = QHBoxLayout()
        task_buttons.addWidget(button("Add task", self._new_task))
        task_buttons.addWidget(button("Archive / restore", self._toggle_task_archive))
        task_buttons.addWidget(button("Delete", self._delete_task))
        task_buttons.addStretch(1)

        hint = label("Leave rate empty to inherit it. Task rate → project rate → "
                     "client rate → default rate.", "Small")
        hint.setWordWrap(True)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addSpacing(8)
        root.addWidget(label("Tasks", "Big"))
        root.addWidget(self.tasks_table, 1)
        root.addLayout(task_buttons)
        root.addWidget(hint)
        root.addWidget(_buttons(self, "Save" if project else "Create"))

        self.client_combo.currentIndexChanged.connect(self._on_client_changed)
        self.rate_edit.textChanged.connect(lambda: self._refresh_task_placeholders())

    # client / color / rate
    def _fill_clients(self, select_id: int | None) -> None:
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("No client", None)
        for c in self.db.clients(include_archived=True):
            if c["archived"] and c["id"] != select_id:
                continue
            self.client_combo.addItem(c["name"], c["id"])
        self.client_combo.addItem("+ New client…", self.NEW_CLIENT)
        idx = self.client_combo.findData(select_id)
        self.client_combo.setCurrentIndex(max(0, idx))
        self._last_client = self.client_combo.currentData()
        self.client_combo.blockSignals(False)

    def _on_client_changed(self) -> None:
        if self.client_combo.currentData() == self.NEW_CLIENT:
            dlg = ClientDialog(self.db, self)
            self._fill_clients(dlg.client_id if dlg.exec() else self._last_client)
        self._last_client = self.client_combo.currentData()
        self._update_rate_placeholder()

    def _inherited_rate(self) -> float | None:
        cid = self.client_combo.currentData()
        if cid and cid != self.NEW_CLIENT:
            rate = self.db.get_client(cid)["rate"]
            if rate is not None:
                return rate
        return self.db.default_rate

    def _update_rate_placeholder(self) -> None:
        cid = self.client_combo.currentData()
        source = "client" if cid and cid != self.NEW_CLIENT and \
            self.db.get_client(cid)["rate"] is not None else "default"
        self.rate_edit.setPlaceholderText(
            f"Inherit from {source} ({fmt_rate(self._inherited_rate(), self.db.currency)})")
        self._refresh_task_placeholders()

    def _project_rate(self) -> float | None:
        try:
            own = parse_rate(self.rate_edit.text())
        except ValueError:
            own = None
        return own if own is not None else self._inherited_rate()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color), self, "Project color")
        if color.isValid():
            self.color = color.name()
            self._render_color()

    def _render_color(self) -> None:
        self.color_btn.setStyleSheet(f"background: {self.color}; border: none; min-height: 22px;")

    # tasks
    def _add_task_row(self, name: str, rate: float | None, archived: bool,
                      task_id: int | None) -> None:
        row = self.tasks_table.rowCount()
        self.tasks_table.insertRow(row)
        name_item = QTableWidgetItem(name)
        name_item.setData(ROLE, task_id)
        rate_item = QTableWidgetItem("" if rate is None else f"{rate:g}")
        status_item = QTableWidgetItem("Archived" if archived else "Active")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        status_item.setData(ROLE, archived)
        self.tasks_table.setItem(row, 0, name_item)
        self.tasks_table.setItem(row, 1, rate_item)
        self.tasks_table.setItem(row, 2, status_item)
        self._refresh_task_placeholders()

    def _refresh_task_placeholders(self) -> None:
        inherited = fmt_rate(self._project_rate(), "")
        self.tasks_table.setToolTip(f"Empty rate = project rate ({inherited})")

    def _new_task(self) -> None:
        name, ok = QInputDialog.getText(self, "New task", "Task name:")
        if ok and name.strip():
            self._add_task_row(name.strip(), None, False, None)

    def _toggle_task_archive(self) -> None:
        row = self.tasks_table.currentRow()
        if row < 0:
            return
        item = self.tasks_table.item(row, 2)
        archived = not item.data(ROLE)
        item.setData(ROLE, archived)
        item.setText("Archived" if archived else "Active")

    def _delete_task(self) -> None:
        row = self.tasks_table.currentRow()
        if row < 0:
            return
        task_id = self.tasks_table.item(row, 0).data(ROLE)
        if task_id:
            n = self.db.count_entries(task_id=task_id)
            if n and not confirm(self, "Delete task",
                                 f"{n} time entries use this task. They will be kept without "
                                 "a task. Delete it?"):
                return
            self._deleted_tasks.append(task_id)
        self.tasks_table.removeRow(row)

    def _collect_tasks(self) -> list[dict]:
        tasks, seen = [], set()
        for row in range(self.tasks_table.rowCount()):
            name = (self.tasks_table.item(row, 0).text() or "").strip()
            if not name:
                raise ValueError(f"Task in row {row + 1} has no name")
            if name.casefold() in seen:
                raise ValueError(f'Task "{name}" is listed twice')
            seen.add(name.casefold())
            rate_item = self.tasks_table.item(row, 1)
            tasks.append({
                "id": self.tasks_table.item(row, 0).data(ROLE),
                "name": name,
                "rate": parse_rate(rate_item.text() if rate_item else ""),
                "archived": bool(self.tasks_table.item(row, 2).data(ROLE)),
            })
        return tasks

    def accept(self) -> None:
        try:
            tasks = self._collect_tasks()
            rate = self.rate_edit.value()
            client_id = self.client_combo.currentData()
            if client_id == self.NEW_CLIENT:
                client_id = None
            if self.project_id:
                self.db.update_project(self.project_id, name=self.name_edit.text(),
                                       client_id=client_id, color=self.color, rate=rate)
            else:
                self.project_id = self.db.add_project(self.name_edit.text(), client_id,
                                                      self.color, rate)
            for task_id in self._deleted_tasks:
                self.db.delete_task(task_id)
            # Renamed tasks go through a temporary name first, so swapping two names
            # doesn't trip the uniqueness check. Unchanged names are left alone.
            existing = [t for t in tasks if t["id"]]
            current = {t["id"]: t["name"] for t in self.db.tasks(self.project_id, True)}
            renamed = [t for t in existing if current.get(t["id"]) != t["name"]]
            for t in renamed:
                self.db.update_task(t["id"], name=f"~renaming~{t['id']}")
            for t in existing:
                self.db.update_task(t["id"], name=t["name"], rate=t["rate"], archived=t["archived"])
            for t in tasks:
                if not t["id"]:
                    tid = self.db.add_task(self.project_id, t["name"], t["rate"])
                    if t["archived"]:
                        self.db.update_task(tid, archived=True)
        except ValueError as exc:
            show_error(self, exc)
            return
        super().accept()


# ================================================================= pomodoro
class PomodoroPrompt(QDialog):
    """Stays on top until answered. finished(code): PRIMARY, SECONDARY or DISMISSED (✕/Esc)."""

    DISMISSED, PRIMARY, SECONDARY = 0, 1, 2

    def __init__(self, parent: QWidget | None, title: str, text: str, primary: str,
                 secondary: str):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("SD Time · Pomodoro")
        self.setMinimumWidth(420)
        self.setModal(False)

        icon = label()
        icon.setPixmap(tomato_pixmap(48, self.devicePixelRatioF()))
        heading = label(title, "H1")
        body = label(text, "Muted")
        body.setWordWrap(True)
        primary_btn = button(primary, lambda: self.done(self.PRIMARY), "Primary")
        secondary_btn = button(secondary, lambda: self.done(self.SECONDARY))
        primary_btn.setDefault(True)

        text_col = QVBoxLayout()
        text_col.addWidget(heading)
        text_col.addWidget(body)
        top = QHBoxLayout()
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        top.addSpacing(8)
        top.addLayout(text_col, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(secondary_btn)
        buttons.addWidget(primary_btn)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(16)
        root.addLayout(top)
        root.addLayout(buttons)

    def present(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()


def ask_text(parent: QWidget, title: str, text: str, value: str = "") -> str | None:
    result, ok = QInputDialog.getText(parent, title, text, QLineEdit.EchoMode.Normal, value)
    result = result.strip()
    return result if ok and result else None

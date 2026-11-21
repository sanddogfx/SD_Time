"""Shared widgets: project picker, cards, small helpers."""
from __future__ import annotations

import html
from contextlib import contextmanager

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox, QSizePolicy, QSpinBox, QToolButton,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .db import NO_COLOR, Database
from .icons import color_icon, inline_icon_html
from .theme import C, CTRL_H
from .util import fmt_rate, parse_rate

ROLE = Qt.ItemDataRole.UserRole
ADD_TASK = Qt.ItemDataRole.UserRole + 2      # project id on a picker "+ Add task" row


def label(text: str = "", name: str | None = None) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    return w


def button(text: str, slot=None, name: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if slot is not None:
        b.clicked.connect(slot)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def nav_button(icon: str, tip: str, slot, dpr: float) -> QToolButton:
    """Square icon button (prev / next) the same height as the text buttons beside it."""
    from .icons import hover_icon
    b = QToolButton()
    b.setObjectName("Nav")
    b.setFixedSize(CTRL_H, CTRL_H)
    b.setIcon(hover_icon(icon, dpr, 16, normal="#c9c9c9"))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(slot)
    return b


def header_pill(text: str = "") -> QLabel:
    """Read-only figure in a page header (e.g. week total), sized like a control."""
    w = QLabel(text)
    w.setObjectName("HeaderPill")
    w.setFixedHeight(CTRL_H)
    w.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return w


def clear_layout(lay) -> None:
    """Empty a layout. Widgets are hidden at once: deleteLater alone leaves them painted
    (at a stale geometry, over their neighbours) until the event loop gets to them."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.deleteLater()


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def show_error(parent: QWidget, exc: Exception | str) -> None:
    QMessageBox.warning(parent, "SD Time", str(exc))


def confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a toward b by t (0 = a, 1 = b)."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def chip_colors(color: str | None) -> tuple[str, str]:
    """Tinted pill for a project: (background, text) — the project's hue, readable on cards."""
    color = color or NO_COLOR
    return mix(color, C["card"], 0.80), mix(color, "#ffffff", 0.45)


def chip_label(text: str, color: str | None, size_pt: float = 9.5) -> QLabel:
    bg, fg = chip_colors(color)
    w = QLabel(text)
    w.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 4px; padding: 4px 10px; "
                    f"font-size: {size_pt}pt;")
    w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)   # never squeezed into overlap
    return w


def project_html(project: str | None, color: str | None, task: str | None = None,
                 client: str | None = None, empty: str = "No project") -> str:
    if not project:
        return f'<span style="color:{C["muted"]}">{html.escape(empty)}</span>'
    out = f'<span style="color:{color or NO_COLOR}">●&nbsp;{html.escape(project)}</span>'
    if task:
        out += f'<span style="color:{C["text"]}">: {html.escape(task)}</span>'
    if client:
        out += f'<span style="color:{C["muted"]}">&nbsp;-&nbsp;{html.escape(client)}</span>'
    return out


def entry_html(e, empty: str = "No project") -> str:
    return project_html(e["project_name"], e["project_color"], e["task_name"],
                        e["client_name"], empty)


class RateEdit(QLineEdit):
    """Hourly rate input. Empty = inherit (placeholder shows what is inherited)."""

    def __init__(self, rate: float | None = None, inherited: str = "", parent=None):
        super().__init__(parent)
        if rate is not None:
            self.setText(f"{rate:g}")
        self.setPlaceholderText(inherited)

    def value(self) -> float | None:
        return parse_rate(self.text())


# ----------------------------------------------------------- project picker
class ProjectPopup(QFrame):
    """Searchable list: clients -> projects -> tasks. Emits chosen(project_id, task_id)."""

    chosen = Signal(object, object)

    def __init__(self, db: Database, parent: QWidget | None = None, allow_none: bool = True):
        super().__init__(parent, Qt.WindowType.Popup)
        self.db = db
        self.allow_none = allow_none
        self.setObjectName("Popup")
        self.setMinimumSize(360, 380)

        self.search = QLineEdit(placeholderText="Search project or task")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.itemActivated.connect(self._on_click)
        create_btn = button("+  New project", lambda: self._create_project(), "Link")
        create_btn.setToolTip("Create a project and pick it")
        client_btn = button("+  New client", self._create_client, "Link")
        client_btn.setToolTip("Create a client, then its first project")
        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(create_btn)
        actions.addWidget(client_btn)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)

        self.search.textChanged.connect(self._fill)
        self.search.returnPressed.connect(self._choose_best)
        self._fill()
        self.search.setFocus()

    def _choose_best(self) -> None:
        """Enter in the search box picks the first item whose own name matches."""
        query = self.search.text().strip().casefold()
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        first = None
        while stack:
            item = stack.pop(0)
            if item.data(0, ROLE) is not None:
                first = first or item
                if query and query in item.text(0).casefold():
                    self._on_click(item)
                    return
            stack[0:0] = [item.child(i) for i in range(item.childCount())]
        if first is not None:
            self._on_click(first)

    def _fill(self) -> None:
        self._fill_tree(create_mode=False)
        if self.search.text().strip() and self.tree.topLevelItemCount() == 0:
            # Nothing matches: the text is probably a new task. Offer it in every project.
            self._fill_tree(create_mode=True)

    def _fill_tree(self, create_mode: bool) -> None:
        query = self.search.text().strip().casefold()
        self.tree.clear()
        if self.allow_none and not query:
            none_item = QTreeWidgetItem(["No project"])
            none_item.setForeground(0, QColor(C["muted"]))
            none_item.setData(0, ROLE, (None, None))
            self.tree.addTopLevelItem(none_item)

        groups: dict = {}
        for p in self.db.projects():
            groups.setdefault((p["client_name"] or "", p["client_id"]), []).append(p)
        bold_font = self.tree.font()
        bold_font.setBold(True)
        for (client_name, _), projects in sorted(groups.items(), key=lambda kv: (kv[0][0] == "",
                                                                                kv[0][0].lower())):
            header = QTreeWidgetItem([(client_name or "Without client").upper()])
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setForeground(0, QColor(C["muted"]))
            added = False
            for p in projects:
                tasks = self.db.tasks(p["id"])
                p_match = (not query or query in p["name"].casefold()
                           or query in client_name.casefold())
                t_matches = [t for t in tasks if p_match or query in t["name"].casefold()]
                if not p_match and not t_matches and not create_mode:
                    continue
                item = QTreeWidgetItem([p["name"]])
                item.setIcon(0, color_icon(p["color"], 10))
                item.setForeground(0, QColor(p["color"]))
                item.setData(0, ROLE, (p["id"], None))
                for t in t_matches:
                    child = QTreeWidgetItem([t["name"]])
                    child.setData(0, ROLE, (p["id"], t["id"]))
                    item.addChild(child)
                # "Add task" row. When the search text is not the project's / client's name and
                # not an existing task here, the row creates that task at once
                # ("+ Add task “Edit”"); otherwise it opens the task window.
                raw = self.search.text().strip()
                quick = raw if raw and query not in p["name"].casefold() \
                    and query not in client_name.casefold() else ""
                if not any(t["name"].casefold() == query for t in tasks):
                    add = QTreeWidgetItem([f"+  Add task “{quick}”" if quick else "+  Add task"])
                    add.setData(0, ADD_TASK, (p["id"], quick))
                    add.setForeground(0, QColor(C["accent_text"]))
                    add.setToolTip(0, f"New task in {p['name']}")
                    item.addChild(add)
                header.addChild(item)
                added = True
            if added:
                self.tree.addTopLevelItem(header)
                header.setExpanded(True)
                if query:      # expanding only works once the item is in the tree
                    for i in range(header.childCount()):
                        header.child(i).setExpanded(True)

    def _on_click(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        add = item.data(0, ADD_TASK)
        if add is not None:
            self._add_task(*add)
            return
        value = item.data(0, ROLE)
        if value is None:
            return
        self.chosen.emit(*value)
        self.close()

    def _add_task(self, project_id: int, name: str = "") -> None:
        from .dialogs import TaskDialog
        if name:
            try:
                task_id = self.db.add_task(project_id, name)
            except ValueError as exc:
                show_error(self, exc)
                return
        else:
            self.hide()
            dlg = TaskDialog(self.db, project_id, self.parentWidget())
            task_id = dlg.task_id if dlg.exec() else None
        if task_id:
            self.chosen.emit(project_id, task_id)
        self.close()

    def _create_project(self, client_id: int | None = None) -> None:
        from .dialogs import ProjectDialog
        self.hide()
        dlg = ProjectDialog(self.db, self.parentWidget(), name=self.search.text().strip(),
                            client_id=client_id)
        if dlg.exec() and dlg.project_id:
            self.chosen.emit(dlg.project_id, None)
        self.close()

    def _create_client(self) -> None:
        """New client, then straight on to its first project (time is logged on projects)."""
        from .dialogs import ClientDialog, ProjectDialog
        self.hide()
        dlg = ClientDialog(self.db, self.parentWidget(), name=self.search.text().strip())
        if dlg.exec() and dlg.client_id:
            pdlg = ProjectDialog(self.db, self.parentWidget(), client_id=dlg.client_id)
            if pdlg.exec() and pdlg.project_id:
                self.chosen.emit(pdlg.project_id, None)
        self.close()


class ProjectPicker(QLabel):
    """Clickable "● Project: Task - Client" label that opens ProjectPopup."""

    changed = Signal(object, object)

    def __init__(self, db: Database, parent: QWidget | None = None,
                 placeholder: str = "Project", allow_none: bool = True):
        super().__init__(parent)
        self.db = db
        self.placeholder = placeholder
        self.allow_none = allow_none
        self.project_id: int | None = None
        self.task_id: int | None = None
        self.setObjectName("Picker")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTextFormat(Qt.TextFormat.RichText)
        self._render()

    def set_value(self, project_id: int | None, task_id: int | None) -> None:
        self.project_id, self.task_id = project_id, task_id
        self._render()

    def set_entry(self, e) -> None:
        """Show an entry row's project without extra queries (used for every list row)."""
        self.project_id, self.task_id = e["project_id"], e["task_id"]
        if not e["project_id"]:
            self._show(None, None, None, None, None)
        else:
            self._show(e["project_name"], e["project_color"], e["task_name"], e["client_name"],
                       e["own_rate"])

    def _render(self) -> None:
        p = self.db.get_project(self.project_id) if self.project_id else None
        t = self.db.get_task(self.task_id) if self.task_id else None
        if p is None:
            self._show(None, None, None, None, None)
        else:
            self._show(p["name"], p["color"], t["name"] if t else None, p["client_name"],
                       t["own_rate"] if t else p["own_rate"])

    def _show(self, project, color, task, client, rate) -> None:
        if project is None:
            icon = inline_icon_html("plus", C["accent_text"], 15, self.devicePixelRatioF())
            self.setText(f'{icon}&nbsp;<span style="color:{C["accent_text"]}">'
                         f'{html.escape(self.placeholder)}</span>')
            self.setStyleSheet("QLabel#Picker { background: transparent; }"
                               f"QLabel#Picker:hover {{ background: {C['raised']}; }}")
            self.setToolTip("Choose project")
            return
        # A tinted pill in the project's colour: "Project · Task"; client and rate in the tooltip.
        bg, fg = chip_colors(color)
        text = html.escape(project) + (f" · {html.escape(task)}" if task else "")
        self.setText(f'<span style="color:{fg}">{text}</span>')
        self.setStyleSheet(f"QLabel#Picker {{ background: {bg}; }}"
                           f"QLabel#Picker:hover {{ background: {mix(color or NO_COLOR, C['card'], 0.65)}; }}")
        if rate is None:
            rate = self.db.default_rate
        self.setToolTip(" · ".join(x for x in (client, f"Rate: {fmt_rate(rate, self.db.currency)}") if x))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_popup()

    def open_popup(self) -> None:
        popup = ProjectPopup(self.db, self.window(), self.allow_none)
        popup.chosen.connect(self._on_chosen)
        pos = self.mapToGlobal(QPoint(0, self.height() + 2))
        screen = self.screen().availableGeometry()
        if pos.x() + popup.minimumWidth() > screen.right():
            pos.setX(screen.right() - popup.minimumWidth())
        if pos.y() + popup.minimumHeight() > screen.bottom():
            pos.setY(self.mapToGlobal(QPoint(0, 0)).y() - popup.minimumHeight() - 2)
        popup.move(pos)
        popup.show()

    def _on_chosen(self, project_id, task_id) -> None:
        self.set_value(project_id, task_id)
        self.changed.emit(project_id, task_id)


class Stepper(QWidget):
    """[−] value [+] — a spin box with big, obvious step buttons instead of tiny arrows.
    Typing and the mouse wheel still work on the value."""

    def __init__(self, lo: int, hi: int, suffix: str = "", width: int = 110, parent=None):
        super().__init__(parent)
        self.spin = QSpinBox()
        self.spin.setObjectName("StepValue")
        self.spin.setRange(lo, hi)
        self.spin.setSuffix(suffix)
        # Qt bug: a stylesheet-styled QSpinBox with NoButtons collapses its text field to
        # 1 px. So the arrows stay on and are hidden by the theme (#StepValue buttons: width 0).
        self.spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setFixedWidth(width)
        self.minus = QToolButton(text="−")
        self.plus = QToolButton(text="+")
        for b, step in ((self.minus, -1), (self.plus, 1)):
            b.setObjectName("Step")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoRepeat(True)           # hold to keep stepping
            b.setAutoRepeatDelay(350)
            b.setAutoRepeatInterval(60)
            b.clicked.connect(lambda _=False, s=step: self._step(s))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.minus)
        lay.addWidget(self.spin)
        lay.addWidget(self.plus)
        lay.addStretch(1)
        self.spin.valueChanged.connect(self._update_buttons)
        self._update_buttons()

    def _step(self, steps: int) -> None:
        self.spin.stepBy(steps)
        self.spin.lineEdit().deselect()   # stepBy selects the number; don't leave it highlighted

    def _update_buttons(self) -> None:
        self.minus.setEnabled(self.spin.value() > self.spin.minimum())
        self.plus.setEnabled(self.spin.value() < self.spin.maximum())

    def value(self) -> int:
        return self.spin.value()

    def setValue(self, value: int) -> None:
        self.spin.setValue(value)


@contextmanager
def bulk_fill(table):
    """Fill a QTableWidget fast. With ResizeToContents columns Qt re-measures every row
    after each setItem (quadratic); switch that off while filling, measure once at the end."""
    header = table.horizontalHeader()
    modes = [header.sectionResizeMode(i) for i in range(header.count())]
    table.setUpdatesEnabled(False)
    table.blockSignals(True)
    for i, mode in enumerate(modes):
        if mode == QHeaderView.ResizeMode.ResizeToContents:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
    try:
        yield table
    finally:
        for i, mode in enumerate(modes):
            header.setSectionResizeMode(i, mode)
        table.blockSignals(False)
        table.setUpdatesEnabled(True)


def segmented(options: list[tuple[str, str]], current: str, on_change) -> QFrame:
    """Pill-shaped segmented control: [Day | Week | Month]. on_change(key) on click."""
    frame = QFrame()
    frame.setObjectName("SegGroup")
    frame.setFixedHeight(CTRL_H)
    lay = QHBoxLayout(frame)
    lay.setContentsMargins(4, 4, 4, 4)
    lay.setSpacing(2)
    frame.buttons = {}
    for key, text in options:
        b = QPushButton(text)
        b.setObjectName("Seg")
        b.setFixedHeight(CTRL_H - 8)
        b.setCheckable(True)
        b.setAutoExclusive(True)
        b.setChecked(key == current)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=key: on_change(k))
        lay.addWidget(b)
        frame.buttons[key] = b
    return frame


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C['header']};")
    return f


def vsep() -> QFrame:
    f = QFrame()
    f.setFixedWidth(1)
    f.setStyleSheet(f"background: {C['border']};")
    return f


def hbox(*widgets, margins=(0, 0, 0, 0), spacing=8) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def cursor_pos() -> QPoint:
    return QCursor.pos()

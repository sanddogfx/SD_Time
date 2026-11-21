"""Projects, Clients and Settings pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel,
    QSpinBox,
    QLineEdit, QMenu, QScrollArea, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import __version__, autostart
from ..dialogs import ClientDialog, ProjectDialog, TaskDialog
from ..icons import color_icon, timer_pixmap
from ..theme import C
from ..util import fmt_clock, fmt_money, fmt_rate
from ..pomodoro import KINDS
from ..updates import RELEASES_URL, REPO_URL
from ..widgets import (RateEdit, Stepper, bulk_fill, button, card, confirm, label,
                       segmented, show_error)

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
    h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
KIND = Qt.ItemDataRole.UserRole + 1          # "project" | "task" | "add"
COLS = ["Name", "Client", "Rate", "Tracked", "Amount", "Status"]


class ProjectsPage(QWidget):
    """Projects with their tasks underneath. A project expands to show its tasks and an
    "Add task" row; double-click edits, right-click has the rest."""
    title = "Projects"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self._collapsed: set[int] = set()     # projects the user folded; others start open

        self.search = QLineEdit(placeholderText="Search projects, clients, tasks")
        self.search.setFixedWidth(300)
        self.show_archived = QCheckBox("Show archived")
        top = QHBoxLayout()
        top.addWidget(label("Projects", "H1"))
        top.addStretch(1)
        top.addWidget(button("Create new project", self.create, "Primary"))

        bar = QHBoxLayout()
        bar.addWidget(self.search)
        bar.addWidget(self.show_archived)
        bar.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setObjectName("ProjectTree")
        self.tree.setColumnCount(len(COLS))
        self.tree.setHeaderLabels(COLS)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(22)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h = self.tree.header()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(COLS)):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        for i in (3, 4):
            self.tree.headerItem().setTextAlignment(i, Qt.AlignmentFlag.AlignRight
                                                    | Qt.AlignmentFlag.AlignVCenter)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemCollapsed.connect(lambda it: self._collapsed.add(it.data(0, ROLE)))
        self.tree.itemExpanded.connect(lambda it: self._collapsed.discard(it.data(0, ROLE)))
        self.tree.customContextMenuRequested.connect(self._menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(14)
        root.addLayout(top)
        root.addLayout(bar)
        root.addWidget(self.tree, 1)
        root.addWidget(label("Each project holds its tasks. Double-click a project or task to edit it, "
                             "right-click for more.", "Small"))
        self.search.textChanged.connect(self.refresh)
        self.show_archived.toggled.connect(self.refresh)

    # ------------------------------------------------------------ fill
    def refresh(self) -> None:
        query = self.search.text().strip().casefold()
        archived = self.show_archived.isChecked()
        cur, default = self.db.currency, self.db.default_rate
        totals = self.db.totals_by_project()
        task_totals = self.db.totals_by_task()
        tasks_by_project: dict[int, list] = {}
        for row in self.db.conn.execute(
                "SELECT * FROM tasks" + ("" if archived else " WHERE archived = 0")
                + " ORDER BY archived, name COLLATE NOCASE"):
            tasks_by_project.setdefault(row["project_id"], []).append(row)

        selected = self._selected_key()
        scroll = self.tree.verticalScrollBar().value()
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        for p in self.db.projects(include_archived=archived):
            tasks = tasks_by_project.get(p["id"], [])
            own_match = not query or query in p["name"].casefold() \
                or query in (p["client_name"] or "").casefold()
            if not own_match:
                tasks = [t for t in tasks if query in t["name"].casefold()]
                if not tasks:
                    continue
            item = self._project_item(p, totals, cur, default)
            self.tree.addTopLevelItem(item)
            inherited = p["rate"] if p["rate"] is not None else p["client_rate"]
            for t in tasks:
                item.addChild(self._task_item(t, p, inherited, task_totals, cur, default))
            if not p["archived"]:
                add = QTreeWidgetItem(["+  Add task"])
                add.setData(0, KIND, "add")
                add.setData(0, ROLE, p["id"])
                add.setForeground(0, QColor(C["accent_text"]))
                add.setToolTip(0, f"Add a task to {p['name']}")
                item.addChild(add)
            item.setExpanded(bool(query) or p["id"] not in self._collapsed)
            if selected == ("project", p["id"]):
                self.tree.setCurrentItem(item)
            for i in range(item.childCount()):
                ch = item.child(i)
                if selected == (ch.data(0, KIND), ch.data(0, ROLE)) and ch.data(0, KIND) == "task":
                    self.tree.setCurrentItem(ch)
        self.tree.setUpdatesEnabled(True)
        self.tree.verticalScrollBar().setValue(scroll)

    def _project_item(self, p, totals, cur, default) -> QTreeWidgetItem:
        if p["rate"] is not None:
            rate, rate_muted = fmt_rate(p["rate"], cur), False
        elif p["client_rate"] is not None:
            rate, rate_muted = f"{fmt_rate(p['client_rate'], cur)} (client)", True
        else:
            rate, rate_muted = (f"{fmt_rate(default, cur)} (default)" if default else "—"), True
        tot = totals.get(p["id"], {"seconds": 0, "amount": 0.0})
        item = QTreeWidgetItem([p["name"], p["client_name"] or "—", rate, fmt_clock(tot["seconds"]),
                                fmt_money(tot["amount"], cur) if tot["amount"] else "—",
                                "Archived" if p["archived"] else "Active"])
        item.setData(0, KIND, "project")
        item.setData(0, ROLE, p["id"])
        item.setIcon(0, color_icon(p["color"], 10))
        item.setForeground(0, QColor(p["color"]))
        f = item.font(0)
        f.setWeight(QFont.Weight.DemiBold)
        item.setFont(0, f)
        muted = QColor(C["muted"])
        if not p["client_name"]:
            item.setForeground(1, muted)
        if rate_muted:
            item.setForeground(2, muted)
        if p["archived"]:
            item.setForeground(5, muted)
        for i in (3, 4):
            item.setTextAlignment(i, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _task_item(self, t, p, inherited, task_totals, cur, default) -> QTreeWidgetItem:
        if t["rate"] is not None:
            rate, rate_muted = fmt_rate(t["rate"], cur), False
        else:
            base = inherited if inherited is not None else default
            rate, rate_muted = (fmt_rate(base, cur) if base else "—"), True
        tot = task_totals.get(t["id"], {"seconds": 0, "amount": 0.0})
        item = QTreeWidgetItem([t["name"], "", rate, fmt_clock(tot["seconds"]) if tot["seconds"] else "—",
                                fmt_money(tot["amount"], cur) if tot["amount"] else "—",
                                "Archived" if t["archived"] else ""])
        item.setData(0, KIND, "task")
        item.setData(0, ROLE, t["id"])
        muted = QColor(C["muted"])
        if t["archived"]:
            for i in range(len(COLS)):
                item.setForeground(i, QColor(C["faint"]))
        else:
            if rate_muted:
                item.setForeground(2, muted)
            if not tot["seconds"]:
                item.setForeground(3, muted)
                item.setForeground(4, muted)
        if rate_muted:
            item.setToolTip(2, "Inherited from the project / client. Edit the task to set its own rate.")
        for i in (3, 4):
            item.setTextAlignment(i, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    # ------------------------------------------------------------ selection
    def _selected_key(self):
        it = self.tree.currentItem()
        return (it.data(0, KIND), it.data(0, ROLE)) if it else None

    def _project_of(self, it) -> int | None:
        if it is None:
            return None
        if it.data(0, KIND) == "project":
            return it.data(0, ROLE)
        return it.parent().data(0, ROLE) if it.parent() else None

    def _selected(self):
        """The selected project (also when a task row is selected)."""
        pid = self._project_of(self.tree.currentItem())
        return self.db.get_project(pid) if pid else None

    def _clicked(self, it, _col) -> None:
        if it.data(0, KIND) == "add":
            self.add_task(it.data(0, ROLE))

    def _double_clicked(self, it, _col) -> None:
        kind = it.data(0, KIND)
        if kind == "task":
            self.edit_task(it.data(0, ROLE))
        elif kind == "project":
            self.edit()

    # ------------------------------------------------------------ projects
    def create(self) -> None:
        if ProjectDialog(self.db, self).exec():
            self.ctl.notify()

    def edit(self) -> None:
        p = self._selected()
        if p and ProjectDialog(self.db, self, project=p).exec():
            self.ctl.notify()

    def _menu(self, pos: QPoint) -> None:
        it = self.tree.itemAt(pos)
        if it is None:
            return
        self.tree.setCurrentItem(it)
        menu = QMenu(self)
        if it.data(0, KIND) == "task":
            task = self.db.get_task(it.data(0, ROLE))
            menu.addAction("Edit task…", lambda: self.edit_task(task["id"]))
            menu.addAction("Restore task" if task["archived"] else "Archive task",
                           lambda: self.toggle_task_archive(task["id"]))
            menu.addSeparator()
            menu.addAction("Delete task…", lambda: self.delete_task(task["id"]))
        else:
            p = self._selected()
            if p is None:
                return
            if not p["archived"]:
                menu.addAction("Add task…", lambda: self.add_task(p["id"]))
            menu.addAction("Edit project…", self.edit)
            menu.addAction("Restore" if p["archived"] else "Archive", self.toggle_archive)
            menu.addSeparator()
            menu.addAction("Delete project…", self.delete)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

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

    # ------------------------------------------------------------ tasks
    def add_task(self, project_id: int) -> None:
        self._collapsed.discard(project_id)
        if TaskDialog(self.db, project_id, self).exec():
            self.ctl.notify()

    def edit_task(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task and TaskDialog(self.db, task["project_id"], self, task=task).exec():
            self.ctl.notify()

    def toggle_task_archive(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task:
            self.db.update_task(task_id, archived=not task["archived"])
            self.ctl.notify()

    def delete_task(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            return
        n = self.db.count_entries(task_id=task_id)
        text = f"Delete task “{task['name']}”?"
        if n:
            text += f"\n\n{n} time entries will stay in {task['project_name']} without a task. " \
                    "Archive the task instead to keep them grouped."
        if confirm(self, "Delete task", text):
            self.db.delete_task(task_id)
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
        root.setContentsMargins(30, 26, 30, 20)
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
        self.mini_hotkey = QKeySequenceEdit()
        self.mini_hotkey.setMaximumSequenceLength(1)
        self.mini_hotkey.setFixedWidth(200)
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
        mk_row = QHBoxLayout()
        mk_row.addWidget(self.mini_hotkey)
        mk_row.addWidget(button("Clear", self.mini_hotkey.clear))
        mk_row.addStretch(1)
        form.addRow("Mini timer hotkey", mk_row)
        form.addRow("", label("Shows or hides the small always-on-top timer. It also opens from "
                              "the tray menu and the button next to Add time.", "Small"))
        form.addRow("", self.close_to_tray)
        form.addRow("", self.autostart)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.data_dir)
        dir_row.addWidget(button("Open folder", self._open_dir))
        dir_row.addStretch(1)
        form.addRow("Data folder", dir_row)

        # ---- Pomodoro
        self.pomo_focus = Stepper(1, 180, " min")
        self.pomo_short = Stepper(1, 60, " min")
        self.pomo_long = Stepper(1, 120, " min")
        self.pomo_every = Stepper(1, 12, " sessions")
        # Which timer START uses; each kind keeps its own lengths (edited here, saved on Save).
        self._lengths: dict[str, dict[str, int]] = {}
        self._kind = "tomato"
        self.kind_seg = segmented([(k.key, k.name) for k in KINDS.values()], self._kind, self._set_kind)
        dpr = self.devicePixelRatioF()
        for key, b in self.kind_seg.buttons.items():
            b.setIcon(QIcon(timer_pixmap(key, 18, dpr)))
            b.setIconSize(QSize(18, 18))
        self.kind_blurb = label("", "Small")
        self.pomo_icon = label()
        self.pomo_auto = QCheckBox("Start the next focus session automatically after a break")
        self.pomo_sound = QCheckBox("Play a sound when a focus session or break ends")
        pomo_box = card()
        pf = QFormLayout(pomo_box)
        pf.setContentsMargins(20, 20, 20, 20)
        pf.setSpacing(14)
        pomo_title = QHBoxLayout()
        pomo_title.setSpacing(8)
        pomo_title.addWidget(self.pomo_icon)
        pomo_title.addWidget(label("Focus timer", "Big"))
        pomo_title.addStretch(1)
        pf.addRow(pomo_title)
        pf.addRow("Timer", self.kind_seg)
        pf.addRow("", self.kind_blurb)
        pf.addRow("Focus", self.pomo_focus)
        pf.addRow("Short break", self.pomo_short)
        pf.addRow("Long break", self.pomo_long)
        pf.addRow("Long break after", self.pomo_every)
        pf.addRow("", self.pomo_auto)
        pf.addRow("", self.pomo_sound)
        pf.addRow("", label("The selected timer is the one START uses; each keeps its own lengths. "
                            "Turn it on or switch it with the chip above the ring on the Tracker. "
                            "Only focus time is tracked; when it ends the entry stops and the break "
                            "starts.", "Small"))

        # ---- About: version, GitHub, updates
        about_box = card()
        al = QVBoxLayout(about_box)
        al.setContentsMargins(20, 20, 20, 20)
        al.setSpacing(10)
        about_title = QHBoxLayout()
        about_title.addWidget(label("About", "Big"))
        about_title.addStretch(1)
        about_title.addWidget(label(f"SD Time {__version__}", "Muted"))
        al.addLayout(about_title)
        links = QHBoxLayout()
        links.setSpacing(4)
        for text, url in (("GitHub page", REPO_URL), ("Releases", RELEASES_URL),
                          ("Report a problem", f"{REPO_URL}/issues")):
            links.addWidget(button(text, lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)), "Link"))
        links.addStretch(1)
        al.addLayout(links)
        upd_row = QHBoxLayout()
        self.check_btn = button("Check for updates", lambda: self.ctl.check_updates(manual=True))
        self.download_btn = button("Download", lambda: self.ctl.open_update_page(), "Primary")
        self.download_btn.hide()
        self.update_status = label("", "Muted")
        self.update_status.setWordWrap(True)
        upd_row.addWidget(self.check_btn)
        upd_row.addWidget(self.download_btn)
        upd_row.addWidget(self.update_status, 1)
        al.addLayout(upd_row)
        self.auto_updates = QCheckBox("Check for updates automatically (once a day)")
        al.addWidget(self.auto_updates)
        al.addWidget(label("Only asks GitHub for the number of the latest version. Nothing about you "
                           "or your time data is sent. Updates are never installed on their own: "
                           "you download the new installer from the release page.", "Small"))

        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(pomo_box)
        right.addStretch(1)

        # The page scrolls when the window is short (two tall cards side by side).
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(30, 26, 30, 20)
        inner.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(label("Settings", "H1"))
        head.addStretch(1)
        head.addWidget(button("Save", self.save, "Primary"))    # in view however long the page is
        inner.addLayout(head)
        cards = QHBoxLayout()
        cards.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(box)
        left.addWidget(about_box)
        left.addStretch(1)
        cards.addLayout(left, 3)
        cards.addLayout(right, 2)
        inner.addLayout(cards)
        for hint in content.findChildren(QLabel, "Small"):
            hint.setWordWrap(True)
        inner.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self) -> None:
        self.currency.setText(self.db.currency)
        rate = self.db.default_rate
        self.default_rate.setText("" if rate is None else f"{rate:g}")
        self.hotkey.setKeySequence(QKeySequence(self.ctl.hotkey_text()))
        self.mini_hotkey.setKeySequence(QKeySequence(self.ctl.mini_hotkey_text()))
        self.close_to_tray.setChecked(self.ctl.settings.value("close_to_tray", True, type=bool))
        self.autostart.setChecked(autostart.is_enabled())
        self.data_dir.setText(str(Path(self.ctl.settings.fileName()).parent))
        self.auto_updates.setChecked(self.ctl.auto_update_check())
        self.show_update_state()
        cfg = self.ctl.pomodoro_config()
        self._lengths = {k: self.ctl.timer_lengths(k) for k in KINDS}
        self._kind = cfg.kind
        self.kind_seg.buttons[cfg.kind].setChecked(True)
        self._show_kind()
        self.pomo_auto.setChecked(cfg.auto_next)
        self.pomo_sound.setChecked(cfg.sound)

    def _steppers(self) -> dict:
        return {"focus_min": self.pomo_focus, "short_break_min": self.pomo_short,
                "long_break_min": self.pomo_long, "long_every": self.pomo_every}

    def _set_kind(self, kind: str) -> None:
        """Switch the edited timer: keep what was typed for the previous one."""
        self._lengths[self._kind] = {k: w.value() for k, w in self._steppers().items()}
        self._kind = kind
        self._show_kind()

    def _show_kind(self) -> None:
        m = self._lengths.get(self._kind) or self.ctl.timer_lengths(self._kind)
        for key, w in self._steppers().items():
            w.setValue(m[key])
        self.kind_blurb.setText(KINDS[self._kind].blurb)
        self.pomo_icon.setPixmap(timer_pixmap(self._kind, 26, self.devicePixelRatioF()))

    def show_update_state(self) -> None:
        info = self.ctl.update_info
        state = info.get("state")
        self.check_btn.setEnabled(state != "checking")
        self.download_btn.setVisible(state == "available")
        if state == "available":
            self.download_btn.setText(f"Download {info['version']}")
            self.update_status.setText(f"SD Time {info['version']} is available.")
        elif state == "checking":
            self.update_status.setText("Checking…")
        elif state == "latest":
            self.update_status.setText("You have the latest version.")
        elif state == "failed":
            self.update_status.setText(f"Couldn't check: {info.get('message', 'unknown error')}.")
        else:
            self.update_status.setText("")

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
        self.ctl.settings.setValue("updates/auto", self.auto_updates.isChecked())
        try:
            autostart.set_enabled(self.autostart.isChecked())
        except OSError as exc:
            show_error(self, f"Couldn't change autostart: {exc}")
        s = self.ctl.settings
        self._lengths[self._kind] = {k: w.value() for k, w in self._steppers().items()}
        for kind, lengths in self._lengths.items():
            self.ctl.set_timer_lengths(kind, lengths)
        if self._kind != self.ctl.pomodoro_kind():
            s.setValue("pomodoro/kind", self._kind)
            if self.ctl.pomo.phase == "idle":
                self.ctl.pomo.reset()
        s.setValue("pomodoro/auto_next", self.pomo_auto.isChecked())
        s.setValue("pomodoro/sound", self.pomo_sound.isChecked())
        self.ctl.reload_pomodoro_config()
        fmt = QKeySequence.SequenceFormat.PortableText
        hotkey = self.hotkey.keySequence().toString(fmt)
        mini_hotkey = self.mini_hotkey.keySequence().toString(fmt)
        if self.ctl.set_hotkey(hotkey) and self.ctl.set_mini_hotkey(mini_hotkey):
            self.ctl.toast("Settings saved")
        self.ctl.notify(origin=self)

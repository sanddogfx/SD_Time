"""Main window: sidebar navigation, pages, tray icon, global hotkey, controller."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from .db import Database
from .dialogs import EntryDialog, PomodoroPrompt
from .hotkey import GlobalHotkey
from .icons import color_icon, logo_pixmap, make_icon, nav_icon
from .pages.calendar_page import CalendarPage
from .pages.manage import ClientsPage, ProjectsPage, SettingsPage
from .pages.reports import ReportsPage
from .pages.timesheet import TimesheetPage
from .pages.tracker import TrackerPage
from .pomodoro import ASK, BREAK, FOCUS, IDLE, Pomodoro, PomodoroConfig
from .sound import play as play_sound
from .sound import prepare_in_background as prepare_sounds
from .theme import C
from .util import fmt_clock, fmt_time
from .widgets import confirm, show_error

DEFAULT_HOTKEY = "Ctrl+Alt+T"

NAV = [   # (icon name, label, page) — a row without a page is a section header
    ("tracker", "TIME TRACKER", TrackerPage),
    ("calendar", "CALENDAR", CalendarPage),
    ("timesheet", "TIMESHEET", TimesheetPage),
    ("reports", "REPORTS", ReportsPage),
    ("projects", "PROJECTS", ProjectsPage),
    ("clients", "CLIENTS", ClientsPage),
    ("settings", "SETTINGS", SettingsPage),
]


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: QSettings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.running = db.running_entry()
        self._really_quit = False
        self._dirty: set = set()
        self.pomo = Pomodoro(self.pomodoro_config())
        self.pomo.load({k: settings.value(f"pomodoro_state/{k}")
                        for k in ("phase", "end", "count", "entry_id", "long")})
        self._pomo_last: tuple | None = None   # activity to continue after a break
        self._prompt = None                    # open "break or skip?" window

        self.icon_idle = make_icon(False)
        self.icon_run = make_icon(True)
        self.setWindowTitle("SD Time")
        self.setWindowIcon(self.icon_idle)
        self.resize(1320, 840)
        self.setMinimumSize(1000, 640)

        self._build_shell()
        self._build_tray()

        self.hotkey = GlobalHotkey(int(self.winId()), self)
        self.hotkey.activated.connect(self.on_hotkey)
        self.hotkey.register(self.hotkey_text())

        self.ticker = QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self.on_tick)
        self.ticker.start()

        # Select the first page without triggering its refresh: notify() below does it once.
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(0)
        self.nav.blockSignals(False)
        self.stack.setCurrentWidget(self.tracker)
        self._pomo_restore()
        self.notify()
        # Synthesize the chimes ahead of time so the first alert plays instantly.
        prepare_sounds(self._data_dir())

    # ================================================================ shell
    def _build_shell(self) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        brand = QWidget()
        brand_lay = QHBoxLayout(brand)
        brand_lay.setContentsMargins(20, 16, 12, 12)
        brand_lay.setSpacing(10)
        dpr = self.devicePixelRatioF()
        logo = logo_pixmap(int(30 * dpr), small=True)   # 30 px on screen: small artwork
        if logo is not None:
            logo.setDevicePixelRatio(dpr)     # crisp on high-DPI screens
            logo_label = QLabel()
            logo_label.setPixmap(logo)
            brand_lay.addWidget(logo_label)
        brand_text = QLabel("SD TIME")
        brand_text.setObjectName("BrandText")
        brand_lay.addWidget(brand_text)
        brand_lay.addStretch(1)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setIconSize(QSize(20, 20))
        self.stack = QStackedWidget()
        self.pages: list[QWidget] = []
        self._row_to_page: dict[int, int] = {}
        dpr = self.devicePixelRatioF()
        for icon, text, page_cls in NAV:
            item = QListWidgetItem(text)
            if page_cls is None:
                # Section header: disabled item, styled muted & small via #Nav::item:disabled.
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                font = item.font()
                font.setPointSizeF(8)
                font.setBold(True)
                font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
                item.setFont(font)
                self.nav.addItem(item)
                continue
            item.setIcon(nav_icon(icon, dpr))
            self.nav.addItem(item)
            page = page_cls(self)
            self._row_to_page[self.nav.count() - 1] = len(self.pages)
            self.pages.append(page)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._on_nav)

        self.side_timer = QLabel()
        self.side_timer.setObjectName("Muted")
        self.side_timer.setWordWrap(True)
        self.side_timer.setContentsMargins(19, 8, 12, 16)
        self.side_timer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.side_timer.mousePressEvent = lambda _e: self.go(self.tracker)

        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(brand)
        sl.addWidget(self.nav, 1)
        sl.addWidget(self.side_timer)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(sidebar)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    @property
    def tracker(self) -> TrackerPage:
        return self.pages[0]

    def go(self, page: QWidget) -> None:
        idx = self.pages.index(page)
        for row, pidx in self._row_to_page.items():
            if pidx == idx:
                self.nav.setCurrentRow(row)

    def _on_nav(self, row: int) -> None:
        if row not in self._row_to_page:
            return
        page = self.pages[self._row_to_page[row]]
        self.stack.setCurrentWidget(page)
        if page in self._dirty or not getattr(page, "_shown", False):
            page._shown = True
            self._dirty.discard(page)
            page.refresh()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon_idle, self)
        self.tray_menu = QMenu()
        self.tray_toggle = QAction("Start timer", self)
        self.tray_toggle.triggered.connect(self.toggle_timer)
        self.tray_menu.addAction(self.tray_toggle)
        self.recent_menu = self.tray_menu.addMenu("Continue")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.tray_menu.addSeparator()
        for text, slot in (("Open SD Time", self.show_window),
                           ("Reports", lambda: (self.show_window(), self.go(self.pages[3])))):
            act = QAction(text, self)
            act.triggered.connect(slot)
            self.tray_menu.addAction(act)
        self.tray_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_act)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # =========================================================== controller
    def notify(self, origin: QWidget | None = None) -> None:
        """Data changed: refresh the visible page, mark the others for refresh."""
        self.running = self.db.running_entry()
        running = self.running is not None
        if self.pomo.phase in (FOCUS, ASK) and (
                not running or self.running["id"] != self.pomo.entry_id):
            # The focused entry was stopped or deleted some other way (edit dialog, delete).
            self.pomo.interrupt()
            self._pomo_save()
        if self._prompt is not None and (
                (self._prompt.kind == "focus_done" and self.pomo.phase != ASK)
                or (self._prompt.kind == "break_done" and running)):
            self._close_prompt()   # answered some other way (STOP, START, ...)
        icon = self.icon_run if running else self.icon_idle
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray_toggle.setText("Stop timer" if running else "Start timer")
        current = self.stack.currentWidget()
        for page in self.pages:
            if page is current:
                if page is not origin:
                    page.refresh()
                    page._shown = True
            else:
                self._dirty.add(page)
        if current is not self.tracker:
            self.tracker.sync_top()
        self.on_tick()

    def start(self, project_id=None, task_id=None, description: str = "") -> None:
        if self.pomo.phase == ASK and self.running is not None \
                and self.running["id"] == self.pomo.entry_id:
            # Starting something else while the break question is open: the finished
            # focus ends where it ended, the gap until now isn't tracked.
            self.db.stop(now=self.pomo.end)
        entry_id = self.db.start(project_id, task_id, description)
        if self.pomodoro_enabled():
            # Starting during a break ends the break early.
            if self.pomo.phase == BREAK:
                self.pomo.finish_break()
            self.pomo.begin_focus(entry_id, int(time.time()))
            self._pomo_save()
        self.notify()

    def stop(self) -> None:
        self.db.stop()
        if self.pomo.phase in (FOCUS, ASK):
            self.pomo.interrupt()
            self._pomo_save()
        self.tracker.clear_draft()
        self.notify()

    # ============================================================= pomodoro
    def pomodoro_config(self) -> PomodoroConfig:
        s = self.settings
        return PomodoroConfig(
            focus=s.value("pomodoro/focus_min", 25, type=int) * 60,
            short_break=s.value("pomodoro/short_break_min", 5, type=int) * 60,
            long_break=s.value("pomodoro/long_break_min", 15, type=int) * 60,
            long_every=s.value("pomodoro/long_every", 4, type=int),
            auto_next=s.value("pomodoro/auto_next", False, type=bool),
            sound=s.value("pomodoro/sound", True, type=bool),
        )

    def reload_pomodoro_config(self) -> None:
        """Settings changed: new lengths apply from the next focus/break."""
        self.pomo.config = self.pomodoro_config()

    def pomodoro_enabled(self) -> bool:
        return self.settings.value("pomodoro/enabled", False, type=bool)

    def set_pomodoro_enabled(self, on: bool) -> None:
        self.settings.setValue("pomodoro/enabled", on)
        if on and self.running is not None and self.pomo.phase == IDLE:
            # Turning it on while a timer runs starts a focus session from now.
            self.pomo.begin_focus(self.running["id"], int(time.time()))
        elif not on:
            self.pomo.reset()
        self._pomo_save()
        self.notify()

    def skip_break(self) -> None:
        if self.pomo.phase == BREAK:
            self.pomo.finish_break()
            self._pomo_save()
            self.notify()

    def _pomo_save(self) -> None:
        for k, v in self.pomo.to_dict().items():
            self.settings.setValue(f"pomodoro_state/{k}", v)

    def _pomo_restore(self) -> None:
        """After a restart: drop a stale state, or finish what ran out while closed."""
        running = self.db.running_entry()
        on_entry = running is not None and running["id"] == self.pomo.entry_id
        if self.pomo.phase in (FOCUS, ASK) and not on_entry:
            self.pomo.interrupt()
        if not self.pomodoro_enabled():
            self.pomo.reset()
        if self.pomo.phase == ASK:
            # Closed while the question was open: end the entry at the focus end.
            self.db.stop(now=self.pomo.end)
            self.pomo.interrupt()
        self._pomo_save()
        self._pomo_check(quiet_if_old=True)

    def _pomo_check(self, quiet_if_old: bool = False) -> None:
        now = int(time.time())
        if not self.pomo.due(now):
            return
        if self.pomo.phase == FOCUS:
            running = self.db.running_entry()
            if running is not None and running["id"] == self.pomo.entry_id:
                self._pomo_last = (running["project_id"], running["task_id"],
                                   running["description"])
            if quiet_if_old:
                # Focus ran out while SD Time was closed: stop at the focus end, no question.
                if running is not None and running["id"] == self.pomo.entry_id:
                    self.db.stop(now=self.pomo.end)
                self.pomo.interrupt()
                self._pomo_save()
                if self._pomo_last:
                    self.tracker.set_draft(*self._pomo_last)
                self.notify()
                return
            # The entry keeps running until the user answers.
            self.pomo.focus_done()
            self._pomo_save()
            minutes = self.pomo.next_break_length() // 60
            kind = "long" if self.pomo.long else "short"
            self._ask("focus_done", "Focus session done",
                      f"{self._entry_title(running) if running else 'Nice work'}.\n"
                      f"Take a {minutes}-minute {kind} break, or skip it and keep working? "
                      "The timer keeps running until you choose.",
                      f"Take a break · {minutes} min", "Skip, keep working",
                      self.take_break, self.skip_break_keep_working,
                      on_dismiss=self.take_break)   # ✕ = don't count unconfirmed work
            self.notify()
        elif self.pomo.phase == BREAK:
            self.pomo.finish_break()
            self._pomo_save()
            if quiet_if_old:
                self.notify()
                return
            if self.pomo.config.auto_next and self._pomo_last:
                self.start(*self._pomo_last)
                self._alert("break_done", "Break is over", "Next focus session started.")
                return
            focus_min = self.pomo.config.focus // 60
            what = self._pomo_last[2] if self._pomo_last and self._pomo_last[2] else "work"
            self._ask("break_done", "Break is over",
                      f"Ready for the next {focus_min}-minute focus session on “{what}”?",
                      f"Start focus · {focus_min} min", "Later",
                      self.start_next_focus, lambda: None)
            self.notify()

    # -- answers to the pomodoro questions
    def take_break(self) -> None:
        if self.pomo.phase != ASK:
            return
        running = self.db.running_entry()
        if running is not None and running["id"] == self.pomo.entry_id:
            self.db.stop(now=self.pomo.end)          # track exactly the focus length
        self.pomo.take_break(int(time.time()))
        self._pomo_save()
        if self._pomo_last:
            self.tracker.set_draft(*self._pomo_last)
        self.notify()

    def skip_break_keep_working(self) -> None:
        if self.pomo.phase != ASK:
            return
        running = self.db.running_entry()
        if running is not None and running["id"] == self.pomo.entry_id:
            self.pomo.skip_break(running["id"], int(time.time()))
            self._pomo_save()
            self.notify()
        elif self._pomo_last:
            self.start(*self._pomo_last)

    def start_next_focus(self) -> None:
        if self.running is None:
            if self._pomo_last:
                self.start(*self._pomo_last)
            else:
                self._start_from_draft_or_last()

    def _ask(self, sound_kind: str, title: str, text: str, primary: str, secondary: str,
             on_primary, on_secondary, on_dismiss=None) -> None:
        self._close_prompt()
        self._alert(sound_kind, title, text.split("\n")[-1])
        prompt = PomodoroPrompt(self, title, text, primary, secondary)
        prompt.kind = sound_kind
        actions = {PomodoroPrompt.PRIMARY: on_primary, PomodoroPrompt.SECONDARY: on_secondary,
                   PomodoroPrompt.DISMISSED: on_dismiss or on_secondary}

        def finished(code: int) -> None:
            self._prompt = None
            prompt.deleteLater()
            actions.get(code, on_secondary)()

        prompt.finished.connect(finished)
        self._prompt = prompt
        prompt.present()

    def _close_prompt(self) -> None:
        if self._prompt is not None:
            prompt, self._prompt = self._prompt, None
            prompt.blockSignals(True)
            prompt.close()
            prompt.deleteLater()

    def _alert(self, sound_kind: str, title: str, text: str) -> None:
        self.tray.showMessage(title, text, self.icon_run, 6000)
        QApplication.alert(self, 0)   # flash the taskbar button
        if self.pomo.config.sound:
            play_sound(sound_kind, self._data_dir())

    def _data_dir(self) -> Path:
        return Path(self.settings.fileName()).parent

    def toggle_timer(self) -> None:
        if self.running is not None:
            self.tracker._desc_done()
            self.stop()
        else:
            self._start_from_draft_or_last()

    def _start_from_draft_or_last(self) -> bool:
        project_id, task_id, desc = self.tracker.draft()
        if project_id or desc:
            self.start(project_id, task_id, desc)
            return True
        last = self.db.last_entry()
        if last is not None:
            self.start(last["project_id"], last["task_id"], last["description"])
            return True
        self.show_window()
        self.go(self.tracker)
        self.tracker.desc.setFocus()
        return False

    def on_hotkey(self) -> None:
        if self.running is not None:
            entry = self.running
            self.tracker._desc_done()
            self.stop()
            self.tray.showMessage("Timer stopped", f"{self._entry_title(entry)} · "
                                  f"{fmt_clock(self.db.duration(entry))}", self.icon_idle, 2500)
        elif self._start_from_draft_or_last():
            self.tray.showMessage("Timer started", self._entry_title(self.running),
                                  self.icon_run, 2500)

    @staticmethod
    def _entry_title(e) -> str:
        parts = [x for x in (e["description"], e["project_name"], e["task_name"]) if x]
        return " · ".join(parts) or "No description"

    def new_entry(self, **prefill) -> None:
        dlg = EntryDialog(self.db, self, **prefill)
        if dlg.exec():
            v = dlg.values()
            try:
                self.db.add_entry(v["start_ts"], v["end_ts"], v["project_id"], v["task_id"],
                                  v["description"])
            except ValueError as exc:
                show_error(self, exc)
            self.notify()

    def edit_entry(self, entry_id: int) -> None:
        entry = self.db.get_entry(entry_id)
        if entry is None:
            return
        dlg = EntryDialog(self.db, self, entry=entry)
        if dlg.exec():
            try:
                self.db.update_entry(entry_id, **dlg.values())
            except ValueError as exc:
                show_error(self, exc)
            self.notify()

    def duplicate_entry(self, entry_id: int) -> None:
        e = self.db.get_entry(entry_id)
        if e is not None and e["end_ts"] is not None and e["end_ts"] > e["start_ts"]:
            self.db.add_entry(e["start_ts"], e["end_ts"], e["project_id"], e["task_id"],
                              e["description"])
            self.notify()

    def delete_entry(self, entry_id: int) -> None:
        e = self.db.get_entry(entry_id)
        if e is None:
            return
        text = (f"Delete this time entry?\n\n{self._entry_title(e)}\n"
                f"{fmt_time(e['start_ts'])} · {fmt_clock(self.db.duration(e))}")
        if confirm(self, "Delete entry", text):
            self.db.delete_entry(entry_id)
            self.notify()

    def hotkey_text(self) -> str:
        return self.settings.value("hotkey", DEFAULT_HOTKEY, type=str)

    def set_hotkey(self, text: str) -> bool:
        self.settings.setValue("hotkey", text)
        if not text:
            self.hotkey.unregister()
            return True
        if not self.hotkey.register(text):
            show_error(self, self.hotkey.error or "Couldn't register the hotkey.")
            return False
        return True

    def toast(self, message: str) -> None:
        self.statusBar().showMessage(message, 3000)

    # ================================================================= tick
    def on_tick(self) -> None:
        self._pomo_check()
        if self.stack.currentWidget() is self.tracker:
            self.tracker.tick()
        e = self.running
        phase = self.pomo.phase
        left = fmt_clock(self.pomo.remaining(int(time.time())))
        if e is None:
            if phase == BREAK:
                self.tray.setToolTip(f"SD Time — {self.pomo.label()}: {left} left")
                self.setWindowTitle(f"Break {left} · SD Time")
                self.side_timer.setText(f'<span style="color:{C["accent_text"]}">'
                                        f'<b>{left}</b></span><br>{self.pomo.label()}')
            else:
                self.tray.setToolTip("SD Time — timer stopped")
                self.setWindowTitle("SD Time")
                self.side_timer.setText("")
            return
        elapsed = fmt_clock(self.db.duration(e))
        title = self._entry_title(e)
        if phase == FOCUS:
            self.tray.setToolTip(f"SD Time — {self.pomo.label()}: {left} left\n{title}")
            self.setWindowTitle(f"Focus {left} · SD Time")
            shown, subtitle = left, f"{self.pomo.label()} · {title}"
        else:
            self.tray.setToolTip(f"SD Time — {elapsed}\n{title}")
            self.setWindowTitle(f"{elapsed} · SD Time")
            shown, subtitle = elapsed, title
        color = e["project_color"] or C["accent_text"]
        self.side_timer.setText(f'<span style="color:{color}">●</span> '
                                f'<span style="color:{C["text"]}"><b>{shown}</b></span><br>'
                                f'{subtitle}')

    # ================================================================ window
    def show_window(self) -> None:
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
                self.hide()
            else:
                self.show_window()

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.db.recent_activities(10)
        if not recent:
            act = self.recent_menu.addAction("Nothing yet")
            act.setEnabled(False)
            return
        for e in recent:
            act = QAction(color_icon(e["project_color"] or C["muted"]), self._entry_title(e),
                          self.recent_menu)
            act.triggered.connect(lambda _=False, e=e: self.start(e["project_id"], e["task_id"],
                                                                  e["description"]))
            self.recent_menu.addAction(act)

    def closeEvent(self, event) -> None:
        if self._really_quit:
            event.accept()
            return
        event.ignore()
        if self.settings.value("close_to_tray", True, type=bool) and \
                QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            if not self.settings.value("tray_hint_shown", False, type=bool):
                self.tray.showMessage("SD Time is still running",
                                      "It lives in the tray. Right-click the icon to quit.",
                                      self.icon_idle, 4000)
                self.settings.setValue("tray_hint_shown", True)
        else:
            self.quit_app()

    def quit_app(self) -> None:
        self.tracker._desc_done()
        if self.db.running_entry() is not None:
            self.show_window()
            box = QMessageBox(self)
            box.setWindowTitle("Quit SD Time")
            box.setText("The timer is still running. Stop it before quitting?")
            box.setInformativeText("If you keep it running, the time keeps counting and the "
                                   "timer continues when you start SD Time again.")
            stop_btn = box.addButton("Stop and quit", QMessageBox.ButtonRole.AcceptRole)
            keep_btn = box.addButton("Quit, keep running", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is stop_btn:
                self.db.stop()
            elif clicked is not keep_btn:
                return
        self._really_quit = True
        self.hotkey.unregister()
        self.tray.hide()
        self.settings.sync()
        QApplication.quit()

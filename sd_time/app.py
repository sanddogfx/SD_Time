"""Entry point: single instance, data in %APPDATA%\\SD_Time.

Command line:
    --hidden            start in the tray without showing the window (autostart)
    --selftest=FILE     start on a throw-away database, check the UI comes up, write
                        "OK ..." or the error to FILE and exit (used to verify builds)
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .db import Database, default_data_dir

SERVER_NAME = "SD_Time_single_instance"
MUTEX_NAME = "SD_Time_AppMutex"   # the installer checks it to ask you to close SD Time
_mutex = None


def _set_app_id() -> None:
    """Own taskbar icon on Windows instead of the Python one."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SD_Tools.SD_Time")
        except Exception:
            pass


def _hold_mutex() -> None:
    global _mutex
    if sys.platform == "win32":
        import ctypes
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)


def _notify_running_instance() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def _selftest_target() -> Path | None:
    for arg in sys.argv[1:]:
        if arg.startswith("--selftest="):
            return Path(arg.split("=", 1)[1])
    return None


def main() -> int:
    _set_app_id()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)
    app.setApplicationName("SD Time")
    app.setOrganizationName("SD_Tools")
    app.setQuitOnLastWindowClosed(False)
    selftest = _selftest_target()

    if selftest is None:
        if _notify_running_instance():
            return 0
        _hold_mutex()
        QLocalServer.removeServer(SERVER_NAME)
        server = QLocalServer()
        server.listen(SERVER_NAME)

    from .theme import apply_theme
    from .main_window import MainWindow  # after QApplication: icons are QPixmaps

    apply_theme(app)
    data_dir = Path(tempfile.mkdtemp(prefix="sd_time_selftest_")) if selftest else default_data_dir()
    db = Database(data_dir / "sd_time.db")
    settings = QSettings(str(data_dir / "settings.ini"), QSettings.Format.IniFormat)
    if selftest:
        settings.setValue("hotkey", "")          # don't grab the real hotkey
    window = MainWindow(db, settings)

    if selftest:
        return _run_selftest(app, window, db, selftest)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.deleteLater()
        window.show_window()

    server.newConnection.connect(on_connection)

    if "--hidden" not in sys.argv:
        window.show()
    code = app.exec()
    db.close()
    return code


def _run_selftest(app, window, db, target: Path) -> int:
    """Open every page, start/stop the timer, check bundled assets; report to `target`."""
    from . import __version__
    from .icons import assets_dir, logo_pixmap

    result = {"code": 1}

    def run() -> None:
        try:
            window.show()
            for row in range(window.nav.count()):
                window.nav.setCurrentRow(row)
                app.processEvents()
            checks = {
                "logo": logo_pixmap(64) is not None,
                "logo_small": logo_pixmap(24) is not None,
                "chevron": (assets_dir() / "ui" / "chevron-down.svg").exists(),
                # The update check needs HTTPS: Qt's TLS plugin must be in the build.
                "tls": __import__("PySide6.QtNetwork", fromlist=["QSslSocket"]).QSslSocket.supportsSsl(),
            }
            p = db.add_project("Selftest")
            window.start(p, None, "selftest")
            ok_running = db.running_entry() is not None
            db.update_entry(db.running_entry()["id"], start_ts=db.running_entry()["start_ts"] - 60)
            window.stop()
            checks["timer"] = ok_running and db.count_entries() == 1
            failed = [k for k, v in checks.items() if not v]
            if failed:
                raise RuntimeError(f"failed checks: {failed}")
            target.write_text(f"OK SD Time {__version__} pages={len(window.pages)} "
                              f"assets={assets_dir()}", encoding="utf-8")
            result["code"] = 0
        except Exception:
            target.write_text("FAIL\n" + traceback.format_exc(), encoding="utf-8")
        finally:
            window._really_quit = True
            window.tray.hide()
            app.quit()

    QTimer.singleShot(300, run)
    app.exec()
    db.close()
    return result["code"]


if __name__ == "__main__":
    sys.exit(main())

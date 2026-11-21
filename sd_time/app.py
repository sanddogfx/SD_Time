"""Entry point: single instance, data in %APPDATA%\\SD_Time."""
from __future__ import annotations

import sys

from PySide6.QtCore import QLocale, QSettings
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .db import Database, default_data_dir

SERVER_NAME = "SD_Time_single_instance"


def _set_app_id() -> None:
    """Own taskbar icon on Windows instead of the Python one."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SD_Tools.SD_Time")
        except Exception:
            pass


def _notify_running_instance() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    _set_app_id()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)
    app.setApplicationName("SD Time")
    app.setOrganizationName("SD_Tools")
    app.setQuitOnLastWindowClosed(False)

    if _notify_running_instance():
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    from .theme import apply_theme
    from .main_window import MainWindow  # after QApplication: icons are QPixmaps

    apply_theme(app)
    data_dir = default_data_dir()
    db = Database(data_dir / "sd_time.db")
    settings = QSettings(str(data_dir / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(db, settings)

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


if __name__ == "__main__":
    sys.exit(main())

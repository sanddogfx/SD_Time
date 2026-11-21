"""Global Windows hotkey (RegisterHotKey)."""
from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

_SPECIAL = {
    "SPACE": 0x20, "PGUP": 0x21, "PGDOWN": 0x22, "END": 0x23, "HOME": 0x24,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "INS": 0x2D, "INSERT": 0x2D, "DEL": 0x2E, "DELETE": 0x2E, "PAUSE": 0x13,
}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+T' -> (modifiers, virtual key). Raises ValueError if it can't be parsed."""
    mods, vk = 0, None
    for part in (text or "").replace(" ", "").split("+"):
        u = part.upper()
        if not u:
            continue
        if u in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif u == "ALT":
            mods |= MOD_ALT
        elif u == "SHIFT":
            mods |= MOD_SHIFT
        elif u in ("META", "WIN"):
            mods |= MOD_WIN
        elif len(u) == 1 and u.isascii() and u.isalnum():
            vk = ord(u)
        elif u.startswith("F") and u[1:].isdigit() and 1 <= int(u[1:]) <= 24:
            vk = 0x6F + int(u[1:])
        elif u in _SPECIAL:
            vk = _SPECIAL[u]
        else:
            raise ValueError(f"Unknown key: {part}")
    if vk is None:
        raise ValueError("No main key given")
    if mods == 0 and not (0x70 <= vk <= 0x87):
        raise ValueError("Add a modifier (Ctrl, Alt, Shift or Win)")
    return mods, vk


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()
    HOTKEY_ID = 0x5D71

    def __init__(self, hwnd: int, parent: QObject | None = None, hotkey_id: int | None = None):
        super().__init__(parent)
        self.hwnd = hwnd
        if hotkey_id is not None:          # a second hotkey needs its own id
            self.HOTKEY_ID = hotkey_id
        self.registered = False
        self.error = ""
        self._filter = None
        if sys.platform == "win32":
            self._filter = _NativeFilter(self._on_hotkey)
            QCoreApplication.instance().installNativeEventFilter(self._filter)

    def register(self, text: str) -> bool:
        self.unregister()
        self.error = ""
        if sys.platform != "win32":
            self.error = "Global hotkeys are supported on Windows only"
            return False
        if not text:
            return False
        try:
            mods, vk = parse_hotkey(text)
        except ValueError as exc:
            self.error = str(exc)
            return False
        import ctypes
        ok = ctypes.windll.user32.RegisterHotKey(
            ctypes.c_void_p(self.hwnd), self.HOTKEY_ID, mods | MOD_NOREPEAT, vk)
        self.registered = bool(ok)
        if not ok:
            self.error = f"{text} is already used by another program"
        return self.registered

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(ctypes.c_void_p(self.hwnd), self.HOTKEY_ID)
        self.registered = False

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == self.HOTKEY_ID:
            self.activated.emit()

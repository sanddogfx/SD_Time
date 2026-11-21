"""Update check against the project's GitHub releases.

Asks https://api.github.com for the latest published release and compares its tag
(vMAJOR.MINOR.PATCH) with the running version. Nothing else is sent: no data, no IDs,
only a generic User-Agent that GitHub requires. Downloading stays a manual click on the
release page: an unsigned installer that replaces itself silently is not worth the risk.
"""
from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__

REPO = "sanddogfx/SD_Time"
REPO_URL = f"https://github.com/{REPO}"
RELEASES_URL = f"{REPO_URL}/releases"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600          # automatic checks: at most once a day


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v0.4.0' / '0.4.0' / '0.4' -> (0, 4, 0). Pre-releases and junk -> None."""
    m = re.fullmatch(r"\s*v?(\d+)\.(\d+)(?:\.(\d+))?\s*", text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(candidate: str, current: str | None = None) -> bool:
    a, b = parse_version(candidate), parse_version(current or __version__)
    return a is not None and b is not None and a > b


class UpdateChecker(QObject):
    """One request at a time. Emits exactly one of the signals per check()."""

    available = Signal(str, str)      # version ("0.5.0"), release page URL
    up_to_date = Signal(str)          # latest published version
    failed = Signal(str)              # short, human-readable reason

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._net = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def check(self) -> None:
        if self._reply is not None:
            return
        req = QNetworkRequest(QUrl(API_LATEST))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", f"SD-Time/{__version__}".encode("ascii"))
        req.setTransferTimeout(15000)
        self._reply = self._net.get(req)
        self._reply.finished.connect(self._done)

    def _done(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError and status is None:
                self.failed.emit("No connection to GitHub")
                return
            if status == 404:
                self.failed.emit("No releases published yet")
                return
            if status != 200:
                self.failed.emit(f"GitHub answered {status}")
                return
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag = str(data.get("tag_name", ""))
            version = ".".join(map(str, parse_version(tag) or ())) or tag
            url = str(data.get("html_url") or RELEASES_URL)
            if not url.startswith(REPO_URL + "/"):    # only ever open our own pages
                url = RELEASES_URL
            if data.get("draft") or data.get("prerelease") or parse_version(tag) is None:
                self.failed.emit("The latest release has no version number")
            elif is_newer(tag):
                self.available.emit(version, url)
            else:
                self.up_to_date.emit(version)
        except (ValueError, TypeError) as exc:
            self.failed.emit(f"Unexpected answer from GitHub ({exc.__class__.__name__})")
        finally:
            reply.deleteLater()

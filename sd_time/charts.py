"""Painted charts: stacked bars by day and a donut."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from .theme import C
from .util import fmt_clock


class StackedBarChart(QWidget):
    """bars: list of (label, [(seconds, color, name), ...])."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bars: list[tuple[str, list]] = []
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self._hit: list[tuple[QRectF, str]] = []

    def set_data(self, bars: list[tuple[str, list]]) -> None:
        self.bars = bars
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hit = []
        small = QFont(self.font())
        small.setPointSizeF(8.5)
        fm = QFontMetrics(small)
        left, right, top, bottom = 46, 12, 28, 34
        area = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
        totals = [sum(s for s, _, _ in stack) for _, stack in self.bars]
        max_h = max(totals, default=0) / 3600
        step = 1
        for candidate in (1, 2, 4, 5, 10, 20, 25, 50, 100, 200, 500):
            if max_h / candidate <= 6:
                step = candidate
                break
        top_h = max(step, math.ceil(max_h / step) * step) if max_h else step * 4

        p.setFont(small)
        for i in range(int(top_h / step) + 1):
            h = i * step
            y = area.bottom() - h / top_h * area.height()
            p.setPen(QPen(QColor(C["grid"]), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(0, y - 8, left - 6, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{h:g}.0h")

        n = len(self.bars)
        if not n:
            return
        slot = area.width() / n
        bar_w = min(160.0, slot * 0.72)
        show_labels = fm.horizontalAdvance("Mon, Nov 30") < slot or n <= 12
        for i, (text, stack) in enumerate(self.bars):
            x = area.left() + i * slot + (slot - bar_w) / 2
            y = area.bottom()
            for seconds, color, name in stack:
                if seconds <= 0:
                    continue
                h = seconds / 3600 / top_h * area.height()
                rect = QRectF(x, y - h, bar_w, h)
                p.fillRect(rect, QColor(color))
                self._hit.append((rect, f"{text}\n{name}: {fmt_clock(seconds)}"))
                y -= h
            p.setPen(QColor(C["text"]))
            if totals[i] or n <= 14:
                p.drawText(QRectF(x - 20, y - 20, bar_w + 40, 18),
                           Qt.AlignmentFlag.AlignCenter, fmt_clock(totals[i]))
            if show_labels or i % max(1, n // 10) == 0:
                p.drawText(QRectF(area.left() + i * slot - 10, area.bottom() + 6, slot + 20, 20),
                           Qt.AlignmentFlag.AlignCenter, text)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        for rect, tip in self._hit:
            if rect.contains(pos):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()


class DonutChart(QWidget):
    """slices: list of (seconds, color, name)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.slices: list[tuple[int, str, str]] = []
        self.center_text = ""
        self.setMinimumSize(240, 240)
        self.setMouseTracking(True)

    def set_data(self, slices: list[tuple[int, str, str]], center_text: str) -> None:
        self.slices = [s for s in slices if s[0] > 0]
        self.center_text = center_text
        self.update()

    def _geometry(self) -> tuple[QRectF, float]:
        side = min(self.width(), self.height()) - 20
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        return rect, side * 0.22

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect, thickness = self._geometry()
        total = sum(s for s, _, _ in self.slices)
        if not total:
            pen = QPen(QColor(C["grid"]), thickness)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawEllipse(rect.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2))
        else:
            angle = 90.0
            inner = rect.adjusted(thickness, thickness, -thickness, -thickness)
            for seconds, color, _ in self.slices:
                span = -seconds / total * 360
                path = QPainterPath()
                path.arcMoveTo(rect, angle)
                path.arcTo(rect, angle, span)
                path.arcTo(inner, angle + span, -span)
                path.closeSubpath()
                p.fillPath(path, QColor(color))
                p.setPen(QPen(QColor(C["card"]), 2))
                p.drawPath(path)
                angle += span
        font = QFont(self.font())
        font.setPointSizeF(12)
        p.setFont(font)
        p.setPen(QColor(C["text"]))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.center_text)

    def mouseMoveEvent(self, event) -> None:
        rect, thickness = self._geometry()
        total = sum(s for s, _, _ in self.slices)
        pos = event.position()
        dx, dy = pos.x() - rect.center().x(), rect.center().y() - pos.y()
        r = math.hypot(dx, dy)
        if not total or not (rect.width() / 2 - thickness <= r <= rect.width() / 2):
            QToolTip.hideText()
            return
        # Angle measured clockwise from 12 o'clock, matching the drawing order.
        angle = (90 - math.degrees(math.atan2(dy, dx))) % 360
        acc = 0.0
        for seconds, _, name in self.slices:
            acc += seconds / total * 360
            if angle <= acc:
                QToolTip.showText(event.globalPosition().toPoint(),
                                  f"{name}: {fmt_clock(seconds)} ({seconds / total:.0%})", self)
                return

"""Calendar page: week / day view of time entries on an hour grid."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QScrollArea, QToolTip, QVBoxLayout, QWidget,
)

from ..db import NO_COLOR, day_start_ts
from ..theme import C
from ..util import fmt_clock, fmt_time, week_start
from ..widgets import button, label, show_error

GUTTER = 60
SNAP = 15 * 60
EDGE = 6  # px from a block's top/bottom edge that grabs the edge instead of the block


def drag_times(mode: str, start: int, end: int | None, day0: int, target_day0: int,
               delta: float, now: int) -> tuple[int, int | None]:
    """New (start, end) of an entry dragged by `delta` seconds, snapped to SNAP.

    mode: "move" (keeps duration, may land on another day), "top" (start edge),
    "bottom" (end edge). end None = running timer: only its start can change.
    day0 / target_day0: start of the entry's day / of the day under the cursor.
    """
    if end is None or mode == "top":
        limit = (end - SNAP) if end is not None else now - 60
        new_start = day0 + round((start - day0 + delta) / SNAP) * SNAP
        return max(day0, min(new_start, limit)), end
    if mode == "move":
        tod = round((start - day0 + delta) / SNAP) * SNAP
        tod = max(0, min(86400 - SNAP, tod))
        new_start = target_day0 + tod
        return new_start, new_start + (end - start)
    new_end = day0 + round((end - day0 + delta) / SNAP) * SNAP
    return start, max(start + SNAP, min(new_end, day0 + 86400))


class CalendarHeader(QWidget):
    def __init__(self, page: "CalendarPage"):
        super().__init__()
        self.page = page
        self.setFixedHeight(50)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C["header"]))
        days = self.page.days
        if not days:
            return
        width = self.page.view.width()
        col = (width - GUTTER) / len(days)
        totals = self.page.view.day_totals()
        small = QFont(self.font())
        small.setPointSizeF(9)
        today = date.today()
        for i, d in enumerate(days):
            x = GUTTER + i * col
            color = QColor(C["accent_text"] if d == today else C["text"])
            p.setPen(color)
            p.setFont(self.font())
            p.drawText(QRectF(x, 6, col, 20), Qt.AlignmentFlag.AlignCenter,
                       f"{d:%a}, {d:%b} {d.day}")
            p.setFont(small)
            p.drawText(QRectF(x, 25, col, 18), Qt.AlignmentFlag.AlignCenter,
                       fmt_clock(totals.get(d, 0)))
            p.setPen(QPen(QColor(C["grid"]), 1))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))


class CalendarView(QWidget):
    def __init__(self, page: "CalendarPage"):
        super().__init__()
        self.page = page
        self.db = page.db
        self.hour_h = 48
        self.data: list = []
        self.blocks: list[tuple[QRectF, object]] = []
        self._press = None        # (x, y, entry or None)
        self._drag = None         # (day_index, start_ts, cur_ts) — creating a new entry
        self._edit = None         # dict — moving/resizing an existing entry
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMinimumHeight(24 * self.hour_h + 1)

    # ------------------------------------------------------------- geometry
    def days(self) -> list[date]:
        return self.page.days

    def col_width(self) -> float:
        return (self.width() - GUTTER) / max(1, len(self.days()))

    def set_zoom(self, hour_h: int) -> None:
        self.hour_h = max(20, min(140, hour_h))
        self.setMinimumHeight(24 * self.hour_h + 1)
        self.setFixedHeight(24 * self.hour_h + 1)
        self.update()

    def reload(self) -> None:
        days = self.days()
        if not days:
            return
        t0 = day_start_ts(days[0])
        t1 = day_start_ts(days[-1] + timedelta(days=1))
        self.data = self.db.entries(t0, t1)
        self.update()

    def day_totals(self) -> dict:
        totals: dict = {}
        for e in self.data:
            d = datetime.fromtimestamp(e["start_ts"]).date()
            totals[d] = totals.get(d, 0) + self.db.duration(e)
        return totals

    def _pos_to_slot(self, x: float, y: float) -> tuple[int, int] | None:
        days = self.days()
        if x < GUTTER or not days:
            return None
        idx = min(len(days) - 1, int((x - GUTTER) // self.col_width()))
        seconds = max(0, min(86400, y / self.hour_h * 3600))
        seconds = int(round(seconds / SNAP) * SNAP)
        return idx, day_start_ts(days[idx]) + seconds

    def _span(self, e, now: int) -> tuple[int, int]:
        """Start/end to draw: the live drag position for the entry being edited."""
        ed = self._edit
        if ed and ed["moved"] and ed["entry"]["id"] == e["id"]:
            start, end = ed["new"]
        else:
            start, end = e["start_ts"], e["end_ts"]
        return start, end if end is not None else now

    def _layout_blocks(self) -> None:
        self.blocks = []
        days = self.days()
        col = self.col_width()
        now = int(time.time())
        by_day: dict[int, list] = {}
        for e in self.data:
            start, end = self._span(e, now)
            d = datetime.fromtimestamp(start).date()
            if d in days:
                by_day.setdefault(days.index(d), []).append((start, end, e))
        for idx, items in by_day.items():
            day0 = day_start_ts(days[idx])
            spans = []
            for abs_start, abs_end, e in sorted(items, key=lambda x: x[0]):
                start = abs_start - day0
                end = abs_end - day0
                spans.append([start, min(max(end, start + 60), 86400), e, 0, 1])
            # Greedy lanes for overlapping entries, cluster by cluster.
            cluster: list = []
            cluster_end = -1

            def flush():
                lanes = max((s[3] for s in cluster), default=0) + 1
                for s in cluster:
                    s[4] = lanes

            lane_ends: list[int] = []
            for s in spans:
                if s[0] >= cluster_end and cluster:
                    flush()
                    cluster, lane_ends = [], []
                for lane, lane_end in enumerate(lane_ends):
                    if lane_end <= s[0]:
                        s[3] = lane
                        lane_ends[lane] = s[1]
                        break
                else:
                    s[3] = len(lane_ends)
                    lane_ends.append(s[1])
                cluster.append(s)
                cluster_end = max(cluster_end, s[1])
            if cluster:
                flush()
            for start, end, e, lane, lanes in spans:
                w = (col - 8) / lanes
                x = GUTTER + idx * col + 4 + lane * w
                y = start / 3600 * self.hour_h
                h = max(14.0, (end - start) / 3600 * self.hour_h)
                self.blocks.append((QRectF(x, y + 1, w - 2, h - 2), e))

    # --------------------------------------------------------------- paint
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg"]))
        days = self.days()
        if not days:
            return
        col = self.col_width()
        today = date.today()
        if today in days:
            i = days.index(today)
            p.fillRect(QRectF(GUTTER + i * col, 0, col, self.height()), QColor(C["today_col"]))

        grid = QPen(QColor(C["grid"]), 1, Qt.PenStyle.DashLine)
        small = QFont(self.font())
        small.setPointSizeF(9)
        p.setFont(small)
        for h in range(25):
            y = h * self.hour_h
            p.setPen(grid)
            p.drawLine(QPointF(GUTTER, y), QPointF(self.width(), y))
            if 0 < h < 24:
                p.setPen(QColor(C["muted"]))
                p.drawText(QRectF(0, y - 9, GUTTER - 8, 18),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{h:02d}:00")
        for i in range(len(days) + 1):
            x = GUTTER + i * col
            p.setPen(grid)
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))

        self._layout_blocks()
        fm = QFontMetrics(small)
        now_ts = int(time.time())
        editing_id = self._edit["entry"]["id"] if self._edit and self._edit["moved"] else None
        for rect, e in self.blocks:
            color = QColor(e["project_color"] or NO_COLOR)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["header"]))
            p.drawRect(rect)
            p.setBrush(color)
            p.drawRect(QRectF(rect.x(), rect.y(), 3, rect.height()))
            if e["id"] == editing_id:
                p.setPen(QPen(QColor(C["accent_text"]), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect)
            elif e["end_ts"] is None:
                p.setPen(QPen(QColor(C["accent_text"]), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect)
            inner = rect.adjusted(8, 3, -5, -3)
            title = e["project_name"] or e["description"] or "No project"
            sub = e["client_name"] if e["project_name"] else ""
            span_start, span_end = self._span(e, now_ts)
            dur = fmt_clock(span_end - span_start)
            p.setFont(small)
            if rect.height() >= 34:
                p.setPen(color if e["project_name"] else QColor(C["muted"]))
                text = fm.elidedText(title + (f" - {sub}" if sub else ""),
                                     Qt.TextElideMode.ElideRight, int(inner.width()))
                p.drawText(inner, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
                if rect.height() >= 52 and e["description"] and e["project_name"]:
                    p.setPen(QColor(C["muted"]))
                    desc = fm.elidedText(e["description"], Qt.TextElideMode.ElideRight,
                                         int(inner.width()))
                    p.drawText(inner.adjusted(0, fm.height() + 2, 0, 0),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, desc)
                p.setPen(QColor(C["text"]))
                p.drawText(inner, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, dur)
            elif rect.height() >= 14:
                p.setPen(QColor(C["text"]))
                dur_w = fm.horizontalAdvance(dur) + 6
                p.drawText(inner, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, dur)
                p.setPen(color)
                text = fm.elidedText(title, Qt.TextElideMode.ElideRight,
                                     max(0, int(inner.width() - dur_w)))
                p.drawText(inner, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

        if editing_id is not None:
            # Time badge above the dragged block: "09:15 - 11:00".
            for rect, e in self.blocks:
                if e["id"] != editing_id:
                    continue
                new_start, new_end = self._edit["new"]
                text = f"{fmt_time(new_start)} - " + (fmt_time(new_end) if new_end else "now")
                w = fm.horizontalAdvance(text) + 14
                y = rect.top() - fm.height() - 8
                if y < 0:
                    y = rect.bottom() + 4
                badge = QRectF(rect.left(), y, w, fm.height() + 6)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(C["accent"]))
                p.drawRoundedRect(badge, 3, 3)
                p.setPen(QColor(C["on_accent"]))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
                break

        if self._drag:
            idx, a, b = self._drag
            lo, hi = sorted((a, b))
            day0 = day_start_ts(days[idx])
            rect = QRectF(GUTTER + idx * col + 4, (lo - day0) / 3600 * self.hour_h,
                          col - 8, max(2, (hi - lo) / 3600 * self.hour_h))
            fill = QColor(C["accent"])
            fill.setAlpha(55)
            p.setPen(QPen(QColor(C["accent_text"]), 1))
            p.setBrush(fill)
            p.drawRect(rect)
            p.setPen(QColor(C["text"]))
            p.drawText(rect.adjusted(6, 2, -4, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       f"{fmt_time(lo)} - {fmt_time(hi)}")

        if today in days:
            i = days.index(today)
            now = datetime.now()
            y = (now.hour * 3600 + now.minute * 60 + now.second) / 3600 * self.hour_h
            x0 = GUTTER + i * col
            p.setPen(QPen(QColor(C["accent_text"]), 2))
            p.drawLine(QPointF(x0, y), QPointF(x0 + col, y))
            p.setBrush(QColor(C["accent_text"]))
            p.drawEllipse(QPointF(x0, y), 4, 4)

    # --------------------------------------------------------------- mouse
    def _block_at(self, pos) -> object | None:
        hit = self._hit(pos)
        return hit[0] if hit else None

    def _hit(self, pos) -> tuple[object, str] | None:
        """(entry, zone) under pos; zone is "top", "bottom" or "move"."""
        for rect, e in reversed(self.blocks):
            if rect.contains(pos):
                if rect.height() >= 3 * EDGE:
                    if pos.y() - rect.top() <= EDGE:
                        return e, "top"
                    if rect.bottom() - pos.y() <= EDGE and e["end_ts"] is not None:
                        return e, "bottom"
                # A running timer has no fixed end: dragging it moves its start.
                return e, "move" if e["end_ts"] is not None else "top"
        return None

    def _day_index_at(self, x: float) -> int:
        n = len(self.days())
        return max(0, min(n - 1, int((x - GUTTER) // self.col_width())))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos = event.position()
        hit = self._hit(pos)
        entry = hit[0] if hit else None
        self._press = (pos.x(), pos.y(), entry)
        if hit:
            day0 = day_start_ts(datetime.fromtimestamp(entry["start_ts"]).date())
            self._edit = {"entry": entry, "mode": hit[1], "y": pos.y(), "day0": day0,
                          "moved": False, "new": (entry["start_ts"], entry["end_ts"])}
            if self.cursor().shape() == Qt.CursorShape.OpenHandCursor:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            slot = self._pos_to_slot(pos.x(), pos.y())
            if slot:
                self._drag = (slot[0], slot[1], slot[1])

    def _update_edit(self, pos) -> None:
        ed = self._edit
        if not ed["moved"]:
            if abs(pos.x() - self._press[0]) + abs(pos.y() - self._press[1]) < 5:
                return
            ed["moved"] = True
            QToolTip.hideText()
        e = ed["entry"]
        delta = (pos.y() - ed["y"]) / self.hour_h * 3600
        target_day0 = day_start_ts(self.days()[self._day_index_at(pos.x())])
        ed["new"] = drag_times(ed["mode"], e["start_ts"], e["end_ts"], ed["day0"],
                               target_day0, delta, int(time.time()))
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and (self._edit or self._drag):
            self._edit = self._drag = self._press = None
            self.unsetCursor()
            self.update()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._edit:
            self._update_edit(pos)
            return
        if self._drag:
            idx, start, _ = self._drag
            slot = self._pos_to_slot(pos.x(), pos.y())
            if slot:
                day0 = day_start_ts(self.days()[idx])
                cur = min(max(slot[1] - (day_start_ts(self.days()[slot[0]]) - day0), day0),
                          day0 + 86400)
                self._drag = (idx, start, cur)
                self.update()
            return
        hit = self._hit(pos)
        entry = hit[0] if hit else None
        if hit is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            # A running timer reports "top" for its whole body; only the real edge resizes.
            at_edge = hit[1] == "bottom" or (
                hit[1] == "top" and pos.y() - self._rect_of(entry).top() <= EDGE)
            self.setCursor(Qt.CursorShape.SizeVerCursor if at_edge
                           else Qt.CursorShape.OpenHandCursor)
        if entry is not None:
            end = fmt_time(entry["end_ts"]) if entry["end_ts"] is not None else "now"
            parts = [entry["description"] or "(no description)",
                     " · ".join(x for x in (entry["project_name"], entry["task_name"],
                                            entry["client_name"]) if x) or "No project",
                     f"{fmt_time(entry['start_ts'])} - {end}  ({fmt_clock(self.db.duration(entry))})"]
            QToolTip.showText(event.globalPosition().toPoint(), "\n".join(parts), self)
        else:
            QToolTip.hideText()

    def _rect_of(self, entry) -> QRectF:
        for rect, e in self.blocks:
            if e["id"] == entry["id"]:
                return rect
        return QRectF()

    def mouseReleaseEvent(self, event) -> None:
        press, drag, edit = self._press, self._drag, self._edit
        self._press = self._drag = self._edit = None
        self.update()
        if press is None:
            return
        if edit is not None:
            self.unsetCursor()
            if not edit["moved"]:
                self.page.ctl.edit_entry(edit["entry"]["id"])
                return
            e = edit["entry"]
            new_start, new_end = edit["new"]
            if (new_start, new_end) == (e["start_ts"], e["end_ts"]):
                return
            fields = {"start_ts": new_start}
            if e["end_ts"] is not None:
                fields["end_ts"] = new_end
            try:
                self.db.update_entry(e["id"], **fields)
            except ValueError as exc:
                show_error(self, exc)
            self.page.ctl.notify()
            return
        if drag:
            _, a, b = drag
            lo, hi = sorted((a, b))
            if hi - lo >= SNAP:
                self.page.ctl.new_entry(start_ts=lo, end_ts=hi)

    def mouseDoubleClickEvent(self, event) -> None:
        pos = event.position()
        if self._block_at(pos) is None:
            slot = self._pos_to_slot(pos.x(), pos.y())
            if slot:
                self._drag = None
                self.page.ctl.new_entry(start_ts=slot[1], end_ts=slot[1] + 3600)


class CalendarPage(QWidget):
    title = "Calendar"

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.db = ctl.db
        self.anchor = date.today()
        self.mode = "week"
        self.days: list[date] = []
        self._scrolled = False

        week_btn = button("Week")
        day_btn = button("Day")
        for b in (week_btn, day_btn):
            b.setCheckable(True)
        week_btn.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(week_btn)
        group.addButton(day_btn)
        week_btn.clicked.connect(lambda: self._set_mode("week"))
        day_btn.clicked.connect(lambda: self._set_mode("day"))
        self.range_label = label("", "Big")
        self.total_label = label("", "Muted")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(week_btn)
        toolbar.addWidget(day_btn)
        toolbar.addSpacing(12)
        toolbar.addWidget(button("Today", self._today))
        toolbar.addWidget(button("‹", lambda: self._shift(-1)))
        toolbar.addWidget(button("›", lambda: self._shift(1)))
        toolbar.addSpacing(12)
        toolbar.addWidget(self.range_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.total_label)
        toolbar.addSpacing(12)
        toolbar.addWidget(button("−", lambda: self._zoom(-12)))
        toolbar.addWidget(button("+", lambda: self._zoom(12)))
        toolbar.addWidget(button("Add entry", lambda: self.ctl.new_entry(), "Primary"))

        self.view = CalendarView(self)
        self.header = CalendarHeader(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, self.scroll.verticalScrollBar().sizeHint().width(), 0)
        header_row.addWidget(self.header)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 10)
        root.setSpacing(10)
        root.addLayout(toolbar)
        root.addSpacing(6)
        root.addLayout(header_row)
        root.setSpacing(0)
        root.addWidget(self.scroll, 1)

        self.hint = label("Drag on empty space to add time. Drag an entry to move it, drag its "
                          "top or bottom edge to change the time, click it to edit. "
                          "Esc cancels a drag.", "Small")
        root.addSpacing(6)
        root.addWidget(self.hint)

        self.ticker = QTimer(self)
        self.ticker.setInterval(30_000)
        self.ticker.timeout.connect(self._minute_tick)
        self.ticker.start()
        self._compute_days()

    def _compute_days(self) -> None:
        if self.mode == "week":
            ws = week_start(self.anchor)
            self.days = [ws + timedelta(days=i) for i in range(7)]
            we = self.days[-1]
            if ws == week_start(date.today()):
                self.range_label.setText("This week")
            else:
                self.range_label.setText(f"{ws:%b} {ws.day} - {we:%b} {we.day}, {we.year}")
        else:
            self.days = [self.anchor]
            self.range_label.setText(f"{self.anchor:%A}, {self.anchor:%B} {self.anchor.day}")

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def _today(self) -> None:
        self.anchor = date.today()
        self.refresh()

    def _shift(self, step: int) -> None:
        self.anchor += timedelta(days=7 * step if self.mode == "week" else step)
        self.refresh()

    def _zoom(self, delta: int) -> None:
        bar = self.scroll.verticalScrollBar()
        ratio = bar.value() / max(1, self.view.height())
        self.view.set_zoom(self.view.hour_h + delta)
        bar.setValue(int(ratio * self.view.height()))

    def _minute_tick(self) -> None:
        if self.isVisible():
            self.view.update()
            self.header.update()

    def refresh(self) -> None:
        self._compute_days()
        self.view.set_zoom(self.view.hour_h)
        self.view.reload()
        total = sum(self.view.day_totals().values())
        self.total_label.setText(f"Total: {fmt_clock(total)}")
        self.header.update()
        if not self._scrolled:
            self._scrolled = True
            starts = [datetime.fromtimestamp(e["start_ts"]).hour for e in self.view.data]
            first = min(starts) if starts else 8
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
                max(0, first - 1) * self.view.hour_h))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.header.update()

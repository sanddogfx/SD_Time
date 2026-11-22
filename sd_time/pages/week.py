"""Week page: days as rows, hours running left to right. Day / Week / Month.

Drag on an empty row to log time, drag a block to move it (also to another day), drag its
left or right edge to change start or end, click to edit, right-click for Continue / Duplicate /
Delete, double-click for a one-hour entry, Esc cancels a drag.
"""
from __future__ import annotations

import calendar
import math
import time
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget,
)

from .. import theme
from ..db import NO_COLOR, day_start_ts
from ..icons import hover_icon
from ..theme import C
from ..util import fmt_amounts, fmt_clock, fmt_hm, fmt_money, fmt_time, fmt_words, week_start
from ..widgets import (button, card, chip_label, clear_layout, header_pill, label, nav_button,
                       segmented, show_error)

SNAP = 15 * 60
EDGE = 6          # px from a block's left/right edge that grabs the edge instead of the block
LABEL_W = 118     # day label column
TOP = 28          # hour labels
PAD_R = 12
ROW_H = {"day": 150, "week": 66, "month": 30}


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


def text_on(color: str) -> str:
    """Dark text on light blocks, white on dark ones."""
    c = QColor(color)
    lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#141414" if lum > 0.55 else "#ffffff"


class WeekRows(QWidget):
    def __init__(self, page: "WeekPage"):
        super().__init__()
        self.page, self.db = page, page.db
        self.data: list = []
        self.blocks: list[tuple[QRectF, object]] = []
        self.h0, self.h1 = 8.0, 19.0
        self._press = None     # (x, y, entry or None)
        self._drag = None      # (row, start_ts, cur_ts) creating
        self._edit = None      # moving / resizing
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ------------------------------------------------------------ geometry
    @property
    def days(self) -> list[date]:
        return self.page.days

    @property
    def row_h(self) -> int:
        return ROW_H[self.page.mode]

    def track_w(self) -> float:
        return max(10.0, self.width() - LABEL_W - PAD_R)

    def px_per_hour(self) -> float:
        return self.track_w() / max(0.25, self.h1 - self.h0)

    def x_of(self, seconds_into_day: float) -> float:
        return LABEL_W + (seconds_into_day / 3600 - self.h0) * self.px_per_hour()

    def row_of(self, y: float) -> int:
        return max(0, min(len(self.days) - 1, int((y - TOP) // self.row_h)))

    def row_rect(self, i: int) -> QRectF:
        return QRectF(0, TOP + i * self.row_h, self.width(), self.row_h)

    def bar_rect(self, i: int) -> QRectF:
        pad = 6 if self.row_h > 40 else 3
        return QRectF(LABEL_W, TOP + i * self.row_h + pad, self.track_w(), self.row_h - 2 * pad)

    def reload(self) -> None:
        days = self.days
        t0, t1 = day_start_ts(days[0]), day_start_ts(days[-1] + timedelta(days=1))
        self.data = self.db.entries(t0, t1)
        lo, hi = self.page.ctl.day_hours()
        now = time.time()
        for e in self.data:
            day0 = day_start_ts(datetime.fromtimestamp(e["start_ts"]).date())
            end = e["end_ts"] if e["end_ts"] is not None else now
            lo = min(lo, math.floor((e["start_ts"] - day0) / 3600))
            hi = max(hi, math.ceil((end - day0) / 3600))
        if date.today() in days:
            hi = max(hi, math.ceil((now - day_start_ts(date.today())) / 3600))
        self.h0, self.h1 = max(0.0, lo), min(24.0, max(hi, lo + 4))
        self.setMinimumHeight(TOP + len(days) * self.row_h + 8)
        self.setFixedHeight(TOP + len(days) * self.row_h + 8)
        self.update()

    def day_totals(self) -> dict:
        totals: dict = {}
        for e in self.data:
            d = datetime.fromtimestamp(e["start_ts"]).date()
            totals[d] = totals.get(d, 0) + self.db.duration(e)
        return totals

    def _span(self, e, now: int) -> tuple[int, int]:
        ed = self._edit
        if ed and ed["moved"] and ed["entry"]["id"] == e["id"]:
            start, end = ed["new"]
        else:
            start, end = e["start_ts"], e["end_ts"]
        return start, end if end is not None else now

    def _layout(self) -> None:
        self.blocks = []
        now = int(time.time())
        by_row: dict[int, list] = {}
        for e in self.data:
            s, t = self._span(e, now)
            d = datetime.fromtimestamp(s).date()
            if d in self.days:
                by_row.setdefault(self.days.index(d), []).append((s, t, e))
        for row, items in by_row.items():
            day0 = day_start_ts(self.days[row])
            items.sort(key=lambda x: x[0])
            lanes_end: list[int] = []
            placed = []
            cluster, cluster_end = [], -1

            def flush():
                n = max((p[3] for p in cluster), default=0) + 1
                for p in cluster:
                    p[4] = n

            for s, t, e in items:
                if s >= cluster_end and cluster:
                    flush()
                    cluster, lanes_end = [], []
                for lane, lend in enumerate(lanes_end):
                    if lend <= s:
                        lanes_end[lane] = t
                        break
                else:
                    lane = len(lanes_end)
                    lanes_end.append(t)
                rec = [s, t, e, lane, 1]
                cluster.append(rec)
                placed.append(rec)
                cluster_end = max(cluster_end, t)
            if cluster:
                flush()
            bar = self.bar_rect(row)
            for s, t, e, lane, n in placed:
                x0 = self.x_of(s - day0)
                x1 = self.x_of(min(t, day0 + 86400) - day0)
                h = (bar.height() - 2) / n
                rect = QRectF(x0, bar.top() + 1 + lane * h, max(4.0, x1 - x0 - 2), h - 2)
                self.blocks.append((rect, e))

    # ------------------------------------------------------------ paint
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        days, today = self.days, date.today()
        small = QFont(self.font())
        small.setPointSizeF(9)
        mono = theme.mono(8.5)
        totals = self.day_totals()

        # hour labels and grid
        pph = self.px_per_hour()
        step = 1 if pph >= 46 else 2
        p.setFont(mono)
        h = math.ceil(self.h0)
        while h <= self.h1:
            x = self.x_of(h * 3600)
            if h % step == 0:
                p.setPen(QColor("#8a8a8a"))
                cx = min(x, self.width() - 26)          # keep the last label inside
                p.drawText(QRectF(cx - 24, 4, 48, 18), Qt.AlignmentFlag.AlignCenter, f"{h:02d}:00")
            h += 1

        compact = self.row_h < 40
        for i, d in enumerate(days):
            row = self.row_rect(i)
            if d == today:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(C["today_col"]))
                p.drawRoundedRect(row.adjusted(0, 1, 0, -1), 5, 5)
            bar = self.bar_rect(i)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#181818"))
            p.drawRoundedRect(bar, 4 if not compact else 2, 4 if not compact else 2)
            p.setPen(QPen(QColor(C["grid"]), 1))
            h = math.ceil(self.h0)
            while h <= self.h1:
                x = self.x_of(h * 3600)
                p.drawLine(QPointF(x, bar.top() + 2), QPointF(x, bar.bottom() - 2))
                h += 1
            # label
            name = f"{d:%a} {d.day}"
            tot = totals.get(d, 0)
            color = QColor(C["accent_soft_text"] if d == today else C["text"])
            f = QFont(self.font())
            f.setPointSizeF(10 if not compact else 9)
            f.setBold(True)
            p.setFont(f)
            p.setPen(color)
            if compact:
                p.drawText(QRectF(10, row.top(), 60, row.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
                p.setFont(mono)
                p.setPen(QColor(C["muted"]))
                p.drawText(QRectF(60, row.top(), LABEL_W - 66, row.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                           fmt_hm(tot) if tot else "")
            else:
                p.drawText(QRectF(10, row.center().y() - 19, LABEL_W - 14, 20),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
                p.setFont(mono)
                p.setPen(QColor(C["muted"]))
                p.drawText(QRectF(10, row.center().y() + 1, LABEL_W - 14, 18),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           fmt_words(tot) if tot else "—")

        self._layout()
        fm = QFontMetrics(small)
        p.setFont(small)
        editing_id = self._edit["entry"]["id"] if self._edit and self._edit["moved"] else None
        for rect, e in self.blocks:
            color = e["project_color"] or NO_COLOR
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(rect, 3 if not compact else 2, 3 if not compact else 2)
            if e["id"] == editing_id or e["end_ts"] is None:
                p.setPen(QPen(QColor(C["accent_text"]), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 3, 3)
            if rect.width() > 46 and rect.height() >= 22:
                p.setPen(QColor(text_on(color)))
                title = e["description"] or e["project_name"] or "No description"
                inner = rect.adjusted(8, 2, -6, -2)
                if rect.height() >= 52 and e["project_name"] and e["description"]:
                    p.drawText(inner.adjusted(0, 2, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                               fm.elidedText(e["project_name"], Qt.TextElideMode.ElideRight, int(inner.width())))
                    p.drawText(inner.adjusted(0, 0, 0, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                               fm.elidedText(title, Qt.TextElideMode.ElideRight, int(inner.width())))
                else:
                    p.drawText(inner, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               fm.elidedText(title, Qt.TextElideMode.ElideRight, int(inner.width())))

        if editing_id is not None:
            for rect, e in self.blocks:
                if e["id"] == editing_id:
                    s, t = self._edit["new"]
                    self._badge(p, fm, rect, f"{fmt_time(s)} – " + (fmt_time(t) if t else "now"))
                    break
        if self._drag:
            row, a, b = self._drag
            lo, hi = sorted((a, b))
            day0 = day_start_ts(days[row])
            bar = self.bar_rect(row)
            rect = QRectF(self.x_of(lo - day0), bar.top() + 1,
                          max(2.0, (hi - lo) / 3600 * pph), bar.height() - 2)
            fill = QColor(C["accent_text"])
            fill.setAlpha(60)
            p.setPen(QPen(QColor(C["accent_text"]), 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3, 3)
            self._badge(p, fm, rect, f"{fmt_time(lo)} – {fmt_time(hi)}")
        if today in days:
            i = days.index(today)
            now = datetime.now()
            x = self.x_of(now.hour * 3600 + now.minute * 60 + now.second)
            bar = self.bar_rect(i)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["accent_text"]))
            p.drawRoundedRect(QRectF(x - 1, bar.top() - 5, 2, bar.height() + 10), 1, 1)

    def _badge(self, p: QPainter, fm: QFontMetrics, rect: QRectF, text: str) -> None:
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

    # ------------------------------------------------------------ mouse
    def _hit(self, pos) -> tuple[object, str] | None:
        for rect, e in reversed(self.blocks):
            if rect.contains(pos):
                if rect.width() >= 3 * EDGE:
                    if pos.x() - rect.left() <= EDGE:
                        return e, "top"
                    if rect.right() - pos.x() <= EDGE and e["end_ts"] is not None:
                        return e, "bottom"
                return e, "move" if e["end_ts"] is not None else "top"
        return None

    def _slot(self, x: float, y: float) -> tuple[int, int] | None:
        if x < LABEL_W or y < TOP:
            return None
        row = self.row_of(y)
        secs = (self.h0 + (x - LABEL_W) / self.px_per_hour()) * 3600
        secs = max(0, min(86400, round(secs / SNAP) * SNAP))
        return row, day_start_ts(self.days[row]) + int(secs)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos = event.position()
        hit = self._hit(pos)
        self._press = (pos.x(), pos.y(), hit[0] if hit else None)
        if hit:
            e = hit[0]
            day0 = day_start_ts(datetime.fromtimestamp(e["start_ts"]).date())
            self._edit = {"entry": e, "mode": hit[1], "x": pos.x(), "day0": day0,
                          "moved": False, "new": (e["start_ts"], e["end_ts"])}
            if self.cursor().shape() == Qt.CursorShape.OpenHandCursor:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            slot = self._slot(pos.x(), pos.y())
            if slot:
                self._drag = (slot[0], slot[1], slot[1])

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._edit:
            ed = self._edit
            if not ed["moved"]:
                if abs(pos.x() - self._press[0]) + abs(pos.y() - self._press[1]) < 5:
                    return
                ed["moved"] = True
                QToolTip.hideText()
            e = ed["entry"]
            delta = (pos.x() - ed["x"]) / self.px_per_hour() * 3600
            target_day0 = day_start_ts(self.days[self.row_of(pos.y())])
            ed["new"] = drag_times(ed["mode"], e["start_ts"], e["end_ts"], ed["day0"],
                                   target_day0, delta, int(time.time()))
            self.update()
            return
        if self._drag:
            row, start, _ = self._drag
            day0 = day_start_ts(self.days[row])
            secs = (self.h0 + (pos.x() - LABEL_W) / self.px_per_hour()) * 3600
            secs = max(0, min(86400, round(secs / SNAP) * SNAP))
            self._drag = (row, start, day0 + int(secs))
            self.update()
            return
        hit = self._hit(pos)
        if hit is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            QToolTip.hideText()
            return
        e, zone = hit
        rect = next(r for r, x in self.blocks if x["id"] == e["id"])
        at_edge = zone == "bottom" or (zone == "top" and pos.x() - rect.left() <= EDGE)
        self.setCursor(Qt.CursorShape.SizeHorCursor if at_edge else Qt.CursorShape.OpenHandCursor)
        end = fmt_time(e["end_ts"]) if e["end_ts"] is not None else "now"
        tip = "\n".join([e["description"] or "(no description)",
                         " · ".join(x for x in (e["project_name"], e["task_name"], e["client_name"]) if x)
                         or "No project",
                         f"{fmt_time(e['start_ts'])} – {end}  ({fmt_clock(self.db.duration(e))})"])
        QToolTip.showText(event.globalPosition().toPoint(), tip, self)

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
        if self._hit(pos) is None:
            slot = self._slot(pos.x(), pos.y())
            if slot:
                self._drag = None
                self.page.ctl.new_entry(start_ts=slot[1], end_ts=slot[1] + 3600)

    def contextMenuEvent(self, event) -> None:
        if self._edit or self._drag:
            return
        hit = self._hit(QPointF(event.pos()))
        if hit:
            QToolTip.hideText()
            self.page.ctl.entry_menu(hit[0]["id"], event.globalPos(), self)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and (self._edit or self._drag):
            self._edit = self._drag = self._press = None
            self.unsetCursor()
            self.update()
            return
        super().keyPressEvent(event)


class WeekPage(QWidget):
    title = "Week"

    def __init__(self, ctl):
        super().__init__()
        self.ctl, self.db = ctl, ctl.db
        self.anchor = date.today()
        self.mode = "week"
        self.days: list[date] = []
        dpr = self.devicePixelRatioF()

        self.title_label = label("", "H1")
        self.seg = segmented([("day", "Day"), ("week", "Week"), ("month", "Month")], self.mode,
                             self._set_mode)
        prev_btn = nav_button("left", "Previous", lambda: self._shift(-1), dpr)
        next_btn = nav_button("chevron", "Next", lambda: self._shift(1), dpr)
        today_btn = button("Today", self._today)
        self.total_pill = header_pill()
        add = button("Add time", lambda: self.ctl.new_entry())
        add.setIcon(hover_icon("add", dpr, 16))
        add.setIconSize(QSize(16, 16))
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.seg)
        header.addWidget(prev_btn)
        header.addWidget(next_btn)
        header.addWidget(today_btn)
        header.addWidget(self.total_pill)
        header.addWidget(add)

        self.view = WeekRows(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.view)
        box = card()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 14, 16, 14)
        bl.addWidget(self.scroll)

        self.legend = QHBoxLayout()
        self.legend.setSpacing(8)
        legend_box = QWidget()
        legend_box.setLayout(self.legend)
        hint = label("Drag across a row to log time · drag a block to move it, also to another day · "
                     "drag its edges to change the time · click to edit · Esc cancels a drag.", "Small")
        hint.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(16)
        root.addLayout(header)
        root.addWidget(box, 1)
        root.addWidget(legend_box)
        root.addWidget(hint)

        self.ticker = QTimer(self)
        self.ticker.setInterval(30_000)
        self.ticker.timeout.connect(lambda: self.isVisible() and self.view.update())
        self.ticker.start()
        self._compute_days()

    # ------------------------------------------------------------ navigation
    def _compute_days(self) -> None:
        a = self.anchor
        if self.mode == "day":
            self.days = [a]
            self.title_label.setText(f"{a:%A}, {a.day} {a:%B}")
        elif self.mode == "week":
            ws = week_start(a)
            self.days = [ws + timedelta(days=i) for i in range(7)]
            we = self.days[-1]
            self.title_label.setText(f"{ws.day} – {we.day} {we:%B}" if ws.month == we.month
                                     else f"{ws.day} {ws:%b} – {we.day} {we:%b}")
        else:
            n = calendar.monthrange(a.year, a.month)[1]
            self.days = [date(a.year, a.month, i + 1) for i in range(n)]
            self.title_label.setText(f"{a:%B} {a.year}")

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def _shift(self, step: int) -> None:
        if self.mode == "day":
            self.anchor += timedelta(days=step)
        elif self.mode == "week":
            self.anchor += timedelta(weeks=step)
        else:
            m = self.anchor.month - 1 + step
            self.anchor = date(self.anchor.year + m // 12, m % 12 + 1, 1)
        self.refresh()

    def _today(self) -> None:
        self.anchor = date.today()
        self.refresh()

    # ------------------------------------------------------------ data
    def refresh(self) -> None:
        self._compute_days()
        self.view.reload()
        totals = self.view.day_totals()
        total = sum(totals.values())
        money_text = fmt_amounts(self.db.amounts(self.view.data), short=True, order=self.db.currencies)
        self.total_pill.setText(fmt_words(total) + (f" · {money_text}" if money_text else ""))
        clear_layout(self.legend)
        per_project: dict = {}
        for e in self.view.data:
            key = e["project_id"]
            item = per_project.setdefault(key, [e["project_name"] or "No project",
                                                e["project_color"] or NO_COLOR, 0])
            item[2] += self.db.duration(e)
        ranked = sorted(per_project.values(), key=lambda x: -x[2])
        for name, color, secs in ranked[:6]:
            self.legend.addWidget(chip_label(f"{name}  {fmt_hm(secs)}", color))
        if len(ranked) > 6:
            more = label(f"+{len(ranked) - 6} more", "Small")
            more.setToolTip("\n".join(f"{n}  {fmt_hm(s)}" for n, _, s in ranked[6:]))
            self.legend.addWidget(more)
        self.legend.addStretch(1)
        self.seg.buttons[self.mode].setChecked(True)
        if self.mode == "day" or not getattr(self, "_scrolled_once", False):
            self._scrolled_once = True
            if date.today() in self.days and self.mode == "month":
                i = self.days.index(date.today())
                QTimer.singleShot(0, lambda: self.scroll.ensureVisible(0, TOP + i * ROW_H["month"], 0, 120))

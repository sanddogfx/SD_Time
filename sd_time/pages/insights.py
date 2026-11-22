"""Insights page: KPI cards, a 12-week heatmap, ranked bars, a by-client strip, and export.

Replaces the old stacked-bars + donut + tree report. Filters: period (week / month / quarter /
year, with prev/next), client and project.
"""
from __future__ import annotations

import csv
import math
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QMenu, QMessageBox, QScrollArea,
    QToolTip, QVBoxLayout, QWidget,
)

from .. import theme
from ..db import NO_COLOR, PALETTE, day_start_ts
from ..icons import color_icon, hover_icon, tomato_pixmap
from ..theme import C
from ..util import (fmt_amounts, fmt_clock, fmt_date, fmt_hm, fmt_money, fmt_time, fmt_words,
                    short_money, week_start)
from ..widgets import button, card, label, nav_button, segmented, show_error

ALL, NONE = "__all__", "__none__"
HEAT = ["#262626", "#33421f", "#4b6a22", "#6a942a", "#9bcc45"]


def period_range(kind: str, anchor: date) -> tuple[date, date]:
    if kind == "week":
        s = week_start(anchor)
        return s, s + timedelta(days=6)
    if kind == "month":
        s = anchor.replace(day=1)
        return s, (s + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if kind == "quarter":
        q = (anchor.month - 1) // 3
        s = date(anchor.year, q * 3 + 1, 1)
        e = date(anchor.year + (q == 3), (q * 3 + 3) % 12 + 1, 1) - timedelta(days=1)
        return s, e
    return date(anchor.year, 1, 1), date(anchor.year, 12, 31)


def shift_anchor(kind: str, anchor: date, step: int) -> date:
    if kind == "week":
        return anchor + timedelta(weeks=step)
    months = {"month": 1, "quarter": 3, "year": 12}[kind] * step
    m = anchor.month - 1 + months
    return date(anchor.year + m // 12, m % 12 + 1, 1)


# ------------------------------------------------------------------ painted widgets
class Heatmap(QWidget):
    """Last 12 weeks, one square per day, darker → lighter green with more hours."""

    CELL, GAP, LEFT, TOPM = 22, 5, 36, 20

    def __init__(self):
        super().__init__()
        self.cells: list[tuple[date, float]] = []
        self.setMouseTracking(True)
        self.setFixedSize(self.LEFT + 12 * (self.CELL + self.GAP), self.TOPM + 7 * (self.CELL + self.GAP))

    def set(self, end: date, hours_by_day: dict[date, float]) -> None:
        start = week_start(end) - timedelta(weeks=11)
        self.cells = [(start + timedelta(days=i), hours_by_day.get(start + timedelta(days=i), 0.0))
                      for i in range(84)]
        self.end = end
        self.update()

    @staticmethod
    def level(h: float) -> int:
        return 0 if h <= 0 else 1 if h < 3 else 2 if h < 6 else 3 if h < 8 else 4

    def _rect(self, i: int) -> QRectF:
        col, row = divmod(i, 7)
        return QRectF(self.LEFT + col * (self.CELL + self.GAP), self.TOPM + row * (self.CELL + self.GAP),
                      self.CELL, self.CELL)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(theme.mono(8))
        p.setPen(QColor("#8a8a8a"))
        for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun")):
            p.drawText(QRectF(0, self.TOPM + row * (self.CELL + self.GAP), self.LEFT - 4, self.CELL),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        last_month, last_x = None, -100.0
        for i, (d, h) in enumerate(self.cells):
            if i % 7 == 0 and d.month != last_month:
                last_month = d.month
                x = self._rect(i).left()
                if x - last_x >= 2 * (self.CELL + self.GAP):   # skip a label that would collide
                    p.setPen(QColor("#8a8a8a"))
                    p.drawText(QRectF(x, 0, 60, 16), Qt.AlignmentFlag.AlignLeft, f"{d:%b}")
                    last_x = x
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(HEAT[self.level(h)] if d <= self.end else "#1c1c1c"))
            p.drawRoundedRect(self._rect(i), 3, 3)

    def mouseMoveEvent(self, event) -> None:
        for i, (d, h) in enumerate(self.cells):
            if self._rect(i).contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(),
                                  f"{d:%a}, {d.day} {d:%b}: {fmt_words(h * 3600)}", self)
                return
        QToolTip.hideText()


class RankedBars(QWidget):
    """name · bar · hours · amount, longest first; a Total line under them."""

    ROW = 34
    GAP = 8          # space above the Total line

    def __init__(self):
        super().__init__()
        self.rows: list[tuple[str, str, int, str]] = []
        self.total: tuple[int, str] | None = None

    def set(self, rows, total: tuple[int, str] | None = None) -> None:
        self.rows = rows
        self.total = total if rows else None
        extra = self.ROW + self.GAP if self.total else 0
        self.setFixedHeight(max(1, len(rows)) * self.ROW + extra)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            p.setPen(QColor(C["muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "No time tracked in this period.")
            return
        name_w, hours_w = 170, 64
        texts = [r[3] for r in self.rows] + ([self.total[1]] if self.total else [])
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        amount_w = max([96] + [QFontMetrics(bold).horizontalAdvance(t) + 24 for t in texts])
        bar_x = name_w + 12
        bar_w = max(40, self.width() - bar_x - hours_w - amount_w - 24)
        top = max(s for _, _, s, _ in self.rows) or 1
        f = QFont(self.font())
        fm = QFontMetrics(f)
        for i, (name, color, secs, amount) in enumerate(self.rows):
            y = i * self.ROW
            p.setFont(f)
            p.setPen(QColor(C["text"]))
            p.drawText(QRectF(0, y, name_w, self.ROW), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, name_w))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#262626"))
            track = QRectF(bar_x, y + self.ROW / 2 - 7, bar_w, 14)
            p.drawRoundedRect(track, 3, 3)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(bar_x, track.top(), max(6, bar_w * secs / top), 14), 3, 3)
            p.setFont(theme.mono(9.5))
            p.setPen(QColor(C["text"]))
            p.drawText(QRectF(bar_x + bar_w + 12, y, hours_w, self.ROW),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, fmt_hm(secs))
            p.setFont(f)
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(bar_x + bar_w + 12 + hours_w, y, amount_w, self.ROW),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, amount)
        if self.total:
            secs, amount = self.total
            y = len(self.rows) * self.ROW + self.GAP
            p.setPen(QPen(QColor(C["card_border"]), 1))
            p.drawLine(QPointF(0, y - self.GAP / 2), QPointF(self.width(), y - self.GAP / 2))
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            p.setFont(bold)
            p.setPen(QColor(C["text"]))
            p.drawText(QRectF(0, y, name_w, self.ROW),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Total")
            mono = theme.mono(9.5)
            mono.setWeight(QFont.Weight.DemiBold)
            p.setFont(mono)
            p.drawText(QRectF(bar_x + bar_w + 12, y, hours_w, self.ROW), right, fmt_hm(secs))
            p.setFont(bold)
            p.drawText(QRectF(bar_x + bar_w + 12 + hours_w, y, amount_w, self.ROW), right, amount)


class StackedStrip(QWidget):
    """One horizontal bar split by share (clients)."""

    def __init__(self):
        super().__init__()
        self.parts: list[tuple[str, str, int]] = []
        self.setFixedHeight(18)
        self.setMouseTracking(True)
        self._hits: list[tuple[QRectF, str]] = []

    def set(self, parts) -> None:
        self.parts = parts
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(s for _, _, s in self.parts) or 1
        x, gap = 0.0, 3
        self._hits = []
        usable = self.width() - gap * max(0, len(self.parts) - 1)
        for name, color, secs in self.parts:
            w = usable * secs / total
            r = QRectF(x, 0, max(3.0, w), self.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(r, 2, 2)
            self._hits.append((r, f"{name}: {fmt_words(secs)} ({secs / total:.0%})"))
            x += w + gap

    def mouseMoveEvent(self, event) -> None:
        for r, tip in self._hits:
            if r.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return


# ------------------------------------------------------------------ page
class InsightsPage(QWidget):
    title = "Insights"

    def __init__(self, ctl):
        super().__init__()
        self.ctl, self.db = ctl, ctl.db
        self.kind, self.anchor, self.group = "month", date.today(), "project"
        self.entries: list = []
        dpr = self.devicePixelRatioF()

        self.title_label = label("", "H1")
        self.period_seg = segmented([("week", "Week"), ("month", "Month"), ("quarter", "Quarter"),
                                     ("year", "Year")], self.kind, self._set_kind)
        nav = [nav_button("left", "Previous", lambda: self._shift(-1), dpr),
               nav_button("chevron", "Next", lambda: self._shift(1), dpr)]
        self.client_combo = QComboBox()
        self.project_combo = QComboBox()
        for c in (self.client_combo, self.project_combo):
            c.setMinimumWidth(150)
        export = button("Export", name="MenuButton")
        export.setIcon(hover_icon("download", dpr, 16))
        export.setIconSize(QSize(16, 16))
        menu = QMenu(export)
        menu.addAction("Excel workbook (.xlsx)…", self.export_excel)
        menu.addAction("CSV, all entries…", self.export_csv)
        export.setMenu(menu)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.period_seg)
        for b in nav:
            header.addWidget(b)
        header.addWidget(self.client_combo)
        header.addWidget(self.project_combo)
        header.addWidget(export)

        # KPI cards
        self.kpis = {}
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (key, title) in enumerate((("tracked", "Tracked"), ("billable", "Billable"),
                                          ("workday", "Per workday"), ("focus", "Focus sessions"))):
            box = card()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(18, 14, 18, 16)
            bl.setSpacing(4)
            head = QHBoxLayout()
            head.setSpacing(6)
            if key == "focus":
                ic = label()
                ic.setPixmap(tomato_pixmap(16, dpr))
                head.addWidget(ic)
            head.addWidget(label(title, "Muted"))
            head.addStretch(1)
            value, note = label("", "MonoBig"), label("", "Small")
            bl.addLayout(head)
            bl.addWidget(value)
            bl.addWidget(note)
            self.kpis[key] = (value, note)
            grid.addWidget(box, 0, i)

        # Heatmap
        heat_card = card()
        hl = QVBoxLayout(heat_card)
        hl.setContentsMargins(20, 16, 20, 18)
        hl.setSpacing(12)
        hl.addWidget(label("Every day, last 12 weeks", "H3"))
        self.heatmap = Heatmap()
        hl.addWidget(self.heatmap)
        legend = QHBoxLayout()
        legend.setSpacing(5)
        legend.addWidget(label("Less", "Small"))
        for c in HEAT:
            sw = QWidget()
            sw.setFixedSize(13, 13)
            sw.setStyleSheet(f"background: {c}; border-radius: 2px;")
            legend.addWidget(sw)
        legend.addWidget(label("More", "Small"))
        legend.addStretch(1)
        hl.addLayout(legend)
        hl.addStretch(1)
        heat_card.setFixedWidth(self.heatmap.width() + 40)

        # Where the time went + by client
        where = card()
        wl = QVBoxLayout(where)
        wl.setContentsMargins(20, 16, 20, 18)
        wl.setSpacing(12)
        wh = QHBoxLayout()
        wh.addWidget(label("Where the time went", "H3"), 1)
        self.group_seg = segmented([("project", "Projects"), ("client", "Clients"), ("task", "Tasks")],
                                   self.group, self._set_group)
        wh.addWidget(self.group_seg)
        wl.addLayout(wh)
        self.bars = RankedBars()
        wl.addWidget(self.bars)
        wl.addSpacing(14)
        wl.addWidget(label("By client", "H3"))
        self.strip = StackedStrip()
        wl.addWidget(self.strip)
        self.strip_legend = label("", "Small")
        self.strip_legend.setWordWrap(True)
        wl.addWidget(self.strip_legend)
        wl.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(heat_card)
        bottom.addWidget(where, 1)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(30, 26, 30, 22)
        root.setSpacing(16)
        root.addLayout(header)
        root.addLayout(grid)
        root.addLayout(bottom, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.client_combo.currentIndexChanged.connect(self._on_client)
        self.project_combo.currentIndexChanged.connect(self.refresh_data)

    # ------------------------------------------------------------ filters
    def _set_kind(self, kind: str) -> None:
        self.kind = kind
        self.refresh_data()

    def _set_group(self, group: str) -> None:
        self.group = group
        self.refresh_data()

    def _shift(self, step: int) -> None:
        self.anchor = shift_anchor(self.kind, self.anchor, step)
        self.refresh_data()

    def _fill_filters(self) -> None:
        cur = self.client_combo.currentData()
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("All clients", ALL)
        self.client_combo.addItem("Without client", NONE)
        for c in self.db.clients(include_archived=True):
            self.client_combo.addItem(c["name"], c["id"])
        self.client_combo.setCurrentIndex(max(0, self.client_combo.findData(cur)))
        self.client_combo.blockSignals(False)
        self._fill_projects()

    def _fill_projects(self) -> None:
        cur = self.project_combo.currentData()
        client = self.client_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("All projects", ALL)
        if client in (ALL, None):
            self.project_combo.addItem("Without project", NONE)
        for p in self.db.projects(include_archived=True):
            if client == NONE and p["client_id"] is not None:
                continue
            if client not in (ALL, NONE, None) and p["client_id"] != client:
                continue
            self.project_combo.addItem(color_icon(p["color"]), p["name"], p["id"])
        self.project_combo.setCurrentIndex(max(0, self.project_combo.findData(cur)))
        self.project_combo.blockSignals(False)

    def _on_client(self) -> None:
        self._fill_projects()
        self.refresh_data()

    def _filters(self) -> dict:
        kwargs = {}
        for name, combo in (("client_id", self.client_combo), ("project_id", self.project_combo)):
            v = combo.currentData()
            if v == NONE:
                kwargs[name] = None
            elif v not in (ALL, None):
                kwargs[name] = v
        return kwargs

    def _range(self) -> tuple[date, date]:
        return period_range(self.kind, self.anchor)

    def _query(self, d0: date, d1: date) -> list:
        return self.db.entries(day_start_ts(d0), day_start_ts(d1 + timedelta(days=1)), **self._filters())

    # ------------------------------------------------------------ data
    def refresh(self) -> None:
        self._fill_filters()
        self.refresh_data()

    def refresh_data(self) -> None:
        d0, d1 = self._range()
        cur = self.db.currency
        self.period_seg.buttons[self.kind].setChecked(True)
        self.group_seg.buttons[self.group].setChecked(True)
        self.title_label.setText({
            "week": f"Insights · {d0.day} {d0:%b} – {d1.day} {d1:%b}",
            "month": f"Insights · {d0:%B} {d0.year}",
            "quarter": f"Insights · Q{(d0.month - 1) // 3 + 1} {d0.year}",
            "year": f"Insights · {d0.year}"}[self.kind])
        self.entries = self._query(d0, d1)
        total = sum(self.db.duration(e) for e in self.entries)
        amounts = self.db.amounts(self.entries)

        # Tracked, with change vs the previous period of the same kind
        p0, p1 = period_range(self.kind, shift_anchor(self.kind, d0, -1))
        prev = sum(self.db.duration(e) for e in self._query(p0, p1))
        if prev:
            change = (total - prev) / prev
            note = f"{change:+.0%} vs previous {self.kind}"
        else:
            note = f"nothing in the previous {self.kind}"
        self._kpi("tracked", fmt_words(total), note)

        billed: dict[str, int] = {}          # seconds with a rate, per currency
        for e in self.entries:
            if self.db.rate_of(e):
                code = self.db.currency_of(e)
                billed[code] = billed.get(code, 0) + self.db.duration(e)
        order = self.db.currencies
        avg = {code: amounts.get(code, 0.0) / (secs / 3600) for code, secs in billed.items() if secs}
        self._kpi("billable", fmt_amounts(amounts, short=len(amounts) > 1, order=order, empty="—"),
                  (fmt_amounts(avg, order=order) + " per hour on average") if avg else "no rates set")

        per_day: dict[date, int] = {}
        for e in self.entries:
            d = datetime.fromtimestamp(e["start_ts"]).date()
            per_day[d] = per_day.get(d, 0) + self.db.duration(e)
        if per_day:
            best = max(per_day, key=per_day.get)
            self._kpi("workday", fmt_words(total / len(per_day)),
                      f"{len(per_day)} days tracked · longest {best:%a} {best.day} {fmt_words(per_day[best])}")
        else:
            self._kpi("workday", "—", "no days tracked")

        sessions = self.db.focus_sessions(day_start_ts(d0), day_start_ts(d1 + timedelta(days=1)))
        taken = sum(1 for s in sessions if s["outcome"] == "break")
        self._kpi("focus", str(len(sessions)),
                  f"{taken} with a break · {len(sessions) - taken} skipped" if sessions
                  else "turn on Pomodoro to count them")

        # Heatmap: last 12 weeks up to the period end (or today)
        end = min(d1, date.today())
        h0 = week_start(end) - timedelta(weeks=11)
        heat: dict[date, float] = {}
        for e in self._query(h0, end):
            d = datetime.fromtimestamp(e["start_ts"]).date()
            heat[d] = heat.get(d, 0.0) + self.db.duration(e) / 3600
        self.heatmap.set(end, heat)

        self._fill_bars(cur)
        self._fill_strip()

    def _kpi(self, key: str, value: str, note: str) -> None:
        v, n = self.kpis[key]
        v.setText(value)
        n.setText(note)

    def _group_key(self, e) -> tuple:
        if self.group == "client":
            return (e["client_id"],), e["client_name"] or "Without client", ""
        if self.group == "task":
            name = (f"{e['project_name']}: {e['task_name']}" if e["task_name"]
                    else (e["project_name"] or "No project"))
            return (e["project_id"], e["task_id"]), name, e["project_color"] or NO_COLOR
        return (e["project_id"],), e["project_name"] or "No project", e["project_color"] or NO_COLOR

    def _groups(self) -> list[dict]:
        groups: dict = {}
        for e in self.entries:
            key, name, color = self._group_key(e)
            g = groups.setdefault(key, {"name": name, "color": color, "seconds": 0, "amount": {}})
            g["seconds"] += self.db.duration(e)
            for code, value in self.db.amounts([e]).items():
                g["amount"][code] = g["amount"].get(code, 0.0) + value
        out = sorted(groups.values(), key=lambda g: -g["seconds"])
        for i, g in enumerate(out):
            g["color"] = g["color"] or PALETTE[i % len(PALETTE)]
        return out

    def _fill_bars(self, cur: str) -> None:
        groups = self._groups()
        order = self.db.currencies
        rows = [(g["name"], g["color"], g["seconds"],
                 fmt_amounts(g["amount"], short=len(g["amount"]) > 1, order=order, empty="—"))
                for g in groups[:9]]
        rest = groups[9:]
        if rest:
            merged = self._merge([g["amount"] for g in rest])
            rows.append((f"{len(rest)} more", "#555555", sum(g["seconds"] for g in rest),
                         fmt_amounts(merged, short=len(merged) > 1, order=order, empty="—")))
        everything = self._merge([g["amount"] for g in groups])
        total = (sum(g["seconds"] for g in groups),
                 fmt_amounts(everything, short=len(everything) > 1, order=order, empty="—"))
        self.bars.set(rows, total)

    @staticmethod
    def _merge(amounts: list[dict]) -> dict:
        out: dict[str, float] = {}
        for a in amounts:
            for code, value in a.items():
                out[code] = out.get(code, 0.0) + value
        return out

    def _fill_strip(self) -> None:
        per: dict = {}
        for e in self.entries:
            k = e["client_id"]
            item = per.setdefault(k, [e["client_name"] or "No client", 0])
            item[1] += self.db.duration(e)
        ranked = sorted(per.values(), key=lambda x: -x[1])
        colors = ["#2196f3", "#ab47bc", "#ff9800", "#26a69a", "#ec407a", "#7cb342", "#8d6e63"]
        parts = [(name, colors[i % len(colors)], secs) for i, (name, secs) in enumerate(ranked)]
        self.strip.set(parts)
        dots = [f'<span style="color:{c}">●</span> {n} · {fmt_words(s)}' for n, c, s in parts]
        self.strip_legend.setText("&nbsp;&nbsp;&nbsp;".join(dots) if parts else "")

    # ------------------------------------------------------------ export
    def _file_name(self, ext: str) -> str:
        d0, d1 = self._range()
        return f"SD_Time_report_{d0:%Y-%m-%d}_{d1:%Y-%m-%d}.{ext}"

    def _detail_rows(self) -> list[list]:
        rows = []
        for e in self.entries:
            sec = self.db.duration(e)
            rows.append([fmt_date(e["start_ts"]), fmt_time(e["start_ts"]),
                         fmt_time(e["end_ts"]) if e["end_ts"] is not None else "running",
                         sec, e["client_name"] or "", e["project_name"] or "", e["task_name"] or "",
                         e["description"], self.db.rate_of(e), self.db.amount(e),
                         self.db.currency_of(e) if self.db.rate_of(e) else ""])
        return rows

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", self._file_name("csv"), "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Date", "Start", "End", "Duration", "Hours", "Client", "Project", "Task",
                            "Description", "Rate", "Amount", "Currency"])
                for r in self._detail_rows():
                    sec = r[3]
                    w.writerow(r[:3] + [fmt_clock(sec), f"{sec / 3600:.2f}"] + r[4:8]
                               + ["" if r[8] is None else f"{r[8]:.2f}", f"{r[9]:.2f}", r[10]])
        except OSError as exc:
            show_error(self, exc)
            return
        QMessageBox.information(self, "SD Time", f"Saved:\n{path}")

    def export_excel(self) -> None:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            show_error(self, "openpyxl is not installed. Run: pip install openpyxl")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", self._file_name("xlsx"),
                                              "Excel workbook (*.xlsx)")
        if not path:
            return
        wb = Workbook()
        head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2B2B2B")

        def header(ws, cols):
            ws.append(cols)
            for c in ws[1]:
                c.font, c.fill = head_font, head_fill

        ws = wb.active
        ws.title = "Summary"
        groups = self._groups()
        totals = self._merge([g["amount"] for g in groups])
        codes = [c for c in self.db.currencies if c in totals] + \
                sorted(c for c in totals if c not in self.db.currencies)
        codes = codes or [self.db.currency]
        header(ws, ["Group", "Duration", "Hours"] + [f"Amount, {c}" for c in codes])
        for g in groups:
            ws.append([g["name"], g["seconds"] / 86400, round(g["seconds"] / 3600, 2)]
                      + [round(g["amount"].get(c, 0.0), 2) for c in codes])
        total = sum(g["seconds"] for g in groups)
        ws.append(["Total", total / 86400, round(total / 3600, 2)]
                  + [round(totals.get(c, 0.0), 2) for c in codes])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
        for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            row[0].number_format = "[h]:mm:ss"
        for col, width in zip("ABCDEFGH", (36, 12, 10, 14, 14, 14, 14, 14)):
            ws.column_dimensions[col].width = width
        ws2 = wb.create_sheet("Detailed")
        header(ws2, ["Date", "Start", "End", "Duration", "Hours", "Client", "Project", "Task",
                     "Description", "Rate / h", "Amount", "Currency"])
        for r in self._detail_rows():
            sec = r[3]
            ws2.append(r[:3] + [sec / 86400, round(sec / 3600, 2)] + r[4:8]
                       + [r[8], round(r[9], 2), r[10]])
        for row in ws2.iter_rows(min_row=2, min_col=4, max_col=4):
            row[0].number_format = "[h]:mm:ss"
        for col, width in zip("ABCDEFGHIJKL", (11, 7, 8, 10, 8, 18, 20, 18, 40, 10, 12, 9)):
            ws2.column_dimensions[col].width = width
        try:
            wb.save(path)
        except OSError as exc:
            show_error(self, exc)
            return
        QMessageBox.information(self, "SD Time", f"Saved:\n{path}")

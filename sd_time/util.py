"""Time/money formatting and period calculations."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta


def day_bounds(d: date) -> tuple[int, int]:
    start = datetime.combine(d, dtime.min)
    end = datetime.combine(d + timedelta(days=1), dtime.min)
    return int(start.timestamp()), int(end.timestamp())


def range_bounds(d0: date, d1: date) -> tuple[int, int]:
    """Bounds of the period from d0 to d1 inclusive."""
    return day_bounds(d0)[0], day_bounds(d1)[1]


def period_dates(key: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if key == "today":
        return today, today
    if key == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if key == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if key == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if key == "month":
        start = today.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        return start, nxt - timedelta(days=1)
    if key == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if key == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    raise ValueError(key)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_duration(text: str) -> int:
    """'1:30' / '1:30:15' / '1.5' (hours) / '90m' / '' -> seconds."""
    text = (text or "").strip().lower().replace(",", ".")
    if not text:
        return 0
    try:
        if ":" in text:
            parts = [int(p or 0) for p in text.split(":")]
            if len(parts) == 2:
                return parts[0] * 3600 + parts[1] * 60
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            raise ValueError
        if text.endswith("m"):
            return int(float(text[:-1]) * 60)
        if text.endswith("h"):
            text = text[:-1]
        return int(round(float(text) * 3600))
    except ValueError:
        raise ValueError(f"Can't read duration: {text!r}. Use 1:30 or 1.5") from None


def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def fmt_clock(seconds: float) -> str:
    """04:12:16"""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def day_title(d: date, today: date | None = None) -> str:
    today = today or date.today()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return f"{d:%a}, {d:%b} {d.day}"


def fmt_words(seconds: float) -> str:
    """3h 12m (or 45m) — for totals in pills and headers."""
    minutes = max(0, int(seconds)) // 60
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fmt_hm(seconds: float) -> str:
    minutes = max(0, int(seconds)) // 60
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02d}"


def fmt_hours(seconds: float) -> str:
    return f"{max(0, seconds) / 3600:.2f}"


def fmt_money(value: float, currency: str = "") -> str:
    text = f"{value:,.2f}"
    return f"{text} {currency}".strip()


def fmt_rate(rate: float | None, currency: str = "") -> str:
    return "—" if rate is None else f"{fmt_money(rate, currency)}/h"


def parse_rate(text: str) -> float | None:
    """'' -> None (inherit); '45', '45.5', '45,5', '1 200' -> float. ValueError otherwise."""
    text = (text or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    value = float(text)
    if value < 0:
        raise ValueError("Rate cannot be negative")
    return value


def fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def fmt_date(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

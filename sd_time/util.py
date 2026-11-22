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


def parse_clock(text: str) -> tuple[int, int]:
    """Time of day as typed: '1245' / '12:45' / '12.45' -> (12, 45); '930' -> (9, 30);
    '9' -> (9, 0). ValueError when it isn't a time."""
    t = (text or "").strip()
    for sep in ".,: ":
        if sep in t:
            parts = [p for p in t.split(sep) if p]
            if len(parts) != 2 or not all(p.isdigit() for p in parts) or len(parts[1]) > 2:
                raise ValueError(f'"{text}" is not a time')
            h, m = int(parts[0]), int(parts[1])
            break
    else:
        if not t.isdigit() or len(t) > 4:
            raise ValueError(f'"{text}" is not a time')
        h, m = (int(t), 0) if len(t) <= 2 else (int(t[:-2]), int(t[-2:]))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f'"{text}" is not a time')
    return h, m


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


def short_money(value: float, currency: str = "") -> str:
    """Whole units from 100 up ("1,240 USD"), cents below ("18.40 USD")."""
    return f"{value:,.0f} {currency}".strip() if value >= 100 else fmt_money(value, currency)


def fmt_amounts(amounts: dict[str, float], short: bool = False, order: list[str] | None = None,
                empty: str = "") -> str:
    """{"USD": 120, "EUR": 40} -> "120.00 USD · 40.00 EUR". Currencies are never added up.
    order: the user's currencies (default first); others follow, largest first."""
    items = [(c, v) for c, v in amounts.items() if v]
    if not items:
        return empty
    rank = {c: i for i, c in enumerate(order or [])}
    items.sort(key=lambda cv: (rank.get(cv[0], len(rank)), -cv[1]))
    fmt = short_money if short else fmt_money
    return " · ".join(fmt(v, c) for c, v in items)


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

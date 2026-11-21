"""Pomodoro cycle: focus -> (ask) -> break or another focus ... long break every N sessions.

Pure state machine, driven by timestamps so it can be restored after a restart.
When focus time is up the cycle waits in ASK for the user's choice: take a break
(the entry is stopped at the focus end) or skip it (the entry keeps running and a
new focus session starts). Breaks are not tracked.
"""
from __future__ import annotations

from dataclasses import dataclass

IDLE, FOCUS, ASK, BREAK = "idle", "focus", "ask", "break"


@dataclass
class PomodoroConfig:
    focus: int = 25 * 60
    short_break: int = 5 * 60
    long_break: int = 15 * 60
    long_every: int = 4
    auto_next: bool = False
    sound: bool = True


class Pomodoro:
    def __init__(self, config: PomodoroConfig | None = None):
        self.config = config or PomodoroConfig()
        self.phase = IDLE
        self.end = 0
        self.count = 0           # finished focus sessions in the current cycle
        self.entry_id: int | None = None
        self.long = False        # current break is a long one

    # ------------------------------------------------------------ transitions
    def begin_focus(self, entry_id: int, now: int) -> None:
        """Timer started. Switching task during focus keeps the countdown."""
        if self.phase != FOCUS:
            self.phase = FOCUS
            self.end = now + self.config.focus
        self.entry_id = entry_id

    def focus_done(self) -> None:
        """Focus time is up: count it and wait for the user's choice. `end` keeps the
        moment focus ended (the entry is stopped there if the user takes a break)."""
        self.count += 1
        self.long = self.count % max(1, self.config.long_every) == 0
        self.phase = ASK

    def next_break_length(self) -> int:
        return self.config.long_break if self.long else self.config.short_break

    def take_break(self, now: int) -> int:
        """User chose a break; it starts now. Returns its length (seconds)."""
        length = self.next_break_length()
        self.phase = BREAK
        self.end = now + length
        self.entry_id = None
        return length

    def skip_break(self, entry_id: int, now: int) -> None:
        """User keeps working: a new focus session starts now on the same entry."""
        self.long = False
        self.phase = FOCUS
        self.end = now + self.config.focus
        self.entry_id = entry_id

    def finish_break(self) -> None:
        self.phase = IDLE
        self.end = 0
        if self.long:
            self.count = 0
            self.long = False

    def interrupt(self) -> None:
        """Timer stopped by hand during focus: this session doesn't count."""
        self.phase = IDLE
        self.end = 0
        self.entry_id = None

    def reset(self) -> None:
        self.interrupt()
        self.count = 0
        self.long = False

    # ----------------------------------------------------------------- query
    def due(self, now: int) -> bool:
        return self.phase in (FOCUS, BREAK) and now >= self.end

    def remaining(self, now: int) -> int:
        return max(0, self.end - now) if self.phase in (FOCUS, BREAK) else 0

    def session_number(self) -> int:
        """1-based number of the current/next focus session within the cycle."""
        every = max(1, self.config.long_every)
        return self.count % every + 1

    def label(self) -> str:
        every = max(1, self.config.long_every)
        if self.phase == FOCUS:
            return f"Focus {self.session_number()}/{every}"
        if self.phase == ASK:
            return "Focus done: break or skip?"
        if self.phase == BREAK:
            return "Long break" if self.long else "Short break"
        return f"Pomodoro {self.session_number()}/{every}"

    # ------------------------------------------------------------- persisting
    def to_dict(self) -> dict:
        return {"phase": self.phase, "end": self.end, "count": self.count,
                "entry_id": self.entry_id or 0, "long": int(self.long)}

    def load(self, data: dict) -> None:
        phase = data.get("phase", IDLE)
        self.phase = phase if phase in (IDLE, FOCUS, ASK, BREAK) else IDLE
        self.end = int(data.get("end") or 0)
        self.count = int(data.get("count") or 0)
        self.entry_id = int(data.get("entry_id") or 0) or None
        self.long = bool(int(data.get("long") or 0))

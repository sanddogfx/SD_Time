import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sd_time.pomodoro import ASK, BREAK, FOCUS, IDLE, Pomodoro, PomodoroConfig  # noqa: E402

M = 60


class TimerKindTest(unittest.TestCase):
    def test_kinds_and_label(self):
        from sd_time.pomodoro import KINDS
        self.assertEqual(list(KINDS), ["tomato", "potato", "cucumber"])
        self.assertEqual((KINDS["potato"].focus, KINDS["cucumber"].focus), (50, 15))
        p = Pomodoro(PomodoroConfig(focus=50 * M, long_every=3, kind="potato"))
        self.assertEqual(p.label(), "Potato 1/3")
        p.begin_focus(1, 0)
        self.assertEqual((p.end, p.label()), (50 * M, "Focus 1/3"))
        self.assertEqual(PomodoroConfig(kind="nope").name, "Pomodoro")   # unknown -> default


class PomodoroTest(unittest.TestCase):
    def setUp(self):
        self.p = Pomodoro(PomodoroConfig(focus=25 * M, short_break=5 * M, long_break=15 * M,
                                         long_every=4))

    def test_focus_ask_then_break(self):
        self.p.begin_focus(1, now=1000)
        self.assertEqual((self.p.phase, self.p.end, self.p.label()), (FOCUS, 1000 + 25 * M, "Focus 1/4"))
        self.assertFalse(self.p.due(1000 + 25 * M - 1))
        self.assertTrue(self.p.due(1000 + 25 * M))
        self.p.focus_done()
        self.assertEqual(self.p.phase, ASK)
        self.assertEqual(self.p.end, 1000 + 25 * M)        # focus end kept for stopping the entry
        self.assertFalse(self.p.due(10 ** 9))              # waits for the user, never "due"
        self.assertEqual(self.p.remaining(10 ** 9), 0)
        # user answers 2 minutes later: break starts from the click
        click = 1000 + 27 * M
        self.assertEqual(self.p.take_break(click), 5 * M)
        self.assertEqual((self.p.phase, self.p.end, self.p.label()), (BREAK, click + 5 * M, "Short break"))
        self.p.finish_break()
        self.assertEqual((self.p.phase, self.p.label()), (IDLE, "Pomodoro 2/4"))

    def test_skip_break_continues_focus(self):
        self.p.begin_focus(1, now=0)
        self.p.focus_done()
        self.p.skip_break(1, now=26 * M)
        self.assertEqual((self.p.phase, self.p.end, self.p.entry_id), (FOCUS, 51 * M, 1))
        self.assertEqual(self.p.label(), "Focus 2/4")      # skipped session still counted

    def test_long_break_every_fourth(self):
        lengths = []
        for i in range(5):
            self.p.begin_focus(1, now=i * 1000)
            self.p.focus_done()
            lengths.append(self.p.take_break(i * 1000 + 1))
            self.p.finish_break()
        self.assertEqual(lengths, [5 * M, 5 * M, 5 * M, 15 * M, 5 * M])
        self.assertEqual(self.p.label(), "Pomodoro 2/4")   # cycle restarted after long break

    def test_switch_task_keeps_countdown(self):
        self.p.begin_focus(1, now=0)
        self.p.begin_focus(2, now=600)
        self.assertEqual((self.p.entry_id, self.p.end), (2, 25 * M))

    def test_start_while_asking_begins_new_focus(self):
        self.p.begin_focus(1, now=0)
        self.p.focus_done()
        self.p.begin_focus(2, now=30 * M)
        self.assertEqual((self.p.phase, self.p.end, self.p.entry_id), (FOCUS, 55 * M, 2))

    def test_interrupt_does_not_count(self):
        self.p.begin_focus(1, now=0)
        self.p.interrupt()
        self.assertEqual((self.p.phase, self.p.count), (IDLE, 0))

    def test_persist_roundtrip(self):
        self.p.begin_focus(7, now=50)
        self.p.focus_done()
        q = Pomodoro(self.p.config)
        q.load({k: str(v) for k, v in self.p.to_dict().items()})   # QSettings returns strings
        self.assertEqual((q.phase, q.end, q.entry_id, q.count), (ASK, 50 + 25 * M, 7, 1))
        q.load({})
        self.assertEqual(q.phase, IDLE)


if __name__ == "__main__":
    unittest.main()

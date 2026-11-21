import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sd_time.pages.week import SNAP, drag_times  # noqa: E402

H = 3600
DAY0 = 86400 * 20000   # any midnight-aligned value
NEXT_DAY0 = DAY0 + 86400
NOW = DAY0 + 20 * H


class DragTimesTest(unittest.TestCase):
    def test_move_keeps_duration_and_snaps(self):
        start, end = DAY0 + 9 * H, DAY0 + 11 * H
        self.assertEqual(drag_times("move", start, end, DAY0, DAY0, 50 * 60, NOW),
                         (DAY0 + 9 * H + 45 * 60, DAY0 + 11 * H + 45 * 60))
        # 7 minutes rounds back to the original slot
        self.assertEqual(drag_times("move", start, end, DAY0, DAY0, 7 * 60, NOW), (start, end))

    def test_move_to_another_day(self):
        start, end = DAY0 + 9 * H, DAY0 + 10 * H
        self.assertEqual(drag_times("move", start, end, DAY0, NEXT_DAY0, -H, NOW),
                         (NEXT_DAY0 + 8 * H, NEXT_DAY0 + 9 * H))

    def test_move_clamped_to_day(self):
        start, end = DAY0 + 1 * H, DAY0 + 2 * H
        self.assertEqual(drag_times("move", start, end, DAY0, DAY0, -5 * H, NOW),
                         (DAY0, DAY0 + H))
        self.assertEqual(drag_times("move", start, end, DAY0, DAY0, 30 * H, NOW)[0],
                         DAY0 + 86400 - SNAP)

    def test_resize_top(self):
        start, end = DAY0 + 9 * H, DAY0 + 11 * H
        self.assertEqual(drag_times("top", start, end, DAY0, DAY0, -30 * 60, NOW),
                         (DAY0 + 8 * H + 30 * 60, end))
        # can't pass the end: at least SNAP remains
        self.assertEqual(drag_times("top", start, end, DAY0, DAY0, 5 * H, NOW),
                         (end - SNAP, end))

    def test_resize_bottom(self):
        start, end = DAY0 + 9 * H, DAY0 + 11 * H
        self.assertEqual(drag_times("bottom", start, end, DAY0, DAY0, 44 * 60, NOW),
                         (start, DAY0 + 11 * H + 45 * 60))
        self.assertEqual(drag_times("bottom", start, end, DAY0, DAY0, -5 * H, NOW),
                         (start, start + SNAP))
        self.assertEqual(drag_times("bottom", start, end, DAY0, DAY0, 30 * H, NOW),
                         (start, DAY0 + 86400))

    def test_running_entry_moves_start_only(self):
        start = DAY0 + 18 * H
        for mode in ("move", "top", "bottom"):
            new_start, new_end = drag_times(mode, start, None, DAY0, NEXT_DAY0, -H, NOW)
            self.assertEqual((new_start, new_end), (DAY0 + 17 * H, None))
        # can't move the start past "now"
        new_start, _ = drag_times("move", start, None, DAY0, DAY0, 5 * H, NOW)
        self.assertEqual(new_start, NOW - 60)


if __name__ == "__main__":
    unittest.main()

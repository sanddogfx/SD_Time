import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sd_time.updates import is_newer, parse_version  # noqa: E402


class VersionTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_version("v0.4.0"), (0, 4, 0))
        self.assertEqual(parse_version("1.2"), (1, 2, 0))
        self.assertEqual(parse_version(" v10.0.3 "), (10, 0, 3))
        for bad in ("", "latest", "v1", "v1.2.3-beta", "1.2.3.4", None):
            self.assertIsNone(parse_version(bad), bad)

    def test_newer(self):
        self.assertTrue(is_newer("v0.5.0", "0.4.0"))
        self.assertTrue(is_newer("v0.4.1", "0.4.0"))
        self.assertTrue(is_newer("v0.10.0", "0.9.9"))       # numbers, not text
        self.assertFalse(is_newer("v0.4.0", "0.4.0"))
        self.assertFalse(is_newer("v0.3.9", "0.4.0"))
        self.assertFalse(is_newer("nightly", "0.4.0"))


if __name__ == "__main__":
    unittest.main()

"""Aufräumen temporärer Testdatenbanken: Wiederholung bei Nachzügler-Dateien (CI-Fehler 2.0.0-dev20, test_ui_workday)."""
import errno
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402


class Flaky:
    def __init__(self, errors):
        self.errors, self.calls = list(errors), 0

    def cleanup(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


class CleanupTests(unittest.TestCase):
    def test_retries_when_directory_refills(self):
        tmp = Flaky([OSError(errno.ENOTEMPTY, 'Directory not empty'), PermissionError(13, 'gesperrt')])
        cleanup_tmp(tmp, attempts=5, pause=0)
        self.assertEqual(tmp.calls, 3)

    def test_other_errors_are_not_hidden(self):
        with self.assertRaises(OSError):
            cleanup_tmp(Flaky([OSError(errno.EIO, 'E/A-Fehler')]), attempts=5, pause=0)
        with self.assertRaises(OSError):
            cleanup_tmp(Flaky([OSError(errno.ENOTEMPTY, 'x')] * 3), attempts=3, pause=0)


if __name__ == '__main__':
    unittest.main()

"""
Tests for io/logging.py's logging.enabled config off-switch.

append_line_to_log() is the single choke point every caller (the GUI's
Status/Log panel persistence via mainwindow_qt.py's _persist_log_message(),
and append_to_log()'s structured measurement entries) goes through, so
gating it there is enough to make the whole application log respect the
setting without each caller checking it individually.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.io import logging as eqe_logging


class IsEnabledTests(unittest.TestCase):
    def test_defaults_true_when_key_missing(self):
        with mock.patch.object(eqe_logging, "load_config", return_value={}):
            self.assertTrue(eqe_logging.is_enabled())

    def test_respects_explicit_false(self):
        config = {"logging": {"enabled": False}}
        with mock.patch.object(eqe_logging, "load_config", return_value=config):
            self.assertFalse(eqe_logging.is_enabled())

    def test_respects_explicit_true(self):
        config = {"logging": {"enabled": True}}
        with mock.patch.object(eqe_logging, "load_config", return_value=config):
            self.assertTrue(eqe_logging.is_enabled())


class AppendLineToLogGatingTests(unittest.TestCase):
    def test_skips_write_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            logfile = Path(tmp) / "test.log"
            with mock.patch.object(eqe_logging, "is_enabled", return_value=False):
                returned = eqe_logging.append_line_to_log(
                    "should not be written", logfile=logfile
                )

            # Still returns the path -- callers using the return value
            # shouldn't need to special-case a disabled log.
            self.assertEqual(returned, logfile)
            self.assertFalse(logfile.exists())

    def test_writes_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            logfile = Path(tmp) / "test.log"
            with mock.patch.object(eqe_logging, "is_enabled", return_value=True):
                eqe_logging.append_line_to_log("hello", logfile=logfile)

            self.assertIn("hello", logfile.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

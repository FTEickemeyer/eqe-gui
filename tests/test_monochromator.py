"""
Tests for core/instruments/monochromator.py's Cornerstone130 retry/flush
robustness (added 2026-11-02, see CLAUDE.md) -- added after a real-hardware
crash where one comms hiccup (an empty or stale/garbled serial reply) left
the connection permanently desynced for the rest of the session, so every
later command kept reading leftover text and crashing with an
unrelated-looking ValueError.

Cornerstone130 is built without calling its real __init__ (which opens an
actual serial.Serial(port) -- no hardware available here) and given a
FakeSerialPort double instead, so these exercise write()/command()/
query()/_query_numeric() directly against controlled, scripted replies.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.core.instruments.monochromator import Cornerstone130, MonochromatorCommError


class FakeSerialPort:
    """Minimal stand-in for serial.Serial, scripted with queued replies."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.written = []
        self.reset_calls = 0
        self.is_open = True

    def write(self, data):
        self.written.append(data)
        return len(data)

    def read_until(self, terminator):
        if self._replies:
            return self._replies.pop(0)
        return b""

    def reset_input_buffer(self):
        self.reset_calls += 1

    def close(self):
        self.is_open = False


def make_mono(replies, filter_position=3):
    """
    Build a Cornerstone130 bypassing __init__ (no real serial port), with
    its _com swapped for a FakeSerialPort scripted with `replies` --
    raw bytes as Cornerstone130.read() would receive them, one per
    read_until() call. `filter_position` seeds self.filter directly
    (normally set from a real filter_wheel_position query in __init__).
    """
    mono = Cornerstone130.__new__(Cornerstone130)
    mono.port = "COMFAKE"
    mono.term_chars = "\r\n"
    mono.encoding = "utf-8"
    mono.grating_change_nm = 850
    mono.filter = filter_position
    mono._com = FakeSerialPort(replies)
    return mono


class WriteFlushesInputBufferTests(unittest.TestCase):
    def test_write_flushes_before_every_send(self):
        mono = make_mono([b"OK\r\n"])
        mono.command("abort")
        self.assertEqual(mono._com.reset_calls, 1)


class CommandRetryTests(unittest.TestCase):
    def test_returns_reply_on_first_try(self):
        mono = make_mono([b"OK\r\n"])
        self.assertEqual(mono.command("abort"), "OK")
        self.assertEqual(len(mono._com.written), 1)

    def test_retries_once_on_empty_reply(self):
        # First attempt times out (empty read); second succeeds.
        mono = make_mono([b"", b"OK\r\n"])
        self.assertEqual(mono.command("abort"), "OK")
        self.assertEqual(len(mono._com.written), 2)
        # write() flushes before each send, including the retry.
        self.assertEqual(mono._com.reset_calls, 2)

    def test_raises_after_two_empty_replies(self):
        mono = make_mono([b"", b""])
        with self.assertRaises(MonochromatorCommError):
            mono.command("abort")


class QueryRetryTests(unittest.TestCase):
    def test_returns_response_on_first_try(self):
        mono = make_mono([b"WAVE?\r\n", b"550.000\r\n"])
        resp = mono.query("wave")
        self.assertEqual(resp.statement, "WAVE?")
        self.assertEqual(resp.response, "550.000")

    def test_retries_once_when_response_line_is_empty(self):
        # First attempt: statement arrives but the response line never
        # does (empty read, e.g. a timeout). Second attempt: clean.
        mono = make_mono([b"WAVE?\r\n", b"", b"WAVE?\r\n", b"550.000\r\n"])
        resp = mono.query("wave")
        self.assertEqual(resp.response, "550.000")

    def test_raises_after_persistent_empty_reply(self):
        mono = make_mono([b"", b"", b"", b""])
        with self.assertRaises(MonochromatorCommError):
            mono.query("wave")


class QueryNumericRetryTests(unittest.TestCase):
    def test_parses_clean_reply(self):
        mono = make_mono([b"FILTER?\r\n", b"3\r\n"])
        self.assertEqual(mono.filter_wheel_position, 3)

    def test_retries_on_garbled_but_nonempty_reply(self):
        # Simulates the real-hardware failure: the first reply is stale
        # leftover text from an earlier command (non-empty, so query()
        # itself can't tell it's wrong) -- int() fails to parse it, so
        # _query_numeric() retries with a fresh query().
        mono = make_mono([
            b"FILTER?\r\n", b"SHUTTER C\r\n",
            b"FILTER?\r\n", b"3\r\n",
        ])
        self.assertEqual(mono.filter_wheel_position, 3)

    def test_raises_after_persistent_garbage(self):
        mono = make_mono([
            b"FILTER?\r\n", b"SHUTTER C\r\n",
            b"FILTER?\r\n", b"SHUTTER C\r\n",
        ])
        with self.assertRaises(MonochromatorCommError):
            mono.filter_wheel_position

    def test_grating_parses_three_fields(self):
        mono = make_mono([b"GRAT?\r\n", b"1,1200,Grating 1\r\n"])
        grating = mono.grating
        self.assertEqual(grating["number"], 1)
        self.assertEqual(grating["lines"], 1200)
        self.assertEqual(grating["label"], "Grating 1")

    def test_grating_retries_on_malformed_reply(self):
        # Fewer than 3 comma-separated fields -> IndexError -> retried.
        mono = make_mono([
            b"GRAT?\r\n", b"SHUTTER?\r\n",
            b"GRAT?\r\n", b"1,1200,Grating 1\r\n",
        ])
        grating = mono.grating
        self.assertEqual(grating["number"], 1)


if __name__ == "__main__":
    unittest.main()

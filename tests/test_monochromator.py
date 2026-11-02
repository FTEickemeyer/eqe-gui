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

import serial

from eqe.core.instruments.monochromator import Cornerstone130, MonochromatorCommError


class FakeSerialPort:
    """
    Minimal stand-in for serial.Serial, scripted with queued replies and
    (optionally) write-time exceptions -- e.g. serial.SerialTimeoutException,
    confirmed on real hardware (2026-11-02) to be raised by an actual
    Cornerstone130 write() call, not just a slow/missing read.
    """

    def __init__(self, replies, write_errors=None):
        self._replies = list(replies)
        self._write_errors = list(write_errors) if write_errors else []
        self.written = []
        self.reset_calls = 0
        self.reset_output_calls = 0
        self.is_open = True

    def write(self, data):
        if self._write_errors:
            err = self._write_errors.pop(0)
            if err is not None:
                raise err
        self.written.append(data)
        return len(data)

    def read_until(self, terminator):
        if self._replies:
            return self._replies.pop(0)
        return b""

    def reset_input_buffer(self):
        self.reset_calls += 1

    def reset_output_buffer(self):
        self.reset_output_calls += 1

    def close(self):
        self.is_open = False


def make_mono(replies, filter_position=3, write_errors=None):
    """
    Build a Cornerstone130 bypassing __init__ (no real serial port), with
    its _com swapped for a FakeSerialPort scripted with `replies` --
    raw bytes as Cornerstone130.read() would receive them, one per
    read_until() call -- and optionally `write_errors`, exceptions (or
    None for a normal send) raised on successive write() calls instead.
    `filter_position` seeds self.filter directly (normally set from a
    real filter_wheel_position query in __init__).
    """
    mono = Cornerstone130.__new__(Cornerstone130)
    mono.port = "COMFAKE"
    mono.term_chars = "\r\n"
    mono.encoding = "utf-8"
    mono.grating_change_nm = 850
    mono.filter = filter_position
    mono._com = FakeSerialPort(replies, write_errors=write_errors)
    # Instance override: skip the real backoff delay between retries so
    # these tests stay fast -- the retry *count*/behavior is what's
    # under test, not the real timing.
    mono._COMM_RETRY_DELAY_S = 0
    return mono


class WriteFlushesBuffersTests(unittest.TestCase):
    def test_write_flushes_input_and_output_before_every_send(self):
        mono = make_mono([b"OK\r\n"])
        mono.command("abort")
        self.assertEqual(mono._com.reset_calls, 1)
        self.assertEqual(mono._com.reset_output_calls, 1)


class CommandRetryTests(unittest.TestCase):
    def test_returns_reply_on_first_try(self):
        mono = make_mono([b"OK\r\n"])
        self.assertEqual(mono.command("abort"), "OK")
        self.assertEqual(len(mono._com.written), 1)

    def test_retries_on_empty_reply(self):
        # First three attempts time out (empty read); the fourth succeeds
        # -- exercises using up all but the last of the 4 total attempts.
        mono = make_mono([b"", b"", b"", b"OK\r\n"])
        self.assertEqual(mono.command("abort"), "OK")
        self.assertEqual(len(mono._com.written), 4)
        # write() flushes before each send, including every retry.
        self.assertEqual(mono._com.reset_calls, 4)

    def test_retries_on_write_timeout(self):
        # Confirmed on real hardware (2026-11-02): the write() call
        # itself can raise SerialTimeoutException, not just a slow read.
        mono = make_mono(
            [b"OK\r\n"],
            write_errors=[serial.SerialTimeoutException("Write timeout")],
        )
        self.assertEqual(mono.command("abort"), "OK")
        self.assertEqual(len(mono._com.written), 1)

    def test_raises_after_exhausting_write_timeout_retries(self):
        mono = make_mono(
            [],
            write_errors=[serial.SerialTimeoutException("Write timeout")] * 4,
        )
        with self.assertRaises(MonochromatorCommError):
            mono.command("abort")

    def test_raises_after_exhausting_empty_reply_retries(self):
        mono = make_mono([b"", b"", b"", b""])
        with self.assertRaises(MonochromatorCommError):
            mono.command("abort")


class QueryRetryTests(unittest.TestCase):
    def test_returns_response_on_first_try(self):
        mono = make_mono([b"WAVE?\r\n", b"550.000\r\n"])
        resp = mono.query("wave")
        self.assertEqual(resp.statement, "WAVE?")
        self.assertEqual(resp.response, "550.000")

    def test_retries_when_response_line_is_empty(self):
        # First attempt: statement arrives but the response line never
        # does (empty read, e.g. a timeout). Second attempt: clean.
        mono = make_mono([b"WAVE?\r\n", b"", b"WAVE?\r\n", b"550.000\r\n"])
        resp = mono.query("wave")
        self.assertEqual(resp.response, "550.000")

    def test_raises_after_exhausting_empty_reply_retries(self):
        mono = make_mono([b"", b""] * 4)
        with self.assertRaises(MonochromatorCommError):
            mono.query("wave")

    def test_retries_on_write_timeout(self):
        mono = make_mono(
            [b"WAVE?\r\n", b"550.000\r\n"],
            write_errors=[serial.SerialTimeoutException("Write timeout")],
        )
        resp = mono.query("wave")
        self.assertEqual(resp.response, "550.000")


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

    def test_raises_after_exhausting_garbage_retries(self):
        mono = make_mono([b"FILTER?\r\n", b"SHUTTER C\r\n"] * 4)
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

import time
import serial
from collections import namedtuple
from typing import Dict, Union

Response = namedtuple("Response", ["statement", "response"])


class MonochromatorCommError(RuntimeError):
    """
    Raised when the Cornerstone 130 still hasn't given a usable reply
    after one flush-and-retry (see Cornerstone130.write()/_query_numeric()).
    Distinct from the ValueError a caller would otherwise get from trying
    to int()/float() a garbled reply, so it's clear this is a genuine
    comms failure rather than e.g. a bad argument.
    """


class Cornerstone130:
    """
    Monochromator driver for the Oriel Cornerstone 130.

    Typical use:
        mono = Cornerstone130("COM2")
        mono.shutter(True)   # close shutter
        mono.shutter(False)  # open shutter
        mono.goto_nm(800)
        mono.disconnect()
    """

    def __init__(self, port: str, timeout: int = 5, grating_change_nm: int = 850):
        self.port = port
        self.term_chars = "\r\n"
        self.encoding = "utf-8"
        self._com = serial.Serial(port, timeout=timeout)
        self.filter = self.filter_wheel_position
        self.grating_change_nm = grating_change_nm

    def __del__(self):
        com = self.__dict__.get("_com", None)
        if com is not None:
            try:
                if com.is_open:
                    com.close()
            except Exception:
                pass

    def __getattr__(self, attr: str):
        return getattr(self._com, attr)

    def close(self):
        """Compatibility close method."""
        self.disconnect()

    # --- low-level methods ---

    def connect(self):
        self._com.open()

    def disconnect(self):
        self._com.close()

    def write(self, msg: str) -> int:
        # Discard anything already sitting in the input or output buffer
        # before sending a new command. In a correctly-synced exchange
        # nothing should be in the input buffer -- every earlier
        # command()/query() call's own read(s) already blocked until
        # they consumed a full terminator-delimited line (or gave up
        # after the serial timeout). If something IS there anyway -- a
        # short/garbled reply, or leftover bytes from an earlier comms
        # hiccup -- leaving it would get it misread as part of *this*
        # command's response, permanently shifting every later read for
        # the rest of the session instead of just this one call being
        # affected. Confirmed on real hardware (2026-11-02): once one
        # query got an empty/garbled reply, every subsequent command
        # kept reading stale leftover text (e.g. a prior shutter
        # command's own echo) and crashing with an unrelated-looking
        # ValueError. The output buffer is flushed too, so a byte-level
        # write timeout that only got part of a previous message out
        # (see below) can't have the rest of it trail into this send.
        try:
            self._com.reset_input_buffer()
            self._com.reset_output_buffer()
        except Exception:
            pass
        msg += self.term_chars
        msg = msg.upper()
        msg = msg.encode(self.encoding)
        return self._com.write(msg)

    def read(self) -> str:
        resp = self._com.read_until(self.term_chars.encode(self.encoding))
        return resp.decode(self.encoding)

    def command(self, cmd: str, *args) -> str:
        args = map(str, args)
        msg = cmd + " " + " ".join(args)
        resp = ""
        last_error = None
        for attempt in range(2):
            try:
                self.write(msg)
                resp = self.read().rstrip()
            except serial.SerialException as e:
                # e.g. SerialTimeoutException from a write that didn't
                # complete in time -- confirmed on real hardware
                # (2026-11-02). write() flushes both buffers again on
                # retry, in case this one left a partial message queued.
                last_error = e
                resp = ""
                continue
            if resp:
                return resp
            # Empty reply -- nothing arrived within the serial read
            # timeout. One retry (write() flushes the buffers again
            # first) recovers from a one-off hiccup.
        raise MonochromatorCommError(
            f"No reply from monochromator on {self.port} to {msg!r} "
            f"after retrying." + (f" ({last_error})" if last_error else "")
        )

    def query(self, msg: str) -> Response:
        if msg[-1] != "?":
            msg += "?"

        statement = response = ""
        last_error = None
        for attempt in range(2):
            try:
                self.write(msg)
                statement = self.read().rstrip()
                response = self.read().rstrip()
            except serial.SerialException as e:
                last_error = e
                statement = response = ""
                continue
            if statement and response:
                return Response(statement=statement, response=response)
        raise MonochromatorCommError(
            f"No usable reply from monochromator on {self.port} to "
            f"{msg!r} after retrying (got statement={statement!r}, "
            f"response={response!r})."
            + (f" ({last_error})" if last_error else "")
        )

    def _query_numeric(self, msg: str, parse):
        """
        query() plus parsing, retried once if `parse` raises. Covers the
        failure mode query() itself can't detect on its own: a reply
        that's present (so query() returns normally) but not what was
        asked for -- e.g. stale leftover text from an earlier comms
        hiccup (see write()) landing in the response instead of the
        real value. A ValueError/IndexError from `parse` here means the
        reply wasn't usable; one retry (a fresh query(), which re-flushes
        the input buffer via write()) recovers from a one-off hiccup
        instead of propagating a cryptic ValueError.
        """
        last_error = None
        for attempt in range(2):
            resp = self.query(msg)
            try:
                return parse(resp)
            except (ValueError, IndexError) as e:
                last_error = e
        raise MonochromatorCommError(
            f"Monochromator on {self.port} gave an unusable reply to "
            f"{msg!r} after retrying ({last_error})."
        )

    # --- high-level methods ---

    @property
    def info(self) -> str:
        resp = self.query("info")
        return resp.response

    @property
    def position(self) -> float:
        return self._query_numeric("wave", lambda resp: float(resp.response))

    def step(self, steps: int):
        self.command("step", steps)

    def abort(self):
        self.command("abort")

    @property
    def grating(self) -> Dict[str, Union[str, int]]:
        def parse(resp):
            parts = resp.response.split(",")
            return {
                "number": int(parts[0]),
                "lines": int(parts[1]),
                "label": parts[2],
            }

        return self._query_numeric("grat", parse)

    def set_grating(self, grating: int):
        self.command("grat", grating)

    @property
    def filter_wheel_position(self) -> int:
        return self._query_numeric("filter", lambda resp: int(resp.response))

    def set_filter(self, pos: int):
        self._validate_filter(pos)
        self.command("filter", pos)
        self.filter = pos

    def filter_label(self, filter: int, label: Union[None, str] = None) -> str:
        self._validate_filter(filter)
        cmd = f"filter{filter}label"

        if label is not None:
            if len(label) > 8:
                raise ValueError("Label is too long, must be less than 9 characters.")
            self.command(cmd, label)

        resp = self.query(cmd)
        return resp.response

    @property
    def shuttered(self) -> bool:
        resp = self.query("shutter")
        return resp.response == "C"

    def shutter(self, close: bool = True):
        cmd = "C" if close else "O"
        self.command("shutter", cmd)

    @property
    def outport(self) -> int:
        return self._query_numeric("outport", lambda resp: int(resp.response))

    def set_outport(self, port: int):
        self.command("outport", port)

    def slit_width(self, slit: int, width: Union[int, None] = None) -> int:
        cmd = f"slit{slit}microns"
        if width is not None:
            self.command(cmd, width)

        return self._query_numeric(cmd, lambda resp: int(resp.response))

    @staticmethod
    def _validate_filter(pos: int) -> bool:
        min_val = 1
        max_val = 6
        if (pos < min_val) or (pos > max_val):
            raise ValueError(f"Invalid filter value. Must be between {min_val} and {max_val}.")
        return True

    def goto(self, nm: float):
        wavelength = f"{nm:.3f}"
        self.command("gowave", wavelength)

    def goto_nm(self, nm: float, on_status=None, wait: bool = True):
        def emit_status(message: str):
            if on_status is not None:
                on_status(message)

        if 0 <= nm <= 1200:
            if nm < 680:
                if self.filter == 3:
                    emit_status("Switching filter...")
                    self.set_filter(2)
                    time.sleep(9)
                    emit_status("")
            else:
                if self.filter == 2:
                    emit_status("Switching filter...")
                    self.set_filter(3)
                    time.sleep(4)
                    emit_status("")

            if nm < self.grating_change_nm:
                if self.grating["number"] == 2:
                    emit_status("Switching grating...")
                    self.set_grating(1)
                    self.goto(nm)
                    if wait:
                        time.sleep(21)
                    emit_status("")
                else:
                    self.goto(nm)
                    time.sleep(0.2)
            else:
                if self.grating["number"] == 1:
                    emit_status("Switching grating...")
                    self.set_grating(2)
                    self.goto(nm)
                    if wait:
                        time.sleep(26)
                    emit_status("")
                else:
                    self.goto(nm)
                    time.sleep(0.2)
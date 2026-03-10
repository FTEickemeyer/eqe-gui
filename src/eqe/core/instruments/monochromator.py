import time
import serial
from collections import namedtuple
from typing import Dict, Union

Response = namedtuple("Response", ["statement", "response"])


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
        self.write(msg)
        return self.read().rstrip()

    def query(self, msg: str) -> Response:
        if msg[-1] != "?":
            msg += "?"

        self.write(msg)
        statement = self.read().rstrip()
        response = self.read().rstrip()
        return Response(statement=statement, response=response)

    # --- high-level methods ---

    @property
    def info(self) -> str:
        resp = self.query("info")
        return resp.response

    @property
    def position(self) -> float:
        resp = self.query("wave")
        return float(resp.response)

    def step(self, steps: int):
        self.command("step", steps)

    def abort(self):
        self.command("abort")

    @property
    def grating(self) -> Dict[str, Union[str, int]]:
        resp = self.query("grat")
        resp = resp.response.split(",")
        return {
            "number": int(resp[0]),
            "lines": int(resp[1]),
            "label": resp[2],
        }

    def set_grating(self, grating: int):
        self.command("grat", grating)

    @property
    def filter_wheel_position(self) -> int:
        resp = self.query("filter")
        return int(resp.response)

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
        resp = self.query("outport")
        return int(resp.response)

    def set_outport(self, port: int):
        self.command("outport", port)

    def slit_width(self, slit: int, width: Union[int, None] = None) -> int:
        cmd = f"slit{slit}microns"
        if width is not None:
            self.command(cmd, width)

        resp = self.query(cmd)
        return int(resp.response)

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
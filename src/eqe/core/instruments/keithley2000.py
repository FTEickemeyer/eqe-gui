"""
Keithley 2000 driver for EQE reference-current measurements.

Ported from the tested driver/notebook in
`C:\\Users\\dreickem\\Documents\\code\\test\\keithley2000_eqe.py` (and the
raw-serial notebook `test_keithley2000.ipynb`, which exercises the same
commands). Instrument-command logic is unchanged from that tested driver;
only `measure_current()` was added so the class satisfies the
`CurrentMeter` role used by the measurement engine.

Supports:
- Serial / RS-232  [default, tested]
- GPIB via PyVISA

Tested serial setup (COM10)
----------------------------
Baud rate:    9600
Data bits:    8
Parity:       None
Stop bits:    1
Flow control: None
TX terminator: CR
Language:     SCPI

Measurement configuration
--------------------------
Function:     DC current
Range:        10 mA fixed (autorange OFF)
NPLC:         1
Filter:       OFF
Relative:     OFF

The reference signal can be close to zero near the start of a scan
(e.g. ~350 nm). Autorange is intentionally left OFF with a fixed range,
matching the tested/validated configuration -- do not make range
selection depend on an assumption of significant background current.

Hardware
--------
For DC current measurements, use the FRONT-panel AMPS / INPUT LO.
Set INPUTS selector to FRONT.
"""

import time
import serial

try:
    import pyvisa
except ImportError:
    pyvisa = None

from eqe.core.instruments.roles import CurrentMeter


class Keithley2000(CurrentMeter):
    """
    Keithley 2000 driver supporting serial and GPIB communication.

    Parameters
    ----------
    interface : str
        "serial" or "gpib". Default: "serial" (the tested/preferred transport).
    port : str
        Serial COM port. Default: "COM10" (tested value).
    baudrate : int
        Serial baud rate. Default: 9600 (tested value).
    gpib_resource : str
        VISA resource string for GPIB.
    nplc : float
        Integration time in power-line cycles. Default: 1.0 (tested value).
    current_range : float
        Fixed DC-current range in amperes. Default: 0.01 (tested value).
    samples : int
        Number of readings averaged per `measure_current()` call. Default: 1
        (matches the tested notebook, which reads `:READ?` directly).
    timeout : float
        Communication timeout in seconds.
    """

    def __init__(
        self,
        interface="serial",
        port="COM10",
        baudrate=9600,
        gpib_resource="GPIB1::16::INSTR",
        nplc=1.0,
        current_range=0.01,
        samples=1,
        timeout=2.0,
    ):
        self.interface = interface.lower()

        if self.interface not in ("serial", "gpib"):
            raise ValueError("interface must be 'serial' or 'gpib'")

        self.port = port
        self.baudrate = baudrate
        self.gpib_resource = gpib_resource

        self.nplc = nplc
        self.current_range = current_range
        self.samples = samples
        self.timeout = timeout

        self.ser = None
        self.rm = None
        self.instrument = None

        self.dark_current = 0.0

        #: Identity string captured at connect time (role API, used e.g.
        #: to record which hardware was used in a saved measurement file).
        self.identity = None

    # =========================================================
    # Connection
    # =========================================================

    def connect(self):
        """Connect to the Keithley, verify its identity, and configure it."""

        if self.is_connected:
            return

        if self.interface == "serial":
            self._connect_serial()
        elif self.interface == "gpib":
            self._connect_gpib()

        identity = self.get_identity()

        if "MODEL 2000" not in identity.upper():
            self.disconnect()
            raise RuntimeError(f"Unexpected instrument: {identity}")

        self.identity = identity
        print(f"Connected via {self.interface.upper()}: {identity}")

        self.configure()

    def _connect_serial(self):
        """Open RS-232 connection."""

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def _connect_gpib(self):
        """Open GPIB connection using PyVISA."""

        if pyvisa is None:
            raise ImportError(
                "PyVISA is required for GPIB operation. Install it with: pip install pyvisa"
            )

        self.rm = pyvisa.ResourceManager()
        self.instrument = self.rm.open_resource(self.gpib_resource)
        self.instrument.timeout = int(self.timeout * 1000)

    # =========================================================
    # Low-level communication
    # =========================================================

    def write(self, command):
        """Send one SCPI command."""

        self._check_connection()

        if self.interface == "serial":
            message = (command.rstrip("\r\n") + "\r").encode("ascii")
            self.ser.write(message)
            self.ser.flush()
        else:
            self.instrument.write(command)

    def query(self, command):
        """Send a SCPI query and return the response."""

        self._check_connection()

        if self.interface == "serial":
            # Remove old unread bytes before query
            self.ser.reset_input_buffer()
            self.write(command)

            # Keithley TX termination is CR
            response = self.ser.read_until(b"\r")

            if not response:
                raise TimeoutError(f"No response from Keithley 2000 for command: {command}")

            return response.decode("ascii", errors="replace").strip()
        else:
            return self.instrument.query(command).strip()

    # =========================================================
    # Measurement configuration
    # =========================================================

    def configure(self):
        """Configure for low DC photocurrent measurement."""

        self._check_connection()

        # Factory reset
        self.write("*RST")
        time.sleep(0.3)

        # DC current function
        self.write(":SENS:FUNC 'CURR:DC'")

        # Fixed current range
        self.write(f":SENS:CURR:DC:RANG {self.current_range}")

        # Disable autoranging
        self.write(":SENS:CURR:DC:RANG:AUTO OFF")

        # Integration time
        self.write(f":SENS:CURR:DC:NPLC {self.nplc}")

        # Relative measurement off
        self.write(":SENS:CURR:DC:REF:STAT OFF")

        # Internal averaging/filter off
        self.write(":SENS:CURR:DC:AVER:STAT OFF")

        time.sleep(0.2)

    def configure_current_measurement(self, nplc=None, current_range=None):
        """Runtime reconfiguration hook (role API)."""
        if nplc is not None:
            self.set_nplc(nplc)
        if current_range is not None:
            self.set_current_range(current_range)

    # =========================================================
    # Measurement
    # =========================================================

    def read_current(self):
        """Take one current measurement, in amperes."""

        response = self.query(":READ?")

        try:
            return float(response)
        except ValueError as exc:
            raise RuntimeError(f"Invalid current response: {response!r}") from exc

    def read_current_average(self, samples=3):
        """Take several readings and return their mean, in amperes."""

        if samples < 1:
            raise ValueError("samples must be >= 1")

        values = [self.read_current() for _ in range(samples)]
        return sum(values) / len(values)

    def measure_current(self) -> float:
        """CurrentMeter role API: return one (averaged) current reading."""
        return self.read_current_average(samples=self.samples)

    # =========================================================
    # Configuration controls
    # =========================================================

    def set_nplc(self, nplc):
        """Set DC-current NPLC."""

        self.nplc = float(nplc)
        self.write(f":SENS:CURR:DC:NPLC {self.nplc}")

    def set_current_range(self, current_range):
        """Set fixed DC-current range in amperes."""

        self.current_range = float(current_range)
        self.write(f":SENS:CURR:DC:RANG {self.current_range}")
        self.write(":SENS:CURR:DC:RANG:AUTO OFF")

    # =========================================================
    # Diagnostics
    # =========================================================

    def get_identity(self):
        """Return instrument identification."""
        return self.query("*IDN?")

    def get_configuration(self):
        """Return important measurement settings."""

        return {
            "interface": self.interface,
            "function": self.query(":SENS:FUNC?"),
            "range_A": float(self.query(":SENS:CURR:DC:RANG?")),
            "autorange": bool(int(float(self.query(":SENS:CURR:DC:RANG:AUTO?")))),
            "nplc": float(self.query(":SENS:CURR:DC:NPLC?")),
        }

    # =========================================================
    # Status
    # =========================================================

    @property
    def is_connected(self):
        """Return True if communication interface is open."""

        if self.interface == "serial":
            return self.ser is not None and self.ser.is_open
        else:
            return self.instrument is not None

    def _check_connection(self):
        if not self.is_connected:
            raise RuntimeError("Keithley 2000 is not connected. Call connect() first.")

    # =========================================================
    # Shutdown
    # =========================================================

    def disconnect(self):
        """Close communication cleanly. Safe to call more than once."""

        if self.ser is not None:
            try:
                if self.ser.is_open:
                    self.ser.close()
            finally:
                self.ser = None

        if self.instrument is not None:
            try:
                self.instrument.close()
            finally:
                self.instrument = None

        if self.rm is not None:
            try:
                self.rm.close()
            finally:
                self.rm = None

    # =========================================================
    # Context manager
    # =========================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()

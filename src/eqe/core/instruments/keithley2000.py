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
Two modes (see `mode`); NPLC=5, filter/relative OFF in both:

- "current" (the original tested configuration): DC current function,
  10 mA fixed range, autorange OFF. This instrument's DC current
  function only has this one range -- confirmed on real hardware, any
  smaller requested range is silently clamped back to it -- which is far
  larger than the reference cell's actual signal (~10s of nA to a few
  uA), especially at the weaker-signal wavelengths of a sweep. Use the
  FRONT-panel AMPS / INPUT LO, INPUTS selector set to FRONT.

- "voltage_shunt" (added 2026-08-14, current default -- see
  AdvancedAcquisitionPanel): DC voltage function, fixed range (see
  `voltage_range`), reading the voltage drop across a known external
  shunt resistor wired to the Input HI/LO terminals, converted back to
  an equivalent current (voltage / shunt_resistance_ohms) before it
  reaches the rest of the app. DC voltage ranges go much lower than DC
  current ones on this instrument, giving far better resolution for a
  weak signal like this one.

Both modes still benefit from higher NPLC (longer integration): measured
on real hardware, NPLC 1->5 cut relative noise ~5x at a weak-signal
point; NPLC=10 gave no further improvement for ~2x the time.
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
        Integration time in power-line cycles. Default: 5.0. Was 1.0, raised
        after a noisy Si71889 calibration measurement investigated
        2026-08-14: this instrument's DC current function only has one
        range (see `current_range`), far larger than the reference cell's
        actual signal, so the reading sits close to the noise floor at
        the weaker-signal wavelengths of a sweep -- longer integration
        (higher NPLC) directly reduces that. On real hardware at a
        weak-signal point (350 nm), NPLC 1->5 cut relative noise from
        ~2.4% to ~0.5%; NPLC=10 measured no further improvement for ~2x
        the time, so 5 is the better trade-off.
    autorange : bool
        Autorange the DC-current measurement. Default: True. Harmless and
        correct in general (matches what the Keithley 2400 test-cell meter
        already does), but on this specific instrument it makes no
        difference: confirmed on real hardware that its DC current
        function only has one range (0.01 A) -- any smaller range request
        is silently clamped back to it. The actual noise fix is `nplc`
        above; kept here for correctness if this meter is ever swapped for
        a model with more current ranges.
    current_range : float
        Fixed DC-current range in amperes, used only when `autorange` is
        False. Default: 0.01 -- also this instrument's only available DC
        current range (see `autorange` above), so changing this value has
        no effect on real hardware; kept for API completeness/other
        instrument models.
    samples : int
        Number of readings averaged per `measure_current()` call. Default: 1
        (matches the tested notebook, which reads `:READ?` directly). Raising
        `nplc` was measured to reduce noise more efficiently than raising
        this, since each extra sample here costs a full extra serial
        round-trip on top of its integration time.
    mode : str
        "current" (direct DC current sensing, the original tested
        configuration) or "voltage_shunt" (DC voltage sensing across a
        known external shunt resistor, see `shunt_resistance_ohms`; added
        2026-08-14, see class docstring). Default: "current" -- the GUI's
        Advanced Acquisition Settings panel defaults to "voltage_shunt"
        instead, matching the lab's actual current wiring; this
        constructor default stays conservative for any other caller.
    shunt_resistance_ohms : float or None
        The external shunt resistor's resistance, used to convert a
        voltage reading back to an equivalent current
        (current = voltage / shunt_resistance_ohms) when `mode` is
        "voltage_shunt". Required (raises at read time otherwise) in that
        mode; unused in "current" mode.
    voltage_range : float
        Fixed DC-voltage range in volts, used only when `mode` is
        "voltage_shunt" (autorange is not used for this function -- see
        set_mode()). Default: 0.1 (100 mV) -- comfortably covers the
        expected signal (e.g. 598 ohm shunt at up to ~7 uA is ~4.2 mV;
        a future 10 kOhm+ shunt at the same current would be ~70 mV+).
        Raise this if a larger shunt resistor and/or higher current later
        pushes the expected drop closer to 100 mV.
    timeout : float
        Communication timeout in seconds.
    """

    #: `mode` values (role-agnostic strings, not SCPI text).
    MODE_CURRENT = "current"
    MODE_VOLTAGE_SHUNT = "voltage_shunt"

    def __init__(
        self,
        interface="serial",
        port="COM10",
        baudrate=9600,
        gpib_resource="GPIB1::16::INSTR",
        nplc=5.0,
        autorange=True,
        current_range=0.01,
        samples=1,
        mode=MODE_CURRENT,
        shunt_resistance_ohms=None,
        voltage_range=0.1,
        timeout=2.0,
    ):
        self.interface = interface.lower()

        if self.interface not in ("serial", "gpib"):
            raise ValueError("interface must be 'serial' or 'gpib'")

        self.port = port
        self.baudrate = baudrate
        self.gpib_resource = gpib_resource

        self.nplc = nplc
        self.autorange = autorange
        self.current_range = current_range
        self.samples = samples
        self.mode = mode
        self.shunt_resistance_ohms = (
            float(shunt_resistance_ohms) if shunt_resistance_ohms is not None else None
        )
        self.voltage_range = voltage_range
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

        # Function/range/NPLC/filter setup -- shared with set_mode() below,
        # since switching between "current" and "voltage_shunt" needs the
        # exact same per-function setup this does at connect time.
        self.set_mode(self.mode)

        time.sleep(0.2)

    def set_mode(self, mode):
        """
        Switch between direct current sensing ("current", the original
        tested configuration) and voltage-across-a-known-shunt-resistor
        sensing ("voltage_shunt", see `shunt_resistance_ohms`/class
        docstring). Reconfigures the relevant SCPI function/range/NPLC
        from scratch -- these are independent per-function subsystems on
        the instrument, so switching FUNC doesn't carry settings across.
        """

        if mode not in (self.MODE_CURRENT, self.MODE_VOLTAGE_SHUNT):
            raise ValueError(f"Unknown Keithley 2000 measurement mode: {mode!r}")

        self.mode = mode

        if mode == self.MODE_CURRENT:
            self.write(":SENS:FUNC 'CURR:DC'")

            # Range: autorange by default (see class docstring) so the
            # reading keeps good resolution across the reference cell's
            # full dynamic range; a fixed range is only used if autorange
            # is explicitly off.
            if self.autorange:
                self.write(":SENS:CURR:DC:RANG:AUTO ON")
            else:
                self.write(f":SENS:CURR:DC:RANG {self.current_range}")
                self.write(":SENS:CURR:DC:RANG:AUTO OFF")

            self.write(f":SENS:CURR:DC:NPLC {self.nplc}")
            self.write(":SENS:CURR:DC:REF:STAT OFF")
            self.write(":SENS:CURR:DC:AVER:STAT OFF")

        else:  # MODE_VOLTAGE_SHUNT
            self.write(":SENS:FUNC 'VOLT:DC'")

            # Fixed range (not autorange, see class docstring) -- large
            # enough to comfortably cover the expected shunt voltage drop.
            self.write(f":SENS:VOLT:DC:RANG {self.voltage_range}")
            self.write(":SENS:VOLT:DC:RANG:AUTO OFF")

            self.write(f":SENS:VOLT:DC:NPLC {self.nplc}")
            self.write(":SENS:VOLT:DC:REF:STAT OFF")
            self.write(":SENS:VOLT:DC:AVER:STAT OFF")

    def configure_current_measurement(
        self,
        nplc=None,
        current_range=None,
        autorange=None,
        mode=None,
        shunt_resistance_ohms=None,
    ):
        """
        Runtime reconfiguration hook (role API). Order matters: `mode` is
        applied first (it resets the active function's range/NPLC/filter
        from the current `self.*` values), then the other settings are
        layered on top if they were also given a value this call.
        """
        if shunt_resistance_ohms is not None:
            self.shunt_resistance_ohms = float(shunt_resistance_ohms)
        if mode is not None:
            self.set_mode(mode)
        if nplc is not None:
            self.set_nplc(nplc)
        if autorange is not None:
            self.set_autorange(autorange)
        elif current_range is not None:
            self.set_current_range(current_range)

    # =========================================================
    # Measurement
    # =========================================================

    def read_current(self):
        """
        Take one measurement, in amperes.

        In "voltage_shunt" mode, the instrument is actually reading a
        voltage (see set_mode()) -- converted here to an equivalent
        current via shunt_resistance_ohms before it's returned, so every
        caller above this driver (the measurement engine, saved-file
        columns, calibration math, ...) keeps working in amperes exactly
        as before, unaware of how that current was actually sensed.
        """

        response = self.query(":READ?")

        try:
            raw = float(response)
        except ValueError as exc:
            raise RuntimeError(f"Invalid reading response: {response!r}") from exc

        if self.mode == self.MODE_VOLTAGE_SHUNT:
            if not self.shunt_resistance_ohms:
                raise RuntimeError(
                    "Keithley 2000 is in voltage_shunt mode but "
                    "shunt_resistance_ohms is not set."
                )
            return raw / self.shunt_resistance_ohms

        return raw

    def read_current_average(self, samples=3):
        """Take several readings and return their mean, in amperes."""

        if samples < 1:
            raise ValueError("samples must be >= 1")

        values = [self.read_current() for _ in range(samples)]
        return sum(values) / len(values)

    def measure_current(self) -> float:
        """CurrentMeter role API: return one (averaged) current reading."""
        return self.read_current_average(samples=self.samples)

    def settle(self) -> None:
        """
        CurrentMeter role hook (see roles.py): take one throwaway reading
        to let the instrument settle after its function/range was just
        reconfigured (see configure_current_measurement()/set_mode()) --
        confirmed on real hardware 2026-08-19: a reference-meter dark
        current recaptured *immediately* after configure + a just-finished
        scan can be wildly wrong (observed ~170 nA off from the true ~2-3 nA
        dark level -- large enough to corrupt an entire subsequent EQE
        scan's grating-1 range, where the true signal is weakest), but is
        back to normal from the very next reading onward, taken only ~2s
        later -- a one-reading settling transient, not a persistent fault.
        Same pattern as Keithley2400EQE.settle(), just triggered here by a
        function/range reconfigure rather than an autorange jump.

        Callers that reconfigure this meter and then need a trustworthy
        reading right away (see mainwindow_qt.py's dark-current recapture)
        must call this in between. Best-effort: a communication failure
        here just means the settling read didn't happen -- the real
        reading right after this call will surface any actual problem on
        its own.
        """
        try:
            self.read_current()
        except Exception:
            pass

    # =========================================================
    # Configuration controls
    # =========================================================

    def set_nplc(self, nplc):
        """Set DC-current NPLC."""

        self.nplc = float(nplc)
        self.write(f":SENS:CURR:DC:NPLC {self.nplc}")

    def set_current_range(self, current_range):
        """Set a fixed DC-current range in amperes (disables autorange)."""

        self.autorange = False
        self.current_range = float(current_range)
        self.write(f":SENS:CURR:DC:RANG {self.current_range}")
        self.write(":SENS:CURR:DC:RANG:AUTO OFF")

    def set_autorange(self, enabled):
        """Enable/disable DC-current autoranging (see class docstring)."""

        self.autorange = bool(enabled)
        if self.autorange:
            self.write(":SENS:CURR:DC:RANG:AUTO ON")
        else:
            self.write(f":SENS:CURR:DC:RANG {self.current_range}")
            self.write(":SENS:CURR:DC:RANG:AUTO OFF")

    # =========================================================
    # Diagnostics
    # =========================================================

    def get_identity(self):
        """Return instrument identification."""
        return self.query("*IDN?")

    def get_configuration(self):
        """
        Return important measurement settings. Range/autorange/NPLC are
        queried from whichever SCPI subsystem is actually active (mode)
        -- CURR:DC and VOLT:DC each store their own settings independently
        on the instrument, so querying the wrong one would silently
        report stale/irrelevant values.
        """

        subsystem = "VOLT" if self.mode == self.MODE_VOLTAGE_SHUNT else "CURR"

        return {
            "interface": self.interface,
            "function": self.query(":SENS:FUNC?"),
            "mode": self.mode,
            "range": float(self.query(f":SENS:{subsystem}:DC:RANG?")),
            "autorange": bool(int(float(self.query(f":SENS:{subsystem}:DC:RANG:AUTO?")))),
            "nplc": float(self.query(f":SENS:{subsystem}:DC:NPLC?")),
            "shunt_resistance_ohms": self.shunt_resistance_ohms,
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

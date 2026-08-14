"""
Keithley 2400 EQE driver.

Ported from the tested driver in
`C:\\Users\\dreickem\\Documents\\code\\test\\keithley_2400_eqe.py` (validated
by `test_keithley2400.ipynb` against real hardware). Instrument-command
logic (SCPI sequences, ramping, compliance checking) is unchanged from that
tested driver; `measure_current()`, `output_on()` and `dark_current` were
added so the class satisfies the `BiasCurrentMeter` role used by the
measurement engine.

Validated setup
----------------
Instrument: Keithley 2400
Interface: RS-232 via ATEN USB-to-Serial bridge
VISA resource: ASRL8::INSTR  (COM8)
Baud rate: 9600, 8N1, no flow control, LF read/write terminator.

Recommended EQE configuration
------------------------------
Terminals: rear
Source mode: voltage
Sense function: current
Current range: autorange (the EQE current can vary strongly with
wavelength, especially near the start of a scan -- do not turn this off)
Current NPLC: 1
Averaging: performed in Python (default 3 samples)

Safety / compliance behavior
------------------------------
Current compliance is configurable (default 10 mA) and is never silently
raised by this driver. `set_current_compliance()` requires an explicit
value from the caller.

The tested driver raises `ComplianceLimitError` by default when a reading
is at/near compliance (`raise_on_compliance=True`), which is appropriate
for the standalone manual test. When used as the EQE engine's `test_meter`
role, the factory instead constructs this driver with
`raise_on_compliance=False` so a compliance hit is reported as a
`compliance_hit` flag (consistent with how the Keithley 2600 path already
reports compliance) and the scan can continue and warn, rather than abort.

The driver ramps the bias voltage back to 0 V and disables the source on
disconnect whenever possible.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyvisa

from eqe.core.instruments.roles import BiasCurrentMeter


class ComplianceLimitError(RuntimeError):
    """Raised when the measured current is at or near current compliance."""


class Keithley2400EQE(BiasCurrentMeter):
    """Keithley 2400 driver for biased EQE current measurements."""

    def __init__(
        self,
        resource: str = "ASRL8::INSTR",
        baud_rate: int = 9600,
        timeout_ms: int = 5000,
        nplc: float = 1.0,
        current_compliance: float = 0.01,
        samples: int = 3,
        bias_voltage: float = 0.0,
        ramp_steps: int = 10,
        ramp_delay_s: float = 0.05,
        discard_first_reading: bool = True,
        compliance_fraction: float = 0.98,
        raise_on_compliance: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        resource
            VISA resource string. For COM8 this is normally ``ASRL8::INSTR``.
        baud_rate
            RS-232 baud rate. Must match the instrument front-panel setting.
        timeout_ms
            VISA timeout in milliseconds.
        nplc
            Current integration time in power-line cycles.
            NPLC = 1 gave a good speed/noise compromise in testing.
        current_compliance
            Maximum allowed current in amperes while voltage is sourced.
            Default: 0.01 A = 10 mA.
        samples
            Number of readings averaged for each returned current.
        bias_voltage
            Initial bias voltage in volts.
        ramp_steps
            Number of steps used when changing bias voltage.
        ramp_delay_s
            Delay between bias-ramp steps in seconds.
        discard_first_reading
            If True, discard one reading before the readings used for the
            average. Useful when the current autorange changes with wavelength.
        compliance_fraction
            Fraction of the programmed compliance above which a measurement is
            considered "at or near compliance". Default: 0.98.
        raise_on_compliance
            If True, a compliance-limited measurement raises
            ComplianceLimitError. The EQE engine factory sets this to False
            (see module docstring) so the scan can warn and continue instead.
        """
        if samples < 1:
            raise ValueError("samples must be >= 1")
        if ramp_steps < 1:
            raise ValueError("ramp_steps must be >= 1")
        if nplc <= 0:
            raise ValueError("nplc must be > 0")
        if current_compliance <= 0:
            raise ValueError("current_compliance must be > 0")
        if not (0 < compliance_fraction <= 1):
            raise ValueError("compliance_fraction must be > 0 and <= 1")

        self.resource = resource
        self.baud_rate = int(baud_rate)
        self.timeout_ms = int(timeout_ms)
        self.nplc = float(nplc)
        self.current_compliance = float(current_compliance)
        self.samples = int(samples)
        self.bias_voltage = float(bias_voltage)
        self.ramp_steps = int(ramp_steps)
        self.ramp_delay_s = float(ramp_delay_s)
        self.discard_first_reading = bool(discard_first_reading)
        self.compliance_fraction = float(compliance_fraction)
        self.raise_on_compliance = bool(raise_on_compliance)

        self.rm: Optional[pyvisa.ResourceManager] = None
        self.instrument = None
        self._output_enabled = False
        self._programmed_bias = 0.0

        self.dark_current = 0.0
        self.compliance_hit = False

        #: Identity string captured at connect time (role API, used e.g.
        #: to record which hardware was used in a saved measurement file).
        self.identity = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> str:
        """Open the VISA connection, verify identity and configure the instrument."""
        if self.instrument is None:
            self.rm = pyvisa.ResourceManager()

            self.instrument = self.rm.open_resource(
                self.resource,
                baud_rate=self.baud_rate,
                data_bits=8,
                parity=pyvisa.constants.Parity.none,
                stop_bits=pyvisa.constants.StopBits.one,
                read_termination="\n",
                write_termination="\n",
            )
            self.instrument.timeout = self.timeout_ms

            identity = self.get_identity()

            if "MODEL 2400" not in identity.upper():
                self.disconnect(safe=False)
                raise RuntimeError(f"Unexpected instrument at {self.resource}: {identity}")

            self.identity = identity
            print(f"Connected via VISA ({self.resource}): {identity}")

        self.configure()
        return self.get_identity()

    def get_identity(self) -> str:
        """Return the SCPI identification string."""
        self._check_connection()
        return self.instrument.query("*IDN?").strip()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, bias_voltage: Optional[float] = None) -> None:
        """
        Configure the 2400 for rear-terminal voltage-source/current-sense use.

        The source is first enabled at 0 V, after which the requested bias is
        reached using a voltage ramp.
        """
        self._check_connection()

        if bias_voltage is None:
            bias_voltage = self.bias_voltage

        k = self.instrument

        k.write("*RST")

        # Test cell connected to rear terminals.
        k.write(":ROUT:TERM REAR")

        # Source voltage.
        k.write(":SOUR:FUNC VOLT")
        k.write(":SOUR:VOLT 0")
        k.write(":SOUR:VOLT:RANG:AUTO ON")

        # Measure current.
        k.write(":SENS:FUNC 'CURR'")

        # The EQE current can vary strongly with wavelength, especially when
        # the scan begins in a spectrally inactive region. Keep autorange on.
        k.write(":SENS:CURR:RANG:AUTO ON")

        # Integration time.
        k.write(f":SENS:CURR:NPLC {self.nplc}")

        # Current compliance.
        k.write(f":SENS:CURR:PROT {self.current_compliance}")

        # Return current only during normal measurements.
        k.write(":FORM:ELEM CURR")

        # Delays are handled by the higher-level EQE controller.
        k.write(":SOUR:DEL 0")
        k.write(":TRIG:DEL 0")

        # Enable at 0 V, then ramp to desired bias.
        k.write(":OUTP ON")
        self._output_enabled = True
        self._programmed_bias = 0.0

        self.set_bias_voltage(float(bias_voltage))

    def configure_current_measurement(self, nplc=None, current_compliance=None):
        """Runtime reconfiguration hook (role API)."""
        if nplc is not None:
            self.set_nplc(nplc)
        if current_compliance is not None:
            self.set_current_compliance(current_compliance)

    # ------------------------------------------------------------------
    # Bias voltage
    # ------------------------------------------------------------------

    def set_bias_voltage(
        self,
        voltage: float,
        *,
        ramp: bool = True,
        steps: Optional[int] = None,
        delay_s: Optional[float] = None,
    ) -> None:
        """
        Set the DC bias voltage.

        Parameters
        ----------
        voltage
            Target bias voltage in volts.
        ramp
            If True, ramp from the present programmed voltage to the target.
        steps
            Optional number of ramp steps.
        delay_s
            Optional delay between ramp steps.
        """
        self._check_connection()

        target = float(voltage)

        if steps is None:
            steps = self.ramp_steps
        if delay_s is None:
            delay_s = self.ramp_delay_s

        if not self._output_enabled:
            self.instrument.write(":SOUR:VOLT 0")
            self.instrument.write(":OUTP ON")
            self._output_enabled = True
            self._programmed_bias = 0.0

        if not ramp or int(steps) <= 1:
            self.instrument.write(f":SOUR:VOLT {target}")
            self._programmed_bias = target
            self.bias_voltage = target
            return

        start = self._programmed_bias

        for value in np.linspace(start, target, int(steps) + 1)[1:]:
            self.instrument.write(f":SOUR:VOLT {float(value)}")
            time.sleep(float(delay_s))

        self._programmed_bias = target
        self.bias_voltage = target

    def get_bias_voltage(self) -> float:
        """Return the programmed source voltage in volts."""
        self._check_connection()
        return float(self.instrument.query(":SOUR:VOLT?"))

    # ------------------------------------------------------------------
    # Compliance helpers
    # ------------------------------------------------------------------

    def compliance_threshold(self) -> float:
        """Return the current magnitude above which compliance is flagged."""
        return self.compliance_fraction * self.current_compliance

    def is_near_compliance(self, current_A: float) -> bool:
        """Return True if |current| is at or near current compliance."""
        return abs(float(current_A)) >= self.compliance_threshold()

    def _handle_compliance(self, currents_A) -> bool:
        """
        Check one or more readings against current compliance.

        Returns
        -------
        bool
            True if any reading is at/near compliance.
        """
        values = np.atleast_1d(np.asarray(currents_A, dtype=float))
        near = bool(np.any(np.abs(values) >= self.compliance_threshold()))

        if near and self.raise_on_compliance:
            peak = float(np.max(np.abs(values)))
            raise ComplianceLimitError(
                "Keithley 2400 current is at or near compliance: "
                f"peak |I| = {peak*1e3:.4f} mA, "
                f"compliance = {self.current_compliance*1e3:.4f} mA, "
                f"threshold = {self.compliance_fraction*100:.1f}%."
            )

        return near

    # ------------------------------------------------------------------
    # Current measurement
    # ------------------------------------------------------------------

    def read_current(
        self,
        samples: Optional[int] = None,
        *,
        discard_first: Optional[bool] = None,
        return_std: bool = False,
        return_status: bool = False,
    ):
        """
        Measure test-cell current.

        By default, compliance-limited measurements raise ComplianceLimitError.

        Parameters
        ----------
        samples
            Number of readings to average. Defaults to ``self.samples``.
        discard_first
            If True, discard one initial reading before collecting samples.
        return_std
            If True, include sample standard deviation in the return value.
        return_status
            If True, include a boolean compliance flag in the return value.
            This is most useful when ``raise_on_compliance=False``.

        Returns
        -------
        float
            Mean current in amperes, for default options.

        Other return forms
        -------------------
        return_std=True:
            (mean_A, std_A)
        return_status=True:
            (mean_A, near_compliance)
        return_std=True and return_status=True:
            (mean_A, std_A, near_compliance)
        """
        self._check_connection()

        if samples is None:
            samples = self.samples
        samples = int(samples)

        if samples < 1:
            raise ValueError("samples must be >= 1")

        if discard_first is None:
            discard_first = self.discard_first_reading

        if discard_first:
            discarded = float(self.instrument.query(":READ?"))
            # A discarded reading at compliance is still important.
            self._handle_compliance([discarded])

        readings = np.empty(samples, dtype=float)

        for i in range(samples):
            readings[i] = float(self.instrument.query(":READ?"))

        near_compliance = self._handle_compliance(readings)

        mean = float(np.mean(readings))
        std = float(np.std(readings, ddof=1)) if samples > 1 else 0.0

        if return_std and return_status:
            return mean, std, near_compliance
        if return_std:
            return mean, std
        if return_status:
            return mean, near_compliance
        return mean

    def read_current_single(self) -> float:
        """Return one current reading in amperes with compliance checking."""
        self._check_connection()
        current = float(self.instrument.query(":READ?"))
        self._handle_compliance([current])
        return current

    def measure_voltage_current(self):
        """
        Measure voltage and current together.

        Returns
        -------
        tuple[float, float]
            (measured_voltage_V, measured_current_A)

        Notes
        -----
        The normal output format is restored to current-only afterwards.
        Compliance checking is applied to the measured current.
        """
        self._check_connection()

        try:
            self.instrument.write(":FORM:ELEM VOLT,CURR")
            response = self.instrument.query(":READ?").strip()
            voltage, current = map(float, response.split(","))
        finally:
            self.instrument.write(":FORM:ELEM CURR")

        self._handle_compliance([current])
        return voltage, current

    def get_current_range(self) -> float:
        """Return the presently selected current range in amperes."""
        self._check_connection()
        return float(self.instrument.query(":SENS:CURR:RANG?"))

    def measure_current(self) -> float:
        """
        BiasCurrentMeter role API: return one averaged current reading.

        Uses `return_status=True` instead of letting a compliance hit raise,
        so the caller's `raise_on_compliance` setting governs whether that
        translates into an exception (manual test) or a `compliance_hit`
        flag the engine can warn about and continue past (EQE scan).
        """
        mean, near_compliance = self.read_current(return_status=True)
        self.compliance_hit = near_compliance
        return mean

    # ------------------------------------------------------------------
    # Runtime settings
    # ------------------------------------------------------------------

    def set_nplc(self, nplc: float) -> None:
        """Set current integration time in power-line cycles."""
        self._check_connection()
        if nplc <= 0:
            raise ValueError("nplc must be > 0")

        self.instrument.write(f":SENS:CURR:NPLC {float(nplc)}")
        self.nplc = float(nplc)

    def set_current_compliance(self, current_A: float) -> None:
        """
        Set current compliance in amperes.

        This method does not automatically increase compliance when a device
        reaches the limit. The operator/software must choose a safe value.
        """
        self._check_connection()

        current_A = float(current_A)
        if current_A <= 0:
            raise ValueError("current compliance must be > 0")

        self.instrument.write(f":SENS:CURR:PROT {current_A}")
        self.current_compliance = current_A

    # BiasCurrentMeter role API alias.
    set_compliance_current = set_current_compliance

    def get_configuration(self) -> dict:
        """Read back important instrument settings for diagnostics/logging."""
        self._check_connection()

        return {
            "identity": self.get_identity(),
            "terminals": self.instrument.query(":ROUT:TERM?").strip(),
            "source_function": self.instrument.query(":SOUR:FUNC?").strip(),
            "bias_voltage_V": float(self.instrument.query(":SOUR:VOLT?")),
            "sense_function": self.instrument.query(":SENS:FUNC?").strip(),
            "current_range_A": float(self.instrument.query(":SENS:CURR:RANG?")),
            "current_autorange": bool(
                int(float(self.instrument.query(":SENS:CURR:RANG:AUTO?")))
            ),
            "current_nplc": float(self.instrument.query(":SENS:CURR:NPLC?")),
            "current_compliance_A": float(self.instrument.query(":SENS:CURR:PROT?")),
            "compliance_fraction": self.compliance_fraction,
            "compliance_threshold_A": self.compliance_threshold(),
        }

    # ------------------------------------------------------------------
    # Output / shutdown
    # ------------------------------------------------------------------

    def output_on(self) -> None:
        """BiasCurrentMeter role API: enable the source output at 0 V."""
        self._check_connection()

        if self._output_enabled:
            return

        self.instrument.write(":SOUR:VOLT 0")
        self.instrument.write(":OUTP ON")
        self._output_enabled = True
        self._programmed_bias = 0.0

    def output_off(self, *, ramp_to_zero: bool = True) -> None:
        """Optionally ramp to 0 V and then disable the source output."""
        self._check_connection()

        if not self._output_enabled:
            return

        if ramp_to_zero and self._programmed_bias != 0.0:
            self.set_bias_voltage(0.0)

        self.instrument.write(":OUTP OFF")
        self._output_enabled = False
        self._programmed_bias = 0.0

    def disconnect(self, *, safe: bool = True) -> None:
        """Safely close the instrument and VISA resource manager. Safe to call twice."""
        if self.instrument is not None:
            if safe:
                try:
                    self.output_off(ramp_to_zero=True)
                except Exception:
                    try:
                        self.instrument.write(":OUTP OFF")
                    except Exception:
                        pass

            try:
                self.instrument.close()
            finally:
                self.instrument = None
                self._output_enabled = False
                self._programmed_bias = 0.0

        if self.rm is not None:
            try:
                self.rm.close()
            finally:
                self.rm = None

    def _check_connection(self) -> None:
        if self.instrument is None:
            raise RuntimeError("Keithley 2400 is not connected. Call connect() first.")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect(safe=True)

"""
Measurement-role abstractions for the instrument layer.

The measurement engine (`core/measurement_engine.py`) must not know which
physical instrument model is in use. Instead it operates on *roles*:

    reference_meter   -- measures the reference-photodiode current
    test_meter        -- measures the test-cell current and (optionally)
                          sources the bias voltage
    monochromator     -- wavelength control (unchanged, see instruments/monochromator.py)

Concrete drivers (Keithley 2000, Keithley 2400, a Keithley 2600 channel, a
simulated instrument, ...) implement `CurrentMeter` / `BiasCurrentMeter`
below. Which physical instrument plays which role is decided in one place:
`instruments/factory.py`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class CurrentMeter(ABC):
    """
    Role interface for an instrument that measures a DC current.

    `dark_current` is captured once, at connect time (see
    `factory.initialize_system`), and is subtracted by the measurement
    engine -- it is measurement logic, not instrument-driver logic, so it
    does not live inside individual drivers.
    """

    dark_current: float = 0.0

    @abstractmethod
    def connect(self):
        """Open the communication channel and configure the instrument."""

    @abstractmethod
    def disconnect(self):
        """Close the communication channel. Must be safe to call twice."""

    @abstractmethod
    def measure_current(self) -> float:
        """Return one (possibly internally averaged) current reading, in amperes."""

    def configure_current_measurement(self, **kwargs):
        """
        Optional hook for drivers that support runtime reconfiguration
        (e.g. NPLC, current range). Default: no-op.
        """
        return None

    def settle(self):
        """
        Optional hook: take (and discard) whatever throwaway reading a
        driver needs so it's ready for an accurate "real" reading right
        afterward -- e.g. letting autorange resettle after a wavelength
        move jumps the signal to a very different magnitude. Called once
        per wavelength move by the measurement engine, not once per
        reading (see measurement_engine.py) -- most meters need nothing
        here. Default: no-op.
        """
        return None


class BiasCurrentMeter(CurrentMeter):
    """A CurrentMeter that can also source a DC bias voltage."""

    @abstractmethod
    def set_bias_voltage(self, voltage: float):
        ...

    @abstractmethod
    def set_compliance_current(self, current: float):
        ...

    @abstractmethod
    def output_on(self):
        ...

    @abstractmethod
    def output_off(self):
        ...

    #: True if the most recent reading was at/near current compliance.
    #: A plain attribute (not a read-only property) so drivers that track
    #: this per-reading (e.g. Keithley2400EQE) can just assign to it;
    #: drivers that derive it from shared state (e.g. DualChannelTestMeter)
    #: are still free to override this with a read-only @property instead.
    compliance_hit: bool = False


@dataclass
class MeasurementHardware:
    """
    Binds measurement roles to concrete instrument instances.

    This is the abstraction boundary: the measurement engine is written
    entirely in terms of `reference_meter`, `test_meter` and
    `monochromator`. Building this object from a hardware configuration
    (e.g. "Keithley 2000 + Keithley 2400" vs. "Keithley 2600 dual channel")
    is the sole responsibility of `instruments/factory.py`.
    """

    reference_meter: CurrentMeter
    test_meter: BiasCurrentMeter
    monochromator: object

    def close(self):
        """Best-effort shutdown of every instrument in this hardware set."""
        # test_meter first: make sure any applied bias/output is removed.
        for obj in (self.test_meter, self.reference_meter, self.monochromator):
            if obj is None:
                continue
            for method_name in ("disconnect", "close"):
                method = getattr(obj, method_name, None)
                if method is not None:
                    try:
                        method()
                    except Exception:
                        pass
                    break

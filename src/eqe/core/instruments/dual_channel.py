"""
Role adapters for dual-channel instruments that measure both the reference
and the test-cell current from a single synchronized, triggered acquisition
-- currently the Keithley 2600 (`instruments/smu.py`, untouched) and its
simulated stand-in (`instruments/simulated.py`, untouched).

Both `SMU` and `SimulatedSMU` already implement the same small duck-typed
protocol:

    run_dual_measurement()   -- trigger one synchronized acquisition of N
                                 samples on both channels
    get_average() -> (chA, chB)
    chA_dark / chB_dark
    set_bias_voltage(v) / set_compliance_current(i)
    enable_output() / disable_output()
    close()
    compliance_hit            (SMU only; SimulatedSMU has none)

`DualChannelSMUSession` wraps one such instance and exposes it as two
independent `CurrentMeter` / `BiasCurrentMeter` role objects (channel A =
reference, channel B = test + bias), so the measurement engine can call
`reference_meter.measure_current()` and `test_meter.measure_current()`
independently while the *physical* acquisition still happens once per
cycle, exactly as tested.

Do not duplicate the physical connection: build one `DualChannelSMUSession`
per physical instrument and hand out its `.reference_channel` /
`.test_channel` -- never construct two sessions around the same connection.
"""

from eqe.core.instruments.roles import CurrentMeter, BiasCurrentMeter


class DualChannelSMUSession:
    """
    Coordinates a shared triggered dual-channel acquisition.

    `read_channel()` triggers `run_dual_measurement()` at most once per
    "cycle" (defined as: until both channels have been read once), no
    matter which channel is asked for first. This preserves the original,
    tested behavior of one simultaneous triggered read per engine
    iteration, regardless of whether the engine reads the reference or the
    test channel first.
    """

    def __init__(self, smu):
        self._smu = smu
        self._fresh = False
        self._consumed = set()
        self._closed = False

    @property
    def smu(self):
        return self._smu

    def connect(self):
        # The wrapped SMU / SimulatedSMU already opens its connection in
        # __init__ (untouched, tested behavior) -- nothing to do here.
        pass

    def disconnect(self):
        """
        Close the shared connection once, safe to call from both channels.

        Best-effort disables output before closing -- mirrors
        Keithley2400EQE.disconnect()'s safe-shutdown behavior, so a
        disconnect never leaves the test cell biased regardless of which
        hardware profile is active.
        """
        if self._closed:
            return
        self._closed = True
        try:
            self._smu.disable_output()
        except Exception:
            pass
        self._smu.close()

    def _ensure_measured(self):
        if not self._fresh:
            self._smu.run_dual_measurement()
            self._smu.chA, self._smu.chB = self._smu.get_average()
            self._fresh = True
            self._consumed = set()

    def read_channel(self, channel: str) -> float:
        self._ensure_measured()
        self._consumed.add(channel)
        if len(self._consumed) >= 2:
            # Both channels have been read for this cycle -- next read
            # triggers a fresh synchronized acquisition.
            self._fresh = False
        return self._smu.chA if channel == "A" else self._smu.chB

    @property
    def compliance_hit(self) -> bool:
        return getattr(self._smu, "compliance_hit", False)


def _describe_dual_channel_smu(smu, channel: str) -> str:
    """Identity string for a dual-channel role (real SMU or SimulatedSMU)."""
    model = getattr(smu, "Keithley_model", None)
    if model:
        base = f"Keithley {model}"
        sn = getattr(smu, "SN", None)
        if sn:
            base += f" (SN {sn})"
    else:
        base = type(smu).__name__  # e.g. "SimulatedSMU"
    return f"{base}, channel {channel}"


class DualChannelReferenceMeter(CurrentMeter):
    """Reference-signal role backed by channel A of a shared dual-channel session."""

    def __init__(self, session: DualChannelSMUSession):
        self._session = session
        self.dark_current = 0.0

    def connect(self):
        self._session.connect()

    def disconnect(self):
        self._session.disconnect()

    def measure_current(self) -> float:
        return self._session.read_channel("A")

    @property
    def identity(self) -> str:
        return _describe_dual_channel_smu(self._session.smu, "A")


class DualChannelTestMeter(BiasCurrentMeter):
    """Test-cell + bias role backed by channel B of a shared dual-channel session."""

    def __init__(self, session: DualChannelSMUSession):
        self._session = session
        self.dark_current = 0.0

    def connect(self):
        self._session.connect()

    def disconnect(self):
        self._session.disconnect()

    def measure_current(self) -> float:
        return self._session.read_channel("B")

    @property
    def identity(self) -> str:
        return _describe_dual_channel_smu(self._session.smu, "B")

    def set_bias_voltage(self, voltage: float):
        self._session.smu.set_bias_voltage(voltage)

    def set_compliance_current(self, current: float):
        self._session.smu.set_compliance_current(current)

    def output_on(self):
        self._session.smu.enable_output()

    def output_off(self):
        self._session.smu.disable_output()

    @property
    def compliance_hit(self) -> bool:
        return self._session.compliance_hit

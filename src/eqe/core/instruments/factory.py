"""
Hardware factory: the single place that translates a hardware configuration
into the logical `reference_meter` / `test_meter` / `monochromator` roles
consumed by the measurement engine (see `instruments/roles.py`).

Which physical instrument plays which role is selected by
`config["instruments"]["active_profile"]`, with each profile's settings
under `config["instruments"]["profiles"][<name>]` (see
`config/config_default.yaml`). Two profiles are provided out of the box:

    keithley2000_2400  -- Keithley 2000 (reference) + Keithley 2400
                           (test cell + bias). Current replacement hardware.
    keithley2600        -- Keithley 2600, channel A (reference) / channel B
                           (test cell + bias). Original hardware; kept so
                           the app can go back to it without code changes.

Adding another instrument/profile means adding a builder function here (or
a new profile entry in the config) -- the measurement engine and GUI never
need to change.
"""

from eqe.core.instruments.monochromator import Cornerstone130
from eqe.core.instruments.smu import SMU
from eqe.core.instruments.keithley2000 import Keithley2000
from eqe.core.instruments.keithley2400 import Keithley2400EQE
from eqe.core.instruments.dual_channel import (
    DualChannelSMUSession,
    DualChannelReferenceMeter,
    DualChannelTestMeter,
)
from eqe.core.instruments.roles import MeasurementHardware
from eqe.core.instruments.simulated import SimulatedMonochromator, SimulatedSMU
from eqe.config.load_config import load_config


# ---------------------------------------------------------------------
# Per-driver builders (role config dict -> connected role object)
# ---------------------------------------------------------------------

def _build_keithley2000(role_cfg):
    conn = role_cfg.get("connection", {})

    kwargs = {"interface": conn.get("type", "serial")}
    if "port" in conn:
        kwargs["port"] = conn["port"]
    if "baudrate" in conn:
        kwargs["baudrate"] = conn["baudrate"]
    if "gpib_resource" in conn:
        kwargs["gpib_resource"] = conn["gpib_resource"]

    for key in ("nplc", "current_range", "samples", "timeout"):
        if key in role_cfg:
            kwargs[key] = role_cfg[key]

    meter = Keithley2000(**kwargs)
    meter.connect()
    return meter


def _build_keithley2400(role_cfg):
    conn = role_cfg.get("connection", {})

    kwargs = {}
    if "resource" in conn:
        kwargs["resource"] = conn["resource"]
    if "baud_rate" in conn:
        kwargs["baud_rate"] = conn["baud_rate"]

    for key in (
        "nplc",
        "samples",
        "current_compliance",
        "bias_voltage",
        "ramp_steps",
        "ramp_delay_s",
        "discard_first_reading",
        "compliance_fraction",
        "timeout_ms",
    ):
        if key in role_cfg:
            kwargs[key] = role_cfg[key]

    # Embedded in the EQE engine, a compliance hit should be reported and
    # the scan should continue -- like the Keithley 2600 path -- rather
    # than raise. See keithley2400.py module docstring.
    kwargs["raise_on_compliance"] = False

    meter = Keithley2400EQE(**kwargs)
    meter.connect()
    return meter


# Dispatch table for independently-connected current meters. This is the
# one place instrument-type branching is allowed to live -- the
# measurement engine never sees it.
_METER_BUILDERS = {
    "keithley2000": _build_keithley2000,
    "keithley2400": _build_keithley2400,
}


def _build_keithley2600_pair(profile_cfg, N=None, nplc=None, interval=None):
    """
    Build the reference/test role pair for a dual-channel Keithley 2600.

    Both roles share one physical connection (`DualChannelSMUSession`) --
    see dual_channel.py for why, and how the shared triggered acquisition
    is preserved.
    """
    resource = profile_cfg.get("resource", "GPIB1::24::INSTR")

    n_ = N if N is not None else profile_cfg.get("N", 500)
    nplc_ = nplc if nplc is not None else profile_cfg.get("nplc", 0.01)
    interval_ = interval if interval is not None else profile_cfg.get("interval", 0.002)

    smu = SMU(address=resource, N=n_, nplc=nplc_, interval=interval_)
    smu.upload_script()

    # Preserve tested behavior: run_dual_measurement() has always used
    # these fixed values regardless of what was requested above.
    smu.N = 500
    smu.nplc = 0.01
    smu.interval = 0.001

    session = DualChannelSMUSession(smu)
    return DualChannelReferenceMeter(session), DualChannelTestMeter(session)


def build_hardware(config, N=None, nplc=None, interval=None):
    """
    Build a `MeasurementHardware` (reference_meter / test_meter /
    monochromator) from `config["instruments"]`.
    """
    instruments_cfg = config["instruments"]
    profile_name = instruments_cfg.get("active_profile", "keithley2000_2400")
    profiles = instruments_cfg.get("profiles", {})

    if profile_name not in profiles:
        raise KeyError(
            f"Unknown instruments.active_profile: {profile_name!r}. "
            f"Available profiles: {sorted(profiles)}"
        )

    profile_cfg = profiles[profile_name]
    ref_driver = profile_cfg["reference_meter"]["driver"]
    test_driver = profile_cfg["test_meter"]["driver"]

    if ref_driver == "keithley2600" and test_driver == "keithley2600":
        reference_meter, test_meter = _build_keithley2600_pair(
            profile_cfg, N=N, nplc=nplc, interval=interval
        )
    else:
        if ref_driver not in _METER_BUILDERS:
            raise ValueError(f"Unknown reference_meter driver: {ref_driver!r}")
        if test_driver not in _METER_BUILDERS:
            raise ValueError(f"Unknown test_meter driver: {test_driver!r}")

        reference_meter = _METER_BUILDERS[ref_driver](profile_cfg["reference_meter"])
        test_meter = _METER_BUILDERS[test_driver](profile_cfg["test_meter"])

    mono = Cornerstone130(
        instruments_cfg["mono_port"],
        grating_change_nm=config["calibration"]["grating_change_nm"],
    )
    print(mono.info)

    return MeasurementHardware(
        reference_meter=reference_meter,
        test_meter=test_meter,
        monochromator=mono,
    )


def initialize_system(
    hardware=None,
    N=None,
    nplc=None,
    interval=None,
    simulate=False,
    simulate_profile="good_cell",
):
    """
    Connect (or reuse) the configured hardware and return a
    `MeasurementHardware`.

    `hardware`, if given, is a previously connected `MeasurementHardware`
    that will be closed before reconnecting (matching the previous
    mono/smu reconnect behavior).
    """

    if simulate:
        sim_smu = SimulatedSMU(profile=simulate_profile)
        sim_mono = SimulatedMonochromator(smu=sim_smu)

        session = DualChannelSMUSession(sim_smu)
        hardware = MeasurementHardware(
            reference_meter=DualChannelReferenceMeter(session),
            test_meter=DualChannelTestMeter(session),
            monochromator=sim_mono,
        )
        # SimulatedSMU already starts with a fixed dark current; no need to
        # trigger a measurement to obtain it.
        hardware.reference_meter.dark_current = sim_smu.chA_dark
        hardware.test_meter.dark_current = sim_smu.chB_dark
        return hardware

    if hardware is not None:
        hardware.close()

    config = load_config()
    hardware = build_hardware(config, N=N, nplc=nplc, interval=interval)

    hardware.monochromator.shutter(True)
    hardware.reference_meter.dark_current = hardware.reference_meter.measure_current()
    hardware.test_meter.dark_current = hardware.test_meter.measure_current()

    return hardware

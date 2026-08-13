"""
Focused, hardware-independent tests for the instrument role abstraction
(CurrentMeter / BiasCurrentMeter / MeasurementHardware) introduced to
decouple the measurement engine from any particular Keithley model.

Run with:
    python -m unittest discover -s tests -v

No real instruments are used -- everything here talks to fakes/mocks.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.core.instruments.roles import CurrentMeter, BiasCurrentMeter, MeasurementHardware
from eqe.core.instruments.dual_channel import (
    DualChannelSMUSession,
    DualChannelReferenceMeter,
    DualChannelTestMeter,
)
from eqe.core.measurement_engine import perform_measurement


# ---------------------------------------------------------------------
# Fakes standing in for physical instruments
# ---------------------------------------------------------------------

class FakeMonochromator:
    info = "Fake monochromator"

    def __init__(self):
        self.position = None
        self.shutter_closed = None

    def shutter(self, close):
        self.shutter_closed = close

    def goto_nm(self, nm, on_status=None, wait=True):
        self.position = nm


class FakeCurrentMeter(CurrentMeter):
    """Minimal reference-role fake: a fixed current plus dark offset."""

    def __init__(self, value=1e-6, dark_current=0.0):
        self.value = value
        self.dark_current = dark_current
        self.connected = False
        self.measure_count = 0

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def measure_current(self) -> float:
        self.measure_count += 1
        return self.value


class FakeBiasCurrentMeter(BiasCurrentMeter):
    """Minimal test-cell-role fake with bias/compliance bookkeeping."""

    def __init__(self, value=2e-6, dark_current=0.0):
        self.value = value
        self.dark_current = dark_current
        self.connected = False
        self.measure_count = 0
        self.bias_voltage = None
        self.compliance_current = None
        self.output_enabled = False
        self._compliance_hit = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def measure_current(self) -> float:
        self.measure_count += 1
        return self.value

    def set_bias_voltage(self, voltage: float):
        self.bias_voltage = voltage

    def set_compliance_current(self, current: float):
        self.compliance_current = current

    def output_on(self):
        self.output_enabled = True

    def output_off(self):
        self.output_enabled = False

    @property
    def compliance_hit(self) -> bool:
        return self._compliance_hit


class OutputRequiredBiasCurrentMeter(FakeBiasCurrentMeter):
    """
    Mimics the real Keithley 2400: a current reading only succeeds while
    the source output is enabled (on real hardware, reading with output
    off hangs until the instrument times out; here it raises instead so
    the test fails fast rather than hanging).
    """

    def measure_current(self) -> float:
        if not self.output_enabled:
            raise RuntimeError("read attempted with source output disabled")
        return super().measure_current()


class ExplodingBiasCurrentMeter(FakeBiasCurrentMeter):
    """Raises on the second reading, to exercise the exception-safety path."""

    def measure_current(self) -> float:
        self.measure_count += 1
        if self.measure_count >= 2:
            raise RuntimeError("simulated communication loss")
        return self.value


# ---------------------------------------------------------------------
# Engine tests: it must operate on roles only, never on instrument type
# ---------------------------------------------------------------------

class PerformMeasurementRoleAgnosticTests(unittest.TestCase):
    def _calibration_df(self, wavelengths):
        return pd.DataFrame(
            {"incident beam current (A)/intSiref current (A)": [1.0] * len(wavelengths)},
            index=wavelengths,
        )

    def test_scan_completes_with_mock_hardware(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6, dark_current=1e-8)
        test_meter = FakeBiasCurrentMeter(value=5e-7, dark_current=2e-8)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        nm_lim = (400, 420)
        df_incbeamcurr = self._calibration_df(range(400, 421, 10))

        df = perform_measurement(
            hardware,
            df_incbeamcurr,
            calibration_measurement=False,
            nm_lim=nm_lim,
            delta_nm=10,
        )

        # Full sweep: 400, 410, 420
        self.assertEqual(len(df), 3)
        self.assertIn("EQE (%)", df.columns)
        self.assertEqual(reference_meter.measure_count, 3)
        self.assertEqual(test_meter.measure_count, 3)

        # Dark current must be subtracted by the engine (role-agnostic logic).
        expected_ref = reference_meter.value - reference_meter.dark_current
        self.assertAlmostEqual(df["Current ref-chA (A)"].iloc[0], expected_ref)

    def test_bias_is_applied_and_reset_on_normal_completion(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = FakeBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 411, 10))

        perform_measurement(
            hardware,
            df_incbeamcurr,
            calibration_measurement=False,
            nm_lim=(400, 410),
            delta_nm=10,
            bias_enabled=True,
            bias_voltage=0.3,
            compliance_current=1e-3,
        )

        # Bias must have been applied during the scan and reset to 0 V at the end.
        self.assertEqual(test_meter.compliance_current, 1e-3)
        self.assertEqual(test_meter.bias_voltage, 0.0)
        self.assertFalse(test_meter.output_enabled)

    def test_output_is_reenabled_at_scan_start_even_without_bias(self):
        """
        Regression test: a previous scan's end-of-run output_off() cleanup
        must not leave the *next* scan (even a bias-disabled one) unable to
        take a reading. The test-cell source output is required for any
        current reading, biased or not.
        """
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = OutputRequiredBiasCurrentMeter()
        test_meter.output_enabled = False  # as left by a previous scan's cleanup
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 411, 10))

        df = perform_measurement(
            hardware,
            df_incbeamcurr,
            calibration_measurement=False,
            nm_lim=(400, 410),
            delta_nm=10,
            bias_enabled=False,
        )

        self.assertEqual(len(df), 2)
        self.assertEqual(test_meter.measure_count, 2)
        # Left off again at the end, ready for the next scan to re-enable it.
        self.assertFalse(test_meter.output_enabled)

    def test_bias_is_reset_even_if_measurement_raises(self):
        """
        Safety requirement: an aborted measurement must not leave the
        test-cell source output enabled.
        """
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = ExplodingBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 431, 10))

        with self.assertRaises(RuntimeError):
            perform_measurement(
                hardware,
                df_incbeamcurr,
                calibration_measurement=False,
                nm_lim=(400, 430),
                delta_nm=10,
                bias_enabled=True,
                bias_voltage=0.5,
            )

        # Even though the loop raised, cleanup in `finally` must have run.
        self.assertEqual(test_meter.bias_voltage, 0.0)
        self.assertFalse(test_meter.output_enabled)


# ---------------------------------------------------------------------
# DualChannelSMUSession: shared-connection synchronization (Keithley 2600)
# ---------------------------------------------------------------------

class FakeDualChannelSMU:
    """Stands in for `SMU`/`SimulatedSMU`: one triggered read serves both channels."""

    def __init__(self):
        self.trigger_count = 0
        self.chA = 0.0
        self.chB = 0.0
        self.chA_dark = 0.0
        self.chB_dark = 0.0
        self.closed = False
        self.bias_voltage = None
        self.compliance_current = None
        self.output_enabled = False

    def run_dual_measurement(self):
        self.trigger_count += 1
        self.chA = 1e-6 * self.trigger_count
        self.chB = 2e-6 * self.trigger_count

    def get_average(self):
        return self.chA, self.chB

    def set_bias_voltage(self, v):
        self.bias_voltage = v

    def set_compliance_current(self, i):
        self.compliance_current = i

    def enable_output(self):
        self.output_enabled = True

    def disable_output(self):
        self.output_enabled = False

    def close(self):
        self.closed = True


class DualChannelSessionTests(unittest.TestCase):
    def test_one_trigger_serves_both_channels_regardless_of_read_order(self):
        smu = FakeDualChannelSMU()
        session = DualChannelSMUSession(smu)
        reference_meter = DualChannelReferenceMeter(session)
        test_meter = DualChannelTestMeter(session)

        # Cycle 1: read reference first, then test -- one trigger.
        ref_1 = reference_meter.measure_current()
        test_1 = test_meter.measure_current()
        self.assertEqual(smu.trigger_count, 1)
        self.assertEqual(ref_1, smu.chA)
        self.assertEqual(test_1, smu.chB)

        # Cycle 2: read test first, then reference -- a second, single trigger.
        test_2 = test_meter.measure_current()
        ref_2 = reference_meter.measure_current()
        self.assertEqual(smu.trigger_count, 2)
        self.assertEqual(test_2, smu.chB)
        self.assertEqual(ref_2, smu.chA)

    def test_disconnect_closes_shared_connection_once(self):
        smu = FakeDualChannelSMU()
        session = DualChannelSMUSession(smu)
        reference_meter = DualChannelReferenceMeter(session)
        test_meter = DualChannelTestMeter(session)

        reference_meter.disconnect()
        test_meter.disconnect()

        self.assertTrue(smu.closed)

    def test_bias_and_output_delegate_to_shared_smu(self):
        smu = FakeDualChannelSMU()
        session = DualChannelSMUSession(smu)
        test_meter = DualChannelTestMeter(session)

        test_meter.set_bias_voltage(0.25)
        test_meter.set_compliance_current(1e-3)
        test_meter.output_on()
        self.assertEqual(smu.bias_voltage, 0.25)
        self.assertEqual(smu.compliance_current, 1e-3)
        self.assertTrue(smu.output_enabled)

        test_meter.output_off()
        self.assertFalse(smu.output_enabled)


# ---------------------------------------------------------------------
# Factory: config -> correct logical hardware, for both profiles
# ---------------------------------------------------------------------

class BuildHardwareTests(unittest.TestCase):
    """
    Verifies that `build_hardware()` wires up the expected role types for
    both shipped profiles, without talking to real hardware: the driver
    classes it would normally construct are replaced with fakes.
    """

    def _config(self, active_profile):
        return {
            "instruments": {
                "mono_port": "COM_TEST",
                "active_profile": active_profile,
                "profiles": {
                    "keithley2000_2400": {
                        "reference_meter": {
                            "driver": "keithley2000",
                            "connection": {"type": "serial", "port": "COM10", "baudrate": 9600},
                            "nplc": 1.0,
                        },
                        "test_meter": {
                            "driver": "keithley2400",
                            "connection": {"resource": "ASRL8::INSTR"},
                            "nplc": 1.0,
                        },
                    },
                    "keithley2600": {
                        "resource": "GPIB_TEST::INSTR",
                        "N": 500,
                        "nplc": 0.01,
                        "interval": 0.002,
                        "reference_meter": {"driver": "keithley2600", "channel": "A"},
                        "test_meter": {"driver": "keithley2600", "channel": "B"},
                    },
                },
            },
            "calibration": {"grating_change_nm": 850},
        }

    def test_keithley2000_2400_profile(self):
        from eqe.core.instruments import factory

        fake_ref = FakeCurrentMeter()
        fake_test = FakeBiasCurrentMeter()

        with mock.patch.object(factory, "Keithley2000", return_value=fake_ref), \
             mock.patch.object(factory, "Keithley2400EQE", return_value=fake_test), \
             mock.patch.object(factory, "Cornerstone130", return_value=FakeMonochromator()):
            hardware = factory.build_hardware(self._config("keithley2000_2400"))

        self.assertIs(hardware.reference_meter, fake_ref)
        self.assertIs(hardware.test_meter, fake_test)
        self.assertTrue(fake_ref.connected)
        self.assertTrue(fake_test.connected)

    def test_keithley2600_profile_shares_one_session(self):
        from eqe.core.instruments import factory

        fake_smu = FakeDualChannelSMU()

        def fake_smu_ctor(*args, **kwargs):
            return fake_smu

        with mock.patch.object(factory, "SMU", side_effect=fake_smu_ctor), \
             mock.patch.object(factory, "Cornerstone130", return_value=FakeMonochromator()):
            # `SMU.upload_script()` is called unconditionally; give the fake one.
            fake_smu.upload_script = lambda: None
            hardware = factory.build_hardware(self._config("keithley2600"))

        self.assertIsInstance(hardware.reference_meter, DualChannelReferenceMeter)
        self.assertIsInstance(hardware.test_meter, DualChannelTestMeter)
        # Both roles must share the same underlying SMU connection.
        self.assertIs(hardware.reference_meter._session, hardware.test_meter._session)
        self.assertIs(hardware.reference_meter._session.smu, fake_smu)


if __name__ == "__main__":
    unittest.main()

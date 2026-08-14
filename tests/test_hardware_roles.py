"""
Focused, hardware-independent tests for the instrument role abstraction
(CurrentMeter / BiasCurrentMeter / MeasurementHardware) introduced to
decouple the measurement engine from any particular Keithley model.

Run with:
    python -m unittest discover -s tests -v

No real instruments are used -- everything here talks to fakes/mocks.
"""

import sys
import tempfile
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
from eqe.core.measurement_engine import perform_measurement, perform_live_monitoring


# ---------------------------------------------------------------------
# Fakes standing in for physical instruments
# ---------------------------------------------------------------------

class FakeMonochromator:
    info = "Fake monochromator"

    def __init__(self):
        self.position = None
        self.shutter_closed = None
        # Every position visited, in order -- lets tests distinguish "moved
        # through X" from "ended up at X by coincidence".
        self.history = []

    def shutter(self, close):
        self.shutter_closed = close

    def goto_nm(self, nm, on_status=None, wait=True):
        self.position = nm
        self.history.append(nm)


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
        self.assertAlmostEqual(df["Current ref (A)"].iloc[0], expected_ref)

    def test_descending_direction_scans_high_to_low(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = FakeBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 421, 10))

        df = perform_measurement(
            hardware,
            df_incbeamcurr,
            calibration_measurement=False,
            nm_lim=(400, 420),
            delta_nm=10,
            direction="Descending",
        )

        self.assertEqual(list(df.index), [420, 410, 400])

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
# Stabilization time: the "Advanced Acquisition Settings" wait applied
# after every wavelength move, before that point's reading (see
# AdvancedAcquisitionPanel). interruptible_sleep() is mocked out so these
# tests don't actually sleep -- only that it's *called* with the right
# duration matters here.
# ---------------------------------------------------------------------

class StabilizationTimeTests(unittest.TestCase):
    def _calibration_df(self, wavelengths):
        return pd.DataFrame(
            {"incident beam current (A)/intSiref current (A)": [1.0] * len(wavelengths)},
            index=list(wavelengths),
        )

    def test_scan_mode_waits_after_each_wavelength_move(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = FakeBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )
        df_incbeamcurr = self._calibration_df(range(400, 421, 10))

        with mock.patch(
            "eqe.core.measurement_engine.interruptible_sleep", return_value=True
        ) as sleep_mock:
            perform_measurement(
                hardware,
                df_incbeamcurr,
                calibration_measurement=False,
                nm_lim=(400, 420),
                delta_nm=10,
                stabilization_time_s=0.25,
            )

        sleep_durations = [call.args[0] for call in sleep_mock.call_args_list]
        # Once per point (3 points: 400, 410, 420), in addition to the
        # pre-existing 2.0s grating-change wait on the first point.
        self.assertEqual(sleep_durations.count(0.25), 3)

    def test_scan_mode_skips_wait_when_stabilization_time_is_zero(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = FakeBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )
        df_incbeamcurr = self._calibration_df(range(400, 411, 10))

        with mock.patch(
            "eqe.core.measurement_engine.interruptible_sleep", return_value=True
        ) as sleep_mock:
            perform_measurement(
                hardware,
                df_incbeamcurr,
                calibration_measurement=False,
                nm_lim=(400, 410),
                delta_nm=10,
                stabilization_time_s=0.0,
            )

        # Only the pre-existing grating-change wait remains; no extra
        # per-point stabilization wait was added.
        sleep_durations = [call.args[0] for call in sleep_mock.call_args_list]
        self.assertEqual(sleep_durations, [2.0])

    def test_live_monitoring_waits_after_initial_and_mid_run_moves(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6)
        test_meter = FakeBiasCurrentMeter(value=2e-6)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )
        df_incbeamcurr = self._calibration_df(range(400, 601, 10))

        targets = iter([550, 600, 600])

        def get_target_wavelength():
            return next(targets, 600)

        calls = {"n": 0}

        def stop_requested():
            calls["n"] += 1
            return calls["n"] > 3

        with mock.patch(
            "eqe.core.measurement_engine.interruptible_sleep", return_value=True
        ) as sleep_mock:
            perform_live_monitoring(
                hardware,
                df_incbeamcurr,
                wavelength_nm=550,
                stop_requested=stop_requested,
                update_interval_s=0,
                get_target_wavelength=get_target_wavelength,
                stabilization_time_s=0.1,
            )

        sleep_durations = [call.args[0] for call in sleep_mock.call_args_list]
        # Once for the initial move to 550, once for the mid-run move to
        # 600 (update_interval_s=0 disables the separate pacing sleep, so
        # these are the only calls).
        self.assertEqual(sleep_durations.count(0.1), 2)
        self.assertEqual(len(sleep_durations), 2)


# ---------------------------------------------------------------------
# Automatic "latest calibration" selection (analysis/calibration.py)
# ---------------------------------------------------------------------

class FindLatestIncidentBeamFileTests(unittest.TestCase):
    def test_picks_file_with_latest_encoded_timestamp(self):
        from eqe.analysis.calibration import find_latest_incident_beam_file

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            older = tmp / (
                "incbeamcurr_Si71889_850nm-wavelength-change_"
                "date2025-10-23_time10-49-42.csv"
            )
            newer = tmp / (
                "incbeamcurr_Si71889_850nm-wavelength-change_"
                "date2026-08-14_time14-20-53.csv"
            )
            # Write the "older" file *after* the "newer" one, so mtime
            # would pick the wrong file if it were used instead of the
            # filename-encoded timestamp.
            newer.write_text("x")
            older.write_text("x")

            result = find_latest_incident_beam_file(tmp)

        self.assertEqual(result, newer)

    def test_returns_none_when_no_files_present(self):
        from eqe.analysis.calibration import find_latest_incident_beam_file

        with tempfile.TemporaryDirectory() as tmp:
            result = find_latest_incident_beam_file(Path(tmp))

        self.assertIsNone(result)

    def test_falls_back_to_mtime_for_unrecognized_filenames(self):
        import os
        import time

        from eqe.analysis.calibration import find_latest_incident_beam_file

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            first = tmp / "incbeamcurr_legacy_name.csv"
            first.write_text("x")
            second = tmp / "incbeamcurr_newer_legacy_name.csv"
            second.write_text("x")

            # Neither filename matches the timestamp pattern, so mtime is
            # what decides -- set them explicitly rather than relying on
            # two back-to-back writes landing in different mtime ticks.
            now = time.time()
            os.utime(first, (now - 100, now - 100))
            os.utime(second, (now, now))

            result = find_latest_incident_beam_file(tmp)

        self.assertEqual(result, second)


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


class LiveMonitoringWavelengthChangeTests(unittest.TestCase):
    """
    Regression coverage for changing the target wavelength while
    perform_live_monitoring() is running, without stopping/restarting it.
    """

    def _calibration_df(self, wavelengths):
        # Distinct ratio per wavelength so a wrong/stale lookup is
        # detectable, not just coincidentally correct.
        return pd.DataFrame(
            {
                "incident beam current (A)/intSiref current (A)": [
                    1.0 + 0.1 * i for i in range(len(wavelengths))
                ]
            },
            index=list(wavelengths),
        )

    def test_wavelength_change_moves_mono_and_updates_calibration(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6)
        test_meter = FakeBiasCurrentMeter(value=2e-6)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 601, 10))

        calls = {"n": 0}
        targets = iter([550, 550, 600, 600])  # switches to 600 on the 3rd read

        def get_target_wavelength():
            return next(targets, 600)

        def stop_requested():
            calls["n"] += 1
            return calls["n"] > 4

        perform_live_monitoring(
            hardware,
            df_incbeamcurr,
            wavelength_nm=550,
            stop_requested=stop_requested,
            update_interval_s=0,
            get_target_wavelength=get_target_wavelength,
        )

        # The monochromator must have moved to the changed-to wavelength
        # during the run (and the calibration ratio used for the last
        # readings must be the one for 600 nm, not stale from 550 nm --
        # covered by test_wavelength_change_moves_mono_and_updates_calibration's
        # sibling test on the returned DataFrame). It's parked back at
        # 550 nm once finished (see test_returns_monochromator_to_550nm_when_finished),
        # so check the move happened rather than the final position.
        self.assertIn(600, mono.history)

    def test_returns_time_series_dataframe_including_wavelength_changes(self):
        """
        perform_live_monitoring() must return the actual time-series data
        (not an empty DataFrame) so it can be saved -- including the
        per-point wavelength, since it can change mid-run.
        """
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6)
        test_meter = FakeBiasCurrentMeter(value=2e-6)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df(range(400, 601, 10))

        targets = iter([550, 600, 600])

        def get_target_wavelength():
            return next(targets, 600)

        calls = {"n": 0}

        def stop_requested():
            calls["n"] += 1
            return calls["n"] > 3

        df = perform_live_monitoring(
            hardware,
            df_incbeamcurr,
            wavelength_nm=550,
            stop_requested=stop_requested,
            update_interval_s=0,
            get_target_wavelength=get_target_wavelength,
        )

        self.assertEqual(df.index.name, "Time (s)")
        self.assertEqual(
            list(df.columns),
            ["Wavelength (nm)", "EQE (%)", "Current ref (A)", "Current cell (A)"],
        )
        self.assertEqual(len(df), 3)
        # First reading(s) at 550, later ones after the change at 600.
        self.assertEqual(df["Wavelength (nm)"].iloc[0], 550.0)
        self.assertEqual(df["Wavelength (nm)"].iloc[-1], 600.0)

    def test_no_target_wavelength_callback_behaves_as_before(self):
        """get_target_wavelength=None (the default) must not change behavior."""
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6)
        test_meter = FakeBiasCurrentMeter(value=2e-6)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df([550])

        calls = {"n": 0}

        def stop_requested():
            calls["n"] += 1
            return calls["n"] > 2

        perform_live_monitoring(
            hardware,
            df_incbeamcurr,
            wavelength_nm=550,
            stop_requested=stop_requested,
            update_interval_s=0,
        )

        self.assertEqual(mono.position, 550)

    def test_returns_monochromator_to_550nm_when_finished(self):
        """
        Measuring at a wavelength other than 550nm must still leave the
        monochromator parked at 550nm afterward, matching
        perform_measurement()'s behavior (not just coincidentally already
        there, as the other tests in this class start at 550nm).
        """
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter(value=1e-6)
        test_meter = FakeBiasCurrentMeter(value=2e-6)
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        df_incbeamcurr = self._calibration_df([700])

        calls = {"n": 0}

        def stop_requested():
            calls["n"] += 1
            return calls["n"] > 2

        perform_live_monitoring(
            hardware,
            df_incbeamcurr,
            wavelength_nm=700,
            stop_requested=stop_requested,
            update_interval_s=0,
        )

        self.assertEqual(mono.position, 550)


class LiveMonitoringBiasResetOnEarlyFailureTests(unittest.TestCase):
    """
    Safety requirement: whenever bias has been applied, it must be reset
    to 0V afterward -- including when perform_live_monitoring() fails
    before ever entering its measurement loop (e.g. an invalid starting
    wavelength), not just failures during the loop itself.
    """

    def test_bias_is_reset_if_initial_wavelength_lookup_fails(self):
        mono = FakeMonochromator()
        reference_meter = FakeCurrentMeter()
        test_meter = FakeBiasCurrentMeter()
        hardware = MeasurementHardware(
            reference_meter=reference_meter, test_meter=test_meter, monochromator=mono
        )

        # Calibration table does not contain 550nm -- lookup_ratio() must
        # raise KeyError before the loop (and thus before the loop's own
        # try/finally used to begin).
        df_incbeamcurr = pd.DataFrame(
            {"incident beam current (A)/intSiref current (A)": [1.0]},
            index=[600],
        )

        with self.assertRaises(KeyError):
            perform_live_monitoring(
                hardware,
                df_incbeamcurr,
                wavelength_nm=550,
                bias_enabled=True,
                bias_voltage=0.4,
                stop_requested=lambda: False,
            )

        self.assertEqual(test_meter.bias_voltage, 0.0)
        self.assertFalse(test_meter.output_enabled)


class SimulatedHardwareBiasTests(unittest.TestCase):
    """
    Exercises the *real* simulated hardware path (factory.initialize_system
    -> SimulatedSMU/SimulatedMonochromator, not a hand-written fake), so a
    method the engine calls but the simulator doesn't implement fails this
    test instead of only failing silently at runtime. A fake that diverges
    from the real simulator (e.g. implementing set_compliance_current()
    when SimulatedSMU doesn't) cannot mask a regression here.
    """

    def _calibration_df(self, wavelengths):
        return pd.DataFrame(
            {"incident beam current (A)/intSiref current (A)": [1.0] * len(wavelengths)},
            index=list(wavelengths),
        )

    def test_bias_enabled_scan_against_real_simulated_hardware(self):
        from eqe.core.instruments.factory import initialize_system

        hardware = initialize_system(simulate=True, simulate_profile="good_cell")

        warnings = []
        df_incbeamcurr = self._calibration_df(range(400, 411, 10))

        df = perform_measurement(
            hardware,
            df_incbeamcurr,
            calibration_measurement=False,
            nm_lim=(400, 410),
            delta_nm=10,
            bias_enabled=True,
            bias_voltage=0.2,
            compliance_current=1e-3,
            on_status=warnings.append,
        )

        self.assertEqual(len(df), 2)
        failed = [w for w in warnings if "Failed to apply bias" in w]
        self.assertEqual(
            failed, [], f"bias application failed against real simulated hardware: {failed}"
        )
        self.assertEqual(hardware.test_meter._session.smu.compliance_current, 1e-3)


class ControllerReconnectTests(unittest.TestCase):
    """
    connect_instruments() must reconnect when the requested
    simulate/simulate_profile no longer matches the connected hardware,
    instead of silently reusing real hardware after Simulation is
    unchecked (or vice versa).
    """

    def test_reconnects_when_simulate_toggle_changes(self):
        from eqe.core import controller as controller_module

        ctrl = controller_module.MeasurementController()

        calls = []

        def fake_initialize_system(
            hardware=None, N=None, nplc=None, interval=None,
            simulate=False, simulate_profile="good_cell",
        ):
            calls.append(simulate)
            return MeasurementHardware(
                reference_meter=FakeCurrentMeter(),
                test_meter=FakeBiasCurrentMeter(),
                monochromator=FakeMonochromator(),
            )

        with mock.patch.object(
            controller_module, "initialize_system", side_effect=fake_initialize_system
        ):
            ctrl.connect_instruments(simulate=True)
            ctrl.connect_instruments(simulate=True)  # same flag -> reuse
            ctrl.connect_instruments(simulate=False)  # changed -> reconnect

        self.assertEqual(calls, [True, False])


class FactorySimulateSwitchTests(unittest.TestCase):
    """Switching to simulated hardware must not leak a prior connection."""

    def test_switching_to_simulate_closes_previous_hardware(self):
        from eqe.core.instruments.factory import initialize_system

        closed = {"called": False}

        class FakeOldHardware:
            def close(self):
                closed["called"] = True

        hardware = initialize_system(hardware=FakeOldHardware(), simulate=True)

        self.assertTrue(closed["called"])
        self.assertIsInstance(hardware, MeasurementHardware)


if __name__ == "__main__":
    unittest.main()

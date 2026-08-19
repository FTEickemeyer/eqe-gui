"""
Focused tests for the Keithley 2000 reference-meter driver's DC-current
range configuration.

No real hardware involved: `write()` is monkeypatched to record the SCPI
commands sent instead of talking to a serial port, so `configure()` can be
exercised directly.

Context: the reference cell's photocurrent spans 2-3 orders of magnitude
across a wavelength sweep, so a fixed range (the old default: 0.01 A,
autorange off) leaves poor resolution for most of that range -- this was
found to be the root cause of a noisy reference-cell measurement
(2026-08-14). Autorange (matching what the Keithley 2400 test-cell meter
already does) is now the default; these tests guard against that
regressing back to a fixed range silently.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.core.instruments.keithley2000 import Keithley2000


def _make_meter(**kwargs):
    meter = Keithley2000(**kwargs)
    sent = []
    meter.write = sent.append  # bypass the real serial/GPIB connection
    meter._check_connection = lambda: None
    return meter, sent


class Keithley2000RangeConfigurationTests(unittest.TestCase):
    def test_autorange_is_the_default(self):
        meter, _ = _make_meter()
        self.assertTrue(meter.autorange)

    def test_nplc_default_is_5_not_1(self):
        """
        Regression guard: NPLC was raised from 1 to 5 after a noisy
        Si71889 calibration measurement (2026-08-14) -- on real hardware,
        this measured ~5x lower relative noise at a weak-signal wavelength
        (the instrument's DC current function only has one, oversized
        range, so longer integration is what actually helps -- autorange
        alone makes no difference on this specific instrument).
        """
        meter, _ = _make_meter()
        self.assertEqual(meter.nplc, 5.0)

    def test_configure_enables_autorange_by_default(self):
        meter, sent = _make_meter()
        meter.configure()

        self.assertIn(":SENS:CURR:DC:RANG:AUTO ON", sent)
        self.assertFalse(
            any(cmd.startswith(":SENS:CURR:DC:RANG:AUTO OFF") for cmd in sent)
        )
        # No fixed-range command should be sent while autoranging.
        self.assertFalse(
            any(
                cmd.startswith(":SENS:CURR:DC:RANG ")
                and not cmd.startswith(":SENS:CURR:DC:RANG:AUTO")
                for cmd in sent
            )
        )

    def test_configure_with_autorange_off_uses_fixed_range(self):
        meter, sent = _make_meter(autorange=False, current_range=0.002)
        meter.configure()

        self.assertIn(":SENS:CURR:DC:RANG 0.002", sent)
        self.assertIn(":SENS:CURR:DC:RANG:AUTO OFF", sent)

    def test_set_current_range_disables_autorange(self):
        meter, sent = _make_meter()
        meter.set_current_range(0.002)

        self.assertFalse(meter.autorange)
        self.assertIn(":SENS:CURR:DC:RANG 0.002", sent)
        self.assertIn(":SENS:CURR:DC:RANG:AUTO OFF", sent)

    def test_set_autorange_true_re_enables_it(self):
        meter, sent = _make_meter(autorange=False)
        meter.set_autorange(True)

        self.assertTrue(meter.autorange)
        self.assertIn(":SENS:CURR:DC:RANG:AUTO ON", sent)

    def test_configure_current_measurement_autorange_hook(self):
        meter, sent = _make_meter(autorange=False)
        meter.configure_current_measurement(autorange=True)

        self.assertTrue(meter.autorange)
        self.assertIn(":SENS:CURR:DC:RANG:AUTO ON", sent)


# ---------------------------------------------------------------------
# Voltage-shunt mode (added 2026-08-14): the reference cell's current is
# sensed as a voltage drop across a known external shunt resistor wired
# to the Input HI/LO terminals, converted back to an equivalent current
# before it leaves this driver -- see class docstring.
# ---------------------------------------------------------------------

class Keithley2000VoltageShuntModeTests(unittest.TestCase):
    def test_mode_defaults_to_current(self):
        """
        The constructor default stays "current" for any caller that
        doesn't specify a mode -- it's the GUI's Advanced Acquisition
        Settings panel that defaults to "voltage_shunt" instead, matching
        the lab's actual wiring (see advanced_acquisition_panel.py).
        """
        meter, _ = _make_meter()
        self.assertEqual(meter.mode, Keithley2000.MODE_CURRENT)

    def test_set_mode_voltage_shunt_configures_volt_dc(self):
        meter, sent = _make_meter(voltage_range=0.1)
        meter.set_mode("voltage_shunt")

        self.assertEqual(meter.mode, "voltage_shunt")
        self.assertIn(":SENS:FUNC 'VOLT:DC'", sent)
        self.assertIn(":SENS:VOLT:DC:RANG 0.1", sent)
        self.assertIn(":SENS:VOLT:DC:RANG:AUTO OFF", sent)
        self.assertIn(":SENS:VOLT:DC:NPLC 5.0", sent)
        # No CURR:DC commands should be sent while in voltage_shunt mode.
        self.assertFalse(any(cmd.startswith(":SENS:CURR:DC") for cmd in sent))

    def test_set_mode_back_to_current_configures_curr_dc(self):
        meter, sent = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)
        meter.set_mode("current")

        self.assertEqual(meter.mode, "current")
        self.assertIn(":SENS:FUNC 'CURR:DC'", sent)
        self.assertFalse(any(cmd.startswith(":SENS:VOLT:DC") for cmd in sent))

    def test_set_mode_rejects_unknown_mode(self):
        meter, _ = _make_meter()
        with self.assertRaises(ValueError):
            meter.set_mode("not_a_real_mode")

    def test_configure_current_measurement_mode_and_shunt_hook(self):
        meter, sent = _make_meter()
        meter.configure_current_measurement(mode="voltage_shunt", shunt_resistance_ohms=598)

        self.assertEqual(meter.mode, "voltage_shunt")
        self.assertEqual(meter.shunt_resistance_ohms, 598.0)
        self.assertIn(":SENS:FUNC 'VOLT:DC'", sent)

    def test_read_current_converts_voltage_by_shunt_resistance(self):
        meter, _ = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)
        # 598 ohm shunt at ~7 uA -> roughly 4.19 mV, matching the real
        # hardware wiring (confirmed positive on real hardware 2026-08-14).
        meter.query = lambda cmd: "0.00418964"

        result = meter.read_current()

        self.assertAlmostEqual(result, 0.00418964 / 598, places=12)

    def test_read_current_converts_negative_voltage_too(self):
        """Sign-agnostic: the conversion must not assume a particular polarity."""
        meter, _ = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)
        meter.query = lambda cmd: "-0.00418964"

        result = meter.read_current()

        self.assertAlmostEqual(result, -0.00418964 / 598, places=12)

    def test_read_current_in_current_mode_is_unconverted(self):
        meter, _ = _make_meter(mode="current")
        meter.query = lambda cmd: "-2.28e-06"

        self.assertEqual(meter.read_current(), -2.28e-06)

    def test_read_current_raises_if_shunt_resistance_not_set(self):
        meter, _ = _make_meter(mode="voltage_shunt")  # shunt_resistance_ohms left None
        meter.query = lambda cmd: "0.001"

        with self.assertRaises(RuntimeError):
            meter.read_current()

    def test_get_configuration_queries_volt_subsystem_in_voltage_shunt_mode(self):
        meter, _ = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)
        queried = []

        def fake_query(cmd):
            queried.append(cmd)
            if cmd == ":SENS:FUNC?":
                return "\"VOLT:DC\""
            if "RANG:AUTO" in cmd:
                return "0"
            if "RANG" in cmd:
                return "0.1"
            if "NPLC" in cmd:
                return "5.0"
            return "0"

        meter.query = fake_query
        cfg = meter.get_configuration()

        self.assertEqual(cfg["mode"], "voltage_shunt")
        self.assertEqual(cfg["shunt_resistance_ohms"], 598)
        self.assertTrue(any(cmd.startswith(":SENS:VOLT:DC:RANG") for cmd in queried))
        self.assertFalse(any(cmd.startswith(":SENS:CURR:DC:RANG") for cmd in queried))


class Keithley2000SettleTests(unittest.TestCase):
    """
    settle() (CurrentMeter role hook): confirmed on real hardware
    2026-08-19 that a dark-current reading taken immediately after
    configure_current_measurement() -- right after a prior scan just
    finished -- can be wildly wrong (~170nA off from a true ~2-3nA dark
    level), settling back to normal from the very next reading onward.
    mainwindow_qt.py calls settle() right after reconfiguring the
    reference meter and before trusting its dark-current recapture.
    """

    def test_settle_takes_one_throwaway_reading(self):
        meter, _ = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)
        queried = []
        meter.query = lambda cmd: (queried.append(cmd), "1.0e-6")[1]

        meter.settle()

        self.assertEqual(queried, [":READ?"])

    def test_settle_swallows_communication_errors(self):
        """
        Best-effort, like Keithley2400EQE.settle(): a failure here just
        means the settling read didn't happen -- the real reading right
        after this call surfaces any actual problem on its own.
        """
        meter, _ = _make_meter(mode="voltage_shunt", shunt_resistance_ohms=598)

        def raising_query(cmd):
            raise TimeoutError("simulated communication loss")

        meter.query = raising_query

        meter.settle()  # must not raise


if __name__ == "__main__":
    unittest.main()

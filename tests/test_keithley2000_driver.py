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


if __name__ == "__main__":
    unittest.main()

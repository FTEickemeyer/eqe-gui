"""
Tests for utils/validation.py's nm_lim_ok() -- the wavelength-range check
shared by the scan panel's Start button and the ScanPanel/
WavelengthSettingPanel spin boxes' allowed range (NM_MIN/NM_MAX).

A range outside the instrument's physical limits (350-1170 nm) must be
rejected outright (raise), not silently clamped to the nearest valid
value -- a prior version clamped-and-printed to the console, which
windowed launches with no console never see (see gui_qt.py's
_redirect_stdio_for_windowed_launch), so it was never actually a warning
the user saw.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.utils.validation import nm_lim_ok, NM_MIN, NM_MAX


class NmLimOkTests(unittest.TestCase):
    def test_within_range_passes_through_unchanged(self):
        self.assertEqual(nm_lim_ok((400, 900), calibration_measurement=False), (400, 900))

    def test_exact_limits_are_accepted(self):
        self.assertEqual(
            nm_lim_ok((NM_MIN, NM_MAX), calibration_measurement=False), (NM_MIN, NM_MAX)
        )

    def test_below_minimum_raises(self):
        with self.assertRaises(ValueError):
            nm_lim_ok((300, 900), calibration_measurement=False)

    def test_above_maximum_raises(self):
        with self.assertRaises(ValueError):
            nm_lim_ok((400, 1200), calibration_measurement=False)

    def test_upper_below_lower_raises(self):
        with self.assertRaises(ValueError):
            nm_lim_ok((900, 400), calibration_measurement=False)

    def test_calibration_measurement_always_returns_full_range(self):
        # Whatever the panel's Start/Stop fields say is ignored -- a
        # calibration measurement always covers the full range (see
        # calibration_panel.py's docstring).
        self.assertEqual(
            nm_lim_ok((500, 600), calibration_measurement=True), (NM_MIN, NM_MAX)
        )
        self.assertEqual(
            nm_lim_ok((0, 99999), calibration_measurement=True), (NM_MIN, NM_MAX)
        )


if __name__ == "__main__":
    unittest.main()

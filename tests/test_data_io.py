"""
Focused tests for io/data_io.py's save_data() filename convention.

No real hardware or real config/paths involved -- get_paths() is mocked
so a calibration-measurement save can't write into the real (machine-
specific) calibrations directory.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.io import data_io
from eqe.io.data_io import save_data


class SaveDataFilenamePrefixTests(unittest.TestCase):
    """
    A calibration measurement doesn't compute EQE, so its saved file
    should read "Calibration_..." rather than "EQE_..." (see
    docs/EQE_GUI_User_Manual.docx Section 9).
    """

    def test_calibration_measurement_uses_calibration_prefix(self):
        wavelengths = [400, 410, 420, 430, 440]
        df = pd.DataFrame(
            {
                "Wavelength (nm)": wavelengths,
                "Current ref (A)": [1e-6] * len(wavelengths),
                "Current cell (A)": [2e-6] * len(wavelengths),
            }
        ).set_index("Wavelength (nm)")
        df_ref = pd.Series(
            [50.0] * len(wavelengths),
            index=pd.Index(wavelengths, name="Wavelength (nm)"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with mock.patch.object(
                data_io, "get_paths", return_value={"calibrations_dir": tmp}
            ):
                fp = save_data(
                    df=df,
                    df_ref=df_ref,
                    sample_name="Si71889",
                    user_dir=tmp,
                    calibration_measurement=True,
                )

        self.assertTrue(fp.name.startswith("Calibration_"), fp.name)
        self.assertNotIn("EQE_", fp.name)

    def test_regular_measurement_keeps_eqe_prefix(self):
        wavelengths = [400, 410, 420]
        df = pd.DataFrame(
            {
                "Wavelength (nm)": wavelengths,
                "EQE (%)": [10.0, 20.0, 30.0],
                "Current ref (A)": [1e-6] * 3,
                "Current cell (A)": [2e-6] * 3,
            }
        ).set_index("Wavelength (nm)")

        with tempfile.TemporaryDirectory() as tmp:
            fp = save_data(
                df=df,
                df_ref=None,
                sample_name="my_sample",
                user_dir=tmp,
                calibration_measurement=False,
            )

        self.assertTrue(fp.name.startswith("EQE_"), fp.name)


class IncidentBeamCurrentSignTests(unittest.TestCase):
    """
    "incident beam current (A)" stands in for the light intensity itself
    and must always come out positive, regardless of which way the
    *external* Si71889 reference cell's leads happen to be wired for a
    given calibration run (see the two-reference-cells note in
    CLAUDE.md) -- a negative "Current cell (A)" must not silently negate
    the derived ratio, since that ratio later gets multiplied against
    the *internal* reference cell's current (always positive) during a
    normal EQE scan; a negative ratio there previously clamped every
    computed IPCE to 0% instead of raising an error (see git history).
    """

    def _save_and_read_incbeamcurr(self, cell_current):
        """Runs a calibration save with a fixed 'Current cell (A)' value
        (sign varied per test) and returns the saved incbeamcurr file."""
        wavelengths = [400, 410, 420]
        df = pd.DataFrame(
            {
                "Wavelength (nm)": wavelengths,
                "Current ref (A)": [1e-6] * len(wavelengths),
                "Current cell (A)": [cell_current] * len(wavelengths),
            }
        ).set_index("Wavelength (nm)")
        df_ref = pd.Series(
            [50.0] * len(wavelengths),
            index=pd.Index(wavelengths, name="Wavelength (nm)"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with mock.patch.object(
                data_io, "get_paths", return_value={"calibrations_dir": tmp}
            ), mock.patch.object(
                data_io,
                "load_config",
                return_value={"calibration": {"grating_change_nm": 850}},
            ):
                save_data(
                    df=df,
                    df_ref=df_ref,
                    sample_name="Si71889",
                    user_dir=tmp,
                    calibration_measurement=True,
                )

            incbeamcurr_files = list(tmp.glob("incbeamcurr_*.csv"))
            self.assertEqual(len(incbeamcurr_files), 1)
            return pd.read_csv(incbeamcurr_files[0], index_col=0)

    def test_negative_si71889_current_still_yields_positive_ratio(self):
        # Si71889 wired to read negative -- must not flip the sign of the
        # derived "incident beam current" ratio.
        saved = self._save_and_read_incbeamcurr(cell_current=-2e-6)

        ratio = saved["incident beam current (A)/intSiref current (A)"]
        self.assertTrue((ratio > 0).all(), ratio.tolist())
        # Raw "Current cell (A)" is kept as measured -- an honest record,
        # not silently flipped.
        self.assertTrue((saved["Current cell (A)"] < 0).all())

    def test_positive_si71889_current_also_yields_positive_ratio(self):
        # Same physical setup, opposite wiring polarity -- the derived
        # ratio must come out identical either way (sign-independent),
        # since the Si71889's wiring has flipped before and will again.
        saved = self._save_and_read_incbeamcurr(cell_current=2e-6)

        ratio = saved["incident beam current (A)/intSiref current (A)"]
        self.assertTrue((ratio > 0).all(), ratio.tolist())
        self.assertTrue((saved["Current cell (A)"] > 0).all())


if __name__ == "__main__":
    unittest.main()

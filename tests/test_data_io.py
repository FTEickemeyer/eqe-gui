"""
Focused tests for io/data_io.py's save_data() filename convention and
save_mmf_result()'s three-file MMF save.

No real hardware or real config/paths involved -- get_paths() is mocked
so a calibration-measurement save can't write into the real (machine-
specific) calibrations directory.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
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
    "incident beam current (A)" is derived straight from "Current cell
    (A)" -- deliberately *not* abs()'d (see the comment in save_data()).
    Correctness relies on wiring discipline (the external Si71889, the
    internal reference cell, and any DUT all wired to the same polarity
    convention), not a software sign correction: an earlier abs()-based
    "fix" was tried and reverted, since it silently masked genuine wiring
    mistakes and broke the same-cell-after-its-own-calibration
    self-consistency check (see git history). These tests just pin down
    that the derivation is a plain division with no sign games.
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

    def test_negative_si71889_current_yields_negative_ratio(self):
        # Si71889 wired to read negative (a wiring mistake, or a
        # not-yet-fixed polarity) -- the derived ratio must reflect that
        # honestly rather than have its sign corrected away, so a
        # subsequent unbiased scan of a correctly-wired (positive) DUT
        # visibly clamps to 0% instead of silently looking fine.
        saved = self._save_and_read_incbeamcurr(cell_current=-2e-6)

        ratio = saved["incident beam current (A)/intSiref current (A)"]
        self.assertTrue((ratio < 0).all(), ratio.tolist())
        self.assertTrue((saved["Current cell (A)"] < 0).all())

    def test_positive_si71889_current_yields_positive_ratio(self):
        # Correct wiring discipline: Si71889, the internal reference
        # cell, and a normal DUT all read positive -- the derived ratio
        # follows suit, so a normal unbiased scan comes out positive too.
        saved = self._save_and_read_incbeamcurr(cell_current=2e-6)

        ratio = saved["incident beam current (A)/intSiref current (A)"]
        self.assertTrue((ratio > 0).all(), ratio.tolist())
        self.assertTrue((saved["Current cell (A)"] > 0).all())


class SaveMmfResultTests(unittest.TestCase):
    """
    save_mmf_result() (see analysis/mmf.py for MMFResult and how it's
    computed) writes three files sharing one timestamped base name.
    """

    def _make_result(self):
        from eqe.analysis.mmf import MMFResult

        wavelengths = np.array([400.0, 410.0, 420.0])
        return MMFResult(
            mmf=0.987,
            jsc_dut_sim=10.5,
            jsc_dut_am15=9.5,
            jsc_ref_sim=10.0,
            jsc_ref_am15=9.0,
            left_nm=400.0,
            right_nm=420.0,
            delta_nm=10.0,
            wavelengths_nm=wavelengths,
            dut_eqe_pct=np.array([20.0, 21.0, 22.0]),
            ref_eqe_pct=np.array([25.0, 26.0, 27.0]),
            lamp_pf_normalized=np.array([0.5, 1.0, 0.6]),
            am15_pf_normalized=np.array([0.4, 0.9, 0.5]),
            # A comma in the lamp filename (a real-world case, see
            # PF_lamp_spectra/'s "231128 OrielIV, Gemini180.csv") must
            # come through the CSV-quoted summary row intact.
            dut_file=Path("EQE_mycell_date2026-01-01_time12-00-00.csv"),
            ref_file=Path("EQE_Si1812_date2025-10-23_time12-01-11.csv"),
            lamp_file=Path("231128 OrielIV, Gemini180.csv"),
        )

    def test_writes_summary_and_data_csv_without_figure(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            paths = data_io.save_mmf_result(result, user_dir=tmp, cell_name="mycell")

            self.assertIn("summary", paths)
            self.assertIn("data", paths)
            self.assertNotIn("figure", paths)

            self.assertTrue(paths["summary"].name.startswith("MMF_mycell_date"))
            self.assertTrue(paths["data"].name.endswith("_data.csv"))

            summary_df = pd.read_csv(paths["summary"])
            summary = dict(zip(summary_df["Quantity"], summary_df["Value"]))
            self.assertEqual(summary["Lamp spectrum file"], "231128 OrielIV, Gemini180.csv")
            self.assertEqual(summary["Reference cell EQE file"], "EQE_Si1812_date2025-10-23_time12-01-11.csv")
            self.assertAlmostEqual(float(summary["MMF"]), 0.987)
            self.assertAlmostEqual(float(summary["Jsc DUT @ AM1.5 (mA/cm2)"]), 9.5)

            data_df = pd.read_csv(paths["data"])
            self.assertEqual(list(data_df["Wavelength (nm)"]), [400.0, 410.0, 420.0])
            self.assertEqual(list(data_df["EQE DUT (%)"]), [20.0, 21.0, 22.0])

    def test_writes_figure_when_given(self):
        from matplotlib.figure import Figure

        result = self._make_result()
        fig = Figure()
        fig.add_subplot(111).plot([1, 2], [3, 4])

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            paths = data_io.save_mmf_result(
                result, user_dir=tmp, cell_name="mycell", fig=fig
            )
            self.assertIn("figure", paths)
            self.assertTrue(paths["figure"].exists())
            self.assertTrue(paths["figure"].name.endswith(".png"))


if __name__ == "__main__":
    unittest.main()

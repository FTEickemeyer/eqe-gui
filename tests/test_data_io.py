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


if __name__ == "__main__":
    unittest.main()

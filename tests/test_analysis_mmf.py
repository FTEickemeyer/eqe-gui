"""
Tests for analysis/mmf.py -- the Mismatch Factor (MMF) calculation.

No real config/paths or GUI involved. compute_mmf() is cross-checked
against fte_analysis_libraries.Spectrum.EQESpectrum.mmf() itself (the
reference implementation compute_mmf()'s formula mirrors -- see its
module docstring) as an independent correctness check.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.analysis import mmf


def _write_csv(path: Path, header: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")


class ListAndDefaultFileTests(unittest.TestCase):
    def test_list_csv_files_returns_sorted_csvs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "b.csv").write_text("x", encoding="utf-8")
            (tmp / "a.csv").write_text("x", encoding="utf-8")
            (tmp / "notes.txt").write_text("x", encoding="utf-8")

            files = mmf.list_csv_files(tmp)
            self.assertEqual([fp.name for fp in files], ["a.csv", "b.csv"])

    def test_list_csv_files_missing_dir_returns_empty(self):
        self.assertEqual(mmf.list_csv_files(Path("no/such/dir")), [])

    def test_default_lamp_spectrum_file_matches_case_insensitively(self):
        files = [Path("231128 OrielIV, Gemini180.csv"), Path("other.csv")]
        self.assertEqual(
            mmf.default_lamp_spectrum_file(files), files[0]
        )
        files_lower = [Path("orieliv_measurement.csv"), Path("other.csv")]
        self.assertEqual(
            mmf.default_lamp_spectrum_file(files_lower), files_lower[0]
        )

    def test_default_lamp_spectrum_file_none_when_no_match(self):
        files = [Path("a.csv"), Path("b.csv")]
        self.assertIsNone(mmf.default_lamp_spectrum_file(files))
        self.assertIsNone(mmf.default_lamp_spectrum_file([]))

    def test_default_ref_cell_file_picks_most_recently_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            older = tmp / "older.csv"
            newer = tmp / "newer.csv"
            older.write_text("x", encoding="utf-8")
            newer.write_text("x", encoding="utf-8")

            now = __import__("time").time()
            os.utime(older, (now - 100, now - 100))
            os.utime(newer, (now, now))

            self.assertEqual(mmf.default_ref_cell_file([older, newer]), newer)

    def test_default_ref_cell_file_none_when_empty(self):
        self.assertIsNone(mmf.default_ref_cell_file([]))


class ExtractSampleNameTests(unittest.TestCase):
    def test_reads_sample_name_from_header_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "EQE_whatever_date2026-01-01_time12-00-00.csv"
            fp.write_text(
                "# EQE measurement\n"
                "#\n"
                "# Sample / Metadata:\n"
                "#   Sample name: MyRealSample\n"
                "#\n"
                "Wavelength (nm),EQE (%)\n"
                "400,10\n",
                encoding="utf-8",
            )
            self.assertEqual(mmf.extract_sample_name(fp), "MyRealSample")

    def test_falls_back_to_filename_convention(self):
        fp = Path("EQE_Si1812_date2025-10-23_time12-01-11.csv")
        self.assertEqual(mmf.extract_sample_name(fp), "Si1812")

    def test_falls_back_to_stem_when_no_convention_matches(self):
        fp = Path("some_random_file.csv")
        self.assertEqual(mmf.extract_sample_name(fp), "some_random_file")


class LoadSpectrumTests(unittest.TestCase):
    def test_load_eqe_spectrum_skips_comment_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "eqe.csv"
            _write_csv(
                fp,
                "# some metadata\n#\nWavelength (nm),EQE (%),Integrated current (mA/cm2)",
                [[400, 10.0, 0.0], [410, 12.0, 0.1]],
            )
            spectrum = mmf.load_eqe_spectrum(fp)
            self.assertEqual(list(spectrum.x), [400.0, 410.0])
            self.assertEqual(list(spectrum.y), [10.0, 12.0])
            self.assertEqual(spectrum.uy, "%")

    def test_load_eqe_spectrum_without_comment_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "eqe.csv"
            _write_csv(fp, "Wavelength (nm),EQE (%)", [[400, 10.0], [410, 12.0]])
            spectrum = mmf.load_eqe_spectrum(fp)
            self.assertEqual(list(spectrum.x), [400.0, 410.0])

    def test_load_eqe_spectrum_sorts_descending_scan_ascending(self):
        # A Descending-direction scan saves rows in decreasing-wavelength
        # order (see measurement_engine.py's perform_measurement()) --
        # equidist()'s interp1d silently misbehaves on unsorted x, so
        # loading must always sort ascending regardless of file order.
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "eqe_descending.csv"
            _write_csv(
                fp,
                "Wavelength (nm),EQE (%)",
                [[420, 14.0], [410, 12.0], [400, 10.0]],
            )
            spectrum = mmf.load_eqe_spectrum(fp)
            self.assertEqual(list(spectrum.x), [400.0, 410.0, 420.0])
            self.assertEqual(list(spectrum.y), [10.0, 12.0, 14.0])

    def test_load_lamp_spectrum(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "lamp.csv"
            _write_csv(
                fp,
                "Wavelength (nm),Spectral photon flux (1/[s m2 nm])",
                [[400, 1e17], [410, 1.1e17]],
            )
            spectrum = mmf.load_lamp_spectrum(fp)
            self.assertEqual(list(spectrum.x), [400.0, 410.0])
            self.assertAlmostEqual(spectrum.y[0], 1e17)
            self.assertEqual(spectrum.uy, "1/[s m2 nm]")


class ComputeMmfTests(unittest.TestCase):
    def _make_files(self, tmp: Path):
        dut_fp = tmp / "dut.csv"
        ref_fp = tmp / "ref.csv"
        lamp_fp = tmp / "lamp.csv"

        wavelengths = list(range(400, 701, 10))
        _write_csv(
            dut_fp,
            "# EQE measurement\n#\nWavelength (nm),EQE (%)",
            [[w, 20.0] for w in wavelengths],
        )
        _write_csv(
            ref_fp,
            "Wavelength (nm),EQE (%)",
            [[w, 25.0] for w in wavelengths],
        )
        lamp_wavelengths = list(range(350, 751, 10))
        _write_csv(
            lamp_fp,
            "Wavelength (nm),Spectral photon flux (1/[s m2 nm])",
            [[w, 1e17] for w in lamp_wavelengths],
        )
        return dut_fp, ref_fp, lamp_fp

    def test_compute_mmf_matches_library_reference_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dut_fp, ref_fp, lamp_fp = self._make_files(tmp)

            result = mmf.compute_mmf(dut_fp, ref_fp, lamp_fp)

            # Independent cross-check against the library's own mmf()
            # method (see analysis/mmf.py's module docstring).
            dut_eqe = mmf.load_eqe_spectrum(dut_fp)
            ref_eqe = mmf.load_eqe_spectrum(ref_fp)
            lamp_pf = mmf.load_lamp_spectrum(lamp_fp)
            expected_mmf = dut_eqe.mmf(
                ref_EQE=ref_eqe,
                sim_PF=lamp_pf,
                ref_PF="AM15GT",
                left=result.left_nm,
                right=result.right_nm,
                delta=result.delta_nm,
            )
            self.assertAlmostEqual(result.mmf, expected_mmf, places=9)

    def test_integration_range_is_the_overlap_of_all_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dut_fp, ref_fp, lamp_fp = self._make_files(tmp)
            result = mmf.compute_mmf(dut_fp, ref_fp, lamp_fp)
            # DUT/ref cover 400-700 nm, narrower than the lamp's 350-750 nm.
            self.assertEqual(result.left_nm, 400.0)
            self.assertEqual(result.right_nm, 700.0)

    def test_result_contains_matching_plot_arrays(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dut_fp, ref_fp, lamp_fp = self._make_files(tmp)
            result = mmf.compute_mmf(dut_fp, ref_fp, lamp_fp)

            n = len(result.wavelengths_nm)
            self.assertEqual(len(result.dut_eqe_pct), n)
            self.assertEqual(len(result.ref_eqe_pct), n)
            self.assertEqual(len(result.lamp_pf_normalized), n)
            self.assertEqual(len(result.am15_pf_normalized), n)
            # normalize() scales to a max of 1 within the plotted range.
            self.assertAlmostEqual(max(result.lamp_pf_normalized), 1.0, places=6)
            self.assertAlmostEqual(max(result.am15_pf_normalized), 1.0, places=6)

    def test_raises_when_wavelength_ranges_dont_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dut_fp = tmp / "dut.csv"
            ref_fp = tmp / "ref.csv"
            lamp_fp = tmp / "lamp.csv"

            _write_csv(dut_fp, "Wavelength (nm),EQE (%)", [[400, 20.0], [410, 20.0]])
            _write_csv(ref_fp, "Wavelength (nm),EQE (%)", [[400, 25.0], [410, 25.0]])
            # Lamp spectrum entirely below the EQE files' range -- no overlap.
            _write_csv(
                lamp_fp,
                "Wavelength (nm),Spectral photon flux (1/[s m2 nm])",
                [[200, 1e17], [210, 1e17]],
            )

            with self.assertRaises(ValueError):
                mmf.compute_mmf(dut_fp, ref_fp, lamp_fp)


if __name__ == "__main__":
    unittest.main()

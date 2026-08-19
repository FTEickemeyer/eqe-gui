"""
Mismatch Factor (MMF) calculation.

Standard spectral mismatch correction (ASTM E973-style): a solar simulator's
spectrum never exactly matches AM1.5G, so a device's short-circuit current
measured under it is biased relative to what it would be under true AM1.5G.
The mismatch factor corrects for this using the EQE spectra of the device
under test (DUT) and a reference cell, plus the simulator's own measured
spectrum:

    MMF = [Jsc_ref(AM1.5) * Jsc_DUT(sim)] / [Jsc_ref(sim) * Jsc_DUT(AM1.5)]

where Jsc_X(Y) is the short-circuit current density of spectrum X's EQE
integrated against light spectrum Y. See EQESpectrum.mmf() in
fte_analysis_libraries.Spectrum for the reference implementation this
mirrors (calc_jsc() is called directly here, not mmf(), only so all four
Jsc components are available on MMFResult without computing them twice --
only Jsc_DUT(AM1.5) is actually surfaced to the user, as "Integrated
current", but the other three stay around on the result object).

Three kinds of input files are involved, all plain two-column-or-more CSVs
(optionally with a "#"-prefixed metadata header, like this app's own saved
EQE files -- see io/data_io.py's build_measurement_header()):

- DUT EQE file: any of this app's own saved "EQE_*.csv" scan files
  (Wavelength (nm), EQE (%), ...).
- Reference-cell EQE file: same format, for a reference cell with known
  EQE -- kept in paths.mmf_data_dir's EQE_ref_cells/ subfolder.
- Lamp spectrum file: the solar simulator's measured spectral photon flux
  (Wavelength (nm), Spectral photon flux (1/[s m2 nm])) -- kept in
  paths.mmf_data_dir's PF_lamp_spectra/ subfolder.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import fte_analysis_libraries.Spectrum as spc

from eqe.io.paths import get_paths

REF_CELLS_SUBDIR = "EQE_ref_cells"
LAMP_SPECTRA_SUBDIR = "PF_lamp_spectra"

# Wavelength the lamp spectrum and AM1.5GT curves are normalized to (each
# set to 1 at this point) for the plot's right axis -- this lab's
# convention, chosen so the two spectral shapes are easy to compare by
# eye around the middle of a typical scan range. Purely a display choice;
# does not affect the MMF/Jsc calculation itself, which integrates the
# un-normalized spectra.
NORMALIZE_AT_NM = 680.0

# Case-insensitive filename substring used to pick a default lamp spectrum
# file out of PF_lamp_spectra/ (see default_lamp_spectrum_file()).
_DEFAULT_LAMP_MARKER = "orieliv"


def get_mmf_dirs() -> dict:
    """
    Resolve (and create if missing) paths.mmf_data_dir and its two fixed
    subfolders: EQE_ref_cells/ and PF_lamp_spectra/.
    """
    mmf_data_dir = Path(get_paths()["mmf_data_dir"])
    ref_cells_dir = mmf_data_dir / REF_CELLS_SUBDIR
    lamp_spectra_dir = mmf_data_dir / LAMP_SPECTRA_SUBDIR
    ref_cells_dir.mkdir(parents=True, exist_ok=True)
    lamp_spectra_dir.mkdir(parents=True, exist_ok=True)

    return {
        "mmf_data_dir": mmf_data_dir,
        "ref_cells_dir": ref_cells_dir,
        "lamp_spectra_dir": lamp_spectra_dir,
    }


def list_csv_files(directory) -> list:
    """Sorted (by name) list of *.csv files directly inside `directory`."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.csv"))


def default_lamp_spectrum_file(files):
    """
    Default pick for the lamp spectrum file: the one with "OrielIV"
    (case-insensitive) in its filename, matching this lab's naming
    convention for its solar-simulator spectrum measurements. None if no
    file matches (or the list is empty) -- the GUI leaves the field blank
    in that case rather than guessing.
    """
    for fp in files:
        if _DEFAULT_LAMP_MARKER in fp.name.lower():
            return fp
    return None


def default_ref_cell_file(files):
    """
    Default pick for the reference-cell EQE file: the most recently
    modified one. None if the list is empty.
    """
    if not files:
        return None
    return max(files, key=lambda fp: fp.stat().st_mtime)


def _find_column(df: pd.DataFrame, keyword: str) -> str:
    """
    Case-insensitive substring match against `df`'s column names -- e.g.
    keyword="EQE" matches a "EQE (%)" column regardless of the exact unit
    text. Raises a clear error (rather than a bare KeyError) if no column
    matches, since that means the file isn't in the expected format.
    """
    matches = [c for c in df.columns if keyword.lower() in str(c).lower()]
    if not matches:
        raise ValueError(
            f"No column containing {keyword!r} found. Columns present: "
            f"{list(df.columns)}"
        )
    return matches[0]


def _read_csv_skip_comments(path: Path) -> pd.DataFrame:
    """
    Read a data CSV that may have a "#"-prefixed metadata header before
    the real column-header row (this app's own saved EQE files do -- see
    io/data_io.py's build_measurement_header()); a plain CSV with no such
    header (e.g. a hand-curated reference-cell file) reads the same way.
    """
    return pd.read_csv(path, comment="#")


def load_eqe_spectrum(path, name: str | None = None):
    """
    Load an EQE-vs-wavelength CSV (a DUT scan or a reference-cell file)
    into an fte_analysis_libraries EQESpectrum.
    """
    path = Path(path)
    df = _read_csv_skip_comments(path)
    wavelength_col = _find_column(df, "Wavelength")
    # A Descending-direction scan saves rows in decreasing-wavelength
    # order (see measurement_engine.py's perform_measurement()) --
    # equidist()'s interp1d silently gives wrong results on unsorted x, so
    # always sort ascending regardless of how the source file was ordered.
    df = df.sort_values(by=wavelength_col)
    x = df[wavelength_col].to_numpy(dtype=float)
    y = df[_find_column(df, "EQE")].to_numpy(dtype=float)

    return spc.EQESpectrum(
        x,
        y,
        quants={"x": "Wavelength", "y": "EQE"},
        units={"x": "nm", "y": "%"},
        name=name or path.name,
        check_data=False,
    )


def load_lamp_spectrum(path, name: str | None = None):
    """
    Load a lamp spectral-photon-flux CSV into an fte_analysis_libraries
    DiffSpectrum, in the same units (1/[s m2 nm]) as the AM1.5GT reference
    spectrum this gets compared against (see compute_mmf()).
    """
    path = Path(path)
    df = _read_csv_skip_comments(path)
    wavelength_col = _find_column(df, "Wavelength")
    df = df.sort_values(by=wavelength_col)
    x = df[wavelength_col].to_numpy(dtype=float)
    y = df[_find_column(df, "photon flux")].to_numpy(dtype=float)

    return spc.DiffSpectrum(
        x,
        y,
        quants={"x": "Wavelength", "y": "Spectral photon flux"},
        units={"x": "nm", "y": "1/[s m2 nm]"},
        name=name or path.name,
        check_data=False,
    )


def extract_sample_name(path) -> str:
    """
    Best-effort cell/sample name for a saved EQE file, for naming an MMF
    result after the DUT it was computed for. Tries, in order:

    1. The "#   Sample name: ..." line in the file's metadata header (see
       io/data_io.py's build_measurement_header()) -- most reliable, since
       it's the actual value that was in the Metadata panel at save time.
    2. The filename convention this app saves under
       ("EQE_<sample>_date...csv" / "Calibration_<sample>_date...csv").
    3. The bare filename stem, as a last resort.
    """
    path = Path(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith("#"):
                    break
                if "Sample name:" in line:
                    name = line.split("Sample name:", 1)[1].strip()
                    if name:
                        return name
                    break
    except OSError:
        pass

    stem = path.stem
    for prefix in ("EQE_", "Calibration_"):
        if stem.startswith(prefix) and "_date" in stem:
            sample = stem[len(prefix):].split("_date")[0]
            if sample:
                return sample

    return stem or "sample"


@dataclass
class MMFResult:
    """
    Everything computed by compute_mmf(), needed both to display and to
    save the result -- see mainwindow_qt.py's MMF dialog and
    io/data_io.py's save_mmf_result().
    """

    mmf: float
    jsc_dut_sim: float
    jsc_dut_am15: float
    jsc_ref_sim: float
    jsc_ref_am15: float

    left_nm: float
    right_nm: float
    delta_nm: float

    # Common wavelength grid (the overlap of all three input files' own
    # ranges) the four curves below are resampled onto -- this is also
    # exactly the integration window the four Jsc values above use, so
    # what's plotted and what's calculated always agree.
    wavelengths_nm: np.ndarray
    dut_eqe_pct: np.ndarray
    ref_eqe_pct: np.ndarray
    lamp_pf_normalized: np.ndarray
    am15_pf_normalized: np.ndarray

    dut_file: Path
    ref_file: Path
    lamp_file: Path


def compute_mmf(
    dut_path,
    ref_path,
    lamp_path,
    delta_nm: float = 0.5,
    normalize_at_nm: float = NORMALIZE_AT_NM,
) -> MMFResult:
    """
    Compute the mismatch factor (and its four Jsc components) for a DUT
    EQE file against a reference-cell EQE file and a measured lamp
    spectrum file, plus the built-in AM1.5GT reference spectrum.

    Integrates over the overlap of the three files' own wavelength ranges
    only (never extrapolates beyond what any of them actually measured --
    interpolating past a curve's own range would silently zero-fill it,
    see fte_analysis_libraries.Spectrum's int_arr()). Raises ValueError if
    they don't overlap at all.
    """
    dut_path, ref_path, lamp_path = Path(dut_path), Path(ref_path), Path(lamp_path)

    dut_eqe = load_eqe_spectrum(dut_path)
    ref_eqe = load_eqe_spectrum(ref_path)
    lamp_pf = load_lamp_spectrum(lamp_path)

    left = max(float(np.min(dut_eqe.x)), float(np.min(ref_eqe.x)), float(np.min(lamp_pf.x)))
    right = min(float(np.max(dut_eqe.x)), float(np.max(ref_eqe.x)), float(np.max(lamp_pf.x)))
    if right <= left:
        raise ValueError(
            "The DUT EQE, reference-cell EQE, and lamp spectrum files don't "
            f"share any overlapping wavelength range (DUT: {dut_eqe.x.min():.0f}-"
            f"{dut_eqe.x.max():.0f} nm, reference: {ref_eqe.x.min():.0f}-"
            f"{ref_eqe.x.max():.0f} nm, lamp: {lamp_pf.x.min():.0f}-"
            f"{lamp_pf.x.max():.0f} nm)."
        )

    jsc_dut_sim = float(dut_eqe.calc_jsc(left=left, right=right, delta=delta_nm, sp=lamp_pf))
    jsc_dut_am15 = float(dut_eqe.calc_jsc(left=left, right=right, delta=delta_nm, sp="AM15GT"))
    jsc_ref_sim = float(ref_eqe.calc_jsc(left=left, right=right, delta=delta_nm, sp=lamp_pf))
    jsc_ref_am15 = float(ref_eqe.calc_jsc(left=left, right=right, delta=delta_nm, sp="AM15GT"))

    mmf_value = (jsc_ref_am15 * jsc_dut_sim) / (jsc_ref_sim * jsc_dut_am15)

    dut_plot = dut_eqe.copy()
    dut_plot.equidist(left=left, right=right, delta=delta_nm)

    ref_plot = ref_eqe.copy()
    ref_plot.equidist(left=left, right=right, delta=delta_nm)

    lamp_plot = lamp_pf.copy()
    lamp_plot.equidist(left=left, right=right, delta=delta_nm)
    # normalize(x_lim=(n, n)) sets the curve's value *at* n (the nearest
    # available grid point, clamped to [left, right] if n falls outside
    # it) to 1, rather than the default peak-within-range normalization.
    lamp_plot.normalize(x_lim=(normalize_at_nm, normalize_at_nm))

    am15_plot = spc.DiffSpectrum.am15_nm(left=left, right=right, delta=delta_nm)
    am15_plot.normalize(x_lim=(normalize_at_nm, normalize_at_nm))

    return MMFResult(
        mmf=float(mmf_value),
        jsc_dut_sim=jsc_dut_sim,
        jsc_dut_am15=jsc_dut_am15,
        jsc_ref_sim=jsc_ref_sim,
        jsc_ref_am15=jsc_ref_am15,
        left_nm=left,
        right_nm=right,
        delta_nm=delta_nm,
        wavelengths_nm=dut_plot.x,
        dut_eqe_pct=dut_plot.y,
        ref_eqe_pct=ref_plot.y,
        lamp_pf_normalized=lamp_plot.y,
        am15_pf_normalized=am15_plot.y,
        dut_file=dut_path,
        ref_file=ref_path,
        lamp_file=lamp_path,
    )

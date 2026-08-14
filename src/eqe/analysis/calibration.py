import datetime
import re
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from eqe.config.load_config import load_config
from eqe.io.paths import get_paths
from eqe.utils.dataframe import df_interpolate


def get_package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_reference_cell_path(filename: str) -> Path:
    return get_package_root() / "resources" / "calibration_defaults" / filename


# Matches the "_date<YYYY-MM-DD>_time<HH-MM-SS>.csv" suffix save_data()
# writes onto every incbeamcurr_*.csv it produces (see io/data_io.py).
_INCBEAMCURR_TIMESTAMP_RE = re.compile(
    r"_date(?P<date>\d{4}-\d{2}-\d{2})_time(?P<time>\d{2}-\d{2}-\d{2})\.csv$"
)


def find_latest_incident_beam_file(calibrations_dir):
    """
    Return the most recently produced incbeamcurr_*.csv in
    `calibrations_dir`, or None if there isn't one.

    "Most recent" is judged by the date/time encoded in the filename (the
    moment the calibration measurement finished, see save_data()), not
    file modification time, so copying/restoring a file doesn't change
    which one is picked. Falls back to file modification time for any
    file that doesn't match the expected naming pattern.
    """
    calibrations_dir = Path(calibrations_dir)
    candidates = list(calibrations_dir.glob("incbeamcurr_*.csv"))
    if not candidates:
        return None

    def sort_key(fp):
        m = _INCBEAMCURR_TIMESTAMP_RE.search(fp.name)
        if m:
            try:
                return datetime.datetime.strptime(
                    f"{m.group('date')} {m.group('time').replace('-', ':')}",
                    "%Y-%m-%d %H:%M:%S",
                )
            except ValueError:
                pass
        return datetime.datetime.fromtimestamp(fp.stat().st_mtime)

    return max(candidates, key=sort_key)


def open_calibration(nm_lim, calibration_measurement, debug=False, on_status=None):
    """
    Load the two calibration inputs. Not to be confused with each other:

    - `reference_cell_file` / df_ref: the *external* Si71889 reference
      cell's own certified IPCE curve, used only when producing a new
      calibration (calibration_measurement=True).
    - `active_incident_beam_file` / df_incbeamcurr: the incident-beam
      calibration, giving the ratio against the *internal* reference
      cell's current (Siref/intSiref, always read via reference_meter)
      used for every regular EQE scan.

    If `calibration.active_incident_beam_file` isn't set in config, the
    most recently produced incbeamcurr_*.csv in calibrations_dir is used
    automatically (see find_latest_incident_beam_file()) -- set it
    explicitly only to pin a specific file instead of always using the
    latest measurement.

    Returns (df_incbeamcurr, df_ref, fp_incbeamcurr): fp_incbeamcurr is
    the resolved Path of the incident-beam calibration file actually
    used (whichever of the two ways above picked it), or None for a
    calibration measurement (calibration_measurement=True), which
    doesn't use one. Callers that save a measurement should record its
    name in the saved file's metadata so it's traceable afterward.
    """
    config = load_config()
    paths = get_paths()

    calibration_cfg = config["calibration"]

    reference_cell_file = calibration_cfg["reference_cell_file"]
    active_incident_beam_file = calibration_cfg.get("active_incident_beam_file")

    fp_ref_cell = get_reference_cell_path(reference_cell_file)
    if not fp_ref_cell.exists():
        raise FileNotFoundError(
            f"Si71889 reference cell file not found: {fp_ref_cell}"
        )

    df_ref = pd.read_csv(fp_ref_cell).set_index("Wavelength (nm)").squeeze()

    if debug:
        df_ref.plot()
        plt.title("Si71889 reference cell")
        plt.ylabel("IPCE (%)")
        plt.show()

    if calibration_measurement:
        # No incident-beam calibration is used to compute EQE for a
        # calibration measurement itself (it produces one instead).
        return None, df_ref, None

    if active_incident_beam_file:
        # Explicit pin, e.g. for reverting to or testing a specific
        # calibration -- takes priority over auto-selecting the latest.
        fp_incbeamcurr = paths["calibrations_dir"] / active_incident_beam_file
        if not fp_incbeamcurr.exists():
            raise FileNotFoundError(
                f"Configured incident-beam calibration file not found: {fp_incbeamcurr}"
            )
    else:
        fp_incbeamcurr = find_latest_incident_beam_file(paths["calibrations_dir"])
        if fp_incbeamcurr is None:
            raise FileNotFoundError(
                "No incident-beam calibration files found in "
                f"{paths['calibrations_dir']}. Run a calibration measurement "
                "first (see README's 'Running a calibration measurement'), "
                "or set calibration.active_incident_beam_file to pin a "
                "specific file."
            )

    if on_status is not None:
        on_status(f"Using incident-beam calibration: {fp_incbeamcurr.name}")
    elif debug:
        print(f"Using incident-beam calibration: {fp_incbeamcurr}")

    df_incbeamcurr = pd.read_csv(fp_incbeamcurr).set_index("Wavelength (nm)")

    nm_arr = np.arange(nm_lim[0], nm_lim[1] + 1, 1)
    df_incbeamcurr = df_interpolate(df_incbeamcurr, nm_arr)

    if debug:
        df_incbeamcurr.plot()
        plt.show()
        df_incbeamcurr["incident beam current (A)/intSiref current (A)"].plot()
        plt.title("df_incbeamcurr")
        plt.show()

    return df_incbeamcurr, df_ref, fp_incbeamcurr
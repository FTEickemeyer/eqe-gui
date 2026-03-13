import os
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from eqe.config.load_config import load_config
from eqe.io.paths import get_paths
from eqe.io.resources import get_reference_cell_path

GRATING_CHANGE_NM = 850


def df_interpolate(df, new_index_arr):
    """
    Interpolate a dataframe to a new index array.
    """
    lower_limit = min(df.index.values)
    upper_limit = max(df.index.values)

    new_index_arr = new_index_arr[new_index_arr >= lower_limit]
    new_index_arr = new_index_arr[new_index_arr <= upper_limit]

    r = pd.Index(new_index_arr)
    t = df.index

    df_new = df.reindex(t.union(r)).interpolate(method="quadratic", axis="index").loc[r]
    df_new.index.name = df.index.name
    df_new.index = df_new.index.astype(type(new_index_arr[0]))
    return df_new


def find_latest_incident_beam_calibration(calibrations_dir, pattern, grating_change_nm):
    matches = sorted(
        calibrations_dir.glob(f"*{pattern}*{grating_change_nm}*.csv"),
        key=lambda p: p.stat().st_mtime
    )
    if not matches:
        raise FileNotFoundError(
            f"No incident beam calibration found in {calibrations_dir} "
            f"matching pattern '{pattern}' and '{grating_change_nm}'."
        )
    return matches[-1]


def open_calibration(nm_lim, calibration_measurement, debug=False):
    config = load_config()
    paths = get_paths()

    ref_filename = config["calibration"]["reference_cell_file"]
    incident_beam_pattern = config["calibration"]["incident_beam_pattern"]
    grating_change_nm = config["calibration"]["grating_change_nm"]

    fp_ref_cell = get_reference_cell_path(ref_filename)
    df_ref = pd.read_csv(fp_ref_cell).set_index("Wavelength (nm)").squeeze()

    if debug:
        df_ref.plot()
        plt.title("Reference cell")
        plt.ylabel("IPCE (%)")
        plt.show()

    if calibration_measurement:
        return None, df_ref

    fp_incbeamcurr = find_latest_incident_beam_calibration(
        calibrations_dir=paths["calibrations_dir"],
        pattern=incident_beam_pattern,
        grating_change_nm=grating_change_nm,
    )

    if debug:
        print(f"Using incident beam calibration: {fp_incbeamcurr}")

    df_incbeamcurr = pd.read_csv(fp_incbeamcurr).set_index("Wavelength (nm)")

    nm_arr = np.arange(nm_lim[0], nm_lim[1] + 1, 1)
    df_incbeamcurr = df_interpolate(df_incbeamcurr, nm_arr)

    if debug:
        df_incbeamcurr.plot()
        plt.show()
        df_incbeamcurr["incident beam current (A)/intSiref current (A)"].plot()
        plt.title("df_incbeamcurr")
        plt.show()

    return df_incbeamcurr, df_ref
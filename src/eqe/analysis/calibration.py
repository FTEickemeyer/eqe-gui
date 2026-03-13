from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from eqe.config.load_config import load_config
from eqe.io.paths import get_paths


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


def get_package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_reference_cell_path(filename: str) -> Path:
    return get_package_root() / "resources" / "calibration_defaults" / filename


def open_calibration(nm_lim, calibration_measurement, debug=False):
    config = load_config()
    paths = get_paths()

    calibration_cfg = config["calibration"]

    reference_cell_file = calibration_cfg["reference_cell_file"]
    active_incident_beam_file = calibration_cfg.get("active_incident_beam_file")

    fp_ref_cell = get_reference_cell_path(reference_cell_file)
    if not fp_ref_cell.exists():
        raise FileNotFoundError(
            f"Reference cell file not found: {fp_ref_cell}"
        )

    df_ref = pd.read_csv(fp_ref_cell).set_index("Wavelength (nm)").squeeze()

    if debug:
        df_ref.plot()
        plt.title("Reference cell")
        plt.ylabel("IPCE (%)")
        plt.show()

    if calibration_measurement:
        return None, df_ref

    if not active_incident_beam_file:
        raise FileNotFoundError(
            "No active incident-beam calibration file is configured. "
            "Set calibration.active_incident_beam_file in config_local.yaml."
        )

    fp_incbeamcurr = paths["calibrations_dir"] / active_incident_beam_file
    if not fp_incbeamcurr.exists():
        raise FileNotFoundError(
            f"Configured incident-beam calibration file not found: {fp_incbeamcurr}"
        )

    df_incbeamcurr = pd.read_csv(fp_incbeamcurr).set_index("Wavelength (nm)")

    nm_arr = np.arange(nm_lim[0], nm_lim[1] + 1, 1)
    df_incbeamcurr = df_interpolate(df_incbeamcurr, nm_arr)

    if debug:
        print(f"Using incident-beam calibration: {fp_incbeamcurr}")
        df_incbeamcurr.plot()
        plt.show()
        df_incbeamcurr["incident beam current (A)/intSiref current (A)"].plot()
        plt.title("df_incbeamcurr")
        plt.show()

    return df_incbeamcurr, df_ref
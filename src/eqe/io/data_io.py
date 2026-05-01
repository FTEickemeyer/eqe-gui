import datetime
from pathlib import Path

import pandas as pd

from eqe.io.paths import get_paths
from eqe.config.load_config import load_config
from eqe.utils.dataframe import df_interpolate


def save_data(
    df,
    df_ref,
    sample_name,
    user_dir,
    calibration_measurement,
    save_raw_data=False,
    debug=False,
    fig=None,
):
    user_dir = Path(user_dir)

    dat_time = str(datetime.datetime.now())
    dat_time_file = dat_time.split(".")[0].replace(":", "-").replace(" ", "_time")

    fp_ipce = user_dir / f"EQE_{sample_name}_date{dat_time_file}.csv"

    if save_raw_data or calibration_measurement:
        df.to_csv(fp_ipce)
    else:
        df[["EQE (%)", "Integrated current (mA/cm2)"]].to_csv(fp_ipce)

    if fig is not None:
        fp_fig = user_dir / f"EQE_{sample_name}_date{dat_time_file}.png"
        fig.savefig(fp_fig, dpi=300, bbox_inches="tight")

    print(f"File saved: {fp_ipce}")

    if calibration_measurement:
        df_ref_interpol = df_interpolate(df_ref, df.index)
        df["IPCE Siref (%)"] = df_ref_interpol.values
        df["incident beam current (A)"] = df["Current cell-chB (A)"] / df["IPCE Siref (%)"]
        df["incident beam current (A)/intSiref current (A)"] = (
            df["incident beam current (A)"] / df["Current ref-chA (A)"]
        )

        calibration_dir = get_paths()["calibrations_dir"]
        config = load_config()
        grating_change_nm = config["calibration"]["grating_change_nm"]
        fp_incbeamcurr = (
            calibration_dir
            / f"incbeamcurr_{sample_name}_{grating_change_nm}nm-wavelength-change_date{dat_time_file}.csv"
        )

        df[
            [
                "Current ref-chA (A)",
                "Current cell-chB (A)",
                "incident beam current (A)/intSiref current (A)",
            ]
        ].to_csv(fp_incbeamcurr)

        if debug:
            df["incident beam current (A)/intSiref current (A)"].plot()

    return fp_ipce
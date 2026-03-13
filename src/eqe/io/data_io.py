import datetime
from pathlib import Path

import pandas as pd

from eqe.io.paths import get_paths


def df_interpolate(df, new_index_arr):
    """
    Generates an interpolated dataframe, where the index of df is replaced by new_index_arr.
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


def save_data(
    df,
    df_ref,
    sample_name,
    user_dir,
    calibration_measurement,
    save_raw_data=False,
    debug=False,
    fig=None,
    grating_change_nm=850,
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
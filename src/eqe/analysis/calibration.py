import os
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

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


def open_calibration(system_dir, nm_lim, calibration_measurement, debug=False):
    fp_ref_cell = os.path.join(system_dir, "71889_L_IPCE_NIST.csv")
    df_ref = pd.read_csv(fp_ref_cell).set_index("Wavelength (nm)").squeeze()

    if debug:
        df_ref.plot()
        plt.title("Reference cell")
        plt.ylabel("IPCE (%)")
        plt.show()

    if not calibration_measurement:
        fn_root = "incbeamcurr"
        filenames = os.listdir(system_dir)
        fn_incbeamcurr = [
            fn for fn in filenames
            if (fn_root in fn) and (f"{GRATING_CHANGE_NM}" in fn)
        ][-1]

        if debug:
            print(fn_incbeamcurr)

        fp_incbeamcurr = os.path.join(system_dir, fn_incbeamcurr)
        df_incbeamcurr = pd.read_csv(fp_incbeamcurr).set_index("Wavelength (nm)")

        nm_arr = np.arange(nm_lim[0], nm_lim[1] + 1, 1)
        df_incbeamcurr = df_interpolate(df_incbeamcurr, nm_arr)

        if debug:
            df_incbeamcurr.plot()
            plt.show()
            df_incbeamcurr["incident beam current (A)/intSiref current (A)"].plot()
            plt.title("df_incbeamcurr")
            plt.show()
    else:
        df_incbeamcurr = None

    return df_incbeamcurr, df_ref
import numpy as np
import pandas as pd


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

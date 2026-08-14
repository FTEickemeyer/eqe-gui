from dataclasses import dataclass
import pandas as pd


@dataclass
class AppState:
    df_ipce: pd.DataFrame | None = None
    df_ref: pd.Series | None = None

    user: str | None = None
    sample: str | None = None
    user_dir: str | None = None

    calibration_measurement: bool = False
    save_raw: bool = False
    last_saved_file: str | None = None
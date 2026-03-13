import os
import datetime
from pathlib import Path
from eqe.config.load_config import load_config


def create_user_directory(data_dir, user, debug=False):
    """
    Create and return the dated user directory for measurement data.

    Example:
        C:\\Users\\...\\Data\\user\\260310_IPCE
    """
    user_dir = os.path.join(data_dir, user)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    format_dt = "%Y-%m-%d %H:%M:%S.%f"
    datetime_object = datetime.datetime.strptime(str(datetime.datetime.now()), format_dt)
    date = datetime_object.strftime("%y%m%d") + "_IPCE"

    user_dir = os.path.join(data_dir, user, date)

    if debug:
        print(date)
        print(user_dir)

    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    return user_dir


def _expand_path(path_str: str) -> Path:
    path_str = os.path.expandvars(path_str)
    path_str = os.path.expanduser(path_str)
    return Path(path_str).resolve()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_paths() -> dict:
    config = load_config()
    path_cfg = config["paths"]

    measurements_dir = ensure_dir(_expand_path(path_cfg["measurements_dir"]))
    calibrations_dir = ensure_dir(_expand_path(path_cfg["calibrations_dir"]))
    logs_dir = ensure_dir(_expand_path(path_cfg["logs_dir"]))

    return {
        "measurements_dir": measurements_dir,
        "calibrations_dir": calibrations_dir,
        "logs_dir": logs_dir,
    }
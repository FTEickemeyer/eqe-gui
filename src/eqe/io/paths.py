import os
import datetime
from pathlib import Path
from eqe.config.load_config import load_config


def create_user_directory(measurements_dir, user, debug=False):
    """
    Create and return the dated user directory for measurement data.

    Example:
        C:\\Users\\...\\Documents\\EQE\\measurements\\user\\260313_IPCE
    """
    measurements_dir = Path(measurements_dir)

    user_root = measurements_dir / user
    user_root.mkdir(parents=True, exist_ok=True)

    date_folder = datetime.datetime.now().strftime("%y%m%d") + "_IPCE"
    user_dir = user_root / date_folder

    if debug:
        print(date_folder)
        print(user_dir)

    user_dir.mkdir(parents=True, exist_ok=True)
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
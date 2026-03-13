from pathlib import Path


def get_package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_calibration_defaults_dir() -> Path:
    return get_package_root() / "resources" / "calibration_defaults"


def get_reference_cell_path(filename: str) -> Path:
    return get_calibration_defaults_dir() / filename
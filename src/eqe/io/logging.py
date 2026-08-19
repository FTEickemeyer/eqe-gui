from datetime import datetime
from pathlib import Path

from eqe.config.load_config import load_config
from eqe.io.paths import get_paths


def get_log_file_path() -> Path:
    logs_dir = get_paths()["logs_dir"]
    timestamp = datetime.now().strftime("%Y-%m-%d")
    return logs_dir / f"eqe_{timestamp}.log"


def is_enabled() -> bool:
    """
    Whether the application log should be written to disk at all --
    config's logging.enabled (default True, see config_default.yaml).
    Checked by append_line_to_log() itself, so every caller (the GUI's
    Status/Log panel persistence, append_to_log()'s structured measurement
    entries) respects it automatically without needing to check it
    individually. Does not affect the separate startup/crash log
    (gui_qt.py's eqe_gui.log redirect), which always stays on.
    """
    config = load_config()
    return bool(config.get("logging", {}).get("enabled", True))


def append_line_to_log(text: str, logfile: Path | None = None) -> Path:
    """
    Append a free-text line to the application log, unless logging has
    been turned off (see is_enabled()) -- still returns the log file path
    either way, so callers that use the return value don't need to
    special-case it.
    """
    if logfile is None:
        logfile = get_log_file_path()

    if not is_enabled():
        return logfile

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp}  {text}\n"

    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line)

    return logfile


def append_to_log(user, sample, jsc, mmf, calibration_measurement, autosave, filename) -> Path:
    """
    Append one structured measurement entry to the application log.
    """
    logfile = get_log_file_path()

    text = (
        f"user={user} | "
        f"sample={sample} | "
        f"Jsc={jsc} | "
        f"MMF={mmf} | "
        f"calibration_measurement={calibration_measurement} | "
        f"autosave={autosave} | "
        f"filename={filename}"
    )

    return append_line_to_log(text, logfile=logfile)
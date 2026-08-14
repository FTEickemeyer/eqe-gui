from datetime import datetime
from pathlib import Path

from eqe.io.paths import get_paths


def get_log_file_path() -> Path:
    logs_dir = get_paths()["logs_dir"]
    timestamp = datetime.now().strftime("%Y-%m-%d")
    return logs_dir / f"eqe_{timestamp}.log"


def append_line_to_log(text: str, logfile: Path | None = None) -> Path:
    """
    Append a free-text line to the application log.
    """
    if logfile is None:
        logfile = get_log_file_path()

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
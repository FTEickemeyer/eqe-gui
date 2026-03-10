import os
from datetime import datetime


def append_to_log(logfile, text):
    """
    Append a line to the measurement log.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = f"{timestamp}  {text}\n"

    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line)
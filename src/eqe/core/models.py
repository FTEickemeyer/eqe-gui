from dataclasses import dataclass


@dataclass
class MeasurementParams:
    user: str
    sample: str
    wl_start: int
    wl_stop: int
    interval: int
    calibration_measurement: bool
    show_raw: bool
    save_raw: bool
    stop_when_zero: bool
    autosave: bool
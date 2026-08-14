from dataclasses import dataclass


# Measurement mode identifiers.
#
# This is the canonical definition -- the backend (controller.py,
# measurement_engine.py) must not import mode constants from the GUI
# package. app/qt_models.py re-exports these for GUI code, and adds its
# own GUI-only presentation data (labels, section visibility) on top.
STANDARD_EQE = "standard_eqe"
BIASED_EQE = "biased_eqe"
STANDARD_LIVE_EQE = "live_eqe"

LOCKIN_EQE_BG = "lockin_eqe_background"
LOCKIN_LIVE_EQE = "lockin_live_eqe"

# Modes whose measurement loop is perform_live_monitoring() rather than
# perform_measurement() (see controller.py worker()).
LIVE_MODES = (STANDARD_LIVE_EQE, LOCKIN_LIVE_EQE)


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
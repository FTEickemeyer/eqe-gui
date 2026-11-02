"""
Measurement configuration object.

This dataclass collects all parameters required to run an EQE measurement.
It forms the interface between the GUI and the measurement backend.

Later this object will be passed to the MeasurementController.
"""

from dataclasses import dataclass


@dataclass
class MeasurementConfig:
    """
    Configuration for one EQE measurement.
    """

    # -----------------------------
    # Metadata
    # -----------------------------

    sample_name: str
    comments: str
    # None if left unset (most users don't set this) -- see
    # app/widgets/metadata_panel.py's get_values(). Not used in any
    # calculation, only recorded for reference.
    cell_area_cm2: float | None

    # -----------------------------
    # Scan parameters
    # -----------------------------

    start_nm: float
    stop_nm: float
    step_nm: float
    direction: str

    # -----------------------------
    # Session parameters
    # -----------------------------

    user: str
    mode: str

    # -----------------------------
    # Simulation
    # -----------------------------

    simulation: bool
    simulation_profile: str

    # -----------------------------
    # Electrical bias
    # -----------------------------

    bias_enabled: bool
    bias_voltage: float
    compliance_current: float
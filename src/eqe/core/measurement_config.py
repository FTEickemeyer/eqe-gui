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
    cell_area_cm2: float

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
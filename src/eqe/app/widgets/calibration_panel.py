"""
Calibration panel for EQE measurements.

Controls whether the current scan is a calibration measurement: instead
of computing EQE against the active incident-beam calibration file, it
records the reference-cell and test-position raw currents and (on save)
produces a *new* incident-beam calibration file from them, which becomes
the active one for regular EQE scans afterward.

To run one: physically install the reference cell (the one whose IPCE
curve is configured as calibration.reference_cell_file) in place of the
sample, check "Calibration measurement", then Start a normal wavelength
scan. After it finishes, Save writes both the usual measurement file and
a new incbeamcurr_*.csv into the calibrations directory.
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QCheckBox,
    QLabel,
)


class CalibrationPanel(QWidget):
    """
    Panel controlling whether a scan is a calibration measurement.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QFormLayout()
        self.setLayout(layout)

        # ----------------------------------------
        # Calibration measurement
        # ----------------------------------------

        self.calibration_measurement_checkbox = QCheckBox("Calibration measurement")
        layout.addRow(self.calibration_measurement_checkbox)

        hint = QLabel(
            "Check with the reference cell installed instead of the sample.\n"
            "Saving afterward writes a new incident-beam calibration file."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)

    def get_values(self):
        """
        Return calibration settings.
        """
        return {
            "calibration_measurement": self.calibration_measurement_checkbox.isChecked(),
        }

"""
Calibration panel for EQE measurements.

Two different reference cells are involved in an EQE measurement, and
they must not be confused:

- The *internal* reference cell (referred to elsewhere in the codebase
  as "Siref"/"intSiref"): built into the system, monitors the
  monochromatic light via a beamsplitter, and is read continuously for
  every measurement (scan, live, or calibration) via `reference_meter`.
- The *external* Si71889 reference cell (calibration.reference_cell_file):
  a separate, physically swappable cell with its own certified IPCE
  curve, installed in place of the sample only while running a
  calibration measurement, and read via `test_meter` like a sample
  would be.

This panel controls whether the current scan is a calibration
measurement: instead of computing EQE against the active incident-beam
calibration file, it records the internal reference cell's and Si71889's
raw currents and (on save) produces a *new* incident-beam calibration
file from them, which becomes the active one for regular EQE scans
afterward.

To run one: physically install the Si71889 reference cell (the one whose
IPCE curve is configured as calibration.reference_cell_file) in place of
the sample, check "Calibration measurement", then Start a normal
wavelength scan. After it finishes, Save writes both the usual
measurement file and a new incbeamcurr_*.csv into the calibrations
directory.
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QCheckBox,
    QLabel,
)
from PySide6.QtCore import Signal


class CalibrationPanel(QWidget):
    """
    Panel controlling whether a scan is a calibration measurement.
    """

    # Emitted when the checkbox is toggled, so MainWindow can react (e.g.
    # pre-fill the sample name with the Si71889 reference cell's identifier).
    calibration_measurement_toggled = Signal(bool)

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

        self.calibration_measurement_checkbox.toggled.connect(
            self.calibration_measurement_toggled.emit
        )

        hint = QLabel(
            "Check with the Si71889 reference cell installed instead of the sample\n"
            "(not the internal reference cell -- that one stays in place).\n"
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

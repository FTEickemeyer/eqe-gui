"""
Advanced acquisition settings panel.

Currently holds:
- Stabilization time: how long to wait after the monochromator moves to a
  new wavelength, before taking a reading -- gives the cell's photocurrent
  time to settle. Applied after every wavelength move in both scan mode
  (perform_measurement) and live mode (perform_live_monitoring, including
  mid-run wavelength changes triggered from the Wavelength setting panel).

Any parameter added here should also get a line in io/data_io.py's
_advanced_lines() so it's recorded in saved files' metadata header.
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
)


class AdvancedAcquisitionPanel(QWidget):
    """
    Panel containing advanced acquisition parameters.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QFormLayout()
        self.setLayout(layout)

        # ----------------------------------------
        # Stabilization time
        # ----------------------------------------

        self.stabilization_time_spin = QDoubleSpinBox()

        self.stabilization_time_spin.setRange(0, 10000)
        self.stabilization_time_spin.setDecimals(0)
        self.stabilization_time_spin.setValue(100)

        self.stabilization_time_spin.setSuffix(" ms")

        layout.addRow("Stabilization time", self.stabilization_time_spin)

    def get_values(self):
        """
        Return advanced acquisition settings as a dictionary.
        """

        return {
            "stabilization_time_ms": self.stabilization_time_spin.value(),
        }

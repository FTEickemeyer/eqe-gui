"""
Scan panel for EQE measurements.

This panel defines the wavelength scan used for EQE measurements.

Current parameters:
- Start wavelength
- Stop wavelength
- Step size
- Scan direction

Later this panel may be extended with:
- custom wavelength list
- scan preview
- estimated scan duration
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
    QComboBox,
)


class ScanPanel(QWidget):
    """
    Panel containing spectral scan parameters.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):
        """
        Construct the scan parameter form.
        """

        layout = QFormLayout()
        self.setLayout(layout)

        # ----------------------------------------
        # Start wavelength
        # ----------------------------------------

        self.start_nm_spin = QDoubleSpinBox()

        self.start_nm_spin.setRange(200, 2000)
        self.start_nm_spin.setDecimals(1)
        self.start_nm_spin.setValue(300)

        self.start_nm_spin.setSuffix(" nm")

        layout.addRow("Start wavelength", self.start_nm_spin)

        # ----------------------------------------
        # Stop wavelength
        # ----------------------------------------

        self.stop_nm_spin = QDoubleSpinBox()

        self.stop_nm_spin.setRange(200, 2000)
        self.stop_nm_spin.setDecimals(1)
        self.stop_nm_spin.setValue(850)

        self.stop_nm_spin.setSuffix(" nm")

        layout.addRow("Stop wavelength", self.stop_nm_spin)

        # ----------------------------------------
        # Step size
        # ----------------------------------------

        self.step_nm_spin = QDoubleSpinBox()

        self.step_nm_spin.setRange(0.1, 100)
        self.step_nm_spin.setDecimals(1)
        self.step_nm_spin.setValue(10)

        self.step_nm_spin.setSuffix(" nm")

        layout.addRow("Step size", self.step_nm_spin)

        # ----------------------------------------
        # Scan direction
        # ----------------------------------------

        self.direction_combo = QComboBox()

        self.direction_combo.addItems([
            "Ascending",
            "Descending",
        ])

        layout.addRow("Direction", self.direction_combo)

    def get_values(self):
        """
        Return scan settings as a dictionary.

        This will later be replaced by the dataclass config system.
        """

        return {
            "start_nm": self.start_nm_spin.value(),
            "stop_nm": self.stop_nm_spin.value(),
            "step_nm": self.step_nm_spin.value(),
            "direction": self.direction_combo.currentText(),
        }
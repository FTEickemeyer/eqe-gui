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

from eqe.utils.validation import NM_MIN, NM_MAX


class ScanPanel(QWidget):
    """
    Panel containing spectral scan parameters.
    """

    # The instrument's physical wavelength limits (see utils/validation.py's
    # nm_lim_ok(), the single source of truth -- it rejects anything
    # outside this range rather than silently clamping to it, so keeping
    # the spin boxes themselves confined to the same range means a value
    # can't even be entered before that validation would reject it anyway).
    MIN_NM = NM_MIN
    MAX_NM = NM_MAX

    # Standard (non-calibration) scan defaults -- also what a "Calibration
    # measurement" checkbox uncheck restores (see mainwindow_qt.py's
    # _on_calibration_toggled(), which overwrites these with the full
    # 350-1170 nm range while checked).
    DEFAULT_START_NM = 350
    DEFAULT_STOP_NM = 840
    DEFAULT_STEP_NM = 10
    DEFAULT_DIRECTION = "Ascending"

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

        self.start_nm_spin.setRange(self.MIN_NM, self.MAX_NM)
        self.start_nm_spin.setDecimals(1)
        self.start_nm_spin.setValue(self.DEFAULT_START_NM)

        self.start_nm_spin.setSuffix(" nm")

        layout.addRow("Start wavelength", self.start_nm_spin)

        # ----------------------------------------
        # Stop wavelength
        # ----------------------------------------

        self.stop_nm_spin = QDoubleSpinBox()

        self.stop_nm_spin.setRange(self.MIN_NM, self.MAX_NM)
        self.stop_nm_spin.setDecimals(1)
        self.stop_nm_spin.setValue(self.DEFAULT_STOP_NM)

        self.stop_nm_spin.setSuffix(" nm")

        layout.addRow("Stop wavelength", self.stop_nm_spin)

        # ----------------------------------------
        # Step size
        # ----------------------------------------

        self.step_nm_spin = QDoubleSpinBox()

        self.step_nm_spin.setRange(0.1, 100)
        self.step_nm_spin.setDecimals(1)
        self.step_nm_spin.setValue(self.DEFAULT_STEP_NM)

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

    def reset_to_defaults(self):
        """
        Restore the standard (non-calibration) spectral scan settings.

        Called when "Calibration measurement" is unchecked (see
        mainwindow_qt.py's _on_calibration_toggled()) to undo the full
        350-1170 nm range it forces while checked.
        """
        self.start_nm_spin.setValue(self.DEFAULT_START_NM)
        self.stop_nm_spin.setValue(self.DEFAULT_STOP_NM)
        self.step_nm_spin.setValue(self.DEFAULT_STEP_NM)
        self.direction_combo.setCurrentText(self.DEFAULT_DIRECTION)

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
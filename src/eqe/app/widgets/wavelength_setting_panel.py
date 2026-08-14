"""
Wavelength setting panel for live-monitoring modes.

Live EQE / Lock-in Live EQE measure at a single, fixed wavelength over
time rather than sweeping a range -- unlike ScanPanel (start/stop/step/
direction), which only applies to wavelength-sweep modes. This panel has
just the one control that's actually meaningful for live modes: the
target wavelength, which can also be changed while a live measurement is
running (see wavelength_changed).
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
)
from PySide6.QtCore import Signal


class WavelengthSettingPanel(QWidget):
    """
    Panel containing the fixed measurement wavelength for live modes.
    """

    # Emitted whenever the wavelength value changes (including while a
    # live measurement is running), so it can be applied live.
    wavelength_changed = Signal(float)

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QFormLayout()
        self.setLayout(layout)

        self.wavelength_nm_spin = QDoubleSpinBox()

        self.wavelength_nm_spin.setRange(350, 1200)
        self.wavelength_nm_spin.setDecimals(1)
        self.wavelength_nm_spin.setValue(550)

        self.wavelength_nm_spin.setSuffix(" nm")

        layout.addRow("Wavelength", self.wavelength_nm_spin)

        self.wavelength_nm_spin.valueChanged.connect(self.wavelength_changed.emit)

    def get_wavelength(self):
        """
        Return the current wavelength setting, in nm.
        """

        return self.wavelength_nm_spin.value()

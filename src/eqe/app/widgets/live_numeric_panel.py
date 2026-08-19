"""
Live numeric readout panel.

Displays real-time measurement values during EQE measurements.

Initial values displayed:
- wavelength (the wavelength actually being measured right now -- for a
  live mode this is the fixed measurement wavelength, not elapsed time)
- EQE (%)
- test cell current (whatever's in the sample position -- the sample
  itself normally, or the external Si71889 cell during a calibration
  measurement)
- reference cell current (always the internal reference cell, read via
  reference_meter regardless of mode -- never the external Si71889 cell)
- integrated current

Later extensions:
- lock-in amplitude/phase
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QLabel,
)


class LiveNumericPanel(QWidget):
    """
    Real-time numeric measurement readout.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QFormLayout()
        self.setLayout(layout)

        # -----------------------------
        # Wavelength
        # -----------------------------

        self.wavelength_label = QLabel("--- nm")
        layout.addRow("Wavelength", self.wavelength_label)

        # -----------------------------
        # EQE
        # -----------------------------

        self.eqe_label = QLabel("0.00 %")
        layout.addRow("EQE", self.eqe_label)

        # -----------------------------
        # Cell current
        # -----------------------------

        self.cell_current_label = QLabel("0 A")
        layout.addRow("Cell current", self.cell_current_label)

        # -----------------------------
        # Reference current
        # -----------------------------

        self.ref_current_label = QLabel("0 A")
        layout.addRow("Reference current", self.ref_current_label)

        # -----------------------------
        # Integrated current
        # -----------------------------
        # Only meaningful during a wavelength scan (integrated over the
        # spectrum measured so far); always 0 during live monitoring at a
        # fixed wavelength, since there's no spectrum to integrate over.

        self.integrated_current_label = QLabel("0.00 mA/cm²")
        layout.addRow("Integrated current", self.integrated_current_label)

    def set_integrated_current_visible(self, visible: bool):
        """
        Show or hide the integrated-current row (hidden during live
        monitoring at a fixed wavelength, where it's structurally 0).
        """

        layout = self.layout()
        self.integrated_current_label.setVisible(visible)
        label = layout.labelForField(self.integrated_current_label)
        if label is not None:
            label.setVisible(visible)

    def set_eqe_visible(self, visible: bool):
        """
        Show or hide the EQE row (hidden during a calibration measurement,
        where EQE isn't computed -- only raw cell/reference currents are).
        """

        layout = self.layout()
        self.eqe_label.setVisible(visible)
        label = layout.labelForField(self.eqe_label)
        if label is not None:
            label.setVisible(visible)

    def update_values(self, wavelength_nm, eqe, cell_current, ref_current, integrated_current=0.0):
        """
        Update displayed measurement values.
        """

        self.wavelength_label.setText(f"{wavelength_nm:.1f} nm")
        self.eqe_label.setText(f"{eqe:.3f} %")
        self.cell_current_label.setText(f"{cell_current:.3e} A")
        self.ref_current_label.setText(f"{ref_current:.3e} A")
        self.integrated_current_label.setText(f"{integrated_current:.3f} mA/cm²")
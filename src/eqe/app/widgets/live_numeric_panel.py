"""
Live numeric readout panel.

Displays real-time measurement values during EQE measurements.

Initial values displayed:
- EQE (%)
- test cell current
- reference cell current

Later extensions:
- wavelength
- integrated current
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

    def update_values(self, eqe, cell_current, ref_current):
        """
        Update displayed measurement values.
        """

        self.eqe_label.setText(f"{eqe:.3f} %")
        self.cell_current_label.setText(f"{cell_current:.3e} A")
        self.ref_current_label.setText(f"{ref_current:.3e} A")
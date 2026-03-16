"""
Bias panel for EQE measurements.

Controls the bias voltage applied to the test cell via the SMU.

Initially only a constant voltage bias is supported.

Later this panel can be extended with:
- current bias mode
- voltage sweep
- compliance limits
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QCheckBox,
    QDoubleSpinBox,
)


class BiasPanel(QWidget):
    """
    Panel controlling electrical bias during EQE measurements.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QFormLayout()
        self.setLayout(layout)

        # ----------------------------------------
        # Enable bias
        # ----------------------------------------

        self.enable_bias_checkbox = QCheckBox("Enable bias")

        layout.addRow(self.enable_bias_checkbox)

        # ----------------------------------------
        # Bias voltage
        # ----------------------------------------

        self.bias_voltage_spin = QDoubleSpinBox()

        self.bias_voltage_spin.setRange(-5, 5)
        self.bias_voltage_spin.setDecimals(3)
        self.bias_voltage_spin.setSingleStep(0.01)
        self.bias_voltage_spin.setSuffix(" V")

        layout.addRow("Bias voltage", self.bias_voltage_spin)

    def get_values(self):
        """
        Return bias settings.
        """

        return {
            "bias_enabled": self.enable_bias_checkbox.isChecked(),
            "bias_voltage": self.bias_voltage_spin.value(),
        }
"""
Advanced acquisition settings panel.

Currently holds:
- Stabilization time: how long to wait after the monochromator moves to a
  new wavelength, before taking a reading -- gives the cell's photocurrent
  time to settle. Applied after every wavelength move in both scan mode
  (perform_measurement) and live mode (perform_live_monitoring, including
  mid-run wavelength changes triggered from the Wavelength setting panel).
- Reference meter mode + shunt resistance: how the internal reference
  cell's current is sensed by the Keithley 2000 -- directly ("Current"),
  or as a voltage drop across a known external shunt resistor wired to
  the instrument's Input HI/LO terminals ("Voltage (shunt)"), converted
  back to an equivalent current before it reaches the rest of the app
  (see core/instruments/keithley2000.py). Added 2026-08-14: the Keithley
  2000's DC current function only has one, oversized range, giving poor
  resolution for this weak a signal; measuring voltage across a shunt
  instead gives access to much lower (and better-resolution) ranges.
  "Voltage (shunt)" is the default, matching the physical wiring as of
  2026-08-14 (sensing method/wiring unchanged since). The shunt resistor
  itself was swapped from 598 ohm to 1987 ohm on 2026-11-02 -- current
  standard, ~7 uA expected -> ~13.9 mV drop; switch back to "Current" if
  the shunt is ever removed and the reference meter is rewired back to
  direct current sensing.

This whole panel is developer-only (felix) to *edit* -- see
mainwindow_qt.update_mode_visibility() -- since a wrong value here
(especially the shunt resistance) silently corrupts every measurement
that follows. Other users still see and are affected by whatever felix
last configured; they just can't change it themselves.

Any parameter added here should also get a line in io/data_io.py's
_advanced_lines() so it's recorded in saved files' metadata header.
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
    QComboBox,
)


class AdvancedAcquisitionPanel(QWidget):
    """
    Panel containing advanced acquisition parameters.
    """

    # Internal mode keys (not the combo box's display text).
    MODE_CURRENT = "current"
    MODE_VOLTAGE_SHUNT = "voltage_shunt"

    _MODE_LABELS = {
        MODE_CURRENT: "Current (direct)",
        MODE_VOLTAGE_SHUNT: "Voltage (shunt resistor)",
    }

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

        # ----------------------------------------
        # Reference meter mode
        # ----------------------------------------

        self.reference_mode_combo = QComboBox()
        for key, label in self._MODE_LABELS.items():
            self.reference_mode_combo.addItem(label, key)
        # Default matches the physical wiring as of 2026-08-14 (see
        # module docstring).
        self.reference_mode_combo.setCurrentIndex(
            self.reference_mode_combo.findData(self.MODE_VOLTAGE_SHUNT)
        )

        layout.addRow("Reference meter mode", self.reference_mode_combo)

        # ----------------------------------------
        # Shunt resistance
        # ----------------------------------------

        self.shunt_resistance_spin = QDoubleSpinBox()

        self.shunt_resistance_spin.setRange(1, 1_000_000)
        self.shunt_resistance_spin.setDecimals(1)
        # Current standard shunt resistor, as of 2026-11-02 (was 598 ohm).
        self.shunt_resistance_spin.setValue(1987)

        self.shunt_resistance_spin.setSuffix(" Ω")

        layout.addRow("Shunt resistance", self.shunt_resistance_spin)

        # Only meaningful in voltage-shunt mode -- kept enabled/disabled
        # in sync with the mode selection, but its value is preserved
        # either way so switching back doesn't lose it.
        self.reference_mode_combo.currentIndexChanged.connect(
            self._update_shunt_resistance_enabled
        )
        self._update_shunt_resistance_enabled()

    def _update_shunt_resistance_enabled(self):
        is_voltage_shunt = self.reference_mode_combo.currentData() == self.MODE_VOLTAGE_SHUNT
        self.shunt_resistance_spin.setEnabled(is_voltage_shunt)

    def get_values(self):
        """
        Return advanced acquisition settings as a dictionary.
        """

        return {
            "stabilization_time_ms": self.stabilization_time_spin.value(),
            "reference_meter_mode": self.reference_mode_combo.currentData(),
            "shunt_resistance_ohms": self.shunt_resistance_spin.value(),
        }

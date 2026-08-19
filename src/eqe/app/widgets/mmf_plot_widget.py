"""
Mismatch Factor (MMF) plot widget.

Matplotlib canvas embedded in Qt showing, over the common wavelength range
the MMF calculation actually integrated over (see analysis/mmf.py's
compute_mmf()):

- Left axis: EQE (%) of the DUT and of the reference cell.
- Right axis: the (peak-)normalized spectral photon flux of the lamp
  spectrum and of the AM1.5GT reference spectrum, for a shape comparison.

See mmf_dialog.py, which owns the file selection / Run / Save controls
around this widget.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MMFPlotWidget(QWidget):
    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.figure = Figure(figsize=(7, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("EQE (%)")
        self.ax.set_title("MMF spectra")

        self.ax2 = self.ax.twinx()
        self.ax2.set_ylabel("Normalized spectral photon flux")

        (self.dut_line,) = self.ax.plot(
            [], [], color="tab:blue", linestyle="-", label="EQE DUT"
        )
        (self.ref_line,) = self.ax.plot(
            [], [], color="tab:green", linestyle="--", label="EQE reference cell"
        )
        (self.lamp_line,) = self.ax2.plot(
            [], [], color="orange", linestyle="-", label="Lamp spectrum (norm.)"
        )
        (self.am15_line,) = self.ax2.plot(
            [], [], color="black", linestyle="--", label="AM1.5GT (norm.)"
        )

        self._update_legend()
        self.canvas.draw()

    def _update_legend(self):
        handles1, labels1 = self.ax.get_legend_handles_labels()
        handles2, labels2 = self.ax2.get_legend_handles_labels()
        self.ax.legend(handles1 + handles2, labels1 + labels2, loc="best")

    def clear(self):
        for line in (self.dut_line, self.ref_line, self.lamp_line, self.am15_line):
            line.set_data([], [])
        self.ax.set_title("MMF spectra")
        self.canvas.draw_idle()

    def update_curves(self, wavelengths_nm, dut_eqe_pct, ref_eqe_pct, lamp_pf_norm, am15_pf_norm, left_nm, right_nm):
        """
        Update all four curves at once and rescale both axes. `left_nm`/
        `right_nm` (the integration window) are shown in the title so
        it's clear what range the MMF calculation actually covered.
        """

        self.dut_line.set_data(wavelengths_nm, dut_eqe_pct)
        self.ref_line.set_data(wavelengths_nm, ref_eqe_pct)
        self.lamp_line.set_data(wavelengths_nm, lamp_pf_norm)
        self.am15_line.set_data(wavelengths_nm, am15_pf_norm)

        self.ax.set_title(f"MMF spectra ({left_nm:.0f}–{right_nm:.0f} nm)")

        self.ax.relim()
        self.ax.autoscale_view()

        self.ax2.relim()
        self.ax2.autoscale_view()

        self.canvas.draw_idle()

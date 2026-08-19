"""
Mismatch Factor (MMF) plot widget.

Matplotlib canvas embedded in Qt showing, over the common wavelength range
the MMF calculation actually integrated over (see analysis/mmf.py's
compute_mmf()):

- Left axis: EQE (%) of the DUT and of the reference cell.
- Right axis: the spectral photon flux of the lamp spectrum and of the
  AM1.5GT reference spectrum, each normalized to 1 at
  analysis/mmf.py's NORMALIZE_AT_NM (680 nm by default), for a shape
  comparison.

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
        self.ax2.set_ylabel("Spectral photon flux (norm. at 680 nm)")
        # Fixed rather than autoscaled: both curves are normalized to 1 at
        # 680 nm (see compute_mmf()), so a fixed 0-1.1 range keeps that
        # normalization point visually comparable across different runs
        # instead of rescaling to whatever each pair of curves happens to
        # peak at.
        self.ax2.set_ylim(0, 1.1)

        # DUT legend label is overridden per-result to the actual device
        # name (see update_curves()'s dut_label) -- "EQE DUT" here is
        # only the placeholder shown before a first Run.
        (self.dut_line,) = self.ax.plot(
            [], [], color="red", linestyle="-", label="EQE DUT"
        )
        (self.ref_line,) = self.ax.plot(
            [], [], color="tab:green", linestyle="--", linewidth=0.5,
            label="EQE reference cell",
        )
        # Fine (0.5 pt) solid lines for both spectra on the right axis --
        # distinguishes them visually from the thicker DUT curve on the
        # left axis and from each other by color only, not by dashing.
        (self.lamp_line,) = self.ax2.plot(
            [], [], color="orange", linestyle="-", linewidth=0.5,
            label="Lamp spectrum (norm.)",
        )
        (self.am15_line,) = self.ax2.plot(
            [], [], color="black", linestyle="-", linewidth=0.5,
            label="AM1.5GT (norm.)",
        )

        self._update_legend()
        self.canvas.draw()

    def _update_legend(self):
        handles1, labels1 = self.ax.get_legend_handles_labels()
        handles2, labels2 = self.ax2.get_legend_handles_labels()
        self.ax.legend(handles1 + handles2, labels1 + labels2, loc="upper left")

    def clear(self):
        for line in (self.dut_line, self.ref_line, self.lamp_line, self.am15_line):
            line.set_data([], [])
        self.ax.set_title("MMF spectra")
        self.canvas.draw_idle()

    def update_curves(
        self,
        wavelengths_nm,
        dut_eqe_pct,
        ref_eqe_pct,
        lamp_pf_norm,
        am15_pf_norm,
        left_nm,
        right_nm,
        dut_label="EQE DUT",
    ):
        """
        Update all four curves at once and rescale both axes. `left_nm`/
        `right_nm` (the integration window) are shown in the title so
        it's clear what range the MMF calculation actually covered.
        `dut_label` sets the DUT curve's legend entry -- normally the
        device/sample name extracted from the DUT file (see
        mmf_dialog.py's _on_run(), analysis/mmf.py's
        extract_sample_name()) rather than the generic default.
        """

        self.dut_line.set_data(wavelengths_nm, dut_eqe_pct)
        self.ref_line.set_data(wavelengths_nm, ref_eqe_pct)
        self.lamp_line.set_data(wavelengths_nm, lamp_pf_norm)
        self.am15_line.set_data(wavelengths_nm, am15_pf_norm)

        self.dut_line.set_label(dut_label)
        self._update_legend()

        self.ax.set_title(f"MMF spectra ({left_nm:.0f}–{right_nm:.0f} nm)")

        self.ax.relim()
        self.ax.autoscale_view()

        # Fixed, not autoscaled -- see _build_ui()'s set_ylim() comment.
        self.ax2.set_ylim(0, 1.1)

        self.canvas.draw_idle()

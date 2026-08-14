"""
EQE plot widget.

Matplotlib canvas embedded in Qt showing EQE (left axis) and integrated
current (right axis, twin y-axis) on the same plot, sharing one x-axis.

Previously these were two separate stacked plot widgets; combined into
one so both curves are visible together without scrolling.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class EQEPlotWidget(QWidget):
    """
    Widget containing the live EQE plot, with integrated current (or, in
    live-monitoring mode, cell current) on a twin right-hand y-axis.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Create matplotlib figure
        self.figure = Figure(figsize=(6, 5))

        self.canvas = FigureCanvasQTAgg(self.figure)

        layout.addWidget(self.canvas)

        # Left axis: EQE (%)
        self.ax = self.figure.add_subplot(111)

        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("EQE (%)")

        self.ax.set_title("EQE Spectrum")

        # Right axis: integrated current (twin, shares the x-axis)
        self.ax2 = self.ax.twinx()
        self.ax2.set_ylabel("Integrated current (mA/cm²)")

        # Prepare empty lines -- same styling as the two original widgets
        self.line, = self.ax.plot([], [], marker="o", color="tab:blue", label="EQE (%)")
        self.line2, = self.ax2.plot(
            [], [], color="orange", linestyle="-", label="Integrated current"
        )

        # One legend combining both axes' lines -- without this, a
        # two-line/two-axis plot like this doesn't say which curve is
        # which (e.g. during a calibration measurement, the two lines are
        # two different physical cells' currents on very different
        # scales; mixing them up matters). Kept in sync with the actual
        # line labels by set_legend_labels(), called whenever
        # mainwindow_qt.py switches what this plot is showing.
        self._update_legend()

        self.canvas.draw()

    def _update_legend(self):
        handles1, labels1 = self.ax.get_legend_handles_labels()
        handles2, labels2 = self.ax2.get_legend_handles_labels()
        self.ax.legend(handles1 + handles2, labels1 + labels2, loc="best")

    def set_legend_labels(self, label1, label2):
        """
        Update the two curves' legend labels -- call whenever what they
        represent changes (e.g. switching between a regular scan's
        "EQE (%)"/"Integrated current" and a calibration measurement's
        two different cells' raw currents; see mainwindow_qt.py's
        _configure_plots_for_mode()).
        """

        self.line.set_label(label1)
        self.line2.set_label(label2)
        self._update_legend()
        self.canvas.draw_idle()

    def update_curve(self, wavelengths, eqe_values):
        """
        Update the EQE (left-axis) curve only. Kept for callers that only
        have EQE data; prefer update_curves() when both are available.
        """

        self.line.set_data(wavelengths, eqe_values)

        self.ax.relim()
        self.ax.autoscale_view()

        self.canvas.draw_idle()

    def update_curves(self, x_values, eqe_values, current_values):
        """
        Update both curves at once: EQE (left axis) and integrated/cell
        current (right axis), sharing the same x-axis.
        """

        self.line.set_data(x_values, eqe_values)
        self.line2.set_data(x_values, current_values)

        self.ax.relim()
        self.ax.autoscale_view()

        self.ax2.relim()
        self.ax2.autoscale_view()

        self.canvas.draw_idle()

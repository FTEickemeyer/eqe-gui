"""
Integrated current plot widget.

Displays the integrated current calculated from the EQE spectrum.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class IntegratedCurrentPlotWidget(QWidget):
    """
    Widget displaying the integrated photocurrent during EQE scans.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.figure = Figure(figsize=(6, 3))

        self.canvas = FigureCanvasQTAgg(self.figure)

        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)

        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Integrated current (mA/cm²)")
        self.ax.set_title("Integrated Current")

        # orange line without markers (as requested earlier)
        self.line, = self.ax.plot([], [], color="orange", linestyle="-")

        self.canvas.draw()

    def update_curve(self, wavelengths, current_values):
        """
        Update integrated current curve.
        """

        self.line.set_data(wavelengths, current_values)

        self.ax.relim()
        self.ax.autoscale_view()

        self.canvas.draw_idle()
"""
EQE plot widget.

Matplotlib canvas embedded in Qt for displaying EQE spectra.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class EQEPlotWidget(QWidget):
    """
    Widget containing the live EQE plot.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Create matplotlib figure
        self.figure = Figure(figsize=(6, 4))

        self.canvas = FigureCanvasQTAgg(self.figure)

        layout.addWidget(self.canvas)

        # Create axis
        self.ax = self.figure.add_subplot(111)

        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("EQE (%)")

        self.ax.set_title("EQE Spectrum")

        # Prepare empty line
        self.line, = self.ax.plot([], [], marker="o")

        self.canvas.draw()

    def update_curve(self, wavelengths, eqe_values):
        """
        Update EQE curve.
        """

        self.line.set_data(wavelengths, eqe_values)

        self.ax.relim()
        self.ax.autoscale_view()

        self.canvas.draw_idle()
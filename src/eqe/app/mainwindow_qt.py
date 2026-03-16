"""
Main window for the PySide6 EQE/IPCE GUI.

This version establishes the **core layout skeleton** that will remain
stable for the entire application.

Structure:

Top bar:
    Session / Run Control

Main area:
    Left  -> Measurement setup
    Right -> Live monitoring

Later we will insert real widgets into the placeholder group boxes.
"""

from eqe.app.widgets.session_panel import SessionPanel

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QGroupBox,
)
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # Window title
        self.setWindowTitle("EQE / IPCE Measurement GUI (PySide6)")

        # Initial window size
        self.resize(1400, 900)

        # Build the GUI
        self._build_ui()


    def _on_mode_changed(self, mode):
        """
        Called when the measurement mode changes.
        """

        print(f"Mode changed to: {mode}")


    def _on_start(self):
        """
        Placeholder start action.
        """

        print("Start requested")


    def _on_stop(self):
        """
        Placeholder stop action.
        """

        print("Stop requested")


    def _on_save(self):
        """
        Placeholder save action.
        """

        print("Manual save requested")


    def _build_ui(self):
        """
        Construct the main window layout.

        The layout consists of:

        - Top session control bar
        - Horizontal splitter dividing setup and monitoring
        """

        # ---- Central widget ----
        # QMainWindow requires a central widget to host layouts
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout of the window
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # ----------------------------------------------------------
        # 1. Top control bar (Session / Run Control)
        # ----------------------------------------------------------

        self.session_panel = SessionPanel()

        # Connect signals
        self.session_panel.mode_changed.connect(self._on_mode_changed)
        self.session_panel.start_clicked.connect(self._on_start)
        self.session_panel.stop_clicked.connect(self._on_stop)
        self.session_panel.save_clicked.connect(self._on_save)

        main_layout.addWidget(self.session_panel)


        # ----------------------------------------------------------
        # 2. Main horizontal splitter
        # ----------------------------------------------------------

        # Splitter allows the user to resize left/right panels
        splitter = QSplitter(Qt.Horizontal)

        main_layout.addWidget(splitter)

        # ----------------------------------------------------------
        # LEFT PANEL — Measurement setup
        # ----------------------------------------------------------

        setup_widget = QWidget()
        setup_layout = QVBoxLayout()
        setup_widget.setLayout(setup_layout)

        splitter.addWidget(setup_widget)

        # Metadata section
        self.metadata_group = QGroupBox("Sample / Metadata")
        self.metadata_group.setLayout(QVBoxLayout())
        self.metadata_group.layout().addWidget(QLabel("Metadata panel placeholder"))
        setup_layout.addWidget(self.metadata_group)

        # Scan settings
        self.scan_group = QGroupBox("Spectral Scan")
        self.scan_group.setLayout(QVBoxLayout())
        self.scan_group.layout().addWidget(QLabel("Scan settings placeholder"))
        setup_layout.addWidget(self.scan_group)

        # Electrical bias
        self.bias_group = QGroupBox("Electrical Bias")
        self.bias_group.setLayout(QVBoxLayout())
        self.bias_group.layout().addWidget(QLabel("Bias controls placeholder"))
        setup_layout.addWidget(self.bias_group)

        # Optical modulation
        self.modulation_group = QGroupBox("Optical Modulation / Lock-in")
        self.modulation_group.setLayout(QVBoxLayout())
        self.modulation_group.layout().addWidget(QLabel("Lock-in controls placeholder"))
        setup_layout.addWidget(self.modulation_group)

        # Background illumination
        self.background_group = QGroupBox("Background Illumination")
        self.background_group.setLayout(QVBoxLayout())
        self.background_group.layout().addWidget(QLabel("Background light controls placeholder"))
        setup_layout.addWidget(self.background_group)

        # Calibration and saving
        self.calibration_group = QGroupBox("Calibration / Saving")
        self.calibration_group.setLayout(QVBoxLayout())
        self.calibration_group.layout().addWidget(QLabel("Calibration panel placeholder"))
        setup_layout.addWidget(self.calibration_group)

        # Advanced acquisition settings
        self.advanced_group = QGroupBox("Advanced Acquisition Settings")
        self.advanced_group.setLayout(QVBoxLayout())
        self.advanced_group.layout().addWidget(QLabel("Advanced controls placeholder"))
        setup_layout.addWidget(self.advanced_group)

        # Stretch ensures panels stay at the top
        setup_layout.addStretch()

        # ----------------------------------------------------------
        # RIGHT PANEL — Live monitoring
        # ----------------------------------------------------------

        live_widget = QWidget()
        live_layout = QVBoxLayout()
        live_widget.setLayout(live_layout)

        splitter.addWidget(live_widget)

        # Live EQE plot
        self.eqe_plot_group = QGroupBox("Live EQE")
        self.eqe_plot_group.setLayout(QVBoxLayout())
        self.eqe_plot_group.layout().addWidget(QLabel("EQE plot placeholder"))
        live_layout.addWidget(self.eqe_plot_group)

        # Secondary plot
        self.secondary_plot_group = QGroupBox("Secondary Live Signal")
        self.secondary_plot_group.setLayout(QVBoxLayout())
        self.secondary_plot_group.layout().addWidget(QLabel("Secondary plot placeholder"))
        live_layout.addWidget(self.secondary_plot_group)

        # Numeric readout
        self.readout_group = QGroupBox("Live Readout")
        self.readout_group.setLayout(QVBoxLayout())
        self.readout_group.layout().addWidget(QLabel("Numeric readout placeholder"))
        live_layout.addWidget(self.readout_group)

        # Log / status
        self.log_group = QGroupBox("Status / Log")
        self.log_group.setLayout(QVBoxLayout())
        self.log_group.layout().addWidget(QLabel("Log output placeholder"))
        live_layout.addWidget(self.log_group)

        # ----------------------------------------------------------
        # Initial splitter proportions
        # ----------------------------------------------------------

        splitter.setSizes([400, 1000])


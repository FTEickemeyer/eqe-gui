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

"""

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

from eqe.core.measurement_config import MeasurementConfig
from eqe.app.widgets.session_panel import SessionPanel
# Import GUI visibility specification
from eqe.app.qt_models import (
    MODE_SECTIONS,
    SECTION_METADATA,
    SECTION_SCAN,
    SECTION_BIAS,
    SECTION_MODULATION,
    SECTION_BACKGROUND,
    SECTION_CALIBRATION,
    SECTION_ADVANCED,
    SECTION_LIVE_NUMERIC,
)
from eqe.app.widgets.session_panel import SessionPanel
from eqe.app.widgets.metadata_panel import MetadataPanel
from eqe.app.widgets.scan_panel import ScanPanel
from eqe.app.widgets.log_panel import LogPanel
from eqe.app.widgets.bias_panel import BiasPanel
from eqe.app.widgets.live_numeric_panel import LiveNumericPanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # Window title
        self.setWindowTitle("EQE Measurement GUI (PySide6)")

        # Initial window size
        self.resize(1400, 900)

        # --------------------------------------------------
        # 1. Build the GUI (creates all widgets)
        # --------------------------------------------------
        self._build_ui()

        # --------------------------------------------------
        # 2. Map section identifiers to GUI widgets
        # --------------------------------------------------
        self.section_widgets = {
            SECTION_METADATA: self.metadata_group,
            SECTION_SCAN: self.scan_group,
            SECTION_BIAS: self.bias_group,
            SECTION_MODULATION: self.modulation_group,
            SECTION_BACKGROUND: self.background_group,
            SECTION_CALIBRATION: self.calibration_group,
            SECTION_ADVANCED: self.advanced_group,
            SECTION_LIVE_NUMERIC: self.readout_group,
        }

        # --------------------------------------------------
        # 3. Apply visibility for the initial mode
        # --------------------------------------------------
        initial_mode = self.session_panel.get_mode()
        self.update_mode_visibility(initial_mode)

        self.log_panel.append("GUI initialized")


    def _on_mode_changed(self, mode):
        """
        Called when the measurement mode changes.
        """

        print(f"Mode changed to: {mode}")

        # Update panel visibility
        self.update_mode_visibility(mode)   


    def _on_start(self):
        """
        Called when the Start button is pressed.
        """

        config = self.collect_measurement_config()

        self.log_panel.append("Starting measurement")
        self.log_panel.append(str(config))


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


    def collect_measurement_config(self):
        """
        Collect all GUI parameters and build a MeasurementConfig object.
        """

        metadata = self.metadata_panel.get_values()
        scan = self.scan_panel.get_values()
        bias = self.bias_panel.get_values()
        
        config = MeasurementConfig(

            # Metadata
            sample_name=metadata["sample_name"],
            comments=metadata["comments"],
            cell_area_cm2=metadata["cell_area_cm2"],

            # Scan
            start_nm=scan["start_nm"],
            stop_nm=scan["stop_nm"],
            step_nm=scan["step_nm"],
            direction=scan["direction"],

            # Session
            user=self.session_panel.get_user(),
            mode=self.session_panel.get_mode(),

            # Simulation
            simulation=self.session_panel.sim_checkbox.isChecked(),
            simulation_profile=self.session_panel.sim_profile_combo.currentText(),

            # Electrical bias
            bias_enabled=bias["bias_enabled"],
            bias_voltage=bias["bias_voltage"],
        )

        return config


    def update_mode_visibility(self, mode):
        """
        Update GUI panel visibility according to the selected measurement mode.

        The rules are defined in MODE_SECTIONS (qt_models.py).
        """

        # Get visibility rules for the selected mode
        sections = MODE_SECTIONS.get(mode, {})

        for section, widget in self.section_widgets.items():

            # Determine whether this section should be visible
            visible = sections.get(section, False)

            # Show or hide the widget
            widget.setVisible(visible)


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

        # Create and insert the real metadata panel
        self.metadata_panel = MetadataPanel()
        self.metadata_group.layout().addWidget(self.metadata_panel)

        setup_layout.addWidget(self.metadata_group)

        # Spectral scan section
        self.scan_group = QGroupBox("Spectral Scan")
        self.scan_group.setLayout(QVBoxLayout())

        # Create and insert the real scan panel
        self.scan_panel = ScanPanel()
        self.scan_group.layout().addWidget(self.scan_panel)

        setup_layout.addWidget(self.scan_group)

        # Electrical bias
        self.bias_group = QGroupBox("Electrical Bias")
        self.bias_group.setLayout(QVBoxLayout())

        self.bias_panel = BiasPanel()

        self.bias_group.layout().addWidget(self.bias_panel)

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

        # Live numeric readout
        self.readout_group = QGroupBox("Live Readout")
        self.readout_group.setLayout(QVBoxLayout())

        self.live_numeric_panel = LiveNumericPanel()

        self.readout_group.layout().addWidget(self.live_numeric_panel)

        live_layout.addWidget(self.readout_group)

        # Status / log
        self.log_group = QGroupBox("Status / Log")
        self.log_group.setLayout(QVBoxLayout())

        # Create the real log panel
        self.log_panel = LogPanel()

        self.log_group.layout().addWidget(self.log_panel)

        live_layout.addWidget(self.log_group)

        # ----------------------------------------------------------
        # Initial splitter proportions
        # ----------------------------------------------------------

        splitter.setSizes([400, 1000])


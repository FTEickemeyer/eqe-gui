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

from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QGroupBox,
)
from PySide6.QtCore import Qt, Signal

from eqe.core.measurement_config import MeasurementConfig
from eqe.core.controller import MeasurementController
from eqe.core.models import MeasurementParams
from eqe.analysis.calibration import open_calibration
from eqe.utils.validation import nm_lim_ok
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
from eqe.app.widgets.eqe_plot_widget import EQEPlotWidget
from eqe.app.widgets.integrated_current_plot_widget import IntegratedCurrentPlotWidget
from eqe.io.data_io import save_data
from eqe.io.paths import get_paths


class MainWindow(QMainWindow):

    # Signal used to forward point updates safely to the GUI thread
    point_acquired_signal = Signal(float, float, float)

    # Signal used to update the live numeric panel safely in the GUI thread
    live_numeric_signal = Signal(float, float, float)

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

        # Connect worker-thread point updates to a GUI-thread slot
        self.point_acquired_signal.connect(self._handle_point_acquired_gui)
        self.live_numeric_signal.connect(self._handle_live_numeric_gui)

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

        # temporary test data
        self.eqe_plot_widget.update_curve(
            [400, 500, 600, 700, 800],
            [20, 45, 60, 50, 30]
        )

        self.current_plot_widget.update_curve(
            [400, 500, 600, 700, 800],
            [1.5, 5.2, 12.3, 15.8, 17.1]
        )

        # storage for measurement data during scans
        self._wavelengths = []
        self._eqe_values = []
        self._current_values = []

        # Last completed measurement dataframe, used by manual Save
        self._last_result_df = None
        
        # measurement controller
        self.controller = MeasurementController()


    def _on_mode_changed(self, mode):
        """
        Called when the measurement mode changes.
        """

        print(f"Mode changed to: {mode}")

        # Update panel visibility
        self.update_mode_visibility(mode)   


    def _on_start(self):
        """
        Start an EQE measurement using the current legacy controller API.

        For now, the Qt GUI follows the same preparation flow as gui_legacy.py:
        - build MeasurementParams
        - validate wavelength limits
        - connect instruments
        - load calibration
        - start controller.run_measurement_async(...)
        """

        # Collect full config (NEW)
        config = self.collect_measurement_config()

        try:
            # --------------------------------------------------
            # Build legacy MeasurementParams object
            # --------------------------------------------------
            params = MeasurementParams(
                user=self.session_panel.get_user().strip(),
                sample=self.metadata_panel.sample_name_edit.text().strip(),
                wl_start=int(self.scan_panel.start_nm_spin.value()),
                wl_stop=int(self.scan_panel.stop_nm_spin.value()),
                interval=int(self.scan_panel.step_nm_spin.value()),
                calibration_measurement=False,
                show_raw=False,
                save_raw=False,
                stop_when_zero=False,
                autosave=False,
            )

            # Reset plots for a new measurement
            self._reset_plots()

            self.log_panel.append("Starting measurement")

            # --------------------------------------------------
            # Validate wavelength limits
            # --------------------------------------------------
            nm_lim = (params.wl_start, params.wl_stop)
            nm_lim = nm_lim_ok(nm_lim, params.calibration_measurement, debug=False)

            # --------------------------------------------------
            # Connect instruments
            # Match the legacy GUI behavior for now
            # --------------------------------------------------
            self.controller.connect_instruments(
                mono=None,
                smu=None,
                N=500,
                nplc=0.01,
                interval=0.002,
                simulate=self.session_panel.sim_checkbox.isChecked(),
                simulate_profile=self.session_panel.sim_profile_combo.currentText(),
            )

            # --------------------------------------------------
            # Load calibration
            # --------------------------------------------------
            df_incbeamcurr, _df_ref = open_calibration(
                nm_lim,
                params.calibration_measurement,
                debug=False,
            )

            # --------------------------------------------------
            # Start measurement
            # NOTE:
            # ui_dispatch is left as None for now.
            # Thread-safe Qt dispatch will be the next step.
            # --------------------------------------------------
            
            self.controller.run_measurement_async(
                params=params,
                df_incbeamcurr=df_incbeamcurr,
                nm_lim=nm_lim,

                # NEW: bias parameters
                bias_enabled=config.bias_enabled,
                bias_voltage=config.bias_voltage,

                ui_dispatch=None,
                callbacks={
                    "on_live_update": self.on_live_update,
                    "on_status": self.on_status,
                    "on_point_acquired": self.on_point_acquired,
                    "on_done": self.on_measurement_done,
                    "on_error": self.on_measurement_error,
                    "on_finished": self.on_measurement_finished,
                },
            )

            
        except Exception as exc:
            self.log_panel.append(f"ERROR: {exc}")


    def _on_stop(self):

        self.controller.stop_measurement()

        self.log_panel.append("Stop requested")


    def _on_save(self):
        """
        Save the last completed measurement manually.
        """

        # Manual save only makes sense after a successful measurement
        if self._last_result_df is None:
            self.log_panel.append("No completed measurement available to save.")
            return

        try:
            # Use current GUI values for naming
            sample_name = self.metadata_panel.sample_name_edit.text().strip() or "sample"
            user_name = self.session_panel.get_user().strip() or "user"

            # Build the target directory:
            # <measurements_dir>/<user_name>
            measurements_dir = Path(get_paths()["measurements_dir"])

            # Create date-based folder: YYMMDD_EQE
            date_str = datetime.now().strftime("%y%m%d")
            session_dir = measurements_dir / user_name / f"{date_str}_EQE"
            session_dir.mkdir(parents=True, exist_ok=True)

            # For now:
            # - normal EQE measurement
            # - no raw save
            # - no reference dataframe needed
            fp = save_data(
                df=self._last_result_df,
                df_ref=None,
                sample_name=sample_name,
                user_dir=session_dir,
                calibration_measurement=False,
                save_raw_data=False,
                fig=self.eqe_plot_widget.figure,
            )

            self.log_panel.append(f"Saved: {fp}")

        except Exception as exc:
            self.log_panel.append(f"Save failed: {exc}")


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


    def on_live_update(self, *args, **kwargs):
        """
        Handle live status updates from the backend.

        Repetitive per-point measurement messages are no longer shown in the log,
        because the plots and live numeric panel already display that information.

        The log is reserved for higher-level status messages.
        """

        # Legacy backend currently sends a single status string
        if len(args) == 1 and isinstance(args[0], str):
            message = args[0].replace("IPCE", "EQE")

            # Skip repetitive per-point measurement messages
            if message.startswith("Wavelength = "):
                return
            if message.startswith("Integrated current = "):
                return

            self.log_panel.append(message)
            return

        # Fallback for unexpected payloads
        self.log_panel.append(f"Unhandled live_update payload: args={args}, kwargs={kwargs}")


    def on_point_acquired(self, *args, **kwargs):
        """
        Called when a wavelength point is finished.

        Preferred payload from the measurement engine:
        - wavelength
        - eqe
        - integrated_current

        A fallback for legacy keys is kept temporarily.
        """

        # ----------------------------------------
        # Case 1: new clean keyword payload
        # ----------------------------------------
        if kwargs and "wavelength" in kwargs and "eqe" in kwargs:
            wavelength = kwargs["wavelength"]
            eqe = kwargs["eqe"]
            integrated_current = kwargs.get("integrated_current", 0.0)

        # ----------------------------------------
        # Case 2: temporary legacy fallback
        # ----------------------------------------
        elif kwargs:
            wavelength = kwargs.get("nm", kwargs.get("wavelength"))
            eqe = kwargs.get("IPCE", kwargs.get("ipce", kwargs.get("eqe")))
            integrated_current = kwargs.get(
                "int_curr",
                kwargs.get("integrated_current", kwargs.get("jsc", 0.0))
            )

        # ----------------------------------------
        # Case 3: positional payload
        # ----------------------------------------
        elif len(args) == 3:
            wavelength, eqe, integrated_current = args

        else:
            self.log_panel.append(
                f"Unhandled point_acquired payload: args={args}, kwargs={kwargs}"
            )
            return

        # Guard against missing values
        if wavelength is None or eqe is None:
            self.log_panel.append(
                f"Incomplete point_acquired payload: args={args}, kwargs={kwargs}"
            )
            return

        # Forward numeric update safely to the GUI thread
        cell_current = kwargs.get("cell_current", 0.0) if kwargs else 0.0
        ref_current = kwargs.get("ref_current", 0.0) if kwargs else 0.0

        self.live_numeric_signal.emit(
            float(eqe),
            float(cell_current),
            float(ref_current),
        )

        # Forward the plot update safely to the GUI thread
        self.point_acquired_signal.emit(
            float(wavelength),
            float(eqe),
            float(integrated_current),
        )


    def _handle_point_acquired_gui(self, wavelength, eqe, integrated_current):
        """
        Handle point updates in the GUI thread.

        This method is connected to a Qt signal so that the plot widgets
        are updated safely from the main thread.
        """

        # Store data for plotting
        self._wavelengths.append(float(wavelength))
        self._eqe_values.append(float(eqe))
        self._current_values.append(float(integrated_current))

        # Update plots
        self.eqe_plot_widget.update_curve(
            self._wavelengths,
            self._eqe_values,
        )

        self.current_plot_widget.update_curve(
            self._wavelengths,
            self._current_values,
        )


    def _handle_live_numeric_gui(self, eqe, cell_current, ref_current):
        """
        Update the live numeric panel in the GUI thread.
        """

        self.live_numeric_panel.update_values(
            float(eqe),
            float(cell_current),
            float(ref_current),
        )


    def _reset_plots(self):
        """
        Clear stored data and reset plot widgets before starting
        a new measurement.
        """

        self._wavelengths = []
        self._eqe_values = []
        self._current_values = []

        # reset plots
        self.eqe_plot_widget.update_curve([], [])
        self.current_plot_widget.update_curve([], [])


    def on_status(self, message):
        """
        Controller status messages.
        """

        self.log_panel.append(message)


    def on_measurement_done(self, df_result):
        """
        Called when the measurement finishes successfully.
        """

        # Store the completed dataframe for later manual save
        self._last_result_df = df_result

        self.log_panel.append("Measurement done")


    def on_measurement_error(self, exc):
        """
        Called when the measurement worker raises an exception.
        """

        self.log_panel.append(f"ERROR: {exc}")


    def on_measurement_finished(self):
        """
        Called when the measurement worker finishes, whether successfully
        or after an error.
        """

        self.log_panel.append("Measurement finished")


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

        self.eqe_plot_widget = EQEPlotWidget()

        self.eqe_plot_group.layout().addWidget(self.eqe_plot_widget)

        live_layout.addWidget(self.eqe_plot_group)

        # Integrated current plot
        self.current_plot_group = QGroupBox("Integrated Current")
        self.current_plot_group.setLayout(QVBoxLayout())

        self.current_plot_widget = IntegratedCurrentPlotWidget()

        self.current_plot_group.layout().addWidget(self.current_plot_widget)

        live_layout.addWidget(self.current_plot_group)

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


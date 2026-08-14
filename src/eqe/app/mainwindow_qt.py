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
    SECTION_WAVELENGTH,
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
from eqe.app.widgets.wavelength_setting_panel import WavelengthSettingPanel
from eqe.app.widgets.calibration_panel import CalibrationPanel
from eqe.app.widgets.log_panel import LogPanel
from eqe.app.widgets.bias_panel import BiasPanel
from eqe.app.widgets.live_numeric_panel import LiveNumericPanel
from eqe.app.widgets.eqe_plot_widget import EQEPlotWidget
from eqe.app.qt_models import LIVE_MODES
from eqe.io.data_io import save_data
from eqe.io.paths import get_paths, create_user_directory



class MainWindow(QMainWindow):

    # Signal used to forward point updates safely to the GUI thread
    point_acquired_signal = Signal(float, float, float)

    # Signal used to update the live numeric panel safely in the GUI thread
    live_numeric_signal = Signal(float, float, float, float)

    # Signal used to forward a calibration-measurement point (wavelength,
    # reference current, cell current -- no EQE) safely to the GUI thread
    calibration_point_signal = Signal(float, float, float)

    # Generic dispatch signal: marshals an arbitrary measurement callback
    # (with its args/kwargs) from the worker thread onto the GUI thread via
    # Qt's queued cross-thread delivery. Passed to the controller as
    # `ui_dispatch` so callbacks that touch widgets directly (log panel,
    # etc.) never run outside the GUI thread.
    _dispatch_signal = Signal(object, object, object)

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
        self.calibration_point_signal.connect(self._handle_calibration_point_gui)
        self._dispatch_signal.connect(self._run_on_gui_thread, Qt.QueuedConnection)

        # --------------------------------------------------
        # 2. Map section identifiers to GUI widgets
        # --------------------------------------------------
        self.section_widgets = {
            SECTION_METADATA: self.metadata_group,
            SECTION_SCAN: self.scan_group,
            SECTION_WAVELENGTH: self.wavelength_group,
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
        self.eqe_plot_widget.update_curves(
            [400, 500, 600, 700, 800],
            [20, 45, 60, 50, 30],
            [1.5, 5.2, 12.3, 15.8, 17.1],
        )

        # storage for measurement data during scans
        self._wavelengths = []
        self._eqe_values = []
        self._current_values = []
        # storage for calibration-measurement data (raw currents, no EQE)
        self._calib_ref_currents = []
        self._calib_cell_currents = []

        # Last completed measurement dataframe, used by manual Save
        self._last_result_df = None
        # Si71889 (external calibration cell) IPCE curve and calibration
        # flag from the run that produced _last_result_df, needed at save
        # time for a calibration measurement (see
        # _on_start()/_save_last_result()).
        self._last_df_ref = None
        self._active_calibration_measurement = False

        # measurement controller
        self.controller = MeasurementController()

        # Apply a wavelength change live if a live measurement is
        # currently running (see controller.set_live_wavelength()).
        self.wavelength_setting_panel.wavelength_changed.connect(
            self.controller.set_live_wavelength
        )

        # Calibration measurements are a developer-only feature for now --
        # hidden (and unchecked, so a stale checked state can't linger)
        # unless the User field identifies a developer, same gating as
        # Simulation and the Lock-in modes.
        self.session_panel.user_changed.connect(self._update_calibration_visibility)
        self._update_calibration_visibility(self.session_panel.get_user())

        # Pre-fill the sample name with the Si71889 (external calibration
        # cell) identifier when starting a calibration measurement.
        self.calibration_panel.calibration_measurement_toggled.connect(
            self._on_calibration_toggled
        )


    def _update_calibration_visibility(self, user_text=None):
        """
        Re-run the mode-based visibility rules on a user-field change,
        since the Calibration / Saving panel's visibility depends on both
        mode and developer-user status (see update_mode_visibility()) and
        must stay correct regardless of which one just changed.
        """

        self.update_mode_visibility(self.session_panel.get_mode())

    def _on_calibration_toggled(self, checked):
        """
        Pre-fill the sample name with the Si71889 (external calibration
        cell) identifier when "Calibration measurement" is checked.
        """

        if checked:
            self.metadata_panel.sample_name_edit.setText("Si71889")

    def _on_mode_changed(self, mode):
        """
        Called when the measurement mode changes.
        """

        print(f"Mode changed to: {mode}")

        # Update panel visibility
        self.update_mode_visibility(mode)

        # Update plot labels for scan/live modes
        self._configure_plots_for_mode(mode)


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
            mode = self.session_panel.get_mode()
            is_live = mode in LIVE_MODES

            # --------------------------------------------------
            # Wavelength(s): live modes measure at a single fixed
            # wavelength (Wavelength setting panel), not a swept range
            # (Spectral Scan panel) -- there is no "stop"/"step" for a
            # live mode, so building/validating a (start, stop) range
            # for it doesn't apply and must not be attempted.
            # --------------------------------------------------
            if is_live:
                live_wavelength = self.wavelength_setting_panel.get_wavelength()
                wl_start = int(live_wavelength)
                wl_stop = wl_start
                interval = 1  # unused by the live-monitoring path
            else:
                wl_start = int(self.scan_panel.start_nm_spin.value())
                wl_stop = int(self.scan_panel.stop_nm_spin.value())
                interval = int(self.scan_panel.step_nm_spin.value())

            # Calibration measurement is a scan-only, developer-only
            # concept (records raw currents to produce a new incident-beam
            # calibration file); the checkbox is hidden for live modes
            # (SECTION_CALIBRATION) and for non-developer users, but its
            # state isn't reset on mode switch, so ignore it explicitly
            # here too rather than relying on visibility alone.
            is_calibration = (
                not is_live
                and self.session_panel.is_developer_user()
                and self.calibration_panel.get_values()["calibration_measurement"]
            )

            # --------------------------------------------------
            # Build legacy MeasurementParams object
            # --------------------------------------------------
            params = MeasurementParams(
                user=self.session_panel.get_user().strip(),
                sample=self.metadata_panel.sample_name_edit.text().strip(),
                wl_start=wl_start,
                wl_stop=wl_stop,
                interval=interval,
                calibration_measurement=is_calibration,
                show_raw=False,
                save_raw=False,
                stop_when_zero=False,
                autosave=self.session_panel.get_autosave(),
            )

            params.mode = mode
            self._active_mode = mode
            self._active_calibration_measurement = is_calibration
            self._configure_plots_for_mode(self._active_mode, is_calibration=is_calibration)

            # Reset plots for a new measurement
            self._reset_plots()

            self.log_panel.append("Starting measurement")

            # --------------------------------------------------
            # Validate wavelength(s)
            # --------------------------------------------------
            if is_live:
                if not (350.0 <= live_wavelength <= 1170.0):
                    raise ValueError(
                        f"Invalid wavelength: {live_wavelength:.1f} nm. "
                        "Must be between 350 and 1170 nm."
                    )
                # Load calibration across the whole valid range so the
                # wavelength can be changed freely while live monitoring
                # is running (see controller.set_live_wavelength()),
                # not just near the starting value.
                nm_lim = (350, 1170)
                # Sync the initial live-target wavelength before the
                # measurement thread starts polling for changes.
                self.controller.set_live_wavelength(live_wavelength)
            else:
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
            df_incbeamcurr, df_ref = open_calibration(
                nm_lim,
                params.calibration_measurement,
                debug=False,
            )

            # Remembered for _save_last_result(): a calibration
            # measurement's save path needs the Si71889 (external
            # calibration cell) IPCE curve (df_ref) to compute the new
            # incident-beam calibration
            # file, and must use the same calibration_measurement flag
            # the run was actually started with, not a possibly-changed
            # checkbox state at save time.
            self._last_df_ref = df_ref
            self._active_calibration_measurement = params.calibration_measurement

            # --------------------------------------------------
            # Start measurement
            # --------------------------------------------------

            self.controller.run_measurement_async(
                params=params,
                df_incbeamcurr=df_incbeamcurr,
                nm_lim=nm_lim,
                bias_enabled=config.bias_enabled,
                bias_voltage=config.bias_voltage,
                compliance_current=config.compliance_current,
                direction=config.direction,
                ui_dispatch=self._dispatch_to_gui,
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
        Save the last completed measurement manually (Save button).
        """
        self._save_last_result()

    def _save_last_result(self):
        """
        Save the last completed measurement. Shared by the manual Save
        button and autosave-on-completion (see on_measurement_done()).
        """

        if self._last_result_df is None:
            self.log_panel.append("No completed measurement available to save.")
            return

        try:
            # Use current GUI values for naming and for the saved file's
            # metadata header (used hardware, sample/metadata, scan
            # conditions, bias). Live modes measure at a single wavelength
            # that can itself change over time -- it's saved as data (see
            # perform_live_monitoring()'s "Wavelength (nm)" column), not a
            # fixed setting, so there's no "spectral scan conditions" to
            # report in the header for them.
            metadata = self.metadata_panel.get_values()
            is_live = getattr(self, "_active_mode", None) in LIVE_MODES
            scan = None if is_live else self.scan_panel.get_values()
            bias = self.bias_panel.get_values()

            sample_name = metadata["sample_name"] or "sample"
            user_name = self.session_panel.get_user().strip() or "user"

            # Build the target directory via the single shared
            # implementation (io/paths.py), so manual save and any future
            # autosave land in the same place for a given day/user.
            measurements_dir = Path(get_paths()["measurements_dir"])
            session_dir = create_user_directory(measurements_dir, user_name)

            fp = save_data(
                df=self._last_result_df,
                df_ref=self._last_df_ref,
                sample_name=sample_name,
                user_dir=session_dir,
                calibration_measurement=self._active_calibration_measurement,
                fig=self.eqe_plot_widget.figure,
                hardware=self.controller.hardware,
                metadata=metadata,
                scan=scan,
                bias=bias,
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
            compliance_current=bias["compliance_current"],
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
        if wavelength is None:
            self.log_panel.append(
                f"Incomplete point_acquired payload: args={args}, kwargs={kwargs}"
            )
            return

        cell_current = kwargs.get("cell_current", 0.0) if kwargs else 0.0
        ref_current = kwargs.get("ref_current", 0.0) if kwargs else 0.0

        if eqe is None:
            # Expected during a calibration measurement: EQE isn't
            # computed, only raw currents -- plot/readout those instead
            # (see _handle_calibration_point_gui()).
            self.calibration_point_signal.emit(
                float(wavelength), float(ref_current), float(cell_current)
            )
            return

        # Forward numeric update safely to the GUI thread
        time_s = kwargs.get("time_s", None) if kwargs else None
        fixed_wavelength_nm = kwargs.get("fixed_wavelength_nm", None) if kwargs else None

        self.live_numeric_signal.emit(
            float(eqe),
            float(cell_current),
            float(ref_current),
            float(integrated_current) if integrated_current is not None else 0.0,
        )

        # Forward the plot update safely to the GUI thread

        if getattr(self, "_active_mode", None) in LIVE_MODES:
            x_value = float(time_s)
            y2_value = float(cell_current)
        else:
            x_value = float(wavelength)
            y2_value = float(integrated_current)

        self.point_acquired_signal.emit(
            x_value,
            float(eqe),
            y2_value,
        )


    def _run_on_gui_thread(self, callback, args, kwargs):
        """
        Slot for `_dispatch_signal`. Runs on the GUI thread (queued
        connection), so it's safe for `callback` to touch widgets directly.
        """
        callback(*args, **kwargs)

    def _dispatch_to_gui(self, callback, *args, **kwargs):
        """
        `ui_dispatch` passed to the controller: marshals any measurement
        callback onto the GUI thread instead of running it on the worker
        thread. Safe to call from any thread.
        """
        self._dispatch_signal.emit(callback, args, kwargs)

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

        # Update plot (EQE on the left axis, integrated/cell current on
        # the right, twin axis -- see EQEPlotWidget)
        self.eqe_plot_widget.update_curves(
            self._wavelengths,
            self._eqe_values,
            self._current_values,
        )


    def _handle_live_numeric_gui(self, eqe, cell_current, ref_current, integrated_current):
        """
        Update the live numeric panel in the GUI thread.
        """

        self.live_numeric_panel.update_values(
            float(eqe),
            float(cell_current),
            float(ref_current),
            float(integrated_current),
        )

    def _handle_calibration_point_gui(self, wavelength, ref_current, cell_current):
        """
        Handle a calibration-measurement point in the GUI thread: no EQE
        is computed, so plot/readout the raw reference/cell currents
        instead (see on_point_acquired() and _configure_plots_for_mode()).
        """

        self._wavelengths.append(float(wavelength))
        self._calib_ref_currents.append(float(ref_current))
        self._calib_cell_currents.append(float(cell_current))

        # "Live currents": reference current on the left axis, test-cell
        # current on the right -- same widget/axes as EQE/integrated
        # current, just different content for a calibration measurement.
        self.eqe_plot_widget.update_curves(
            self._wavelengths,
            self._calib_ref_currents,
            self._calib_cell_currents,
        )

        # EQE/integrated-current rows are hidden for a calibration
        # measurement (see _configure_plots_for_mode()); pass 0.0
        # placeholders for them.
        self.live_numeric_panel.update_values(0.0, cell_current, ref_current, 0.0)


    def _reset_plots(self):
        """
        Clear stored data and reset plot widgets before starting
        a new measurement.
        """

        self._wavelengths = []
        self._eqe_values = []
        self._current_values = []
        self._calib_ref_currents = []
        self._calib_cell_currents = []

        # reset plot
        self.eqe_plot_widget.update_curves([], [], [])


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

        if self.session_panel.get_autosave():
            self._save_last_result()


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

        # Calibration measurements are developer-only (see
        # _update_calibration_visibility()), on top of the mode-based
        # SECTION_CALIBRATION rule above -- combine both constraints here
        # rather than in two independent places, since this method is
        # re-run on both a mode change and a user-field change and must
        # give the same answer either way.
        is_dev = self.session_panel.is_developer_user()
        self.calibration_group.setVisible(sections.get(SECTION_CALIBRATION, False) and is_dev)
        if not is_dev:
            self.calibration_panel.calibration_measurement_checkbox.setChecked(False)

        # Integrated current is only meaningful over a wavelength sweep;
        # it's structurally always 0 during live monitoring at a single
        # fixed wavelength, so hide it there rather than show a
        # permanent, confusing "0.00".
        self.live_numeric_panel.set_integrated_current_visible(mode not in LIVE_MODES)


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

        # Wavelength setting (live modes only -- a single fixed
        # wavelength, not a sweep range; see SECTION_WAVELENGTH)
        self.wavelength_group = QGroupBox("Wavelength setting")
        self.wavelength_group.setLayout(QVBoxLayout())

        self.wavelength_setting_panel = WavelengthSettingPanel()
        self.wavelength_group.layout().addWidget(self.wavelength_setting_panel)

        setup_layout.addWidget(self.wavelength_group)

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
        self.calibration_panel = CalibrationPanel()
        self.calibration_group.layout().addWidget(self.calibration_panel)
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

        # Live EQE plot (EQE on the left axis, integrated/cell current on
        # a twin right-hand axis -- previously two separate stacked plots)
        self.eqe_plot_group = QGroupBox("Live EQE")
        self.eqe_plot_group.setLayout(QVBoxLayout())

        self.eqe_plot_widget = EQEPlotWidget()

        self.eqe_plot_group.layout().addWidget(self.eqe_plot_widget)

        live_layout.addWidget(self.eqe_plot_group)

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

    def closeEvent(self, event):
        if self.controller.is_measuring:
            self.controller.stop_measurement()
            worker = self.controller._measurement_thread
            if worker is not None:
                worker.join(timeout=3.0)

                if worker.is_alive():
                    # The worker didn't stop in time. It may still be using
                    # the serial/VISA connection -- including its own
                    # finally-block cleanup, which already returns the
                    # monochromator to 550 nm (see measurement_engine.py).
                    # Calling mono.goto_nm() here too would race with that
                    # from a second thread on the same connection, so skip
                    # it and close anyway; the worker is a daemon thread
                    # and will be terminated when the process exits.
                    self.log_panel.append(
                        "WARNING: Measurement did not stop within 3s; "
                        "closing without waiting further. Instrument "
                        "cleanup may still be in progress."
                    )
                    event.accept()
                    return

        if self.controller.mono is not None:
            try:
                self.log_panel.append("Returning monochromator to 550 nm...")
                self.controller.mono.goto_nm(550)
            except Exception:
                pass

        event.accept()

    def _configure_plots_for_mode(self, mode, is_calibration=False):
        """
        Configure plot labels and Live Readout row visibility according
        to the selected measurement mode (and, for scan modes, whether
        it's a calibration measurement).
        """

        if is_calibration:
            # No EQE is computed for a calibration measurement -- show
            # the raw currents instead. Label the two axes by which
            # physical cell each one actually is -- "reference cell"
            # alone is ambiguous between the internal cell (always read
            # via reference_meter) and the external Si71889 calibration
            # cell (installed in the sample position only during a
            # calibration run, read via test_meter), so never mix them up.
            self.eqe_plot_widget.ax.set_xlabel("Wavelength (nm)")
            self.eqe_plot_widget.ax.set_ylabel("Internal reference cell current (A)")
            self.eqe_plot_widget.ax2.set_ylabel("Si71889 reference cell current (A)")
            self.eqe_plot_widget.ax.set_title("Live currents")
            self.live_numeric_panel.set_eqe_visible(False)
            self.live_numeric_panel.set_integrated_current_visible(False)

        elif mode in LIVE_MODES:
            self.eqe_plot_widget.ax.set_xlabel("Time (s)")
            self.eqe_plot_widget.ax.set_ylabel("EQE (%)")
            self.eqe_plot_widget.ax2.set_ylabel("Cell current (A)")
            self.eqe_plot_widget.ax.set_title("Live EQE / Cell Current vs Time")
            self.live_numeric_panel.set_eqe_visible(True)
            self.live_numeric_panel.set_integrated_current_visible(False)

        else:
            self.eqe_plot_widget.ax.set_xlabel("Wavelength (nm)")
            self.eqe_plot_widget.ax.set_ylabel("EQE (%)")
            self.eqe_plot_widget.ax2.set_ylabel("Integrated current (mA/cm²)")
            self.eqe_plot_widget.ax.set_title("EQE Spectrum / Integrated Current")
            self.live_numeric_panel.set_eqe_visible(True)
            self.live_numeric_panel.set_integrated_current_visible(True)

        self.eqe_plot_widget.canvas.draw_idle()
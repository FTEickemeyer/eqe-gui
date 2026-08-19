"""
Mismatch Factor (MMF) dialog.

Lets a user pick a DUT EQE file (defaulting to the most recently measured
one this session, if any), a reference-cell EQE file and a lamp spectrum
file (both defaulting per analysis/mmf.py's default_*() helpers, from
paths.mmf_data_dir's two fixed subfolders), run the MMF calculation, see
the result plotted, and save it.

Non-modal (shown via show(), not exec()) so the main window stays usable
while this is open -- see mainwindow_qt.py's _on_mmf(), which keeps a
single instance alive and raises it rather than opening a second one.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFileDialog,
    QGroupBox,
)

from eqe.analysis.mmf import (
    compute_mmf,
    default_lamp_spectrum_file,
    default_ref_cell_file,
    extract_sample_name,
    get_mmf_dirs,
    list_csv_files,
)
from eqe.app.widgets.mmf_plot_widget import MMFPlotWidget
from eqe.io.data_io import save_mmf_result
from eqe.io.paths import create_user_directory, get_paths


class MMFDialog(QDialog):
    def __init__(self, parent=None, default_dut_path=None, get_user=None):
        super().__init__(parent)

        self.setWindowTitle("Mismatch Factor (MMF)")
        self.resize(900, 700)

        # Zero-arg callable returning the current session's user string,
        # used only at Save time to pick the same per-user dated folder
        # every other save goes into (see io/paths.py's
        # create_user_directory()). Defaults to "" so this dialog is also
        # constructible/testable standalone, without a MainWindow.
        self._get_user = get_user or (lambda: "")

        self._last_result = None

        self._build_ui(default_dut_path)

    # ------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------

    def _build_ui(self, default_dut_path):
        layout = QVBoxLayout()
        self.setLayout(layout)

        files_group = QGroupBox("Files")
        files_layout = QFormLayout()
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)

        # --------------------------------------------------
        # DUT EQE file -- free browse, defaults to the most recently
        # saved EQE-mode measurement this session (if any).
        # --------------------------------------------------
        dut_row = QHBoxLayout()
        self.dut_edit = QLineEdit()
        self.dut_edit.setPlaceholderText("no EQE file selected")
        if default_dut_path:
            self.dut_edit.setText(str(default_dut_path))
        dut_browse = QPushButton("Browse...")
        dut_browse.clicked.connect(self._browse_dut_file)
        dut_row.addWidget(self.dut_edit)
        dut_row.addWidget(dut_browse)
        files_layout.addRow("DUT EQE file", dut_row)

        # --------------------------------------------------
        # Reference-cell EQE file -- picked from mmf_data_dir's
        # EQE_ref_cells/ subfolder, defaulting to the most recent one.
        # --------------------------------------------------
        self.ref_combo = QComboBox()
        files_layout.addRow("Reference cell EQE file", self.ref_combo)

        # --------------------------------------------------
        # Lamp spectrum file -- picked from mmf_data_dir's
        # PF_lamp_spectra/ subfolder, defaulting to the one with
        # "OrielIV" in its filename.
        # --------------------------------------------------
        self.lamp_combo = QComboBox()
        files_layout.addRow("Lamp spectrum file", self.lamp_combo)

        self._populate_file_combos()

        # --------------------------------------------------
        # Run / Save / Close
        # --------------------------------------------------
        button_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self._on_run)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setEnabled(False)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.save_button)
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        # --------------------------------------------------
        # Status / results
        # --------------------------------------------------
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        results_group = QGroupBox("Results")
        results_layout = QFormLayout()
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        self.mmf_label = QLabel("—")
        results_layout.addRow("MMF", self.mmf_label)

        self.jsc_dut_label = QLabel("—")
        results_layout.addRow("Integrated current — DUT @ AM1.5 (mA/cm²)", self.jsc_dut_label)

        self.jsc_details_label = QLabel("—")
        self.jsc_details_label.setWordWrap(True)
        results_layout.addRow("Details", self.jsc_details_label)

        # --------------------------------------------------
        # Plot
        # --------------------------------------------------
        self.plot_widget = MMFPlotWidget()
        layout.addWidget(self.plot_widget)

    def _populate_file_combos(self):
        dirs = get_mmf_dirs()

        ref_files = list_csv_files(dirs["ref_cells_dir"])
        self.ref_combo.clear()
        for fp in ref_files:
            self.ref_combo.addItem(fp.name, str(fp))
        default_ref = default_ref_cell_file(ref_files)
        if default_ref is not None:
            idx = self.ref_combo.findData(str(default_ref))
            if idx >= 0:
                self.ref_combo.setCurrentIndex(idx)

        lamp_files = list_csv_files(dirs["lamp_spectra_dir"])
        self.lamp_combo.clear()
        for fp in lamp_files:
            self.lamp_combo.addItem(fp.name, str(fp))
        default_lamp = default_lamp_spectrum_file(lamp_files)
        if default_lamp is not None:
            idx = self.lamp_combo.findData(str(default_lamp))
            if idx >= 0:
                self.lamp_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def _browse_dut_file(self):
        start_dir = str(get_paths()["measurements_dir"])
        fp, _ = QFileDialog.getOpenFileName(
            self, "Select DUT EQE file", start_dir, "CSV files (*.csv)"
        )
        if fp:
            self.dut_edit.setText(fp)

    def _on_run(self):
        self.save_button.setEnabled(False)
        self._last_result = None

        dut_path = self.dut_edit.text().strip()
        if not dut_path:
            self.status_label.setText("Select a DUT EQE file first.")
            return

        ref_path = self.ref_combo.currentData()
        lamp_path = self.lamp_combo.currentData()
        if not ref_path:
            self.status_label.setText(
                "No reference-cell EQE file available -- add one to "
                f"{get_mmf_dirs()['ref_cells_dir']}."
            )
            return
        if not lamp_path:
            self.status_label.setText(
                "No lamp spectrum file available -- add one to "
                f"{get_mmf_dirs()['lamp_spectra_dir']}."
            )
            return

        try:
            result = compute_mmf(dut_path, ref_path, lamp_path)
        except Exception as exc:
            self.status_label.setText(f"MMF calculation failed: {exc}")
            self.plot_widget.clear()
            self.mmf_label.setText("—")
            self.jsc_dut_label.setText("—")
            self.jsc_details_label.setText("—")
            return

        self._last_result = result

        self.plot_widget.update_curves(
            result.wavelengths_nm,
            result.dut_eqe_pct,
            result.ref_eqe_pct,
            result.lamp_pf_normalized,
            result.am15_pf_normalized,
            result.left_nm,
            result.right_nm,
        )

        self.mmf_label.setText(f"{result.mmf:.4f}")
        self.jsc_dut_label.setText(f"{result.jsc_dut_am15:.3f}")
        self.jsc_details_label.setText(
            f"DUT @ simulator: {result.jsc_dut_sim:.3f} mA/cm² · "
            f"Reference @ AM1.5: {result.jsc_ref_am15:.3f} mA/cm² · "
            f"Reference @ simulator: {result.jsc_ref_sim:.3f} mA/cm² · "
            f"Integration range: {result.left_nm:.0f}–{result.right_nm:.0f} nm"
        )

        self.status_label.setText("")
        self.save_button.setEnabled(True)

    def _on_save(self):
        if self._last_result is None:
            self.status_label.setText("Run a calculation before saving.")
            return

        try:
            cell_name = extract_sample_name(self._last_result.dut_file)
            user_name = (self._get_user() or "").strip() or "user"
            measurements_dir = Path(get_paths()["measurements_dir"])
            session_dir = create_user_directory(measurements_dir, user_name)

            paths = save_mmf_result(
                self._last_result,
                user_dir=session_dir,
                cell_name=cell_name,
                fig=self.plot_widget.figure,
            )
        except Exception as exc:
            self.status_label.setText(f"Save failed: {exc}")
            return

        self.status_label.setText(f"Saved: {paths['summary']}")

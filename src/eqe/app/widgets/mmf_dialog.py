"""
Mismatch Factor (MMF) dialog.

Lets a user pick a DUT EQE file, a reference-cell EQE file and a lamp
spectrum file (both defaulting per analysis/mmf.py's default_*() helpers,
from paths.mmf_data_dir's two fixed subfolders), run the MMF calculation,
see the result plotted, and save it.

Non-modal (shown via show(), not exec()) so the main window stays usable
while this is open -- see mainwindow_qt.py's _on_mmf(), which keeps a
single instance alive and raises it rather than opening a second one,
but always calls set_dut_file() on it first so the DUT field tracks
whatever the most recently measured (saved) EQE scan is -- empty if
nothing's been measured yet -- even on a dialog that's been open for a
while.
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
from eqe.io.paths import get_paths


class MMFDialog(QDialog):
    def __init__(self, parent=None, default_dut_path=None):
        super().__init__(parent)

        self.setWindowTitle("Mismatch Factor (MMF)")
        self.resize(900, 700)

        self._last_result = None

        self._build_ui()
        self.set_dut_file(default_dut_path)

    # ------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        files_group = QGroupBox("Files")
        files_layout = QFormLayout()
        files_group.setLayout(files_layout)
        layout.addWidget(files_group)

        # --------------------------------------------------
        # DUT EQE file -- free browse; kept in sync with the most
        # recently measured (saved) EQE scan by set_dut_file(), called
        # both here (construction) and by mainwindow_qt.py's _on_mmf()
        # on every later open too.
        # --------------------------------------------------
        dut_row = QHBoxLayout()
        self.dut_edit = QLineEdit()
        self.dut_edit.setPlaceholderText("no EQE file selected")
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

    def set_dut_file(self, path):
        """
        Set (or clear, if `path` is None/empty) the DUT EQE file field --
        used both at construction and, importantly, by
        mainwindow_qt.py's _on_mmf() on every open of an already-existing
        dialog, so the default always tracks the most recently measured
        (saved) EQE scan rather than freezing at whatever it was the
        first time this dialog happened to be created.
        """
        self.dut_edit.setText(str(path) if path else "")

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
            dut_label=extract_sample_name(result.dut_file),
        )

        self.mmf_label.setText(f"{result.mmf:.4f}")
        self.jsc_dut_label.setText(f"{result.jsc_dut_am15:.3f}")

        self.status_label.setText("")
        self.save_button.setEnabled(True)

    def _on_save(self):
        if self._last_result is None:
            self.status_label.setText("Run a calculation before saving.")
            return

        try:
            cell_name = extract_sample_name(self._last_result.dut_file)
            # Saved next to the DUT EQE file itself, not a fresh per-user
            # dated folder -- keeps an MMF result alongside the specific
            # scan it was computed from, wherever that happens to live
            # (this session's default folder, or an older one Browsed to).
            dut_dir = Path(self._last_result.dut_file).resolve().parent

            paths = save_mmf_result(
                self._last_result,
                output_dir=dut_dir,
                cell_name=cell_name,
                fig=self.plot_widget.figure,
            )
        except Exception as exc:
            self.status_label.setText(f"Save failed: {exc}")
            return

        self.status_label.setText(f"Saved: {paths['summary']}")

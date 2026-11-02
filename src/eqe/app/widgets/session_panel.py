"""
Session / Run Control panel.

Contains:
- User field
- Admin mode checkbox (PIN-gated -- see _on_admin_toggled())
- Measurement mode selector
- Simulation controls
- Start / Stop / Save buttons

This panel emits signals so the MainWindow can react without tightly
coupling logic into the widget.
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QInputDialog,
    QMessageBox,
)
from PySide6.QtCore import Signal

# Import mode labels from the shared model definition
from eqe.app.qt_models import MODE_LABELS, LOCKIN_EQE_BG, LOCKIN_LIVE_EQE
from eqe.config.load_config import load_config


class SessionPanel(QWidget):
    """
    Top control panel for the measurement session.
    """

    # Signals emitted to the outside world (MainWindow)
    mode_changed = Signal(str)
    start_clicked = Signal()
    stop_clicked = Signal()
    save_clicked = Signal()
    user_changed = Signal(str)
    # Emitted when the Shutter checkbox is toggled by hand (see
    # set_shutter_controls_enabled()/set_shutter_checked(), which change
    # it programmatically via blockSignals and so do NOT re-emit this).
    shutter_toggled = Signal(bool)
    # Emitted whenever admin mode is unlocked or relocked (see
    # _on_admin_toggled()) -- not tied to the user field at all, so a
    # listener should treat this as an independent trigger to re-check
    # is_admin(), not something derivable from user_changed.
    admin_changed = Signal(bool)
    mmf_clicked = Signal()
    about_clicked = Signal()

    def __init__(self):
        super().__init__()

        # Not tied to any particular person's name -- unlocked for the
        # rest of this session by entering the correct PIN (see
        # _on_admin_toggled()), relocked on uncheck or a fresh launch.
        # Never persisted across sessions.
        self._admin_unlocked = False

        self._build_ui()

    def _build_ui(self):
        """
        Build the panel layout.
        """

        layout = QHBoxLayout()
        self.setLayout(layout)

        # --------------------------------------------------
        # User field
        # --------------------------------------------------

        layout.addWidget(QLabel("User"))

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("user name")
        layout.addWidget(self.user_edit)

        self.user_edit.textChanged.connect(self.user_changed.emit)

        # --------------------------------------------------
        # Admin mode (PIN-gated -- see _on_admin_toggled())
        # --------------------------------------------------

        self.admin_checkbox = QCheckBox("Admin")
        layout.addWidget(self.admin_checkbox)
        self.admin_checkbox.toggled.connect(self._on_admin_toggled)

        # --------------------------------------------------
        # Measurement mode selector
        # --------------------------------------------------

        layout.addWidget(QLabel("Mode"))

        self.mode_combo = QComboBox()

        # Lock-in modes aren't implemented yet -- keep them out of the
        # dropdown for normal use; populated once admin state is known.
        self._populate_mode_combo()

        layout.addWidget(self.mode_combo)

        # Emit the internal mode key when changed
        self.mode_combo.currentIndexChanged.connect(self._emit_mode)

        # --------------------------------------------------
        # Simulation controls
        # --------------------------------------------------

        self.sim_checkbox = QCheckBox("Simulation")
        layout.addWidget(self.sim_checkbox)

        self.sim_profile_combo = QComboBox()
        self.sim_profile_combo.addItems([
            "good_cell",
            "weak_cell",
            "dark_cell",
        ])

        layout.addWidget(self.sim_profile_combo)

        # Simulation controls are for development use only -- hidden
        # unless admin mode is unlocked, so they don't show up (or get
        # accidentally toggled) in normal lab use.
        self._update_simulation_visibility()

        # --------------------------------------------------
        # Manual shutter control
        # --------------------------------------------------
        # Independent of running a measurement -- see mainwindow_qt.py's
        # _on_shutter_toggled(). The Shutter checkbox starts disabled: it
        # only means something once instruments are actually connected,
        # which happens as a side effect of Start (there is no separate
        # connect step), and MainWindow disables it again for the
        # duration of any measurement so it can never race with the
        # engine's own shutter control during a scan/live run.

        self.shutter_checkbox = QCheckBox("Shutter open")
        self.shutter_checkbox.setEnabled(False)
        layout.addWidget(self.shutter_checkbox)
        self.shutter_checkbox.toggled.connect(self.shutter_toggled.emit)

        # --------------------------------------------------
        # Run control buttons
        # --------------------------------------------------

        self.start_button = QPushButton("Start")
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        layout.addWidget(self.stop_button)

        self.save_button = QPushButton("Save")
        layout.addWidget(self.save_button)

        self.autosave_checkbox = QCheckBox("Autosave")
        self.autosave_checkbox.setChecked(True)
        layout.addWidget(self.autosave_checkbox)

        # Connect signals
        self.start_button.clicked.connect(self.start_clicked.emit)
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.save_button.clicked.connect(self.save_clicked.emit)

        # Push widgets to the left, "MMF"/"About" to the far right
        layout.addStretch()

        # --------------------------------------------------
        # MMF (Mismatch Factor)
        # --------------------------------------------------

        self.mmf_button = QPushButton("MMF")
        layout.addWidget(self.mmf_button)
        self.mmf_button.clicked.connect(self.mmf_clicked.emit)

        # --------------------------------------------------
        # About
        # --------------------------------------------------

        self.about_button = QPushButton("About")
        layout.addWidget(self.about_button)
        self.about_button.clicked.connect(self.about_clicked.emit)

    # Modes not implemented yet -- excluded from the dropdown unless
    # admin mode is unlocked (see is_admin()).
    _UNIMPLEMENTED_MODES = {LOCKIN_EQE_BG, LOCKIN_LIVE_EQE}

    def is_admin(self):
        """
        Whether admin-only controls (Simulation, unimplemented Lock-in
        modes, Calibration measurement, editing Advanced Acquisition
        Settings -- see mainwindow_qt.py's update_mode_visibility())
        should be available right now. True only after successfully
        entering the PIN via the Admin checkbox this session (see
        _on_admin_toggled()) -- not tied to any particular person's
        name, and never persisted across launches.
        """
        return self._admin_unlocked

    def _on_admin_toggled(self, checked):
        """
        Checking "Admin" prompts for a PIN (config's session.admin_pin,
        normally set in a local, gitignored config_local.yaml -- never
        shipped with a default, so a fresh/public install has no
        built-in PIN to guess). Get it right and admin mode stays
        unlocked for the rest of this session; get it wrong, cancel, or
        leave it unconfigured and the checkbox reverts to unchecked.
        Unchecking it back off needs no PIN.
        """
        if not checked:
            self._admin_unlocked = False
            self._refresh_admin_gated_controls()
            self.admin_changed.emit(self._admin_unlocked)
            return

        admin_pin = (load_config().get("session") or {}).get("admin_pin")
        if not admin_pin:
            QMessageBox.warning(
                self,
                "Admin mode",
                "No admin PIN is configured. Set session.admin_pin in "
                "config_local.yaml first (see README's Configuration "
                "section) -- there is no default PIN.",
            )
            self.admin_checkbox.blockSignals(True)
            self.admin_checkbox.setChecked(False)
            self.admin_checkbox.blockSignals(False)
            return

        entered_pin, ok = QInputDialog.getText(
            self, "Admin mode", "Enter admin PIN:", QLineEdit.EchoMode.Password
        )
        if ok and entered_pin == str(admin_pin):
            self._admin_unlocked = True
        else:
            if ok:
                QMessageBox.warning(self, "Admin mode", "Incorrect PIN.")
            self.admin_checkbox.blockSignals(True)
            self.admin_checkbox.setChecked(False)
            self.admin_checkbox.blockSignals(False)
            self._admin_unlocked = False

        self._refresh_admin_gated_controls()
        self.admin_changed.emit(self._admin_unlocked)

    def _refresh_admin_gated_controls(self):
        """Re-apply every admin-gated rule owned directly by this panel."""
        self._update_simulation_visibility()
        self._update_mode_combo_for_admin()

    def _update_simulation_visibility(self):
        visible = self.is_admin()
        self.sim_checkbox.setVisible(visible)
        self.sim_profile_combo.setVisible(visible)
        if not visible:
            self.sim_checkbox.setChecked(False)

    def _populate_mode_combo(self):
        """
        (Re)build the mode dropdown, excluding not-yet-implemented modes
        unless admin mode is unlocked. Preserves the current selection
        where possible; falls back to the first available mode if the
        selected one just got filtered out.
        """

        previous_mode = self.mode_combo.currentData() if self.mode_combo.count() else None
        include_unimplemented = self.is_admin()

        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for mode_key, label in MODE_LABELS.items():
            if mode_key in self._UNIMPLEMENTED_MODES and not include_unimplemented:
                continue
            self.mode_combo.addItem(label, mode_key)

        restored_index = self.mode_combo.findData(previous_mode)
        self.mode_combo.setCurrentIndex(restored_index if restored_index >= 0 else 0)
        self.mode_combo.blockSignals(False)

    def _update_mode_combo_for_admin(self):
        self._populate_mode_combo()
        # Rebuilding doesn't emit currentIndexChanged (signals were
        # blocked); tell listeners explicitly in case the selection
        # changed (e.g. a Lock-in mode got filtered out).
        self._emit_mode()

    def _emit_mode(self):
        """
        Emit the internal measurement mode key.
        """

        mode_key = self.mode_combo.currentData()
        self.mode_changed.emit(mode_key)

    def get_mode(self):
        """
        Return the currently selected mode.
        """

        return self.mode_combo.currentData()

    def get_user(self):
        """
        Return the current user string.
        """

        return self.user_edit.text()

    def get_autosave(self):
        """
        Return whether autosave is enabled.
        """

        return self.autosave_checkbox.isChecked()

    def set_shutter_controls_enabled(self, enabled: bool):
        """
        Enable/disable the Shutter checkbox -- see mainwindow_qt.py's
        _sync_shutter_control(), called once instruments are connected
        (enable) and around a measurement (disable, since the engine
        takes over shutter control for its duration).
        """
        self.shutter_checkbox.setEnabled(enabled)

    def set_shutter_checked(self, checked: bool):
        """
        Reflect the monochromator's actual current shutter state without
        re-emitting shutter_toggled (this is MainWindow syncing the
        display to hardware, not a user action to act on again).
        """
        self.shutter_checkbox.blockSignals(True)
        self.shutter_checkbox.setChecked(checked)
        self.shutter_checkbox.blockSignals(False)
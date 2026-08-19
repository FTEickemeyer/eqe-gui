"""
Session / Run Control panel.

Contains:
- User field
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
)
from PySide6.QtCore import Signal

# Import mode labels from the shared model definition
from eqe.app.qt_models import MODE_LABELS, LOCKIN_EQE_BG, LOCKIN_LIVE_EQE


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
    mmf_clicked = Signal()
    about_clicked = Signal()

    def __init__(self):
        super().__init__()

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
        self.user_edit.textChanged.connect(self._update_simulation_visibility)
        self.user_edit.textChanged.connect(self._update_mode_combo_for_user)

        # --------------------------------------------------
        # Measurement mode selector
        # --------------------------------------------------

        layout.addWidget(QLabel("Mode"))

        self.mode_combo = QComboBox()

        # Lock-in modes aren't implemented yet -- keep them out of the
        # dropdown for normal use; populated once the user field is known.
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
        # unless the user field identifies the developer, so they don't
        # show up (or get accidentally toggled) in normal lab use.
        self._update_simulation_visibility(self.user_edit.text())

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

    # Users for whom development-only controls (simulation, unimplemented
    # modes) are shown. Case-insensitive.
    _DEVELOPER_USERS = {"felix"}

    # Modes not implemented yet -- excluded from the dropdown unless the
    # user field identifies a developer (see _DEVELOPER_USERS).
    _UNIMPLEMENTED_MODES = {LOCKIN_EQE_BG, LOCKIN_LIVE_EQE}

    def is_developer_user(self):
        return self.user_edit.text().strip().lower() in self._DEVELOPER_USERS

    def _update_simulation_visibility(self, user_text=None):
        visible = self.is_developer_user()
        self.sim_checkbox.setVisible(visible)
        self.sim_profile_combo.setVisible(visible)
        if not visible:
            self.sim_checkbox.setChecked(False)

    def _populate_mode_combo(self):
        """
        (Re)build the mode dropdown, excluding not-yet-implemented modes
        unless the current user is a developer. Preserves the current
        selection where possible; falls back to the first available mode
        if the selected one just got filtered out.
        """

        previous_mode = self.mode_combo.currentData() if self.mode_combo.count() else None
        include_unimplemented = self.is_developer_user()

        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for mode_key, label in MODE_LABELS.items():
            if mode_key in self._UNIMPLEMENTED_MODES and not include_unimplemented:
                continue
            self.mode_combo.addItem(label, mode_key)

        restored_index = self.mode_combo.findData(previous_mode)
        self.mode_combo.setCurrentIndex(restored_index if restored_index >= 0 else 0)
        self.mode_combo.blockSignals(False)

    def _update_mode_combo_for_user(self, user_text=None):
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
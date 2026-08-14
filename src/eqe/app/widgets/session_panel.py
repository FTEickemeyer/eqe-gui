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
from eqe.app.qt_models import MODE_LABELS


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

        # --------------------------------------------------
        # Measurement mode selector
        # --------------------------------------------------

        layout.addWidget(QLabel("Mode"))

        self.mode_combo = QComboBox()

        # Populate combo box with display labels
        for mode_key, label in MODE_LABELS.items():
            self.mode_combo.addItem(label, mode_key)

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
        layout.addWidget(self.autosave_checkbox)

        # Connect signals
        self.start_button.clicked.connect(self.start_clicked.emit)
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.save_button.clicked.connect(self.save_clicked.emit)

        # Push widgets to the left
        layout.addStretch()

    # Users for whom the simulation controls are shown (development use
    # only). Case-insensitive.
    _SIMULATION_VISIBLE_USERS = {"felix"}

    def _update_simulation_visibility(self, user_text):
        visible = user_text.strip().lower() in self._SIMULATION_VISIBLE_USERS
        self.sim_checkbox.setVisible(visible)
        self.sim_profile_combo.setVisible(visible)
        if not visible:
            self.sim_checkbox.setChecked(False)

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
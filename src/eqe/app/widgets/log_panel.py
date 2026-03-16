"""
Log panel for the EQE GUI.

This widget displays runtime messages such as:
- measurement progress
- warnings
- errors
- instrument status

Later this panel will receive messages from the MeasurementController.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
)


class LogPanel(QWidget):
    """
    Panel displaying log messages.
    """

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):
        """
        Construct the log interface.
        """

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # ----------------------------------------
        # Log text area
        # ----------------------------------------

        self.log_text = QTextEdit()

        # Log should be read-only
        self.log_text.setReadOnly(True)

        main_layout.addWidget(self.log_text)

        # ----------------------------------------
        # Control buttons
        # ----------------------------------------

        button_layout = QHBoxLayout()

        self.clear_button = QPushButton("Clear")

        button_layout.addWidget(self.clear_button)

        # push buttons to the left
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # connect button
        self.clear_button.clicked.connect(self.log_text.clear)

    def append(self, message):
        """
        Append a message to the log.
        """

        self.log_text.append(message)
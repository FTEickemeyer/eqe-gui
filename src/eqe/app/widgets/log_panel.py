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
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor


class LogPanel(QWidget):
    """
    Panel displaying log messages.
    """

    # Emitted every time a message is appended, so a listener (MainWindow)
    # can persist it to disk without this widget needing to know anything
    # about backend log files itself -- see append() and
    # mainwindow_qt.py's _persist_log_message().
    message_logged = Signal(str)

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
        Insert a message at the top of the log, so the most recent entry
        is always visible without scrolling.
        """

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        if self.log_text.document().isEmpty():
            cursor.insertText(message)
        else:
            cursor.insertText(message + "\n")

        self.message_logged.emit(message)
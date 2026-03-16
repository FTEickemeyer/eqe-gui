"""
Main window for the PySide6 EQE/IPCE GUI.

At this stage the window is intentionally very simple.
Its purpose is only to verify that:

- PySide6 runs correctly
- the project imports work
- the basic window structure exists

More panels and widgets will be added in later steps.
"""

# Import core Qt widgets used for building the window
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
)


class MainWindow(QMainWindow):
    """
    Main application window.

    QMainWindow is the standard top-level window type in Qt.
    It supports:
    - central widgets
    - menus
    - toolbars
    - status bars
    - dock widgets
    """

    def __init__(self):
        super().__init__()

        # Set the window title shown in the title bar
        self.setWindowTitle("EQE / IPCE Measurement GUI (PySide6)")

        # Optional: set a reasonable initial window size
        self.resize(1200, 800)

        # Build the GUI layout
        self._build_ui()

    def _build_ui(self):
        """
        Construct the basic user interface.

        For now this contains only a placeholder label.
        Later this method will create the full GUI layout.
        """

        # Create the central widget.
        # In Qt, a QMainWindow requires a central widget that
        # holds the main layout.
        central_widget = QWidget()

        # Set this widget as the main content area of the window
        self.setCentralWidget(central_widget)

        # Create a vertical layout for the central widget
        layout = QVBoxLayout()

        # Assign the layout to the central widget
        central_widget.setLayout(layout)

        # Add a placeholder label so we can see something
        label = QLabel("PySide6 GUI initialized successfully")

        # Add the label to the layout
        layout.addWidget(label)
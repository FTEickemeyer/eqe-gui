"""
PySide6 GUI launcher for the EQE/IPCE application.

This file is intentionally minimal. Its only responsibility is to:

1. Create the Qt application
2. Instantiate the main window
3. Start the Qt event loop

Keeping this file small makes it easy to maintain and avoids mixing
startup logic with GUI implementation details.
"""

import sys

# QApplication manages the entire Qt application lifecycle
from PySide6.QtWidgets import QApplication

# Import the main window class of the Qt GUI
from eqe.app.mainwindow_qt import MainWindow


def main():
    """
    Entry point for launching the PySide6 GUI.

    This function:
    - creates the Qt application
    - creates the main window
    - starts the Qt event loop
    """

    # Create the Qt application object.
    # This must exist before creating any Qt widgets.
    app = QApplication(sys.argv)

    # Instantiate the main application window
    window = MainWindow()

    # Show the window on screen
    window.show()

    # Start the Qt event loop.
    # The program will stay here until the GUI is closed.
    sys.exit(app.exec())


# Allow running this file directly:
# python -m eqe.app.gui_qt
if __name__ == "__main__":
    main()
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
from pathlib import Path


def _redirect_stdio_for_windowed_launch():
    """
    The `eqe` command is installed as a Windows GUI entry point (see
    pyproject.toml's [project.gui-scripts]) so launching it never pops up
    a console window. Under that launcher (pythonw.exe), sys.stdout and
    sys.stderr are None -- not just silent, genuinely absent -- so any
    print() call, or an unhandled exception's traceback, would raise
    AttributeError instead of merely being lost. Redirect both to a log
    file in that case so diagnostics (and crash tracebacks) land
    somewhere findable rather than crashing the app a second time.
    Left alone when run from a real console (`eqe` in a terminal,
    `python -m eqe`), where stdout/stderr already work normally.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return

    log_dir = Path.home() / ".eqe"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "eqe_gui.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file


_redirect_stdio_for_windowed_launch()

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
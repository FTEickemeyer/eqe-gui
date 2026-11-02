"""
Metadata panel for the EQE GUI.

This panel contains basic measurement metadata that is independent of the
measurement backend for now.

Current fields:
- Sample name
- Comments
- Cell area

Later, this panel can be extended with additional fields such as:
- batch / substrate ID
- operator
- output folder preview
"""

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QLineEdit,
    QTextEdit,
)
from PySide6.QtGui import QDoubleValidator


class MetadataPanel(QWidget):
    """
    Panel containing sample / metadata inputs.
    """

    def __init__(self):
        super().__init__()

        # Build the widget layout
        self._build_ui()

    def _build_ui(self):
        """
        Construct the metadata form.
        """

        # QFormLayout is convenient for label + input pairs
        layout = QFormLayout()
        self.setLayout(layout)

        # --------------------------------------------------
        # Sample name
        # --------------------------------------------------
        self.sample_name_edit = QLineEdit()
        self.sample_name_edit.setPlaceholderText("sample or device name")
        layout.addRow("Sample name", self.sample_name_edit)

        # --------------------------------------------------
        # Comments
        # --------------------------------------------------
        self.comments_edit = QTextEdit()

        # Keep the comments box compact for now
        self.comments_edit.setPlaceholderText("optional comments")
        self.comments_edit.setFixedHeight(80)

        layout.addRow("Comments", self.comments_edit)

        # --------------------------------------------------
        # Cell area
        # --------------------------------------------------
        # A plain QLineEdit, not a QDoubleSpinBox: most users don't
        # actually set this -- it's not used in any calculation (EQE/Jsc
        # are both area-independent; see measurement_engine.py), only
        # recorded for reference in the saved file's metadata header
        # (see io/data_io.py's _metadata_lines()) -- and a spin box
        # always shows *some* number. A QLineEdit can start genuinely
        # empty instead (a special-value placeholder like "optional"
        # looked like real text sitting in the field, which it isn't --
        # see get_values(), which reports empty as None, and
        # set_cell_area_cm2(), used by mainwindow_qt.py's
        # _on_calibration_toggled() to force 1 cm2 during a calibration
        # measurement).
        self.cell_area_edit = QLineEdit()
        validator = QDoubleValidator(0.0, 1000.0, 4, self.cell_area_edit)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.cell_area_edit.setValidator(validator)

        layout.addRow("Cell area (cm²)", self.cell_area_edit)

    def set_cell_area_cm2(self, value):
        """Set (or, if None, clear) the Cell area field."""
        self.cell_area_edit.setText("" if value is None else str(value))

    def get_values(self):
        """
        Return the current metadata values as a dictionary.

        This is a temporary helper. Later this will likely be replaced
        by a dataclass-based config collection.
        """

        cell_area_text = self.cell_area_edit.text().strip()
        try:
            cell_area_cm2 = float(cell_area_text) if cell_area_text else None
        except ValueError:
            cell_area_cm2 = None

        return {
            "sample_name": self.sample_name_edit.text().strip(),
            "comments": self.comments_edit.toPlainText().strip(),
            "cell_area_cm2": cell_area_cm2,
        }
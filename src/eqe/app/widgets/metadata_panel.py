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
    QDoubleSpinBox,
)


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
        self.cell_area_spin = QDoubleSpinBox()

        # Allow a broad range; precision can be refined later
        self.cell_area_spin.setRange(0.0, 1000.0)
        self.cell_area_spin.setDecimals(4)
        self.cell_area_spin.setSingleStep(0.01)
        self.cell_area_spin.setValue(1.0)

        # Show a unit suffix directly in the widget
        self.cell_area_spin.setSuffix(" cm²")

        layout.addRow("Cell area", self.cell_area_spin)

    def get_values(self):
        """
        Return the current metadata values as a dictionary.

        This is a temporary helper. Later this will likely be replaced
        by a dataclass-based config collection.
        """

        return {
            "sample_name": self.sample_name_edit.text().strip(),
            "comments": self.comments_edit.toPlainText().strip(),
            "cell_area_cm2": self.cell_area_spin.value(),
        }
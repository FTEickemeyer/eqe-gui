# Measurement mode identifiers.
#
# Canonically defined in core/models.py (backend must not depend on the
# GUI package); re-exported here so existing GUI imports keep working.
from eqe.core.models import (
    STANDARD_EQE,
    BIASED_EQE,
    STANDARD_LIVE_EQE,
    LOCKIN_EQE_BG,
    LOCKIN_LIVE_EQE,
    LIVE_MODES,
)

# User-facing labels

MODE_LABELS = {
    STANDARD_EQE: "Standard EQE",
    BIASED_EQE: "Biased EQE",
    STANDARD_LIVE_EQE: "Standard Live EQE",

    LOCKIN_EQE_BG: "Lock-in EQE (with optional background)",
    LOCKIN_LIVE_EQE: "Lock-in Live EQE",
}

# GUI section identifiers

SECTION_METADATA = "metadata"
SECTION_SCAN = "scan"
SECTION_BIAS = "bias"
SECTION_MODULATION = "modulation"
SECTION_BACKGROUND = "background"
SECTION_CALIBRATION = "calibration"
SECTION_ADVANCED = "advanced"
SECTION_LIVE_NUMERIC = "live_numeric"


# Define visibility per mode

MODE_SECTIONS = {

    STANDARD_EQE: {
        SECTION_METADATA: True,
        SECTION_SCAN: True,
        SECTION_BIAS: False,
        SECTION_MODULATION: False,
        SECTION_BACKGROUND: False,
        SECTION_CALIBRATION: True,
        SECTION_ADVANCED: True,
        SECTION_LIVE_NUMERIC: True,
    },

    BIASED_EQE: {
        SECTION_METADATA: True,
        SECTION_SCAN: True,
        SECTION_BIAS: True,
        SECTION_MODULATION: False,
        SECTION_BACKGROUND: False,
        SECTION_CALIBRATION: True,
        SECTION_ADVANCED: True,
        SECTION_LIVE_NUMERIC: True,
    },

    STANDARD_LIVE_EQE: {
        SECTION_METADATA: True,
        SECTION_SCAN: True,
        SECTION_BIAS: True,
        SECTION_MODULATION: False,
        SECTION_BACKGROUND: False,
        SECTION_CALIBRATION: False,
        SECTION_ADVANCED: True,
        SECTION_LIVE_NUMERIC: True,
    },

    LOCKIN_EQE_BG: {
        SECTION_METADATA: True,
        SECTION_SCAN: True,
        SECTION_BIAS: False,
        SECTION_MODULATION: True,
        SECTION_BACKGROUND: True,
        SECTION_CALIBRATION: True,
        SECTION_ADVANCED: True,
        SECTION_LIVE_NUMERIC: False,
    },

    LOCKIN_LIVE_EQE: {
        SECTION_METADATA: True,
        SECTION_SCAN: True,
        SECTION_BIAS: True,
        SECTION_MODULATION: False,
        SECTION_BACKGROUND: False,
        SECTION_CALIBRATION: False,
        SECTION_ADVANCED: True,
        SECTION_LIVE_NUMERIC: True,
    },
}

import datetime
from pathlib import Path

import pandas as pd

from eqe.io.paths import get_paths
from eqe.config.load_config import load_config
from eqe.utils.dataframe import df_interpolate


def _hardware_identity_lines(hardware):
    """
    Identity lines for the hardware header, mirroring what's printed to
    the console on connect (see instruments/factory.py and the
    individual drivers' connect() methods).
    """
    if hardware is None:
        return []

    ref = getattr(hardware, "reference_meter", None)
    test = getattr(hardware, "test_meter", None)
    mono = getattr(hardware, "monochromator", None)

    return [
        "# Hardware:",
        f"#   Reference meter: {getattr(ref, 'identity', None) or 'unknown'}",
        f"#   Test-cell meter: {getattr(test, 'identity', None) or 'unknown'}",
        f"#   Monochromator:   {getattr(mono, 'identity', None) or 'unknown'}",
        "#",
    ]


def _metadata_lines(metadata):
    """`metadata` is the dict returned by MetadataPanel.get_values()."""
    if metadata is None:
        return []

    lines = [
        "# Sample / Metadata:",
        f"#   Sample name: {metadata.get('sample_name', '')}",
        f"#   Cell area (cm2): {metadata.get('cell_area_cm2', '')}",
    ]

    comments = metadata.get("comments", "") or ""
    comment_lines = comments.splitlines() or [""]
    for i, line in enumerate(comment_lines):
        prefix = "Comments: " if i == 0 else "          "
        lines.append(f"#   {prefix}{line}")

    lines.append("#")
    return lines


def _scan_lines(scan):
    """`scan` is the dict returned by ScanPanel.get_values()."""
    if scan is None:
        return []

    return [
        "# Spectral scan conditions:",
        f"#   Start wavelength (nm): {scan.get('start_nm', '')}",
        f"#   Stop wavelength (nm): {scan.get('stop_nm', '')}",
        f"#   Step size (nm): {scan.get('step_nm', '')}",
        f"#   Direction: {scan.get('direction', '')}",
        "#",
    ]


def _bias_lines(bias):
    """`bias` is the dict returned by BiasPanel.get_values()."""
    if bias is None:
        return []

    compliance_A = bias.get("compliance_current")
    compliance_mA = compliance_A * 1e3 if compliance_A is not None else None

    return [
        "# Bias:",
        f"#   Bias enabled: {bias.get('bias_enabled', False)}",
        f"#   Bias voltage (V): {bias.get('bias_voltage', '')}",
        f"#   Compliance current (mA): {compliance_mA}",
        "#",
    ]


def build_measurement_header(hardware=None, metadata=None, scan=None, bias=None):
    """
    Build the commented metadata preamble written before the data table in
    a saved measurement CSV: used hardware, sample/metadata, spectral scan
    conditions, and bias settings. Any section is omitted if its dict/
    object isn't provided, so this stays optional for callers that don't
    have that context (e.g. the calibration-file save path below).
    """

    lines = [
        "# EQE measurement",
        f"# Date: {datetime.datetime.now().isoformat(sep=' ', timespec='seconds')}",
        "#",
    ]

    lines += _hardware_identity_lines(hardware)
    lines += _metadata_lines(metadata)
    lines += _scan_lines(scan)
    lines += _bias_lines(bias)

    return "\n".join(lines) + "\n"


def save_data(
    df,
    df_ref,
    sample_name,
    user_dir,
    calibration_measurement,
    debug=False,
    fig=None,
    hardware=None,
    metadata=None,
    scan=None,
    bias=None,
):
    user_dir = Path(user_dir)

    dat_time = str(datetime.datetime.now())
    dat_time_file = dat_time.split(".")[0].replace(":", "-").replace(" ", "_time")

    fp_ipce = user_dir / f"EQE_{sample_name}_date{dat_time_file}.csv"

    header = build_measurement_header(hardware=hardware, metadata=metadata, scan=scan, bias=bias)

    # Always include the raw reference/test-cell currents alongside EQE
    # (previously the GUI's save path silently dropped "Current ref (A)"/
    # "Current cell (A)").
    with open(fp_ipce, "w", newline="", encoding="utf-8") as f:
        f.write(header)
        df.to_csv(f)

    if fig is not None:
        fp_fig = user_dir / f"EQE_{sample_name}_date{dat_time_file}.png"
        fig.savefig(fp_fig, dpi=300, bbox_inches="tight")

    print(f"File saved: {fp_ipce}")

    if calibration_measurement:
        df_ref_interpol = df_interpolate(df_ref, df.index)
        df["IPCE Si71889 (%)"] = df_ref_interpol.values
        df["incident beam current (A)"] = df["Current cell (A)"] / df["IPCE Si71889 (%)"]
        df["incident beam current (A)/intSiref current (A)"] = (
            df["incident beam current (A)"] / df["Current ref (A)"]
        )

        calibration_dir = get_paths()["calibrations_dir"]
        config = load_config()
        grating_change_nm = config["calibration"]["grating_change_nm"]
        fp_incbeamcurr = (
            calibration_dir
            / f"incbeamcurr_{sample_name}_{grating_change_nm}nm-wavelength-change_date{dat_time_file}.csv"
        )

        df[
            [
                "Current ref (A)",
                "Current cell (A)",
                "incident beam current (A)/intSiref current (A)",
            ]
        ].to_csv(fp_incbeamcurr)

        if debug:
            df["incident beam current (A)/intSiref current (A)"].plot()

    return fp_ipce

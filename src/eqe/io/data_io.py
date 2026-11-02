import csv
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
        # cell_area_cm2 is None (not merely absent) when left unset --
        # `.get(..., '')`'s default only covers a missing key, not an
        # explicit None, so that needs its own fallback here too.
        f"#   Cell area (cm2): {metadata.get('cell_area_cm2') or ''}",
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


def _calibration_source_lines(calibration_filename):
    """
    `calibration_filename` is the name of the incbeamcurr_*.csv this
    measurement's EQE was computed against (see analysis/calibration.py's
    open_calibration()). None for a calibration measurement itself, which
    doesn't use one -- so this section is omitted for those.
    """
    if not calibration_filename:
        return []

    return [
        "# Calibration:",
        f"#   Incident-beam calibration file: {calibration_filename}",
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


def _advanced_lines(advanced):
    """
    `advanced` is the dict returned by AdvancedAcquisitionPanel.get_values().

    Recorded regardless of mode (scan or live) -- these are fixed
    acquisition settings, not something that varies per point the way a
    live measurement's wavelength can.
    """
    if not advanced:
        return []

    return [
        "# Advanced acquisition settings:",
        f"#   Stabilization time (ms): {advanced.get('stabilization_time_ms', '')}",
        f"#   Reference meter mode: {advanced.get('reference_meter_mode', '')}",
        f"#   Shunt resistance (ohm): {advanced.get('shunt_resistance_ohms', '')}",
        "#",
    ]


def build_measurement_header(
    hardware=None,
    metadata=None,
    scan=None,
    bias=None,
    advanced=None,
    calibration_filename=None,
):
    """
    Build the commented metadata preamble written before the data table in
    a saved measurement CSV: used hardware, sample/metadata, spectral scan
    conditions, the incident-beam calibration file used, bias settings,
    and advanced acquisition settings. Any section is omitted if its
    dict/object isn't provided, so this stays optional for callers that
    don't have that context (e.g. the calibration-file save path below).
    """

    lines = [
        "# EQE measurement",
        f"# Date: {datetime.datetime.now().isoformat(sep=' ', timespec='seconds')}",
        "#",
    ]

    lines += _hardware_identity_lines(hardware)
    lines += _metadata_lines(metadata)
    lines += _scan_lines(scan)
    lines += _calibration_source_lines(calibration_filename)
    lines += _bias_lines(bias)
    lines += _advanced_lines(advanced)

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
    advanced=None,
    calibration_filename=None,
):
    user_dir = Path(user_dir)

    dat_time = str(datetime.datetime.now())
    dat_time_file = dat_time.split(".")[0].replace(":", "-").replace(" ", "_time")

    # "Calibration_..." for a calibration measurement (no EQE is computed
    # for it -- see below), "EQE_..." for a regular scan/live measurement.
    file_prefix = "Calibration" if calibration_measurement else "EQE"

    fp_ipce = user_dir / f"{file_prefix}_{sample_name}_date{dat_time_file}.csv"

    header = build_measurement_header(
        hardware=hardware,
        metadata=metadata,
        scan=scan,
        bias=bias,
        advanced=advanced,
        calibration_filename=calibration_filename,
    )

    # Always include the raw reference/test-cell currents alongside EQE
    # (previously the GUI's save path silently dropped "Current ref (A)"/
    # "Current cell (A)").
    with open(fp_ipce, "w", newline="", encoding="utf-8") as f:
        f.write(header)
        df.to_csv(f)

    if fig is not None:
        fp_fig = user_dir / f"{file_prefix}_{sample_name}_date{dat_time_file}.png"
        fig.savefig(fp_fig, dpi=300, bbox_inches="tight")

    print(f"File saved: {fp_ipce}")

    if calibration_measurement:
        df_ref_interpol = df_interpolate(df_ref, df.index)
        df["IPCE Si71889 (%)"] = df_ref_interpol.values
        # "incident beam current" stands in for the light intensity itself
        # (by way of the Si71889's certified IPCE). Deliberately *not*
        # abs()'d: correctness here relies on wiring discipline, not a
        # software correction -- the *external* Si71889 reference cell,
        # the *internal* reference cell (Current ref (A) / intSiref), and
        # any DUT's test-cell reading must all be wired to the same
        # polarity convention (positive), so this ratio and a normal
        # scan's cell_current end up with matching signs and the division
        # in measurement_engine.py comes out positive.
        #
        # If that discipline slips -- e.g. the Si71889 reads negative here
        # -- a later unbiased EQE scan of a correctly-wired DUT will
        # compute a negative IPCE, which measurement_engine.py's 0-200%
        # sanity clamp floors to 0% *with a logged warning* rather than
        # silently correcting it. That's intentional (see git history: an
        # earlier abs()-based auto-correction here was tried and reverted
        # -- it masked genuine wiring mistakes and broke the
        # same-cell-after-its-own-calibration self-consistency check).
        # Treat a clamped-to-0% unbiased scan as "go check wiring
        # polarity," not as a dead cell.
        df["incident beam current (A)"] = (
            df["Current cell (A)"] / df["IPCE Si71889 (%)"]
        )
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


def save_mmf_result(result, output_dir, cell_name, fig=None):
    """
    Save a Mismatch Factor calculation (see analysis/mmf.py's MMFResult)
    as up to three files sharing one timestamped base name, matching this
    app's other "<Prefix>_<name>_date<date>_time<time>" save convention
    (see save_data() above). `output_dir` is typically the DUT EQE file's
    own folder (see mmf_dialog.py's _on_save()), not a fresh per-user
    dated one, so an MMF result stays alongside the specific scan it was
    computed from:

    - MMF_<cell>_date..._time....csv -- summary: the three input files
      used, the integration range, the mismatch factor, and the DUT's
      Jsc under AM1.5.
    - MMF_<cell>_date..._time....png -- the graph, if a matplotlib figure
      is given (omitted otherwise).
    - MMF_<cell>_date..._time...._data.csv -- the full data behind the
      graph: the common wavelength grid (the overlap of all three input
      files' own ranges -- see compute_mmf()) and all four curves
      resampled onto it.

    Returns a dict of the paths actually written, keyed "summary",
    "figure" (only if fig was given), and "data".
    """
    output_dir = Path(output_dir)

    dat_time = str(datetime.datetime.now())
    dat_time_file = dat_time.split(".")[0].replace(":", "-").replace(" ", "_time")

    base_name = f"MMF_{cell_name}_date{dat_time_file}"

    fp_summary = output_dir / f"{base_name}.csv"
    with open(fp_summary, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Quantity", "Value"])
        writer.writerow(["DUT EQE file", Path(result.dut_file).name])
        writer.writerow(["Reference cell EQE file", Path(result.ref_file).name])
        writer.writerow(["Lamp spectrum file", Path(result.lamp_file).name])
        writer.writerow(["Integration range start (nm)", result.left_nm])
        writer.writerow(["Integration range stop (nm)", result.right_nm])
        writer.writerow(["MMF", result.mmf])
        # "Integrated current" (not "Jsc") to match this app's existing
        # terminology for the same quantity elsewhere (a regular scan's
        # "Integrated current (mA/cm2)" column, the live readout's
        # "Integrated current" row, and this dialog's own Results label).
        writer.writerow(["Integrated current DUT @ AM1.5 (mA/cm2)", result.jsc_dut_am15])

    paths = {"summary": fp_summary}

    if fig is not None:
        fp_fig = output_dir / f"{base_name}.png"
        fig.savefig(fp_fig, dpi=300, bbox_inches="tight")
        paths["figure"] = fp_fig

    fp_data = output_dir / f"{base_name}_data.csv"
    data_df = pd.DataFrame(
        {
            "Wavelength (nm)": result.wavelengths_nm,
            "EQE DUT (%)": result.dut_eqe_pct,
            "EQE reference cell (%)": result.ref_eqe_pct,
            "Normalized PF lamp spectrum": result.lamp_pf_normalized,
            "Normalized PF AM1.5GT spectrum": result.am15_pf_normalized,
        }
    )
    data_df.to_csv(fp_data, index=False)
    paths["data"] = fp_data

    return paths

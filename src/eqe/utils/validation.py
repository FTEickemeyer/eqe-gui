# The instrument's physical wavelength limits -- single source of truth,
# shared with the GUI spin boxes that constrain user input to the same
# range (scan_panel.py, wavelength_setting_panel.py) so a value can't
# even be entered before this validation would reject it anyway.
NM_MIN = 350
NM_MAX = 1170


def nm_lim_ok(nm_lim, calibration_measurement, debug=False):
    """
    Validate a (start, stop) wavelength range against the instrument's
    physical limits (350-1170 nm).

    A calibration measurement always covers the full range regardless of
    what's passed in (see calibration_panel.py's docstring), so nm_lim is
    ignored in that case. Otherwise, an out-of-range limit is rejected
    outright -- raises ValueError rather than silently clamping to the
    nearest valid value, so the caller (mainwindow_qt's _on_start(),
    wrapped in a try/except that logs "ERROR: {exc}") surfaces it as a
    visible warning instead of silently running a different scan than
    the one actually requested. A prior version clamped-and-printed to
    the console, which windowed launches with no console never see (see
    gui_qt.py's _redirect_stdio_for_windowed_launch) -- effectively no
    warning at all.
    """
    if calibration_measurement:
        return (NM_MIN, NM_MAX)

    nm_lim = (int(nm_lim[0]), int(nm_lim[1]))
    nm_lim_max = (NM_MIN, NM_MAX)

    if nm_lim[0] > nm_lim[1]:
        # Raise rather than returning None: the caller (mainwindow_qt's
        # _on_start) doesn't check for None, so a silent None here led
        # to a confusing downstream TypeError ("NoneType not
        # subscriptable") in the GUI log instead of this message.
        raise ValueError(
            f"Invalid wavelength range: upper limit ({nm_lim[1]}) is below "
            f"lower limit ({nm_lim[0]})."
        )

    if nm_lim[0] < nm_lim_max[0] or nm_lim[1] > nm_lim_max[1]:
        raise ValueError(
            f"Invalid wavelength range: {nm_lim[0]}-{nm_lim[1]} nm is outside "
            f"the instrument's limits ({nm_lim_max[0]}-{nm_lim_max[1]} nm)."
        )

    if debug:
        print(f"nm_lim = {nm_lim}")

    return nm_lim

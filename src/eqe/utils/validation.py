def nm_lim_ok(nm_lim, calibration_measurement, debug=False):
    if calibration_measurement:
        nm_lim = (350, 1170)
    else:
        nm_lim = (int(nm_lim[0]), int(nm_lim[1]))
        nm_lim_max = (350, 1170)

        if nm_lim[0] > nm_lim[1]:
            # Raise rather than returning None: the caller (mainwindow_qt's
            # _on_start) doesn't check for None, so a silent None here led
            # to a confusing downstream TypeError ("NoneType not
            # subscriptable") in the GUI log instead of this message.
            raise ValueError(
                f"Invalid wavelength range: upper limit ({nm_lim[1]}) is below "
                f"lower limit ({nm_lim[0]})."
            )

        if nm_lim[0] < nm_lim_max[0]:
            nm_lim = (nm_lim_max[0], nm_lim[1])
            print(f"Attention: lower nm limit too low, has to be minimum {nm_lim_max[0]}!")

        if nm_lim[1] > nm_lim_max[1]:
            nm_lim = (nm_lim[0], nm_lim_max[1])
            print(f"Attention: upper nm limit too high, has to be maximum {nm_lim_max[1]}!")

        if debug:
            print(f"nm_lim = {nm_lim}")

    return nm_lim
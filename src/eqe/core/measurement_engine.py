import time
import numpy as np
import pandas as pd

from fte_analysis_libraries import General as gen
from fte_analysis_libraries import Spectrum as spc

# Default only -- perform_measurement() takes grating_change_nm as a
# parameter so the actual value always matches whatever was passed to the
# monochromator driver (config.calibration.grating_change_nm; see
# controller.py). Kept here as a fallback for standalone/direct calls.
GRATING_CHANGE_NM = 850

def interruptible_sleep(duration_s, stop_requested, chunk_s=0.05):
    end_time = time.time() + duration_s
    while time.time() < end_time:
        if stop_requested is not None:
            try:
                if stop_requested():
                    return False
            except Exception:
                pass
        remaining = end_time - time.time()
        time.sleep(min(chunk_s, remaining))
    return True

def perform_measurement(
    hardware,
    df_incbeamcurr,
    calibration_measurement,
    nm_lim,
    delta_nm=10,
    show_raw_signal=False,
    stop_when_zero=False,
    bias_enabled=False,
    bias_voltage=0.0,
    compliance_current=1e-3,
    on_live_update=None,
    on_status=None,
    stop_requested=None,
    on_point_acquired=None,
    grating_change_nm=GRATING_CHANGE_NM,
    direction="Ascending",
):
    """
    GUI-agnostic measurement loop.

    `hardware` is a `MeasurementHardware` (see core/instruments/roles.py)
    exposing `reference_meter`, `test_meter` and `monochromator`. This
    function never assumes a particular instrument model -- only the
    CurrentMeter / BiasCurrentMeter role API.

    Plotting is not handled here.
    Progress and data are emitted via callbacks.
    """

    mono = hardware.monochromator
    reference_meter = hardware.reference_meter
    test_meter = hardware.test_meter

    if calibration_measurement:
        show_IPCE = False
        show_raw_signal = True
    else:
        show_IPCE = True

    def emit_live_update(message):
        if on_live_update is not None:
            on_live_update(message)
        else:
            print(message)

    def emit_status(message):
        if on_status is not None:
            on_status(message)
        elif message:
            print(message)

    def should_stop():
        if stop_requested is not None:
            try:
                return bool(stop_requested())
            except Exception:
                return False
        return False

    if bias_enabled:
        emit_status(f"Bias enabled: {bias_voltage:.3f} V")
    else:
        emit_status("Bias disabled")
    mono.shutter(True)

    # ----------------------------------------
    # Everything from here on is wrapped in the same try/finally as the
    # measurement loop below: bias can be applied a few lines down, and
    # the finally block's reset-to-0V must run no matter what happens
    # afterward -- not just for exceptions raised inside the loop itself.
    # ----------------------------------------
    try:
        # The test-cell source output must be on to take any current
        # reading (even an unbiased 0 V one) -- unconditionally
        # re-enable it here so a previous scan's end-of-run
        # output_off() cleanup doesn't leave the next scan's first
        # reading waiting on a source that's off.
        try:
            test_meter.output_on()
        except Exception as e:
            emit_status(f"WARNING: Failed to enable test-cell output: {e}")

        # ----------------------------------------
        # Apply bias (initial implementation)
        # ----------------------------------------
        if bias_enabled:
            try:
                test_meter.set_bias_voltage(bias_voltage)
                test_meter.set_compliance_current(compliance_current)
                emit_status(f"SMU bias applied: {bias_voltage:.3f} V")
                emit_status(f"Compliance current: {compliance_current:.3e} A")
            except Exception as e:
                emit_status(f"WARNING: Failed to apply bias: {e}")

        wavelengths = np.arange(nm_lim[0], nm_lim[1] + delta_nm, delta_nm)
        if str(direction).strip().lower() == "descending":
            wavelengths = wavelengths[::-1]

        signal_A_arr = []
        signal_B_arr = []
        IPCE_arr = []
        measured_wavelengths = []
        int_curr_arr = []

        trapz_fn = getattr(np, "trapz", np.trapezoid)

        for nm in wavelengths:
            if should_stop():
                emit_status("Measurement stopped.")
                break

            try:

                mono.goto_nm(nm, on_status=emit_status)
                mono.shutter(False)

                if should_stop():
                    emit_status("Measurement stopped.")
                    break

                # wavelengths[0] (not nm_lim[0]) is the actual first point
                # in scan order -- for a descending scan that's nm_lim[1].
                if nm == wavelengths[0] or nm == grating_change_nm:
                    if not interruptible_sleep(2.0, stop_requested):
                        emit_status("Measurement stopped.")
                        break

                intSi71889_current = reference_meter.measure_current() - reference_meter.dark_current
                cell_current = test_meter.measure_current() - test_meter.dark_current

                if should_stop():
                    emit_status("Measurement stopped.")
                    break

                if getattr(test_meter, "compliance_hit", False):
                    emit_status(f"WARNING: Compliance limit reached at {nm} nm")

                IPCE = None
                if not calibration_measurement:
                    incbeamcurr_div_intSi71889current = df_incbeamcurr[
                        "incident beam current (A)/intSi71889 current (A)"
                    ].loc[nm]
                    denominator = incbeamcurr_div_intSi71889current * intSi71889_current
                    if abs(denominator) < 1e-15:
                        IPCE = 0.0
                    else:
                        IPCE = cell_current / denominator
                    if not (0.0 <= IPCE <= 200.0):
                        IPCE = max(0.0, min(IPCE, 200.0)) if np.isfinite(IPCE) else 0.0
                    IPCE_arr.append(IPCE)
                    current_IPCE_arr = np.array(IPCE_arr)

                signal_A_arr.append(intSi71889_current)
                signal_B_arr.append(cell_current)
                measured_wavelengths.append(nm)
                current_nm_arr = np.array(measured_wavelengths)

                int_curr = None
                if show_IPCE:
                    if nm > nm_lim[0] and len(current_IPCE_arr) >= 2:
                        try:
                            sp = spc.DiffSpectrum.am15_nm(
                                left=current_nm_arr[0],
                                right=current_nm_arr[-1],
                                delta=delta_nm,
                            )
                            int_curr = trapz_fn(
                                current_IPCE_arr / 100 * sp.y * gen.q * 1e3 / 1e4,
                                dx=delta_nm,
                            )
                        except Exception as e:
                            print(f"Integration failed: {e}")
                            int_curr = 0.0
                    else:
                        int_curr = 0.0
                    int_curr_arr.append(int_curr)

                if should_stop():
                    emit_status("Measurement stopped.")
                    break

                if show_raw_signal:
                    emit_live_update(
                        f"nm = {nm} nm - signal ref. cell = {intSi71889_current:.2e} A "
                        f"- signal test cell = {cell_current:.2e} A"
                    )

                if show_IPCE:
                    emit_live_update(
                        f"Wavelength = {nm} nm - IPCE = {IPCE:.1f} %\n"
                        f"Integrated current = {int_curr:.2f} mA/cm2"
                    )

                if should_stop():
                    emit_status("Measurement stopped.")
                    break

                if on_point_acquired is not None:
                    on_point_acquired(
                        # ----------------------------------------
                        # New clean keys for the new Qt GUI
                        # ----------------------------------------
                        wavelength=float(nm),
                        eqe=float(IPCE) if IPCE is not None else None,
                        integrated_current=float(int_curr) if int_curr is not None else 0.0,
                        cell_current=float(cell_current) if cell_current is not None else 0.0,
                        ref_current=float(intSi71889_current) if intSi71889_current is not None else 0.0,

                        # ----------------------------------------
                        # Legacy keys kept for backward compatibility
                        # ----------------------------------------
                        nm=nm,
                        measured_wavelengths=list(measured_wavelengths),
                        signal_A_arr=list(signal_A_arr),
                        signal_B_arr=list(signal_B_arr),
                        IPCE_arr=list(IPCE_arr),
                        int_curr_arr=list(int_curr_arr),
                        intSi71889_current=intSi71889_current,
                        cell_current_legacy=cell_current,
                        IPCE=IPCE,
                        int_curr=int_curr,
                        show_IPCE=show_IPCE,
                        show_raw_signal=show_raw_signal,
                        nm_lim=nm_lim,
                    )


                if stop_when_zero and cell_current is not None and abs(cell_current) < 1e-7:
                    emit_status("Measurement stopped because signal reached zero threshold.")
                    break

            except KeyboardInterrupt:
                break

    finally:
        # ----------------------------------------
        # Best-effort safe shutdown: always runs, whether the measurement
        # finished normally, was stopped by the user, or raised. Each step
        # is independent (one failing must not skip the rest), but a
        # failure is still surfaced -- silently swallowing it would leave
        # the operator unaware the instrument might not be in a safe state.
        # ----------------------------------------
        try:
            mono.shutter(False)
        except Exception as e:
            emit_status(f"WARNING: Failed to open monochromator shutter during cleanup: {e}")

        try:
            test_meter.set_bias_voltage(0.0)
            emit_status("SMU bias reset to 0 V")
        except Exception as e:
            emit_status(f"WARNING: Failed to reset SMU bias to 0 V: {e}")

        try:
            test_meter.output_off()
        except Exception as e:
            emit_status(f"WARNING: Failed to disable test-cell output: {e}")

        try:
            emit_status("Returning monochromator to 550 nm...")
            mono.goto_nm(550, on_status=emit_status)
        except Exception as e:
            emit_status(f"WARNING: Failed to return monochromator to 550 nm: {e}")

    if not calibration_measurement:
        df = pd.DataFrame({
            "Wavelength (nm)": np.asarray(measured_wavelengths),
            "EQE (%)": np.asarray(IPCE_arr),
            "Integrated current (mA/cm2)": np.asarray(int_curr_arr),
            "Current ref (A)": np.asarray(signal_A_arr),
            "Current cell (A)": np.asarray(signal_B_arr),
        })
    else:
        df = pd.DataFrame({
            "Wavelength (nm)": np.asarray(measured_wavelengths),
            "Current ref (A)": np.asarray(signal_A_arr),
            "Current cell (A)": np.asarray(signal_B_arr),
        })

    df.set_index("Wavelength (nm)", inplace=True)
    return df


def perform_live_monitoring(
    hardware,
    df_incbeamcurr,
    wavelength_nm,
    bias_enabled=False,
    bias_voltage=0.0,
    compliance_current=1e-3,
    on_live_update=None,
    on_status=None,
    stop_requested=None,
    on_point_acquired=None,
    update_interval_s=0.5,
    get_target_wavelength=None,
):
    """
    GUI-agnostic live monitoring loop at one fixed (but changeable, see
    `get_target_wavelength`) wavelength.

    `hardware` is a `MeasurementHardware` -- see `perform_measurement()`.
    Does not modify the instrument-driver layer.

    Returns a DataFrame indexed by "Time (s)" with columns "Wavelength
    (nm)" (the wavelength actually measured at each point -- changes if
    `get_target_wavelength` moved it mid-run), "EQE (%)", "Current ref
    (A)", "Current cell (A)".

    `update_interval_s` paces readings so the loop doesn't hammer the
    serial/VISA link as fast as the instruments can respond, and so the
    GUI's live plot doesn't accumulate points unboundedly fast during a
    long-running session. There is no GUI control for this yet -- see
    CLAUDE.md roadmap item 3 (acquisition settings panel).

    `get_target_wavelength`, if given, is polled once per cycle; when it
    returns a value different from the wavelength currently being
    measured, the monochromator moves there (shutter closed during the
    move, as at startup) and the calibration ratio is looked up again for
    the new wavelength before measuring continues. Lets the operator
    change wavelength while live monitoring is running, without having
    to stop and restart it.
    """

    mono = hardware.monochromator
    reference_meter = hardware.reference_meter
    test_meter = hardware.test_meter

    def emit_live_update(message):
        if on_live_update is not None:
            on_live_update(message)
        else:
            print(message)

    def emit_status(message):
        if on_status is not None:
            on_status(message)
        elif message:
            print(message)

    def should_stop():
        if stop_requested is not None:
            try:
                return bool(stop_requested())
            except Exception:
                return False
        return False

    nm = float(wavelength_nm)

    emit_status(f"Live monitoring at {nm:.0f} nm")

    def move_to(target_nm):
        mono.shutter(True)
        mono.goto_nm(target_nm, on_status=emit_status)
        mono.shutter(False)

    def lookup_ratio(target_nm):
        try:
            return df_incbeamcurr["incident beam current (A)/intSi71889 current (A)"].loc[
                target_nm
            ]
        except KeyError:
            raise KeyError(
                f"No calibration value found at {target_nm:.0f} nm. "
                "Use a wavelength present in the calibration table."
            )

    # ----------------------------------------
    # Everything from here on is wrapped in the same try/finally as the
    # monitoring loop below: bias can be applied a few lines down, and
    # the finally block's reset-to-0V must run no matter what happens
    # afterward -- including e.g. lookup_ratio() raising because the
    # chosen wavelength isn't in the calibration table, which previously
    # happened before any try/finally was in scope.
    # ----------------------------------------
    try:
        # See perform_measurement(): the test-cell source output must be
        # on to take any current reading, even an unbiased 0 V one.
        try:
            test_meter.output_on()
        except Exception as e:
            emit_status(f"WARNING: Failed to enable test-cell output: {e}")

        if bias_enabled:
            emit_status(f"Bias enabled: {bias_voltage:.3f} V")
            try:
                test_meter.set_bias_voltage(bias_voltage)
                test_meter.set_compliance_current(compliance_current)
                emit_status(f"SMU bias applied: {bias_voltage:.3f} V")
                emit_status(f"Compliance current: {compliance_current:.3e} A")
            except Exception as e:
                emit_status(f"WARNING: Failed to apply bias: {e}")
        else:
            emit_status("Bias disabled")

        move_to(nm)
        incbeamcurr_div_intSi71889current = lookup_ratio(nm)

        t0 = time.time()

        time_arr = []
        wavelength_arr = []
        eqe_arr = []
        ref_current_arr = []
        cell_current_arr = []

        while not should_stop():

            if get_target_wavelength is not None:
                try:
                    target = get_target_wavelength()
                except Exception:
                    target = None
                if target is not None and float(target) != nm:
                    new_nm = float(target)
                    try:
                        new_ratio = lookup_ratio(new_nm)
                    except KeyError as e:
                        emit_status(f"WARNING: {e}")
                    else:
                        nm = new_nm
                        incbeamcurr_div_intSi71889current = new_ratio
                        emit_status(f"Live monitoring wavelength changed to {nm:.0f} nm")
                        move_to(nm)

            intSi71889_current = reference_meter.measure_current() - reference_meter.dark_current
            cell_current = test_meter.measure_current() - test_meter.dark_current

            if getattr(test_meter, "compliance_hit", False):
                emit_status(f"WARNING: Compliance limit reached at {nm:.0f} nm")

            denominator = incbeamcurr_div_intSi71889current * intSi71889_current
            if abs(denominator) < 1e-15:
                IPCE = 0.0
            else:
                IPCE = cell_current / denominator
            if not (0.0 <= IPCE <= 200.0):
                IPCE = max(0.0, min(IPCE, 200.0)) if np.isfinite(IPCE) else 0.0

            elapsed_s = time.time() - t0

            time_arr.append(elapsed_s)
            wavelength_arr.append(nm)
            eqe_arr.append(IPCE)
            ref_current_arr.append(intSi71889_current)
            cell_current_arr.append(cell_current)

            emit_live_update(
                f"Live EQE at {nm:.0f} nm = {IPCE:.2f} %"
            )

            if on_point_acquired is not None:
                on_point_acquired(
                    wavelength=elapsed_s,          # x-axis is now time
                    eqe=float(IPCE),
                    integrated_current=0.0,
                    cell_current=float(cell_current),
                    ref_current=float(intSi71889_current),

                    # explicit live-mode keys
                    time_s=float(elapsed_s),
                    fixed_wavelength_nm=float(nm),
                )

            if update_interval_s > 0:
                interruptible_sleep(update_interval_s, stop_requested)
    finally:
        # Best-effort safe shutdown: always runs, whether monitoring was
        # stopped by the user or raised. A failure here is still surfaced
        # rather than swallowed -- see perform_measurement().
        try:
            test_meter.set_bias_voltage(0.0)
            emit_status("SMU bias reset to 0 V")
        except Exception as e:
            emit_status(f"WARNING: Failed to reset SMU bias to 0 V: {e}")

        try:
            test_meter.output_off()
        except Exception as e:
            emit_status(f"WARNING: Failed to disable test-cell output: {e}")

        try:
            emit_status("Returning monochromator to 550 nm...")
            mono.goto_nm(550, on_status=emit_status)
        except Exception as e:
            emit_status(f"WARNING: Failed to return monochromator to 550 nm: {e}")

    emit_status("Live monitoring stopped")

    df = pd.DataFrame({
        "Time (s)": np.asarray(time_arr),
        "Wavelength (nm)": np.asarray(wavelength_arr),
        "EQE (%)": np.asarray(eqe_arr),
        "Current ref (A)": np.asarray(ref_current_arr),
        "Current cell (A)": np.asarray(cell_current_arr),
    })
    df.set_index("Time (s)", inplace=True)
    return df

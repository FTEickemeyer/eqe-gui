import time
import numpy as np
import pandas as pd

from FTE_analysis_libraries import General as gen
from FTE_analysis_libraries import Spectrum as spc

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
    mono,
    smu,
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
):
    """
    GUI-agnostic measurement loop.

    Plotting is not handled here.
    Progress and data are emitted via callbacks.
    """

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
    # Apply bias (initial implementation)
    # ----------------------------------------
    if bias_enabled:
        try:
            smu.set_bias_voltage(bias_voltage)
            smu.set_compliance_current(compliance_current)
            emit_status(f"SMU bias applied: {bias_voltage:.3f} V")
            emit_status(f"Compliance current: {compliance_current:.3e} A")
        except Exception as e:
            emit_status(f"WARNING: Failed to apply bias: {e}")

    wavelengths = np.arange(nm_lim[0], nm_lim[1] + delta_nm, delta_nm)

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

            if nm == nm_lim[0] or nm == GRATING_CHANGE_NM:
                if not interruptible_sleep(2.0, stop_requested):
                    emit_status("Measurement stopped.")
                    break

            smu.run_dual_measurement()

            if should_stop():
                emit_status("Measurement stopped.")
                break

            smu.chA, smu.chB = smu.get_average()

            intSiref_current = smu.chA - smu.chA_dark
            cell_current = smu.chB - smu.chB_dark

            IPCE = None
            if not calibration_measurement:
                incbeamcurr_div_intSirefcurrent = df_incbeamcurr[
                    "incident beam current (A)/intSiref current (A)"
                ].loc[nm]
                IPCE = cell_current / (incbeamcurr_div_intSirefcurrent * intSiref_current)
                if IPCE < 0.0:
                    IPCE = 0.0
                IPCE_arr.append(IPCE)
                current_IPCE_arr = np.array(IPCE_arr)

            signal_A_arr.append(intSiref_current)
            signal_B_arr.append(cell_current)
            measured_wavelengths.append(nm)
            current_nm_arr = np.array(measured_wavelengths)

            int_curr = None
            if show_IPCE:
                if nm > nm_lim[0] and len(current_IPCE_arr) >= 2:
                    try:
                        sp = spc.diff_spectrum.AM15_nm(
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
                    f"nm = {nm} nm - signal ref. cell (chA) = {intSiref_current:.2e} A "
                    f"- signal test cell (chB) = {cell_current:.2e} A"
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
                    ref_current=float(intSiref_current) if intSiref_current is not None else 0.0,

                    # ----------------------------------------
                    # Legacy keys kept for backward compatibility
                    # ----------------------------------------
                    nm=nm,
                    measured_wavelengths=list(measured_wavelengths),
                    signal_A_arr=list(signal_A_arr),
                    signal_B_arr=list(signal_B_arr),
                    IPCE_arr=list(IPCE_arr),
                    int_curr_arr=list(int_curr_arr),
                    intSiref_current=intSiref_current,
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

    mono.shutter(False)

    # ----------------------------------------
    # Reset bias safely
    # ----------------------------------------
    try:
        smu.set_bias_voltage(0.0)
        emit_status("SMU bias reset to 0 V")
    except Exception:
        pass

    try:
        emit_status("Returning monochromator to 550 nm...")
        mono.goto_nm(550, on_status=emit_status)
    except Exception:
        pass

    if not calibration_measurement:
        df = pd.DataFrame({
            "Wavelength (nm)": np.asarray(measured_wavelengths),
            "EQE (%)": np.asarray(IPCE_arr),
            "Integrated current (mA/cm2)": np.asarray(int_curr_arr),
            "Current ref-chA (A)": np.asarray(signal_A_arr),
            "Current cell-chB (A)": np.asarray(signal_B_arr),
        })
    else:
        df = pd.DataFrame({
            "Wavelength (nm)": np.asarray(measured_wavelengths),
            "Current ref-chA (A)": np.asarray(signal_A_arr),
            "Current cell-chB (A)": np.asarray(signal_B_arr),
        })

    df.set_index("Wavelength (nm)", inplace=True)
    return df
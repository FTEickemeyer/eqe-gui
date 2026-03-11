import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import datetime
import csv
import os
from pathlib import Path

# --- Instrument and libraries ---
from eqe.config.config_loader import load_config
from eqe.core.models import MeasurementParams
from eqe.analysis.calibration import open_calibration
from eqe.io.paths import create_user_directory
from eqe.io.data_io import save_data
from eqe.io.logging import append_to_log
from eqe.app.state import AppState
from eqe.utils.validation import nm_lim_ok
from eqe.analysis import mmf_legacy as MMF
from eqe.core.controller import MeasurementController

from FTE_analysis_libraries import Spectrum as spc

controller = MeasurementController()

config = load_config()

system_dir = config["paths"]["system_dir"]
data_dir = config["paths"]["data_dir"]

gui_plot_state = {}
state = AppState()

def tk_dispatch(callback, *args, **kwargs):
    """
    Ensures GUI updates always run on the Tk main thread.
    """
    root.after(0, lambda: callback(*args, **kwargs))

def connect_instruments():
    try:
        # Close previous instruments first, if any
        try:
            if controller.smu is not None:
                controller.smu.close()
        except Exception as e:
            print(f"Error closing previous SMU: {e}")

        try:
            if controller.mono is not None:
                controller.mono.close()
        except Exception as e:
            print(f"Error closing previous monochromator: {e}")

        controller.mono = None
        controller.smu = None

        controller.connect_instruments(
            mono=None,
            smu=None,
            N=500,
            nplc=0.01,
            interval=0.002,
            simulate=bool(simulate_var.get()),
        )

        if simulate_var.get():
            live_update_var.set("Simulation mode: virtual instruments connected.")
        else:
            live_update_var.set("Hardware instruments connected.")

        print("Instruments connected.")

    except Exception as e:
        print(f"Instrument connection failed: {e}")
        live_update_var.set(f"Instrument connection failed: {e}")

#plt.ion()
matplotlib.rcParams['toolbar'] = 'none'

# --- Instrument Initialization ---
debug = False

# --- Log file path ---
log_file_path = os.path.join(system_dir, "EQE_measurement_log.csv")

# --- Logging Function ---
def append_to_log(user, sample, Jsc, MMF, calibration_measurement, autosave, filename):
    log_exists = os.path.exists(log_file_path)
    with open(log_file_path, mode='a', newline='') as log_file:
        writer = csv.writer(log_file)
        if not log_exists:
            writer.writerow(["Timestamp", "User", "Sample", "Jsc (mA/cm²)", "MMF", "Calibration", "Autosave", "Filename"])
        writer.writerow([
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            user, sample, f"{Jsc:.2f}", f"{MMF:.3f}",
            calibration_measurement, autosave, filename
        ])


#mono = globals().get('mono', None)
#smu = globals().get('smu', None)
#mono, smu = EQE.initialize_system(mono, smu, N=500, nplc=0.01, interval=0.002)
#mono.goto_nm(550.)
#mono.shutter(False)

# --- GUI ---
root = tk.Tk()
root.title("EQE Measurement")
icon_path = Path(__file__).parent / "assets" / "EQE_icon.ico"
root.iconbitmap(icon_path)
root.lift()
root.attributes('-topmost', True)
root.after_idle(root.attributes, '-topmost', False)

frame_all = tk.Frame(root)
frame_all.pack(fill=tk.BOTH, expand=True)

frame_inputs = tk.Frame(frame_all)
frame_inputs.grid(row=0, column=0, sticky="nw", padx=10, pady=10)

frame_plot = tk.Frame(frame_all)
frame_plot.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)
frame_all.grid_rowconfigure(0, weight=1)
frame_all.grid_columnconfigure(1, weight=1)

# --- Entry Fields ---
tk.Label(frame_inputs, text="User Name:").grid(row=0, column=0, sticky='e')
entry_user = tk.Entry(frame_inputs)
entry_user.insert(0, "user")  # 👈 this sets the default text
entry_user.grid(row=0, column=1)

tk.Label(frame_inputs, text="Sample Name:").grid(row=1, column=0, sticky='e')
entry_sample = tk.Entry(frame_inputs)
entry_sample.insert(0, "cell")
entry_sample.grid(row=1, column=1)

tk.Label(frame_inputs, text="Start (>= 350 nm):").grid(row=2, column=0, sticky='e')
entry_start = tk.Entry(frame_inputs)
entry_start.insert(0, "350")
entry_start.grid(row=2, column=1)

tk.Label(frame_inputs, text="Stop (<= 1170 nm):").grid(row=3, column=0, sticky='e')
entry_stop = tk.Entry(frame_inputs)
entry_stop.insert(0, "900")
entry_stop.grid(row=3, column=1)

tk.Label(frame_inputs, text="Interval (nm):").grid(row=4, column=0, sticky='e')
entry_interval = tk.Entry(frame_inputs)
entry_interval.insert(0, "10")
entry_interval.grid(row=4, column=1)

# --- Checkboxes ---
simulate_var = tk.IntVar(value=0)
show_raw_var = tk.IntVar(value=0)
save_raw_var = tk.IntVar(value=1)
calibration_var = tk.IntVar(value=0)
stop_when_zero_var = tk.IntVar(value=1)
autosave_var = tk.IntVar(value=1)

ttk.Checkbutton(
    frame_inputs,
    text="Simulation mode",
    variable=simulate_var
).grid(row=6, column=0, columnspan=2, sticky='w')

ttk.Checkbutton(
    frame_inputs,
    text="Show Raw Signal",
    variable=show_raw_var,
    state='disabled'
).grid(row=7, column=0, columnspan=2, sticky='w')

ttk.Checkbutton(
    frame_inputs,
    text="Save Raw Data",
    variable=save_raw_var,
    state='disabled'
).grid(row=8, column=0, columnspan=2, sticky='w')

calib_check = ttk.Checkbutton(
    frame_inputs,
    text="Calibration Measurement",
    variable=calibration_var
)

ttk.Checkbutton(
    frame_inputs,
    text="Stop when zero",
    variable=stop_when_zero_var
).grid(row=9, column=0, columnspan=2, sticky='w')

ttk.Checkbutton(
    frame_inputs,
    text="Autosave",
    variable=autosave_var
).grid(row=10, column=0, columnspan=2, sticky='w')

# Will be packed later only if user is "Felix"
def toggle_calib_checkbox():
    if entry_user.get().strip().lower() == "felix":
        calib_check.grid(row=5, column=0, columnspan=2, sticky='w')
    else:
        calibration_var.set(0)
        calib_check.grid_forget()

entry_user.bind("<FocusOut>", lambda e: toggle_calib_checkbox())

# --- Button Frame for Even Spacing ---
button_frame = tk.Frame(frame_inputs)
button_frame.grid(row=11, column=0, columnspan=4, pady=10)

# Make all 4 columns the same width
for i in range(4):
    button_frame.grid_columnconfigure(i, weight=1, uniform="button")

# Button width
button_width = 12

# --- Buttons using lambda for consistency ---
start_button = tk.Button(button_frame, text="Start", width=button_width, command=lambda: start_measurement())
start_button.grid(row=0, column=0, padx=5)

save_button = tk.Button(button_frame, text="Save", width=button_width, command=lambda: manual_save())
save_button.grid(row=0, column=1, padx=5)
save_button.config(state='disabled')

stop_button = tk.Button(button_frame, text="Stop", width=button_width, command=lambda: stop_measurement())
stop_button.grid(row=0, column=2, padx=5)
stop_button.config(state='disabled')

exit_button = tk.Button(button_frame, text="Exit", width=button_width, command=lambda: on_closing())
exit_button.grid(row=0, column=3, padx=5)


# --- Live data update ---
live_update_var = tk.StringVar()
live_update_label = tk.Label(frame_inputs, textvariable=live_update_var, fg="black", justify="left", wraplength=350)
live_update_label.grid(row=12, column=0, columnspan=2, pady=(5, 0))

# --- Progress Bar ---
#progress = ttk.Progressbar(frame_inputs, orient="horizontal", length=200, mode="determinate")
#progress.grid(row=11, column=0, columnspan=2, pady=5)

# --- Jsc and MMF ---
status_var = tk.StringVar()
status_label = tk.Label(frame_inputs, textvariable=status_var, fg="blue", justify="left", wraplength=350)
status_label.grid(row=13, column=0, columnspan=2, pady=(10, 0))


# --- Matplotlib Plot Init ---
fig, ax_cell = plt.subplots(figsize=(5, 4), dpi=100)
ax_ref = ax_cell.twinx()
ax_cell.grid(True)
ax_cell.set_xlabel("Wavelength (nm)")
ax_cell.set_ylabel('EQE (%)')
ax_cell.set_xlim(350, 1170)
ax_cell.set_ylim(bottom=0.0, top=100.0)
ax_ref.set_ylabel('Integrated current (mA/cm2)')
ax_ref.set_ylim(bottom=0.0, top=10.001)
ax_cell.set_title('EQE Measurement')
plt.close(fig)
canvas = FigureCanvasTkAgg(fig, master=frame_plot)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

def manual_save():
    if state.df_ipce is None:
        messagebox.showwarning("No Data", "No measurement data available to save.")
        return

    user = entry_user.get().strip()
    state.user_dir = create_user_directory(data_dir, user, debug=debug)
    sample = entry_sample.get().strip()

    if not state.calibration_measurement:
        try:
            JscMMF_text = status_var.get().split('\n')
            Jsc = float(JscMMF_text[2].split('=')[1].split('mA')[0].strip())
            MMF_float = float(JscMMF_text[3].split('=')[1].strip())
            sample = sample + '_' + f"Jsc={Jsc:.2f}mAcm2_MMF={MMF_float:.3f}"
        except:
            #status_var.set("Attention: MMF could not be calculated!")
            Jsc = np.nan
            MMF_float = np.nan
    else:
        Jsc = np.nan
        MMF_float = np.nan

    fp = save_data(
        state.df_ipce,
        state.df_ref,
        sample,
        state.user_dir,
        system_dir,
        state.calibration_measurement,
        save_raw_data=state.save_raw,
        debug=debug,
        fig=fig,
    )
    append_to_log(
        user,
        entry_sample.get().strip(),
        Jsc,
        MMF_float,
        state.calibration_measurement,
        False,
        fp,
    )
    messagebox.showinfo("Data Saved", "Data has been saved successfully.")


def set_gui_running_state():
    stop_button.config(state='normal')
    start_button.config(state='disabled')
    exit_button.config(state='disabled')
    save_button.config(state='disabled')
    status_var.set("")
    live_update_var.set("")


def set_gui_idle_state():
    try:
        start_button.config(state='normal')
        exit_button.config(state='normal')
        save_button.config(state='normal')
        stop_button.config(state='disabled')
    except tk.TclError:
        pass

def stop_measurement():
    try:
        stop_button.config(state='disabled')
    except tk.TclError:
        return

    live_update_var.set("Stopping measurement...")
    controller.request_stop()

def on_live_update(message):
    live_update_var.set(message)


def on_status(message):
    status_var.set(message)

def configure_eqe_axes(ax_cell, ax_ref, nm_lim):
    ax_cell.clear()
    ax_ref.clear()

    ax_cell.grid(True)
    ax_cell.set_xlabel("Wavelength (nm)")
    ax_cell.set_ylabel("EQE (%)")
    ax_ref.set_ylabel("Integrated current (mA/cm²)", labelpad=18)

    ax_ref.yaxis.set_label_position("right")
    ax_ref.yaxis.set_label_coords(1.10, 0.5)

    ax_cell.set_xlim(nm_lim)
    ax_cell.set_ylim(bottom=0.0, top=100.0)
    ax_ref.set_ylim(bottom=0.0)

    ax_cell.set_title("EQE Measurement")

def configure_raw_axes(ax_cell, ax_ref, nm_lim):
    ax_cell.clear()
    ax_ref.clear()

    ax_cell.grid(True)
    ax_cell.set_xlabel("Wavelength (nm)")
    ax_cell.set_ylabel("Signal cell (A)")
    ax_ref.set_ylabel("Signal ref. (A)")
    ax_cell.set_xlim(nm_lim)

    ax_cell.set_title("Raw signal")


def init_plot_lines(ax_cell, ax_ref, show_ipce=True):

    if show_ipce:

        # EQE curve
        line_cell, = ax_cell.plot(
            [], [],
            marker="o",
            linestyle="-",
            label="EQE"
        )

        # Integrated current
        line_ref, = ax_ref.plot(
            [], [],
            linestyle="-",
            marker=None,
            color="orange",
            label="Integrated current"
        )

    else:

        # Raw signals
        line_cell, = ax_cell.plot(
            [], [],
            marker="o",
            linestyle="-",
            label="test cell"
        )

        line_ref, = ax_ref.plot(
            [], [],
            marker="o",
            linestyle="-",
            label="ref cell"
        )

    # Combined legend
    lines1, labels1 = ax_cell.get_legend_handles_labels()
    lines2, labels2 = ax_ref.get_legend_handles_labels()

    if lines1 or lines2:
        ax_cell.legend(lines1 + lines2, labels1 + labels2)

    return line_cell, line_ref


def on_point_acquired(
    nm,
    measured_wavelengths,
    signal_A_arr,
    signal_B_arr,
    IPCE_arr,
    int_curr_arr,
    intSiref_current,
    cell_current,
    IPCE,
    int_curr,
    show_IPCE,
    show_raw_signal,
    nm_lim,
):
    ax_cell = gui_plot_state["ax_cell"]
    ax_ref = gui_plot_state["ax_ref"]
    line_cell = gui_plot_state["line_cell"]
    line_ref = gui_plot_state["line_ref"]

    x = np.asarray(measured_wavelengths)

    if show_IPCE:
        y_cell = np.asarray(IPCE_arr)
        y_ref = np.asarray(int_curr_arr)
    elif show_raw_signal:
        y_cell = np.asarray(signal_B_arr)
        y_ref = np.asarray(signal_A_arr)
    else:
        return

    line_cell.set_data(x, y_cell)
    line_ref.set_data(x, y_ref)

    # Keep x-limits stable
    ax_cell.set_xlim(nm_lim)

    # Update y-limits manually for predictable behavior
    if len(y_cell) > 0:
        y_cell_min = min(0.0, float(np.min(y_cell)))
        y_cell_max = float(np.max(y_cell))
        if y_cell_max == y_cell_min:
            y_cell_max = y_cell_min + 1e-12
        ax_cell.set_ylim(y_cell_min, 1.05 * y_cell_max)

    if len(y_ref) > 0:
        y_ref_min = min(0.0, float(np.min(y_ref)))
        y_ref_max = float(np.max(y_ref))
        if y_ref_max == y_ref_min:
            y_ref_max = y_ref_min + 1e-12
        ax_ref.set_ylim(y_ref_min, 1.05 * y_ref_max)

    canvas.draw_idle()


# --- Start Measurement Function ---
def start_measurement():

    set_gui_running_state()

    # Clear old data
    status_var.set("")
    live_update_var.set("")

    try:
        params = MeasurementParams(
            user=entry_user.get().strip(),
            sample=entry_sample.get().strip(),
            wl_start=int(entry_start.get()),
            wl_stop=int(entry_stop.get()),
            interval=int(entry_interval.get()),
            calibration_measurement=bool(calibration_var.get()),
            show_raw=bool(show_raw_var.get()),
            save_raw=bool(save_raw_var.get()),
            stop_when_zero=bool(stop_when_zero_var.get()),
            autosave=bool(autosave_var.get()),
        )

        user = params.user
        sample = params.sample
        wl_start = params.wl_start
        wl_stop = params.wl_stop
        interval = params.interval
        show_raw = params.show_raw
        stop_when_zero = params.stop_when_zero
        autosave = params.autosave

        state.user = user
        state.sample = sample
        state.calibration_measurement = params.calibration_measurement
        state.save_raw = params.save_raw

        # Check wavelength limits
        if wl_start < 350:
            messagebox.showerror("Input Error", "Wavelength Start must be ≥ 350 nm.")
            return

        if wl_stop > 1170:
            messagebox.showerror("Input Error", "Wavelength Stop must be ≤ 1170 nm.")
            return

        if interval <= 0:
            messagebox.showerror("Input Error", "Interval must be a positive integer.")
            return

        if wl_start >= wl_stop:
            messagebox.showerror("Input Error", "Start wavelength must be less than stop wavelength.")
            return

        toggle_calib_checkbox()  # ensure calibration checkbox is updated

        state.user_dir = create_user_directory(data_dir, user, debug=debug)
        nm_lim = (wl_start, wl_stop)
        nm_lim = nm_lim_ok(nm_lim, state.calibration_measurement, debug=debug)

        connect_instruments()

        mono = controller.mono
        smu = controller.smu

        if simulate_var.get():
            live_update_var.set("Simulation mode: virtual instruments connected.")
        else:
            live_update_var.set("Hardware instruments connected.")

        if mono is None or smu is None:
            messagebox.showerror("Connection Error", "Instruments are not connected.")
            return

        if hasattr(mono, "filter_wheel_position"):
            mono.filter = mono.filter_wheel_position

        df_incbeamcurr, state.df_ref = open_calibration(
            system_dir,
            nm_lim,
            state.calibration_measurement,
            debug=debug
        )

        fig.clear()

        ax_cell = fig.add_subplot(111)
        ax_ref = ax_cell.twinx()
        ax_ref.yaxis.set_label_coords(1.10, 0.5)
        fig.subplots_adjust(right=0.86)

        show_ipce = not show_raw

        if show_ipce:
            configure_eqe_axes(ax_cell, ax_ref, nm_lim)
        else:
            configure_raw_axes(ax_cell, ax_ref, nm_lim)

        line_cell, line_ref = init_plot_lines(ax_cell, ax_ref, show_ipce=show_ipce)

        canvas.draw()

        gui_plot_state["ax_cell"] = ax_cell
        gui_plot_state["ax_ref"] = ax_ref
        gui_plot_state["line_cell"] = line_cell
        gui_plot_state["line_ref"] = line_ref
        gui_plot_state["show_ipce"] = show_ipce
        gui_plot_state["nm_lim"] = nm_lim

        # Perform measurement live
        controller.run_measurement_async(
            params=params,
            df_incbeamcurr=df_incbeamcurr,
            nm_lim=nm_lim,
            ui_dispatch=tk_dispatch,
            callbacks={
                "on_live_update": on_live_update,
                "on_status": on_status,
                "on_point_acquired": on_point_acquired,
                "on_done": on_measurement_done,
                "on_error": on_measurement_error,
                "on_finished": on_measurement_finished,
            },
        )

    except ValueError as e:
        if "invalid literal" in str(e) or "int()" in str(e):
            messagebox.showerror(
                "Input Error",
                "Please enter valid integer values for wavelength limits (350 - 1170 nm) and interval (> 0 nm)."
            )
        else:
            messagebox.showerror("Value Error", f"A value error occurred:\n{e}")
        return

    except Exception as e:
        messagebox.showerror(
            "Unexpected Error",
            f"An unexpected error occurred:\n{e}. Try to restart the program!"
        )
        print(f"Unexpected error: {e}")
        return

def on_measurement_done(df_result):
    state.df_ipce = df_result

    if not state.calibration_measurement:

        try:
            spec_MMF, Jsc = MMF.calc_MMF_and_Jsc(state.df_ipce)
        except Exception:
            spec_MMF = np.nan
            Jsc = 0.0

        Jsc = state.df_ipce['Integrated current (mA/cm2)'].iloc[-1]
        status_var.set(
            "Calculated short circuit current and spectral mismatch factor\n"
            "(MMF only valid for range 350-850nm):\n"
            f"Jsc = {Jsc:.2f} mA/cm²\n"
            f"MMF = {spec_MMF:.3f}"
        )
    else:
        spec_MMF = np.nan
        Jsc = np.nan

    if autosave_var.get():
        manual_save()


def on_measurement_error(exc):
    messagebox.showerror(
        "Unexpected Error",
        f"An unexpected error occurred:\n{exc}\nTry to restart the program!"
    )
    print(f"Unexpected error: {exc}")


def on_measurement_finished():
    set_gui_idle_state()

# --- Shutdown ---
def on_closing():
    try:
        if controller.smu is not None:
            controller.smu.close()
    except Exception as e:
        print("Error closing SMU:", e)

    try:
        if controller.mono is not None:
            controller.mono.close()
    except Exception as e:
        print("Error closing monochromator:", e)

    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()

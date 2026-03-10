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
from eqe.core import eqe_main_legacy as EQE
from eqe.analysis import mmf_legacy as MMF
from FTE_analysis_libraries import Spectrum as spc

#plt.ion()
matplotlib.rcParams['toolbar'] = 'none'

# --- Instrument Initialization ---
debug = False
system_dir = r'C:\Users\labo\Documents\Python'
data_dir = r'C:\Users\labo\Documents\Data'

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
show_raw_var = tk.IntVar(value=1)
save_raw_var = tk.IntVar(value=1)
calibration_var = tk.IntVar(value=0)
stop_when_zero_var = tk.IntVar(value=1)
autosave_var = tk.IntVar(value=1)

ttk.Checkbutton(frame_inputs, text="Show Raw Signal", variable=show_raw_var, state='disabled').grid(row=5, column=0, columnspan=2, sticky='w')
ttk.Checkbutton(frame_inputs, text="Save Raw Data", variable=save_raw_var, state='disabled').grid(row=6, column=0, columnspan=2, sticky='w')
calib_check = ttk.Checkbutton(frame_inputs, text="Calibration Measurement", variable=calibration_var)
ttk.Checkbutton(frame_inputs, text="Stop when zero", variable=stop_when_zero_var).grid(row=8, column=0, columnspan=2, sticky='w')
ttk.Checkbutton(frame_inputs, text="Autosave", variable=autosave_var).grid(row=9, column=0, columnspan=2, sticky='w')

# Will be packed later only if user is "Felix"
def toggle_calib_checkbox():
    if entry_user.get().strip().lower() == "felix":
        calib_check.grid(row=7, column=0, columnspan=2, sticky='w')
    else:
        calibration_var.set(0)
        calib_check.grid_forget()

entry_user.bind("<FocusOut>", lambda e: toggle_calib_checkbox())

# --- Buttons ---

# --- Stop flag (define before button use) ---
stop_flag = tk.BooleanVar(value=False)

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


stop_button = tk.Button(button_frame, text="Stop", width=button_width, command=lambda: stop_flag.set(True))
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
    global df_IPCE, df_ref, calibration_measurement, save_raw
    #if len(last_wavelengths) == 0 or len(last_ipce_values) == 0:
    #    messagebox.showwarning("No Data", "No EQE data available to save.")
    #    return

    user = entry_user.get().strip()
    user_dir = EQE.create_user_directory(data_dir, user, debug=debug)
    sample = entry_sample.get().strip()

    if not calibration_measurement:
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

    fp = EQE.save_data(df_IPCE, df_ref, sample, user_dir, system_dir, calibration_measurement, save_raw_data=save_raw, debug=debug, fig=fig)
    append_to_log(user, entry_sample.get().strip(), Jsc, MMF_float, calibration_measurement, False, fp)
    messagebox.showinfo("Data Saved", "Data has been saved successfully.")


# --- Start Measurement Function ---
def start_measurement():
    global df_IPCE, df_ref, sample, user_dir, calibration_measurement, save_raw

    stop_button.config(state='normal')
    stop_flag.set(False)
    start_button.config(state='disabled')
    exit_button.config(state='disabled')
    save_button.config(state='disabled')

    # Clear old data
    status_var.set("")
    live_update_var.set("")

    user = entry_user.get().strip()
    sample = entry_sample.get().strip()
    try:
        wl_start = int(entry_start.get())
        wl_stop = int(entry_stop.get())
        interval = int(entry_interval.get())

        # Check wavelength stop
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

        show_raw = bool(show_raw_var.get())
        save_raw = bool(save_raw_var.get())
        stop_when_zero = bool(stop_when_zero_var.get())
        calibration_measurement = bool(calibration_var.get())

        user_dir = EQE.create_user_directory(data_dir, user, debug=debug)
        nm_lim = [wl_start, wl_stop]
        nm_lim = EQE.nm_lim_ok(nm_lim, calibration_measurement, debug=debug)
        mono.filter = mono.filter_wheel_position

        df_incbeamcurr, df_ref = EQE.open_calibration(system_dir, nm_lim, calibration_measurement, debug=debug)

        # Clear and prepare plot
        # Clear both the main and twin axes
        for child in fig.get_axes():
            child.cla()  # Clear individual axes
        fig.clear()      # Clear the whole figure if needed


        # Recreate the main axis
        ax_cell = fig.add_subplot(111)
        ax_ref = ax_cell.twinx()
        ax_cell.grid(True)
        ax_cell.set_xlabel("Wavelength (nm)")
        ax_cell.set_ylabel('EQE (%)')
        ax_cell.set_xlim(nm_lim)
        ax_cell.set_ylim(bottom=0.0, top=100.0)
        ax_ref.set_ylabel('Integrated current (mA/cm2)')
        ax_ref.set_ylim(bottom=0.0, top=10.001)
        ax_cell.set_title('EQE Measurement')
        canvas.draw()

        # Perform measurement live
        gui = {'ax_cell': ax_cell, 'ax_ref': ax_ref, 'canvas': canvas, 'live_update_var': live_update_var, 'status_var': status_var, 'stop_flag': stop_flag, 'stop_when_zero': stop_when_zero}
        df_IPCE = EQE.perform_measurement(
            mono, smu, df_incbeamcurr,
            calibration_measurement, nm_lim, delta_nm=interval,
            show_raw_signal=show_raw,
            gui=gui, root=root
        )

        #ax.plot(wls, ipce, label=sample)
        #ax.legend()
        #canvas.draw()

        if not calibration_measurement:
            try:
                spec_MMF, Jsc = MMF.calc_MMF_and_Jsc(df_IPCE)
            except:
                spec_MMF = np.nan
                Jsc = 0.0
            #For some reason the thus calculated Jsc is a bit different from the integrated current shown in the graph
            Jsc = df_IPCE['Integrated current (mA/cm2)'].iloc[-1]
            status_var.set(f"Calculated short circuit current and spectral mismatch factor\n(MMF only valid for range 350-850nm):\nJsc = {Jsc:.2f} mA/cm²\nMMF = {spec_MMF:.3f}")
        else:
            spec_MMF = np.nan
            Jsc = np.nan

        autosave = bool(autosave_var.get())
        if autosave:
            manual_save()

    except ValueError as e:
        if "invalid literal" in str(e) or "int()" in str(e):
            messagebox.showerror("Input Error", "Please enter valid integer values for wavelength limits (350 - 1170 nm) and interval (> 0 nm).")
        else:
            messagebox.showerror("Value Error", f"A value error occurred:\n{e}")
        return
    except Exception as e:
        # Catch unexpected issues like connection loss, COM port errors, etc.
        messagebox.showerror("Unexpected Error", f"An unexpected error occurred:\n{e}. Try to restart the program!")
        print(f"Unexpected error: {e}")
        return

    finally:
        try:
            start_button.config(state='normal')
            exit_button.config(state='normal')
            save_button.config(state='normal')

        except tk.TclError:
            pass  # GUI was closed

# --- Shutdown ---
def on_closing():
    try:
        smu.close()
        mono.close()
    except Exception as e:
        print("Error during shutdown:", e)
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()

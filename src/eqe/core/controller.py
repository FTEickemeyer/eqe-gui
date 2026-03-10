from eqe.core import eqe_main_legacy as EQE
from eqe.config.config_loader import load_config


class MeasurementController:
    def __init__(self):
        self.mono = None
        self.smu = None
        self.config = load_config()

    def connect_instruments(self, mono=None, smu=None, N=None, nplc=None, interval=None):
        if N is None:
            N = self.config["measurement"]["N"]
        if nplc is None:
            nplc = self.config["measurement"]["nplc"]
        if interval is None:
            interval = self.config["measurement"]["interval"]

        self.mono, self.smu = EQE.initialize_system(
            mono,
            smu,
            N=N,
            nplc=nplc,
            interval=interval
        )
        return self.mono, self.smu

    def run_measurement(self, params, df_incbeamcurr, gui, root):
        ax_cell = gui["ax_cell"]
        ax_ref = gui["ax_ref"]
        canvas = gui["canvas"]

        def on_live_update(message):
            gui["live_update_var"].set(message)
            try:
                root.update_idletasks()
            except Exception:
                pass

        def on_status(message):
            gui["status_var"].set(message)
            try:
                root.update_idletasks()
            except Exception:
                pass

        def stop_requested():
            return gui["stop_flag"].get()

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
            ax_cell.cla()
            ax_ref.cla()

            ax_cell.grid(True)
            ax_cell.set_xlabel("Wavelength (nm)")

            if show_IPCE:
                ax_cell.set_ylabel("EQE (%)")
                ax_cell.set_xlim(nm_lim)
                if len(IPCE_arr) > 0:
                    ax_cell.plot(measured_wavelengths, IPCE_arr, marker="o", label="EQE")
                    ax_cell.set_ylim(bottom=0, top=max(0.01, 1.05 * max(IPCE_arr)))

                ax_ref.set_ylabel("Integrated current (mA/cm2)")
                if len(int_curr_arr) > 0:
                    ax_ref.plot(measured_wavelengths, int_curr_arr, label="Integrated current")
                    ax_ref.set_ylim(bottom=0, top=max(0.0001, 1.05 * int_curr_arr[-1]))

                lines1, labels1 = ax_cell.get_legend_handles_labels()
                lines2, labels2 = ax_ref.get_legend_handles_labels()
                if lines1 or lines2:
                    ax_cell.legend(lines1 + lines2, labels1 + labels2)

                ax_cell.set_title("EQE Measurement")

            elif show_raw_signal:
                ax_cell.set_ylabel("Signal cell (A)")
                ax_ref.set_ylabel("Signal ref. (A)")
                ax_cell.set_xlim(nm_lim)

                if len(signal_B_arr) > 0:
                    ax_cell.plot(measured_wavelengths, signal_B_arr, marker="o", label="test cell")
                    y_max = 1.05 * max(signal_B_arr)
                    y_min = min(0, 1.05 * min(signal_B_arr))
                    ax_cell.set_ylim(bottom=y_min, top=y_max if y_max != y_min else y_max + 1e-12)

                if len(signal_A_arr) > 0:
                    ax_ref.plot(measured_wavelengths, signal_A_arr, marker="o", label="ref cell")
                    y_max = 1.05 * max(signal_A_arr)
                    y_min = min(0, 1.05 * min(signal_A_arr))
                    ax_ref.set_ylim(bottom=y_min, top=y_max if y_max != y_min else y_max + 1e-12)

                lines1, labels1 = ax_cell.get_legend_handles_labels()
                lines2, labels2 = ax_ref.get_legend_handles_labels()
                if lines1 or lines2:
                    ax_cell.legend(lines1 + lines2, labels1 + labels2)

                ax_cell.set_title("Raw signal")

            canvas.draw()
            try:
                canvas.flush_events()
            except Exception:
                pass

        df_IPCE = EQE.perform_measurement(
            self.mono,
            self.smu,
            df_incbeamcurr,
            params.calibration_measurement,
            (params.wl_start, params.wl_stop),
            delta_nm=params.interval,
            show_raw_signal=params.show_raw,
            gui=gui,          # still passed because mono.goto_nm uses gui/root for status during filter/grating switching
            root=root,
            on_live_update=on_live_update,
            on_status=on_status,
            stop_requested=stop_requested,
            on_point_acquired=on_point_acquired,
        )
        return df_IPCE
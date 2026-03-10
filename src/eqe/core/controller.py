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

        df_IPCE = EQE.perform_measurement(
            self.mono,
            self.smu,
            df_incbeamcurr,
            params.calibration_measurement,
            (params.wl_start, params.wl_stop),
            delta_nm=params.interval,
            show_raw_signal=params.show_raw,
            gui=gui,              # keep plotting through legacy gui
            root=root,            # keep mono.goto_nm status updates working
            on_live_update=on_live_update,
            on_status=on_status,
            stop_requested=stop_requested,
        )
        return df_IPCE
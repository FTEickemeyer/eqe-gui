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

    def run_measurement(
        self,
        df_incbeamcurr,
        calibration_measurement,
        nm_lim,
        interval,
        show_raw,
        gui,
        root
    ):
        df_IPCE = EQE.perform_measurement(
            self.mono,
            self.smu,
            df_incbeamcurr,
            calibration_measurement,
            nm_lim,
            delta_nm=interval,
            show_raw_signal=show_raw,
            gui=gui,
            root=root
        )
        return df_IPCE
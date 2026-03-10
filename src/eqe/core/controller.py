from eqe.core import eqe_main_legacy as EQE
from eqe.config.config_loader import load_config
from eqe.core.models import MeasurementParams


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

    def run_measurement(self, params: MeasurementParams, df_incbeamcurr, gui, root):
        df_IPCE = EQE.perform_measurement(
            self.mono,
            self.smu,
            df_incbeamcurr,
            params.calibration_measurement,
            (params.wl_start, params.wl_stop),
            delta_nm=params.interval,
            show_raw_signal=params.show_raw,
            gui=gui,
            root=root
        )
        return df_IPCE
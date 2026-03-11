import threading

from eqe.config.config_loader import load_config
from eqe.core.instruments.factory import initialize_system
from eqe.core.measurement_engine import perform_measurement


class MeasurementController:
    def __init__(self):
        self.mono = None
        self.smu = None
        self.config = load_config()

        self._measurement_thread = None
        self._stop_event = threading.Event()
        self._measurement_running = False

    @property
    def is_measuring(self):
        return self._measurement_running

    def connect_instruments(self, mono=None, smu=None, N=None, nplc=None, interval=None):
        if N is None:
            N = self.config["measurement"]["N"]
        if nplc is None:
            nplc = self.config["measurement"]["nplc"]
        if interval is None:
            interval = self.config["measurement"]["interval"]

        self.mono, self.smu = initialize_system(
            mono=mono,
            smu=smu,
            N=N,
            nplc=nplc,
            interval=interval,
        )
        return self.mono, self.smu

    def request_stop(self):
        self._stop_event.set()

    def stop_requested(self):
        return self._stop_event.is_set()

    def _emit(self, callback, ui_dispatch, *args, **kwargs):
        if callback is None:
            return
        if ui_dispatch is None:
            callback(*args, **kwargs)
        else:
            ui_dispatch(callback, *args, **kwargs)

    def run_measurement_async(
        self,
        params,
        df_incbeamcurr,
        nm_lim,
        callbacks=None,
        ui_dispatch=None,
    ):
        if self._measurement_running:
            raise RuntimeError("A measurement is already running.")

        if self.mono is None or self.smu is None:
            raise RuntimeError("Instruments are not connected.")

        callbacks = callbacks or {}
        self._stop_event.clear()
        self._measurement_running = True

        def worker():
            try:
                df_ipce = perform_measurement(
                    self.mono,
                    self.smu,
                    df_incbeamcurr,
                    params.calibration_measurement,
                    nm_lim,
                    delta_nm=params.interval,
                    show_raw_signal=params.show_raw,
                    stop_when_zero=params.stop_when_zero,
                    on_live_update=lambda message: self._emit(
                        callbacks.get("on_live_update"), ui_dispatch, message
                    ),
                    on_status=lambda message: self._emit(
                        callbacks.get("on_status"), ui_dispatch, message
                    ),
                    stop_requested=self.stop_requested,
                    on_point_acquired=lambda **payload: self._emit(
                        callbacks.get("on_point_acquired"), ui_dispatch, **payload
                    ),
                )

                self._emit(callbacks.get("on_done"), ui_dispatch, df_ipce)

            except Exception as exc:
                self._emit(callbacks.get("on_error"), ui_dispatch, exc)

            finally:
                self._measurement_running = False
                self._emit(callbacks.get("on_finished"), ui_dispatch)

        self._measurement_thread = threading.Thread(
            target=worker,
            daemon=True,
        )
        self._measurement_thread.start()
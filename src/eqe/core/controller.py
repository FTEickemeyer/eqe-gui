import threading
import traceback

from eqe.config.load_config import load_config
from eqe.core.instruments.factory import initialize_system
from eqe.core.measurement_engine import (
    perform_measurement,
    perform_live_monitoring,
)
from eqe.core.models import LIVE_MODES

class MeasurementController:
    def __init__(self):
        self.hardware = None
        self.config = load_config()

        self._measurement_thread = None
        self._stop_event = threading.Event()
        self._measurement_running = False

        # What `simulate`/`simulate_profile` self.hardware was actually
        # built with, so a changed toggle triggers a reconnect instead of
        # silently reusing the wrong (real vs. simulated) instruments.
        self._connected_simulate = None
        self._connected_simulate_profile = None

        # Target wavelength for an active live-monitoring run. A plain
        # float attribute rather than a lock/Event: CPython's GIL makes a
        # single attribute's get/set atomic, so it's safe to write from
        # the GUI thread (wavelength panel's valueChanged) and poll from
        # the measurement worker thread (perform_live_monitoring) without
        # extra synchronization -- same reasoning as _measurement_running.
        self._live_target_wavelength = None

    @property
    def mono(self):
        """
        Backward-compatible accessor for the monochromator.

        The GUI reads `controller.mono` directly (e.g. to return it to
        550 nm on stop); `controller.hardware.monochromator` is the
        canonical reference.
        """
        return self.hardware.monochromator if self.hardware is not None else None

    @property
    def is_measuring(self):
        return self._measurement_running

    def connect_instruments(
        self,
        mono=None,
        smu=None,
        N=None,
        nplc=None,
        interval=None,
        simulate=False,
        simulate_profile="good_cell",
        ):
        # --------------------------------------------------
        # Reuse already connected instruments -- but only if they match
        # the requested simulate/simulate_profile. Toggling Simulation in
        # the GUI and clicking Start again is an explicit request for
        # different hardware, not an accidental reconnect.
        # --------------------------------------------------
        if (
            self.hardware is not None
            and self._connected_simulate == simulate
            and self._connected_simulate_profile == simulate_profile
        ):
            print("Reusing existing instrument connections.")
            return self.hardware

        # --------------------------------------------------
        # Otherwise initialize new ones
        # --------------------------------------------------
        self.hardware = initialize_system(
            hardware=self.hardware,
            N=N,
            nplc=nplc,
            interval=interval,
            simulate=simulate,
            simulate_profile=simulate_profile,
        )
        self._connected_simulate = simulate
        self._connected_simulate_profile = simulate_profile

        return self.hardware

    def request_stop(self):
        self._stop_event.set()

    def stop_measurement(self):
        """
        Request the currently running measurement to stop.

        This method is called by the GUI stop button.
        The measurement loop checks this flag between wavelength steps
        and during interruptible sleeps.
        """
        self.request_stop()

    def stop_requested(self):
        return self._stop_event.is_set()

    def set_live_wavelength(self, nm):
        """
        Set the target wavelength for an active (or about-to-start) live
        measurement. Safe to call from the GUI thread while the
        measurement worker thread is running -- see _live_target_wavelength.

        Truncated to whole nm: the calibration table is interpolated to
        an integer-nm grid (see analysis/calibration.py), matching the
        rest of the codebase's convention of treating wavelengths as
        integer nm despite the GUI spin boxes allowing a decimal.
        """
        self._live_target_wavelength = float(int(nm))

    def get_live_wavelength(self):
        return self._live_target_wavelength

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
        bias_enabled=False,
        bias_voltage=0.0,
        compliance_current=1e-3,
        direction="Ascending",
        stabilization_time_s=0.0,
        callbacks=None,
        ui_dispatch=None,
    ):
        if self._measurement_running:
            raise RuntimeError("A measurement is already running.")

        if self.hardware is None:
            raise RuntimeError("Instruments are not connected.")

        callbacks = callbacks or {}
        self._stop_event.clear()
        self._measurement_running = True

        def worker():
            try:
                if getattr(params, "mode", None) in LIVE_MODES:
                    wavelength_nm = params.wl_start

                    df_ipce = perform_live_monitoring(
                        self.hardware,
                        df_incbeamcurr,
                        wavelength_nm=wavelength_nm,

                        bias_enabled=bias_enabled,
                        bias_voltage=bias_voltage,
                        compliance_current=compliance_current,

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
                        get_target_wavelength=self.get_live_wavelength,
                        stabilization_time_s=stabilization_time_s,
                    )

                else:
                    df_ipce = perform_measurement(
                        self.hardware,
                        df_incbeamcurr,
                        params.calibration_measurement,
                        nm_lim,
                        delta_nm=params.interval,
                        show_raw_signal=params.show_raw,
                        stop_when_zero=params.stop_when_zero,

                        bias_enabled=bias_enabled,
                        bias_voltage=bias_voltage,
                        compliance_current=compliance_current,
                        grating_change_nm=self.config["calibration"]["grating_change_nm"],
                        direction=direction,
                        stabilization_time_s=stabilization_time_s,

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
                # The GUI only logs str(exc); print the full traceback to the
                # console so the failing call site is diagnosable.
                traceback.print_exc()
                self._emit(callbacks.get("on_error"), ui_dispatch, exc)

            finally:
                self._measurement_running = False
                self._emit(callbacks.get("on_finished"), ui_dispatch)

        self._measurement_thread = threading.Thread(
            target=worker,
            daemon=True,
        )
        self._measurement_thread.start()

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Any
import threading

from eqe.core import eqe_main_legacy as EQE


@dataclass
class MeasurementConfig:
    wl_min: int
    wl_max: int
    wl_step: int
    bias_voltage: float = 0.0
    stop_when_zero: bool = False


class MeasurementController:
    def __init__(self) -> None:
        self.mono = None
        self.smu = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def connect_instruments(
        self,
        mono=None,
        smu=None,
        N: int = 500,
        nplc: float = 0.01,
        interval: float = 0.002,
    ) -> tuple[Any, Any]:
        """
        Initialize instruments via legacy backend.
        """
        self.mono, self.smu = EQE.initialize_system(
            mono, smu, N=N, nplc=nplc, interval=interval
        )
        return self.mono, self.smu

    def disconnect_instruments(self) -> None:
        """
        Placeholder for later clean shutdown logic.
        """
        self.mono = None
        self.smu = None

    def stop(self) -> None:
        self._stop_event.set()

    def reset_stop_flag(self) -> None:
        self._stop_event.clear()

    def run_measurement(
        self,
        config: MeasurementConfig,
        on_status: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        For now: controller skeleton only.
        Later this will call the legacy measurement function.
        """
        self.reset_stop_flag()

        def worker() -> None:
            try:
                if on_status:
                    on_status("Measurement started.")
                # Placeholder for later integration with perform_measurement(...)
                if on_finished:
                    on_finished("Measurement finished.")
            except Exception as exc:
                if on_error:
                    on_error(str(exc))
                else:
                    raise

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
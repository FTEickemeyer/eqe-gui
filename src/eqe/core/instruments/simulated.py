import math
import time
import numpy as np


class SimulatedMonochromator:
    def __init__(self, smu=None):
        self.current_nm = 550
        self.shutter_open = False
        self.smu = smu

    def goto_nm(self, nm, on_status=None):
        self.current_nm = nm
        if self.smu is not None:
            self.smu.set_wavelength(nm)
        time.sleep(0.05)
        if on_status is not None:
            on_status(f"Simulated monochromator moved to {nm} nm")

    def shutter(self, open_: bool):
        self.shutter_open = open_


class SimulatedSMU:
    def __init__(self, noise_level=2e-9, dark_a=2e-10, dark_b=2e-10):
        self.noise_level = noise_level
        self.chA_dark = dark_a
        self.chB_dark = dark_b
        self.chA = 0.0
        self.chB = 0.0
        self.current_nm = 550

    def set_wavelength(self, nm):
        self.current_nm = nm

    def run_dual_measurement(self):
        time.sleep(0.05)

    def get_average(self):
        nm = self.current_nm

        ref_signal = (
            8e-7
            * math.exp(-((nm - 650) / 260) ** 2)
            * (1.0 + 0.04 * math.sin(nm / 35))
        )

        eqe_percent = (
            78 * math.exp(-((nm - 530) / 170) ** 2)
            + 12 * math.exp(-((nm - 760) / 85) ** 2)
        )
        eqe_percent = max(0.0, min(90.0, eqe_percent))

        test_signal = ref_signal * (eqe_percent / 100.0) * 0.85

        ref_signal += np.random.normal(0.0, self.noise_level)
        test_signal += np.random.normal(0.0, self.noise_level)

        self.chA = ref_signal + self.chA_dark
        self.chB = test_signal + self.chB_dark

        return self.chA, self.chB
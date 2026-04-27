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

    def close(self):
        self.shutter_open = False


class SimulatedSMU:
    def __init__(self, profile="good_cell", noise_level=2e-9, dark_a=2e-10, dark_b=2e-10):
        self.profile = profile
        self.noise_level = noise_level
        self.chA_dark = dark_a
        self.chB_dark = dark_b
        self.chA = 0.0
        self.chB = 0.0
        self.current_nm = 550
        self.bias_voltage = 0.0
        self.bias_enabled = False

    def set_wavelength(self, nm):
        self.current_nm = nm

    def run_dual_measurement(self):
        time.sleep(0.05)

    def get_average(self):
        nm = self.current_nm

        # Reference signal: smooth broad spectral shape
        ref_signal = (
            8e-4
            * math.exp(-((nm - 650) / 260) ** 2)
            * (1.0 + 0.04 * math.sin(nm / 35))
        )

        if self.profile == "good_cell":
            eqe_percent = (
                78 * math.exp(-((nm - 530) / 170) ** 2)
                + 12 * math.exp(-((nm - 760) / 85) ** 2)
            )
            eqe_percent = max(0.0, min(90.0, eqe_percent))
            test_signal = ref_signal * (eqe_percent / 100.0) * 0.85

        elif self.profile == "weak_cell":
            eqe_percent = (
                18 * math.exp(-((nm - 520) / 180) ** 2)
                + 4 * math.exp(-((nm - 760) / 100) ** 2)
            )
            eqe_percent = max(0.0, min(25.0, eqe_percent))
            test_signal = ref_signal * (eqe_percent / 100.0) * 0.75

        elif self.profile == "dark_cell":
            eqe_percent = 0.0
            test_signal = 0.0

        else:
            # fallback
            eqe_percent = (
                60 * math.exp(-((nm - 540) / 180) ** 2)
            )
            eqe_percent = max(0.0, min(80.0, eqe_percent))
            test_signal = ref_signal * (eqe_percent / 100.0) * 0.8

        # Add noise
        ref_signal += np.random.normal(0.0, self.noise_level)
        test_signal += np.random.normal(0.0, self.noise_level)

        # Avoid negative currents in simulation
        ref_signal = max(0.0, ref_signal)
        test_signal = max(0.0, test_signal)

        # Engine subtracts dark current, so include it here
        self.chA = ref_signal + self.chA_dark
        self.chB = test_signal + self.chB_dark

        return self.chA, self.chB

    def get_profile_name(self):
        return self.profile

    def close(self):
        pass

    def set_bias_voltage(self, V):
        self.bias_voltage = V

    def enable_output(self):
        self.bias_enabled = True

    def disable_output(self):
        self.bias_enabled = False
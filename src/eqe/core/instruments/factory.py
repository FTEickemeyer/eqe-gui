from eqe.core.instruments.monochromator import Cornerstone130
from eqe.core.instruments.smu import SMU
from eqe.core.instruments.simulated import SimulatedMonochromator, SimulatedSMU
from eqe.config.load_config import load_config


def initialize_system(
    mono=None,
    smu=None,
    N=None,
    nplc=None,
    interval=None,
    simulate=False,
    simulate_profile="good_cell",
):

    if simulate:
        sim_smu = SimulatedSMU(profile=simulate_profile)
        sim_mono = SimulatedMonochromator(smu=sim_smu)
        return sim_mono, sim_smu

    if mono is not None:
        try:
            mono.close()
        except Exception:
            print("Could not close previous monochromator connection.")

    if smu is not None:
        try:
            smu.close()
        except Exception:
            print("Could not close previous SMU connection.")

    config = load_config()
    grating_change_nm = config["calibration"]["grating_change_nm"]
    mono = Cornerstone130("COM2", grating_change_nm=grating_change_nm)
    print(mono.info)

    smu = SMU(address="GPIB1::24::INSTR", N=N, nplc=nplc, interval=interval)
    smu.upload_script()

    smu.N = 500
    smu.nplc = 0.01
    smu.interval = 0.001

    mono.shutter(True)
    smu.run_dual_measurement()
    smu.chA_dark, smu.chB_dark = smu.get_average()

    return mono, smu
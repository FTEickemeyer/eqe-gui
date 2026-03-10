from eqe.core.instruments.monochromator import Cornerstone130
from eqe.core.instruments.smu import SMU

GRATING_CHANGE_NM = 850


def initialize_system(mono=None, smu=None, N=500, nplc=0.01, interval=0.001):
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

    mono = Cornerstone130("COM2", grating_change_nm=GRATING_CHANGE_NM)
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
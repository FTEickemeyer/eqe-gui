import numpy as np
import pyvisa


class SMU:
    def __init__(self, address="GPIB1::24::INSTR", N=500, nplc=0.01, interval=0.001):
        rm = pyvisa.ResourceManager()
        self.inst = rm.open_resource(address)
        self.inst.timeout = 10000

        self.inst.write("abort")
        self.inst.write("errorqueue.clear()")
        self.inst.write("print(localnode.model)")
        self.Keithley_model = self.inst.read().strip()
        print("Model: Keithley", self.Keithley_model)

        self.inst.write("print(localnode.serialno)")
        self.SN = self.inst.read().strip()
        print("Serial number:", self.SN)

        self.t = None
        self.i_chA = None
        self.i_chB = None
        self.duration = None

        self.N = N
        self.nplc = nplc
        self.interval = interval

        self.chA_dark = None
        self.chB_dark = None
        self.chA = None
        self.chB = None
        self.bias_voltage = 0.0
        self.compliance_current = 1e-3

    def upload_script(self):
        tsp_function = '''
        loadscript "dual_current_triggered"
        function dual_current_triggered(N, nplc, interval, biasV, complianceA)
            smua.reset()
            smub.reset()
            display.smua.measure.func = display.MEASURE_DCAMPS
            display.smub.measure.func = display.MEASURE_DCAMPS

            smua.source.func = smua.OUTPUT_DCVOLTS
            smua.source.levelv = 0
            smua.measure.autorangei = smua.AUTORANGE_OFF
            smua.measure.rangei = 1e-4
            smua.source.output = smua.OUTPUT_ON

            smub.source.func = smub.OUTPUT_DCVOLTS
            smub.source.levelv = biasV
            smub.source.limiti = complianceA
            smub.measure.autorangei = smua.AUTORANGE_OFF
            smub.measure.rangei = 1e-3
            smub.source.output = smub.OUTPUT_ON

            delay(0.1)

            smua.measure.count = N
            smua.measure.nplc = nplc
            smua.measure.interval = interval

            smub.measure.count = N
            smub.measure.nplc = nplc
            smub.measure.interval = interval

            format.data = format.ASCII
            smua.nvbuffer1.clear()
            smub.nvbuffer1.clear()
            smua.nvbuffer1.appendmode = 1
            smub.nvbuffer1.appendmode = 1

            timer.reset()
            local t_start = timer.measure.t()

            smub.measure.overlappedi(smub.nvbuffer1)
            smua.measure.overlappedi(smua.nvbuffer1)

            waitcomplete()
            local t_end = timer.measure.t()
            local duration = t_end - t_start

            print("STARTDATA")
            for i = 1, N do
                local t = (i - 1) * interval
                print(string.format("%.6f\t%.6e\t%.6e", t, smua.nvbuffer1[i], smub.nvbuffer1[i]))
            end
            print("ENDDATA")
            print("DURATION:" .. string.format("%.6f", duration))

            smua.source.output = smua.OUTPUT_OFF
            smub.source.output = smub.OUTPUT_OFF
            smua.nvbuffer1.clear()
            smub.nvbuffer1.clear()
        end
        endscript
        '''
        self.inst.write(tsp_function)
        self.inst.write('script.run("dual_current_triggered")')
        print("TSP function uploaded and started successfully.")

    def run_dual_measurement(self):
        self.inst.write("abort")
        self.inst.write("errorqueue.clear()")
        self.inst.write(
            f"dual_current_triggered({self.N}, {self.nplc}, {self.interval}, {self.bias_voltage}, {self.compliance_current})"
        )
        lines = []
        while True:
            try:
                line = self.inst.read().strip()
                lines.append(line)
                if "ENDDATA" in line:
                    break
            except Exception as e:
                print("Read timeout or error:", e)
                break

        try:
            line = self.inst.read().strip()
            lines.append(line)
        except Exception:
            pass

        t, i_chA, i_chB = [], [], []
        duration = None
        in_data = False

        for line in lines:
            if line == "STARTDATA":
                in_data = True
                continue
            elif line == "ENDDATA":
                in_data = False
                continue
            elif line.startswith("DURATION:"):
                try:
                    duration = float(line.split(":")[1])
                except Exception:
                    duration = None
            elif in_data:
                try:
                    ts, cur1, cur2 = map(float, line.split())
                    t.append(ts)
                    i_chA.append(cur1)
                    i_chB.append(cur2)
                except Exception:
                    continue

        self.t = t
        self.i_chA = np.asarray(i_chA)
        self.i_chB = np.asarray(i_chB)
        self.duration = duration

    def set_bias_voltage(self, V):
        """
        Set DC bias voltage on channel B (test cell).
        """
        self.bias_voltage = V

    def set_compliance_current(self, I):
        self.compliance_current = I
    
    def enable_output(self):
        """
        Enable SMU outputs.
        """
        self.inst.write("smua.source.output = smua.OUTPUT_ON")
        self.inst.write("smub.source.output = smub.OUTPUT_ON")

    def disable_output(self):
        """
        Disable SMU outputs.
        """
        self.inst.write("smua.source.output = smua.OUTPUT_OFF")
        self.inst.write("smub.source.output = smub.OUTPUT_OFF")

    def get_average(self):
        return np.mean(self.i_chA), np.mean(self.i_chB)

    def close(self):
        self.inst.close()
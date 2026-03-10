import os
import time
import datetime
import math
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from IPython import display
import keyboard
from typing import Dict, Union
import serial
from collections import namedtuple
from tkinter import messagebox

import pyvisa
#import pymeasure
#from pymeasure.adapters import VISAAdapter
#from pymeasure.instruments.srs import SR830
#from pymeasure.instruments.keithley import Keithley2600

from FTE_analysis_libraries import General as gen
from FTE_analysis_libraries import Spectrum as spc

trapz = getattr(np, "trapz", np.trapezoid)

Response = namedtuple('Response', ['statement', 'response'])
grating_change_nm = 850 #680

class Cornerstone130:
    """
    use:
    mono = Cornerstone130('COM2')
    mono.shutter(True) : close shutter
    mono.shutter(False) : open shutter
    mono.goto_nm(800)
    mono.shuttered
    mono.position
    mono.disconnect()

    Gratings
    grating 1, 600 lines, grating blaze: 370 nm  
    grating 2, 600 lines, grating blaze: 1000 nm  
      
    Filters  
    filter 1, 2, 5: none  
    filter 3: 591 nm long pass filter  
    filter 4, 6: black  
      
    Grating 1, filter 2
    set position (nm) - real position (nm)
    0 - 0
    400 - 401
    550 - 550
    700 - 698
    800 - 800.5
    860 - 861
    950 - 952
    1010  - not measurable
    
    Grating 2, filter 2
    700 - 700
    800 - 800
    860  - 863
    950 - 952
    1010 - 1012
    
    use filter 2 and from 350 nm to 620 nm
    use filter 3 from 620 nm onwards
    use grating 1 until 750 nm
    use grating 2 from 750 nm onwards

    Additional info: https://pypi.org/project/oriel-cornerstone-260/
    
    """
    
    def __init__(self, port: str, timeout: int = 5, grating_change_nm: int = 850):
        """
        Creates a new Monochromator.

        :param port: Device port.
        :param timeout: Communication timeout.
        """
        self.port = port
        self.term_chars = '\r\n'
        self.encoding = 'utf-8'
        self._com = serial.Serial(port, timeout = timeout)
        self.filter = self.filter_wheel_position
        self.grating_change_nm = grating_change_nm


    def __del__(self):
        """
        Closes serial port connection safely during object destruction.
        """
        com = self.__dict__.get("_com", None)
        if com is not None:
            try:
                if com.is_open:
                    com.close()
            except Exception:
                pass


    def __getattr__(self, attr: str):
        """
        Pass unknown attributes to serial.

        :param attr: Attribute.
        """
        return getattr(self._com, attr)

    #--- low level methods ---

    def connect(self):
        """
        Connects to the device.
        """
        self._com.open()


    def disconnect(self):
        """
        disconnects from the device.
        """
        self._com.close()


    def write(self, msg: str) -> int:
        """
        Writes a message to the monochromator.

        :param msg: Message to send.
        :returns: Number of bytes written.
        """
        msg += self.term_chars
        msg = msg.upper()
        msg = msg.encode(self.encoding)
        return self._com.write(msg)


    def read(self) -> str:
        """
        Reads the buffer of the monochromator.

        :returns: The response.
        """
        resp = self._com.read_until(self.term_chars.encode(self.encoding))
        resp = resp.decode(self.encoding)
        return resp


    def command(self, cmd: str, *args) -> str:
        """
        Sends a command to the monochromator.

        :param msg: Message to send.
        :returns: Command sent.
        """
        args = map(str, args)
        msg = cmd + ' ' +  ' '.join(args)

        self.write(msg)
        return self.read().rstrip()


    def query(self, msg: str) -> Response:
        """
        Queries the monochromator.
        Equivalent to doing a write(msg) then a read().

        :param msg: Query message. '?' added if needed.
        :returns: A dictionary object containing the statement and response.
        """
        if msg[-1] != '?':
            msg += '?'

        self.write(msg)

        statement = self.read().rstrip()
        response  = self.read().rstrip()
        return Response(statement = statement, response = response)


    #--- high level methods ---

    @property
    def info(self) -> str:
        """
        :returns: Device info.
        """
        resp = self.query('info')
        return resp.response


    @property
    def position(self) -> float:
        """
        :returns: Current wavelength position in nanometers.
        """
        resp = self.query('wave')
        resp = resp.response
        return float(resp)


    def step(self, steps: int):
        """
        Moves the monochromator a given number of steps.

        :param steps: Number of steps to move.
        """
        self.command('step', steps)


    def abort(self):
        """
        Halts the monochromator.
        """
        self.command('abort')


    @property
    def grating(self) -> Dict[str, Union[str, int]]:
        """
        :returns: Current grating's properties.
            Dictionary with keys ['number', 'lines', 'label'].
        """
        resp = self.query('grat')
        resp = resp.response.split(',')
        return {
            'number': int(resp[0]),
            'lines':  int(resp[1]),
            'label':  resp[2]
        }


    def set_grating(self, grating: int):
        """
        Sets the grating.

        :param grating: Number of the grating.
        """
        self.command('grat', grating)


    @property
    def filter_wheel_position(self) -> int:
        """
        :returns: Current filter position.
        """
        resp = self.query('filter')
        resp = resp.response
        return int(resp)
    

    def set_filter(self, pos: int):
        """
        Sets the filter to the given position.

        :param filter: Filter position to move to.
        """
        self._validate_filter(pos)
        self.command('filter', pos)
        self.filter = pos


    def filter_label(self, filter: int, label: Union[None, str] = None) -> str:
        """
        Gets or sets a filter's label.

        :param filter: Number of the filter.
        :param label: If None, gets the filter's label.
            Otherwise, the label to assign.
        :returns: The filter's current label.
        :raises ValueError: If label is invalid.
        """
        self._validate_filter()
        cmd = f'filter{filter}label'

        if label is not None:
            if len(label) > 8:
                raise ValueError('Label is too long, must be less than 9 characters.')
            
            self.command(cmd, label)
            
        resp = self.query(cmd)
        return resp.response


    @property
    def shuttered(self) -> bool:
        """
        :returns: True if shutter is close , False if open
        """
        resp = self.query('shutter')
        return (resp.response == 'C')


    def shutter(self, close: bool = True):
        """
        Opens or closes the shutter.

        :param close: True to close the shutter, False to open.
            [Default: True]
        """
        cmd = 'C' if close else 'O'
        self.command('shutter', cmd)


    @property
    def outport(self) -> int:
        """
        :returns: The output port number.
        """
        resp = self.query('outport')
        return int(resp.response)


    def set_outport(self, port: int):
        """
        Sets the ouput port.

        :param port: Output port to set.
        """
        self.command('outport', port)


    def slit_width(self, slit: int, width: Union[int, None] = None) -> int:
        """
        Gets or sets the slit width.

        :param slit: Slit number.
        :param width: If None, returns current slit width.
            If a number, sets the slit width in microns.
            [Default: None]
        :returns: Slit width in microns.
        """
        cmd = f'slit{slit}microns'
        if width is not None:
            self.command(cmd, width)

        resp = self.query(cmd)
        return int(resp.response)


    @staticmethod
    def _validate_filter(pos: int) -> bool:
        """
        Validates a filter position.

        :param pos: Filter position to validate.
        :returns: True if filter position is valid.
        :raises ValueError: If filter position is invalid.
        """
        MIN_VAL = 1
        MAX_VAL = 6

        if (pos < MIN_VAL) or (pos > MAX_VAL):
            raise ValueError(f'Invalid filter value. Must be between {MIN_VAL} and {MAX_VAL}.')
        
        return True

    def goto(self, nm):
        wavelength = f'{nm:.3f}'
        self.command('gowave', wavelength)

    def goto_nm(self, nm, gui=None, root=None, wait=True):
        #Grating change at 705 nm, this is when both gratings yield the same intensity
        if (nm >= 0) and (nm <= 1200):
            if nm < 680:
                if self.filter == 3:
                    if gui is not None:
                        gui["status_var"].set(f"Switching filter...")
                        root.update_idletasks()
                    self.set_filter(2)
                    time.sleep(9)
                    if gui is not None:
                        gui["status_var"].set(f"")
                        root.update_idletasks()
            else:
                if self.filter == 2:
                    if gui is not None:
                        gui["status_var"].set(f"Switching filter...")
                        root.update_idletasks()
                    self.set_filter(3)
                    time.sleep(4)
                    if gui is not None:
                        gui["status_var"].set(f"")
                        root.update_idletasks()

            if nm < self.grating_change_nm:
                if self.grating['number'] == 2:
                    if gui is not None:
                        gui["status_var"].set(f"Switching grating...")
                        root.update_idletasks()
                    self.set_grating(1)
                    self.goto(nm)
                    if wait:
                        time.sleep(21)
                    if gui is not None:
                        gui["status_var"].set(f"")
                        root.update_idletasks()
                else:
                    self.goto(nm)
                    time.sleep(0.2)
            else:
                if self.grating['number'] == 1:
                    if gui is not None:
                        gui["status_var"].set(f"Switching grating...")
                        root.update_idletasks()
                    self.set_grating(2)
                    self.goto(nm)
                    if wait:
                        time.sleep(26)
                    if gui is not None:
                        gui["status_var"].set(f"")
                        root.update_idletasks()
                else:
                    self.goto(nm)
                    time.sleep(0.2)


"""
class LockIn(SR830):
    
    def __init__(self, address="GPIB::8"):
        self.address = address
        self.adapter = VISAAdapter(self.address)
        super(LockIn, self).__init__(self.adapter)
        print(self.id)
        self.reset()
        self.reference_source = 'External'
        self.aux_out_1 = 1.5
        time.sleep(3)
        self.input_config = 'A'
        self.channel1 = 'X'
        self.channel2 = 'Y'
        self.time_constant = 1.0 #s
        self.sensitivity = 1.0 #V
        print(f'Frequency {self.frequency} Hz')
"""

class SMU:
    def __init__(self, address = "GPIB1::24::INSTR", N=500, nplc=0.01, interval=0.001):
        #address = 'COM3'        
        rm = pyvisa.ResourceManager()
        self.inst = rm.open_resource(address)
        self.inst.timeout = 10000
        self.inst.write('abort')
        self.inst.write('errorqueue.clear()')
        self.inst.write('print(localnode.model)')
        self.Keithley_model = self.inst.read().strip()
        print("Model: Keithley", self.Keithley_model)
        self.inst.write('print(localnode.serialno)')
        self.SN = self.inst.read().strip()
        print("Serial number:", self.SN)
        self.t = None
        self.i_chA = None
        self.i_chB = None
        self.duration = None
        self.N=N
        self.nplc=nplc
        self.interval=interval
        self.chA_dark = None
        self.chB_dark = None

    def upload_script(self):
        tsp_function = '''
        loadscript "dual_current_triggered"
        function dual_current_triggered(N, nplc, interval)
            smua.reset()
            smub.reset()
            display.smua.measure.func = display.MEASURE_DCAMPS
            display.smub.measure.func = display.MEASURE_DCAMPS
            -- Configure SMUA and SMUB as voltage sources
            smua.source.func = smua.OUTPUT_DCVOLTS
            smua.source.levelv = 0
            -- smua.measure.autorangei = smua.AUTORANGE_ON
            smua.measure.autorangei = smua.AUTORANGE_OFF
            smua.measure.rangei = 1e-4
            smua.source.output = smua.OUTPUT_ON
        
            smub.source.func = smub.OUTPUT_DCVOLTS
            smub.source.levelv = 0
            -- smub.measure.autorangei = smub.AUTORANGE_ON 
            smub.measure.autorangei = smua.AUTORANGE_OFF
            smub.measure.rangei = 1e-3

            smub.source.output = smub.OUTPUT_ON
        
            delay(0.1)  -- Let bias stabilize
        
            -- Configure measurement parameters
            smua.measure.count = N
            smua.measure.nplc = nplc
            smua.measure.interval = interval
        
            smub.measure.count = N
            smub.measure.nplc = nplc
            smub.measure.interval = interval
        
            -- Prepare buffers
            format.data = format.ASCII 
            smua.nvbuffer1.clear()
            smub.nvbuffer1.clear()
            smua.nvbuffer1.appendmode = 1
            smub.nvbuffer1.appendmode = 1
        
            -- Start simultaneous buffered current measurements
            timer.reset()
            local t_start = timer.measure.t()
        
            smub.measure.overlappedi(smub.nvbuffer1)
            smua.measure.overlappedi(smua.nvbuffer1)
        
            waitcomplete()
            local t_end = timer.measure.t()
            local duration = t_end - t_start
        
            -- Print timestamped data
            print("STARTDATA")
            --printbuffer(1, N, smua.nvbuffer1)
            for i = 1, N do
                local t = (i - 1) * interval
                print(string.format("%.6f\t%.6e\t%.6e", t, smua.nvbuffer1[i], smub.nvbuffer1[i]))
            end
            print("ENDDATA")
            print("DURATION:" .. string.format("%.6f", duration))
        
            -- Turn off outputs
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
        """
        Reads full buffered output from Keithley 2602 running dual_current_triggered()
        """
    
        self.inst.write('abort')
        self.inst.write('errorqueue.clear()')
    
        self.inst.write(f'dual_current_triggered({self.N}, {self.nplc}, {self.interval})')
    
        # Read all lines until we hit "ENDDATA"
        lines = []
        while True:
            try:
                line = self.inst.read().strip()
                lines.append(line)
                if "ENDDATA" in line:
                    break
            except Exception as e:
                print("⚠️ Read timeout or error:", e)
                break
    
        # Continue reading to catch duration (next line)
        try:
            line = self.inst.read().strip()
            lines.append(line)
        except:
            pass
    
        # Parse data
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
                except:
                    duration = None
            elif in_data:
                try:
                    ts, cur1, cur2 = map(float, line.split())
                    t.append(ts)
                    i_chA.append(cur1)
                    i_chB.append(cur2)
                except:
                    continue
    
        self.t = t
        self.i_chA = np.asarray(i_chA)
        self.i_chB = np.asarray(i_chB)
        self.duration = duration

    def get_average(self):
        return np.mean(self.i_chA), np.mean(self.i_chB)

    def close(self):
        self.inst.close()

def df_interpolate(df, new_index_arr):
    """
    Generates an interpolated dataframe, where the index of df is replaced by new_index_arr.

    Parameters
    ----------
    df : pandas dataframe
        The dataframe to be interpolated.
    new_index_arr : numpy array
        The new index.

    Returns
    -------
    pandas dataframeL
        with new index.

    """
    lower_limit = min(df.index.values)
    upper_limit = max(df.index.values)
    new_index_arr = new_index_arr[new_index_arr >= lower_limit]
    new_index_arr = new_index_arr[new_index_arr <= upper_limit]
    r = pd.Index(new_index_arr)
    t = df.index
    df_new = df.reindex(t.union(r)).interpolate(method='quadratic', axis='index').loc[r]
    df_new.index.name = df.index.name
    df_new.index = df_new.index.astype(type(new_index_arr[0]))
    return df_new

def measure_stabilized_LIA_signal(LIA, timeout=20):
    start_time = time.time()
    previous_sig = 0.
    while True:
        sig = LIA.magnitude
        time_now_s = time.time()-start_time
        if time_now_s > 1:
            dsdt = (sig - previous_sig) / (time_now_s  - previous_time_s)
        time.sleep(0.5)
        previous_sig = sig
        previous_time_s = time_now_s
        if (time_now_s > 1 and dsdt < 0) or (time_now_s >= timeout):
            break
    return sig


def nm_lim_ok(nm_lim, calibration_measurement, debug=False):
    if calibration_measurement:
        nm_lim = (350, 1170)
    else:
        nm_lim = (int(nm_lim[0]), int(nm_lim[1]))
        nm_lim_max =  (350, 1170)
        if nm_lim[0] > nm_lim[1]:
            print('Attention: upper nm limit is below lower nm limit!')
            return None
        if nm_lim[0] < nm_lim_max[0]:
            nm_lim = (nm_lim_max[0], nm_lim[1])
            print(f'Attention: lower nm limit too low, has to be minimum {nm_lim_max[0]}!')
        if nm_lim[1] > nm_lim_max[1]:
            nm_lim = (nm_lim[0], nm_lim_max[1])
            print(f'Attention: upper nm limit too high, has to be maximum {nm_lim_max[1]}!')
        if debug:
            print(f'nm_lim = {nm_lim}')
    return nm_lim


def create_user_directory(data_dir, user, debug=False):
    #Make new directory (if doesn't exist)
    user_dir = os.path.join(data_dir, user)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    format_dt = "%Y-%m-%d %H:%M:%S.%f"
    datetime_object = datetime.datetime.strptime(str(datetime.datetime.now()), format_dt)
    date = datetime_object.strftime('%Y%m%d')[2:] + '_IPCE'
    user_dir = os.path.join(data_dir, user, date)
    if debug:
        print(date)
        print(user_dir)   
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir


def open_calibration(system_dir, nm_lim, calibration_measurement, debug=False):
    fp_ref_cell = os.path.join(system_dir, '71889_L_IPCE_NIST.csv')
    df_ref = pd.read_csv(fp_ref_cell).set_index('Wavelength (nm)').squeeze()
    if debug:
        df_ref.plot()
        plt.title('Reference cell')
        plt.ylabel('IPCE (%)')
        plt.show()

    if not calibration_measurement:
        FN_root = 'incbeamcurr'
        FNs = os.listdir(system_dir)
        FN_incbeamcurr = [FN for FN in FNs if (FN_root in FN) and (f'{grating_change_nm}' in FN)][-1]
        if debug:
            print(FN_incbeamcurr)
        fp_incbeamcurr = os.path.join(system_dir, FN_incbeamcurr)
        df_incbeamcurr = pd.read_csv(fp_incbeamcurr).set_index('Wavelength (nm)')
        #Interpolate an a nm level
        nm_arr = np.arange(nm_lim[0], nm_lim[1]+1, 1) 
        df_incbeamcurr = df_interpolate(df_incbeamcurr, nm_arr)
        if debug:
            df_incbeamcurr.plot()
            plt.show()
            df_incbeamcurr['incident beam current (A)/intSiref current (A)'].plot()
            plt.title('df_incbeamcurr')
            plt.show()
    else:
        df_incbeamcurr = None

    return df_incbeamcurr, df_ref


def initialize_system(mono, smu, N=500, nplc=0.01, interval=0.001):

    # Try closing previous handles if they exist
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

    # Initialize monochromator
    mono = Cornerstone130('COM2', grating_change_nm=grating_change_nm)
    print(mono.info)

    # Initialize Keithley2600
    smu = SMU(address="GPIB1::24::INSTR", N=N, nplc=nplc, interval=interval)
    smu.upload_script()
    smu.N = 500
    smu.nplc = 0.01
    smu.interval = 0.001

    # Measure dark signal
    mono.shutter(True)
    smu.run_dual_measurement()
    smu.chA_dark, smu.chB_dark = smu.get_average()

    return mono, smu


def perform_measurement(
    mono,
    smu,
    df_incbeamcurr,
    calibration_measurement,
    nm_lim,
    delta_nm=10,
    show_raw_signal=False,
    gui=None,
    root=None,
    on_live_update=None,
    on_status=None,
    stop_requested=None,
    on_point_acquired=None,
):
    """
    GUI-agnostic measurement loop.

    Plotting is no longer handled here.
    The backend emits progress via callbacks.
    """

    if gui is not None:
        status_var = gui.get('status_var')
        live_update_var = gui.get('live_update_var')
        stop_flag = gui.get('stop_flag')
        stop_when_zero = gui.get('stop_when_zero', False)
    else:
        status_var = None
        live_update_var = None
        stop_flag = None
        stop_when_zero = False

    if calibration_measurement:
        show_IPCE = False
        show_raw_signal = True
    else:
        show_IPCE = True

    def emit_live_update(message):
        if on_live_update is not None:
            on_live_update(message)
        elif live_update_var is not None:
            live_update_var.set(message)
            if root is not None:
                try:
                    root.update_idletasks()
                except Exception:
                    pass
        else:
            print(message)

    def emit_status(message):
        if on_status is not None:
            on_status(message)
        elif status_var is not None:
            status_var.set(message)
            if root is not None:
                try:
                    root.update_idletasks()
                except Exception:
                    pass
        elif message:
            print(message)

    def should_stop():
        if stop_requested is not None:
            try:
                return bool(stop_requested())
            except Exception:
                return False
        if stop_flag is not None:
            try:
                return bool(stop_flag.get())
            except Exception:
                return False
        return False

    mono.shutter(True)
    wavelengths = np.arange(nm_lim[0], nm_lim[1] + delta_nm, delta_nm)

    signal_A_arr = []
    signal_B_arr = []
    IPCE_arr = []
    measured_wavelengths = []
    int_curr_arr = []

    trapz_fn = getattr(np, "trapz", np.trapezoid)

    for nm in wavelengths:
        try:
            if should_stop():
                emit_live_update("Measurement stopped by user.")
                break

            mono.goto_nm(nm, gui=gui, root=root)
            mono.shutter(False)

            if nm == nm_lim[0] or nm == grating_change_nm:
                time.sleep(2)

            smu.run_dual_measurement()
            smu.chA, smu.chB = smu.get_average()

            intSiref_current = smu.chA - smu.chA_dark
            cell_current = smu.chB - smu.chB_dark

            IPCE = None
            if not calibration_measurement:
                incbeamcurr_div_intSirefcurrent = df_incbeamcurr[
                    'incident beam current (A)/intSiref current (A)'
                ].loc[nm]
                IPCE = cell_current / (incbeamcurr_div_intSirefcurrent * intSiref_current)
                if IPCE < 0.0:
                    IPCE = 0.0
                IPCE_arr.append(IPCE)
                current_IPCE_arr = np.array(IPCE_arr)

            signal_A_arr.append(intSiref_current)
            signal_B_arr.append(cell_current)
            measured_wavelengths.append(nm)
            current_nm_arr = np.array(measured_wavelengths)

            int_curr = None
            if show_IPCE:
                if nm > nm_lim[0] and len(current_IPCE_arr) >= 2:
                    try:
                        sp = spc.diff_spectrum.AM15_nm(
                            left=current_nm_arr[0],
                            right=current_nm_arr[-1],
                            delta=delta_nm
                        )
                        int_curr = trapz_fn(
                            current_IPCE_arr / 100 * sp.y * gen.q * 1e3 / 1e4,
                            dx=delta_nm
                        )
                    except Exception as e:
                        print(f"Integration failed: {e}")
                        int_curr = 0.0
                else:
                    int_curr = 0.0
                int_curr_arr.append(int_curr)

            if show_raw_signal:
                emit_live_update(
                    f'nm = {nm} nm - signal ref. cell (chA) = {intSiref_current:.2e} A '
                    f'- signal test cell (chB) = {cell_current:.2e} A'
                )

            if show_IPCE:
                emit_live_update(
                    f'Wavelength = {nm} nm - IPCE = {IPCE:.1f} %\n'
                    f'Integrated current = {int_curr:.2f} mA/cm2'
                )

            if on_point_acquired is not None:
                on_point_acquired(
                    nm=nm,
                    measured_wavelengths=list(measured_wavelengths),
                    signal_A_arr=list(signal_A_arr),
                    signal_B_arr=list(signal_B_arr),
                    IPCE_arr=list(IPCE_arr),
                    int_curr_arr=list(int_curr_arr),
                    intSiref_current=intSiref_current,
                    cell_current=cell_current,
                    IPCE=IPCE,
                    int_curr=int_curr,
                    show_IPCE=show_IPCE,
                    show_raw_signal=show_raw_signal,
                    nm_lim=nm_lim,
                )

            if stop_when_zero and cell_current is not None and abs(cell_current) < 1e-7:
                emit_status("Measurement stopped because signal reached zero threshold.")
                break

        except KeyboardInterrupt:
            break

    mono.shutter(False)
    mono.goto_nm(550, gui=gui, root=root)

    if not calibration_measurement:
        df = pd.DataFrame({
            'Wavelength (nm)': np.asarray(measured_wavelengths),
            'EQE (%)': np.asarray(IPCE_arr),
            'Integrated current (mA/cm2)': np.asarray(int_curr_arr),
            'Current ref-chA (A)': np.asarray(signal_A_arr),
            'Current cell-chB (A)': np.asarray(signal_B_arr)
        })
    else:
        df = pd.DataFrame({
            'Wavelength (nm)': np.asarray(measured_wavelengths),
            'Current ref-chA (A)': np.asarray(signal_A_arr),
            'Current cell-chB (A)': np.asarray(signal_B_arr)
        })

    df.set_index('Wavelength (nm)', inplace=True)
    return df


def save_data(df, df_ref, sample_name, user_dir, system_dir, calibration_measurement, save_raw_data=False, debug=False, fig=None):
    dat_time = str(datetime.datetime.now())
    dat_time_file = dat_time.split('.')[0].replace(':', '-').replace(' ', '_time')
    fp_IPCE = os.path.join(user_dir, f'EQE_{sample_name}_date{dat_time_file}.csv')
    if save_raw_data or calibration_measurement:
        df.to_csv(fp_IPCE)
    else:
        df[['EQE (%)', 'Integrated current (mA/cm2)']].to_csv(fp_IPCE)
    if fig is not None:
        fp_fig = os.path.join(user_dir, f'EQE_{sample_name}_date{dat_time_file}.png')
        fig.savefig(fp_fig, dpi=300, bbox_inches='tight')
    print(f'File saved: {fp_IPCE}')
    if calibration_measurement:
        df_ref_interpol = df_interpolate(df_ref, df.index)
        df['IPCE Siref (%)'] = df_ref_interpol.values
        df['incident beam current (A)'] = df['Current cell-chB (A)'] / df['IPCE Siref (%)']
        df['incident beam current (A)/intSiref current (A)'] = df['incident beam current (A)'] / df['Current ref-chA (A)']
        fp_incbeamcurr = os.path.join(system_dir, f'incbeamcurr_{sample_name}_{grating_change_nm}nm-wavelength-change_date{dat_time_file}.csv')
        df[['Current ref-chA (A)', 'Current cell-chB (A)', 'incident beam current (A)/intSiref current (A)']].to_csv(fp_incbeamcurr)
        if debug:
            df['incident beam current (A)/intSiref current (A)'].plot()

    return fp_IPCE

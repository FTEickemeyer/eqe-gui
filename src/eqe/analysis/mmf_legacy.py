""" **Calculation of Spectral mismatch factor**

_by Felix Eickemeyer_

_This notebook calculates the spectral mismatch factor_

_Version 18.01.2022 in Python 3_

Change log:  
ver 11: New integration for photocurrent used, np.trapz instead of sum  
ver 12: New data directories introduced  
12.01_1100nm: Until 1100nm, no second Si reference cell, calculation of Jsc and MMF for bandgap added at the end  
12.02: KACST version, calculation of MMF as function of bandgap  
12.10: In '\\Data\\Lamp and sun spectra\\' there is an 'old' directory which is disregarded  
12.20: Save dialog included  
13.0.0: Modules used  
13.1.0: Debugged, now it gives the same values as version 12  
13.2.0: FTE_analysis_libraries implemented  
13.3.0: Problem with unaccuracies in MMF caluclation solved 

this version is based on MMF_13.4.3.ipynb"""

# Import libraries and modules, define constants

import os

import numpy as np
import pandas as pd
import math
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import pprint

from FTE_analysis_libraries import General as gen
from FTE_analysis_libraries.General import plot_first_n_lines, Vsq, pi, h, hbar, c, k
from FTE_analysis_libraries import Tkdialogs as tk
from FTE_analysis_libraries import Spectrum as spc
from FTE_analysis_libraries import IV


file_dialog = False

# Determine if files of reference cell, lamp spectra and test cells shall be chosen
# Has to be False before transformed to standalone python code
choose_files = True

# Directroy of IPCE of test cells
#cells_directory = os.path.join(os.getcwd(), 'MMF_data', 'IPCE_test_cells')
cells_directory = r'C:\Users\labo\Documents\Data\Felix\250411_IPCE'

# File to save data
save_FN = os.path.join(os.getcwd(), 'results.csv')

# Directroy of lamp spectra
lamps_directory = os.path.join(os.getcwd(), 'MMF_data', 'PF_lamp_spectra')

# Directroy of IPCE of reference cells
ref_directory = os.path.join(os.getcwd(), 'MMF_data', 'IPCE_ref_cells')

# Import AM1.5GT spectrum
AM15GT = spc.diff_spectrum.AM15_nm()
#AM15GT.plot(left = 350, right = 1000, bottom = 0, top = 5e18, figsize = (8,5))

# Import lamp spectra

# Get filenames of lamp spectra
lamp_filenames = os.listdir(lamps_directory)
lamp_filenames.remove('all')

#for idx, lamp_FN in enumerate(lamp_filenames):
#    print(f'{idx:2} {lamp_FN}')


# Select lamp spectra, load spectra and plot

do_this = True
lamp_FNs = lamp_filenames
if do_this and choose_files:
    # order_lamps = [9, 10]
    order_lamps = [0]
    lamp_FNs = [lamp_filenames[idx] for idx in order_lamps]
    do_this = False
    # for idx, lamp_FN in enumerate(lamp_FNs):
        # print(f'{idx:2} {lamp_FN}')

lamp_PF = []
for i, FN in enumerate(lamp_FNs):
    if '.csv' in FN:
        # print(FN)
        sp = spc.diff_spectrum.load(lamps_directory, FN = FN, take_quants_and_units_from_file = True)
        lamp_PF.append(sp)

lamps = spc.diff_spectra(lamp_PF)
lamps.names_to_label(split_ch = '.csv')
m = lamps.max_within(left = 350, right = 800)
#lamps.plot(bottom = 0, top = m*1.1, showindex = False)


# Chose reference cell and import

# Get filenames of lamp spectra
ref_filenames = os.listdir(ref_directory)
ref_filenames.remove('all')

#for idx, ref_FN in enumerate(ref_filenames):
#    print(f'{idx:2} {ref_FN}')


ref_PF = []
for i, FN in enumerate(ref_filenames):
    #print(FN)

    if 'IPCE_Si1812' in FN:
    	sp = spc.EQE_spectrum.load(ref_directory, FN = FN, quants = dict(x='Wavelength', y='EQE'), units = dict(x='nm', y='%'))
    elif FN == '191126_IPCE_Si1902.txt': #This spectrum was measured at Newport
        sp = spc.EQE_spectrum.load(ref_directory, FN = FN, quants = dict(x='Wavelength', y='EQE'), units = dict(x='nm', y='%'), delimiter = '\t', header = 0)
    else:
        sp = spc.EQE_spectrum.load(ref_directory, FN = FN, take_quants_and_units_from_file=True)
        #sp = spc.EQE_spectrum.load_Cicci(ref_directory, FN = FN)

    ref_PF.append(sp)

refs = spc.spectra(ref_PF)
refs.names_to_label(split_ch = '.csv')
m = refs.max_within(left = 350, right = 800)
#refs.plot(bottom = 0, top = m*1.1, showindex = True)

# Select one reference cell spectrum, load it and plot

idx = 0
ref_IPCE = refs.sa[idx]

# Reference spectrum with short pass filter
# cut_off = 820 #  nm
# ref_IPCE = spc.EQE_spectrum.EQE100(f1240/cut_off, start = 350, stop = 1000, step = 0.5)

#ref_IPCE.plot(hline=0)



def calc_MMF_and_Jsc(cell_IPCE):

    if isinstance(cell_IPCE, spc.EQE_spectrum):
        pass
    elif isinstance(cell_IPCE, pd.Series) or isinstance(cell_IPCE, pd.DataFrame):
        cell_IPCE = spc.EQE_spectrum.from_df(cell_IPCE)
        
    use_MMF_method = False
    
    # convert is used if not the MMF method of EQE_spectrum is used. The latter is about four times slower.
    
    #Below 350 nm the lamp spectrum has very low intensity, so very unprecise
    left = max(350, cell_IPCE.x[0])
    #Lamp spectrum only measured until 850 nm (that's when the detectivity of the Gemini180 system ends)
    right = min(850, cell_IPCE.x[-1])
    delta = 0.5
    
    def convert(sp, left = left, right = right, delta = delta):
        s = sp.copy()
        s.equidist(left = left, right = right, delta = delta)
        return s
    
    if not use_MMF_method:
        AM = convert(AM15GT)
        ref = convert(ref_IPCE)
    
        
    if not use_MMF_method:
        cell = convert(cell_IPCE)
    else:
        cell = cell_IPCE

    if use_MMF_method:
        #MMF_cell_lamps.append(cell.MMF(ref_IPCE, lamp_spec, ref_PF = AM15GT, left = left, right = right, delta = delta)) #  is a bit slower
        MMF = cell.MMF(ref_IPCE, lamp_PF[0], ref_PF = AM15GT) #  is a bit slower
    else:
        lamp = convert(lamp_PF[0])
        MMF = np.trapezoid( ref.y * AM.y) * np.trapezoid(cell.y * lamp.y) / ( np.trapezoid(ref.y * lamp.y) * np.trapezoid(cell.y * AM.y) )

    return MMF, cell_IPCE.calc_Jsc()
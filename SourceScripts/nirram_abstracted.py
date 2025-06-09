# region Import necessary libraries

import pdb
import argparse
import time
from dataclasses import dataclass, asdict
import sys
from os.path import abspath
from os import getcwd
from os import remove as remove_file
import os
import nidigital
import numpy as np
import pandas as pd
import csv
from datetime import date, datetime
from BitVector import BitVector
from itertools import chain
import threading
import matplotlib.pyplot as plt
import copy

# sys.path.append(getcwd() + '\\SourceScripts')
from masks import Masks
from digital_pattern import DigitalPattern
from SourceScripts.settings_util import SettingsUtil
from debug_util import DebugUtil

# endregion

@dataclass
class RRAMCells:
    """Data class to store the BL, SL, and WL channels of an RRAM device"""
    cells: list
    wls: list
    bls: list
    bls_unsel:list
    bls_sel:list
    sls: list

@dataclass
class VoltageSettings:
    """Data class to store the voltage settings for an RRAM operation"""
    vbl: float
    vbl_unsel: float
    vsl: float
    vwl: float
    vwl_unsel: float
    vb: float

@dataclass
class RRAMPulseOperation:
    """Data class to store an RRAM operation
    (e.g. set, reset, form, etc.)
    """
    mode: str
    cells: RRAMCells
    voltages: VoltageSettings
    pw: float
    target: float

class NIRRAMException(Exception):
    """Exception produced by the NIRRAM class"""
    def __init__(self, msg):
        super().__init__(f"NIRRAM: {msg}")

class NIRRAM:
    """The NI RRAM controller class that controls the instrument drivers."""
    """  This class has fewer functions than the original NIRRAM class   """
    """  but is more general. Different cards, relays, and instruments   """
    """  can be used with this class.                                    """
    """  --------------------------------------------------------------  """
    """  The class is designed to be used with the NI PXIe-6570/1 cards  """
    """  and the NI PXIe-2527 relay cards. Given the following:          """
    """  - In the NI System PXIe 6570s have consistent PXI numbering and """
    """    6571s have consistent PXI numbering, but PXIe 6570 and 6571   """
    """    do not share the same PXI numbering. Slot numbers dont matter """    
    """        e.g. PXIe 6571s: 'PXI6571Slot9,PXI6571Slot8'              """
    """             PXIe 6570s: 'PXI6570Slot9,PXI6570Slot8'              """
    """ - Pinmaps must be listed in the same order as the PXI numbers    """
    """ - If relays are used, RELAY_CARD should be set to True and the   """
    """   relays should be listed in the configuration toml file,        """
    """ ---------------------------------------------------------------- """

    # ---------------------------------------------------------------- #
    #                 Setup and Initialization Functions               #
    # ---------------------------------------------------------------- #

    def __init__(
            self,
            chip: str,
            device: str,
            polarity: str = "PMOS",
            settings: str = "settings/MPW_Direct_Write.toml",
            test_type: str = "Dir_Write",
            additional_info: str = "",
            debug: bool = False
        ):
        """Initialize the NIRRAM class with the given settings and test type."""
        
        self.debug = debug
        self.chip = chip
        self.device = device
        self.polarity = polarity
        self.dbg = DebugUtil(debug=self.debug)
        
        self.dbg.start_function_debug(self.debug)

        # Load and set up settings
        self._initialize_settings(settings)

        # Initialize RRAM Test logging
        self._initialize_logging(test_type, additional_info)

        # Load device-specific settings and session information
        self.load_settings(self.settings_manager)
        self.load_session()

        # Initialize row selectors for rows not part of the test
        self.zero_rows = None
        self.NC_rows = None

        self.digital_patterns.ppmu_set_voltage(["DIR_PERIPH_SEL"],2,source=True)

        self.dbg.end_function_debug()

    def _initialize_settings(self, settings: str):
        """Load and set up settings."""
        self.settings_manager = SettingsUtil(settings)
        self.settings = self.settings_manager.settings
        self.settings_path = self.settings_manager.settings_path
        
        # Convert NIDigital spec paths to absolute paths
        self.settings["NIDigital"]["specs"] = [
            abspath(path) for path in self.settings["NIDigital"]["specs"]
        ]

    def _initialize_logging(self, test_type: str, additional_info: str):
        """Set up the RRAM logging."""
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        self.hash_value = self.update_data_log(
            current_date,
            current_time,
            f"chip_{self.chip}_device_{self.device}",
            test_type,
            additional_info
        )

        self.datafile_path = f"{self.settings_manager.get_setting('path.data_header')}/{test_type}/{current_date}_{self.chip}_{self.device}_{self.hash_value}.csv"


    def load_settings(self, settings_manager: SettingsUtil, debug: bool = None):
        """Load and store settings for the RRAM device."""
        self.dbg.start_function_debug(debug)

        # Store/initialize parameters
        self.target_res = settings_manager.get_setting("target_res", required=True)
        self.op = settings_manager.get_setting("op", required=True)
        self.dev = settings_manager.get_setting("device", required=True)

        # Load device settings
        self._load_device_settings(settings_manager)

        # Load relay settings
        self._load_relay_settings(settings_manager)

        # Load pulse settings
        self._load_pulse_settings(settings_manager)

        self.dbg.end_function_debug()

    def _load_device_settings(self, settings_manager: SettingsUtil):
        """Load device-specific settings from the provided settings manager."""
        self.body = settings_manager.get_setting("device.body")
        self.all_wls = settings_manager.get_setting("device.all_WLS", required=True)
        self.all_bls = settings_manager.get_setting("device.all_BLS", required=True)
        self.all_sls = settings_manager.get_setting("device.all_SLS", required=True)

        self.wls = settings_manager.get_setting("device.WLS", required=True)
        self.bls = settings_manager.get_setting("device.BLS", required=True)
        self.sls = settings_manager.get_setting("device.SLS", required=True)
        self.wl_unsel = settings_manager.get_setting("device.WL_UNSEL", required=True)

        self.WL_IN = settings_manager.get_setting("device.WL_IN", default=settings_manager.get_setting("device.WL_IN"))
        self.all_WL_IN = settings_manager.get_setting("device.all_WL_IN", default=settings_manager.get_setting("device.all_WL_IN"))

        self.zero_rows = settings_manager.get_setting("device.zero_rows", default=None)
        if self.zero_rows == []:
            self.zero_rows = None

        self.NC_rows = settings_manager.get_setting("device.NC_rows", default=None)
        if self.NC_rows == []:
            self.NC_rows = None

    def _load_relay_settings(self, settings_manager: SettingsUtil):
        """Load relay-specific settings from the provided settings manager."""
        self.relays = None
        self.relay_information = settings_manager.get_setting("NISwitch", default=None)
        
        if self.relay_information:
            self.relays = settings_manager.get_setting("NISwitch.deviceID", required=True)
            self.all_channels = [self.all_bls, self.all_sls, self.all_WL_IN]
        else:
            self.all_channels = [self.all_bls, self.all_sls, self.all_wls]

        self.all_channels_flat = self._flatten(self.all_channels)

    def _load_pulse_settings(self, settings_manager: SettingsUtil):
        """Load pulse-specific settings from the provided settings manager."""
        target_res_dict = settings_manager.get_setting("target_res", required=True)
        for mode, value in target_res_dict.items():
            self.def_target_res(mode.lower(), value)

        self.prepulse_len = settings_manager.get_setting("PULSE.prepulse_len")
        self.pulse_len = settings_manager.get_setting("PULSE.pulse_len")
        self.wl_buffer = settings_manager.get_setting("PULSE.wl_buffer")
        self.blsl_buffer = settings_manager.get_setting("PULSE.blsl_buffer")
        self.postpulse_len = settings_manager.get_setting("PULSE.postpulse_len")
        self.max_pulse_len = settings_manager.get_setting("PULSE.max_pulse_len", default=1e4)

    
    def load_session(self, debug: bool = None):
        """Initialize the NIDigital session and configure the device for operation."""
        self.dbg.start_function_debug(debug)

        # Initialize address indexes and profiles for 1T1R arrays
        self._initialize_address_indexes()

        # Load and configure the NIDigital session
        self._configure_digital_session()

        self.dbg.end_function_debug()

    def _initialize_address_indexes(self):
        """Initialize address indexes and profiles for the 1T1R array."""
        self.addr_idxs = {}
        self.addr_prof = {}

        for wl in self.wls:
            self.addr_idxs[wl] = {}
            self.addr_prof[wl] = {}
            for i, bl in enumerate(self.bls):
                sl = self.sls[i] if len(self.sls) == len(self.bls) else self.sls[0]
                self.addr_idxs[wl][bl] = (bl, sl, wl)
                self.addr_prof[wl][bl] = {"FORMs": 0, "READs": 0, "SETs": 0, "RESETs": 0}

    def _configure_digital_session(self):
        """Configure the NIDigital session."""
        self.digital_patterns = DigitalPattern(self.settings_manager,wl_unsel=True)
        self.digital = self.digital_patterns.sessions

        self.digital_patterns.configure_read(sessions=None, pins=[self.bls, self.sls], sort=False)
        self.digital_patterns.digital_all_pins_to_zero()
        self.digital_patterns.commit_all()
        self.closed_relays = []



    """ ================================================================= """
    """                    Directly Reading RRAM Cells                    """
    """  This function reads the resistance of the RRAM cells directly.   """
    """ ================================================================= """

    def direct_read(
        self,
        vbl=None,
        vsl=None,
        vwl=None,
        vwl_unsel_offset=None,
        vb=None,
        wls=None,
        bls=None,
        remove_bias=None,
        meas_vbls=True,
        meas_vsls=True,
        meas_vwls=False,
        meas_isls=True,
        meas_ibls=False,
        meas_i_gate=True,
        record=False,
        check=True,
        print_info = True,
        debug = None,
        relayed=False
    ):
        """Perform a READ operation. This operation works for single 1T1R devices and 
        arrays of devices, where each device has its own WL/BL.
        Returns list (per-bitline) of tuple with (res, cond, meas_i, meas_v)"""
        # Start debug based on debug value
        self.dbg.start_function_debug(debug)

        # The RRAM cells are selected based on provided bls and wls, sorted by session, then redistributed to wls, bls, sls
        rram_cells = self.select_memory_cells(bls=bls, wls=wls)
        wls, bls, sls = [rram_cells.wls, rram_cells.bls, rram_cells.sls]
        
        
        read_op = self.op["READ"]
        
        # Default values for read voltages based on previous testing at MIT
        vbl_default = 0.3 #Bitline read voltage at 0.3V based on the 0.1 - 0.7V read range from old measurements
        vsl_default = 0 # Sourceline Read voltage, set at 0V 
        vb_default = 0 # Set the base voltage to 0V to ground
        
        if self.polarity.upper() in ["P","PMOS","PTYPE","CNT"]:
            vwl_default = -1 # Wordline Read voltage, set at -1V to turn on without breaking down dielectric
            vwl_unsel_offset_default = 2 # Unselected wordline read voltage based on MPW wafer measurements at MIT 2-4V off range. Ideally reduced in future tests
            
        else:
            vwl_default = 1.8 # Wordline Read voltage, set at -1V to turn on without breaking down dielectric
            vwl_unsel_offset_default = 0.9 # Unselected wordline voltage offset based on 2D measurements on MPW wafer at MIT, no bias needed

        # Set the read voltage parameters based on parameter inputs if given,
        # If not specified in parameters use reference settings file,
        # If not referenced use default values in function.
        vbl = self.op["READ"][self.polarity].get("VBL", vbl_default) if vbl is None else vbl
        vsl = self.op["READ"][self.polarity].get("VSL", vsl_default) if vsl is None else vsl
        vwl = self.op["READ"][self.polarity].get("VWL", vwl_default)  if vwl is None else vwl
        vwl_unsel_offset = self.op["READ"][self.polarity].get("VWL_UNSEL_OFFSET", vwl_unsel_offset_default) if vwl_unsel_offset is None else vwl_unsel_offset
        vwl_unsel = vsl + vwl_unsel_offset
        
        vb  = self.op["READ"][self.polarity].get("VB", vb_default) if vb  is None else vb

        # print(f"VBL: {vbl}, VSL{vsl}, VWL:{vwl}")
        settling_time = read_op.get("settling_time",1E-3)

        # Initialize dataframes to store resistance, conductance, current, and voltage measurements
        self._define_measurement_dataframes(wls, bls)
        self.dbg.operation_debug("Direct Read", ["VBL, VWL, VSL, VB, VWL_UNSEL"], [vbl, vwl, vsl, vb, vwl_unsel])
        
        # let the supplies settle for accurate measurement
        self._settle(settling_time) 
        

        if self.op["READ"]["mode"] != "digital":
            NIRRAMException("READ mode must be set to 'digital' in settings.")

        if remove_bias is None:
            remove_bias = []
        
        if self.relays is not None:
            self.WL_IN = self.settings["device"]["all_WL_IN"]
        for wl,wl_bls,wl_sls in zip(wls,bls,sls):
            if self.relays is not None:
                wl_entry = wl
                wl,all_wls = self.relay_switch([wl]+remove_bias,relayed=relayed,debug=False)
                time.sleep(20e-3)
                wl = wl[0]

            self.set_to_ppmu([self.bls,self.sls],["BL","SL","DIR_PERIPH_SEL"])
            # print(f"Setting TO OFF: {self.bls}, {wl_bls}")
            if self.bls != wl_bls:
                self.set_to_off([bl for bl in self.bls if bl not in wl_bls],["BL"])
                self.set_to_off([sl for sl in self.sls if sl not in wl_sls],["SL"])

            self.digital_patterns.ppmu_set_voltage(["DIR_PERIPH_SEL"],2,source=True)
            
            # if remove_bias is not None:
            # self.set_to_off([w for w in self.WL_IN if wl not in wl_entry],["WL_IN"])

            self.set_to_off([f"WL_IN_{i}" for i in range(24)],["WL_IN"])
            pdb.set_trace()
            self._settle(2e-3)
            self.ppmu_set_vwl(["WL_UNSEL"], vwl_unsel, sort=True)
            self._settle(2e-6)
            self.ppmu_set_vwl(wl, vwl)
            self._settle(2e-6)
            self.ppmu_set_vsl(wl_sls,vsl)
            self._settle(2e-6)
            self.ppmu_set_vbl(wl_bls,vbl)
            # self.ppmu_set_vbl([bl for bl in self.bls if bl not in bls[0]],vwl/2)
            # self.ppmu_set_vsl([sl for sl in self.sls if sl not in sls[0]],vwl/2)
            
            #Let the supplies settle for accurate measurement
            self._settle(settling_time)

            # Measure selected voltage. Default is to measure VBL
            if meas_vbls:
                _,_,meas_bls_v = self.digital_patterns.measure_voltage([wl_bls,[],[]],sort=False)
                # print(f"VBL_MEAS: {meas_bls_v}")
            
            meas_vsls = True
            if meas_vsls:
                _,_,meas_sls_v = self.digital_patterns.measure_voltage([[],wl_sls,[]],sort=False)
                # print(f"VSL_MEAS: {meas_sls_v}")

            if meas_vwls:
                _,_,meas_wls_v = self.digital_patterns.measure_voltage([[],[],wl],sort=False)

            # Measure selected current, default is to measure ISL and I gate
            if meas_isls: 
                _,_,meas_sls_i = self.digital_patterns.measure_current([[],wl_sls,[]],sort=False)
                # print(f"ISL: {meas_sls_i}")

            if meas_ibls:
                _,_,meas_bls_i = self.digital_patterns.measure_current([[],[],wl_bls],sort=False)
                # print(f"IBL: {meas_bls_i}")

            if meas_i_gate:
                if type(wl) is str:
                    _,_,meas_wls_i = self.digital_patterns.measure_current([[],[],[wl]],sort=False)
                elif type(wl) is list:
                    _,_,meas_wls_i = self.digital_patterns.measure_current([[],[],wl],sort=False)
                elif type(wl) is int or type(wl) is np.uint8:
                    if self.relays is not None:
                        _,_,meas_wls_i = self.digital_patterns.measure_current([[],[],[f"WL_IN_{wl}"]],sort=False)
                    else:
                        _,_,meas_wls_i = self.digital_patterns.measure_current([[],[],[f"WL_{wl}"]],sort=False)
            self.ppmu_set_vbl(self.bls,0)
            self.ppmu_set_vsl(self.sls,0)
            self.ppmu_set_vwl(wl, 0)

            #for wl_i in remove_bias:
            #    self.ppmu_set_vwl(wl, 0)
            self.ppmu_set_vwl(["WL_UNSEL"], 0, sort=True)
            self._settle(2E-3)

            r_wl_sl = None
            r_wl_bl = None

            if meas_isls:
                r_wl_sl = np.abs((np.array(meas_bls_v) - np.array(meas_sls_v))/np.array(meas_sls_i) - self.op["READ"]["shunt_res_value"])

            if meas_ibls:
                r_wl_bl = np.abs((np.array(meas_bls_v) - np.array(meas_sls_v))/np.array(meas_bls_i) - self.op["READ"]["shunt_res_value"])
            
            if r_wl_sl is not None and r_wl_bl is not None:
                r_wl = np.where(np.logical_and(r_wl_sl != None, r_wl_bl != None), (r_wl_sl + r_wl_bl) / 2, None)
            else:
                r_wl = r_wl_sl if r_wl_sl is not None else r_wl_bl
            

            if r_wl is None:
                if meas_i_gate: 
                    print("Measuring I gate for resistance between gate and source")
                    r_wl = np.abs((self.op["READ"][self.polarity]["VWL"] - self.op["READ"][self.polarity]["VSL"])/np.array(meas_wls_i) - self.op["READ"]["shunt_res_value"])
                else:
                    print("No current measurement selected, cannot calculate resistance")
                    r_wl = None

            wl = wl_entry if self.relays is not None else wl

            r_wl = np.array([None if res_bit not in wl_bls else r_wl[wl_bls.index(res_bit)] for res_bit in self.res_array_bls])

            r_wl = np.maximum(r_wl, 1e-12)            
            
            c_wl = 1/r_wl if r_wl is not None else None
            
            self.res_array.loc[wl] = r_wl
            self.cond_array.loc[wl] = c_wl
            self.meas_v_array.loc[wl] = meas_bls_v if meas_vbls else meas_sls_v
            self.meas_i_array.loc[wl] = meas_bls_i if meas_ibls else meas_sls_i
            self.meas_i_leak_array.loc[wl] = meas_i_gate if meas_i_gate else None

            self.formatted_measurement["res"].append([f"{value/1000:.2f}kΩ" for value in r_wl])
            self.formatted_measurement["cond"].append([f"{value:.2e}S" for value in c_wl])
            self.formatted_measurement["i"].append([f"{value:.2e}A" for value in self.meas_i_array.loc[wl]])
            self.formatted_measurement["v"].append([f"{value:.2e}V" for value in self.meas_v_array.loc[wl]])

            self.all_wls = self.settings["device"]["all_WLS"]


        # Print read information if print_info is True or specific information based on string/list input
        self._print_measurement_results(wls, bls, print_info)

        # Record Information to datafile if record is True
        if record: self._record_measurement_results(wls, bls, check)
        
        self._settle(self.op["READ"]["settling_time"])

        self.dbg.end_function_debug()
        return self.res_array, self.cond_array, self.meas_i_array, self.meas_v_array, self.meas_i_leak_array

    def _define_measurement_dataframes(self, wls, bls):
        
        """ Fix BLs to be flattened list with all unique BLs"""
        if type(bls[0])==list:
            res_array_bls = list(set(np.concatenate(bls).tolist()))
            self.res_array_bls = sorted(res_array_bls, key=lambda s: int(s.split('_')[1]))
        else:
            self.res_array_bls = sorted(bls, key=lambda s: int(s.split('_')[1]))
        bls = self.res_array_bls
        """Define the dataframes to store measurement results."""
        self.res_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        self.cond_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        self.meas_v_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        self.meas_i_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        self.meas_i_leak_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)

        """Define lists to store formatted measurement results for display."""
        self.formatted_measurement = {"res": [],"cond": [],"i": [],"v": []}
        self.measurement_names = {"res": "Resistance","cond": "Conductance","i": "Current","v": "Voltage"}

    def _set_read_voltages(self,wls,bls,sls,vbl,vsl,vwl,vwl_unsel):
        """Set the read voltages for the selected word lines, bit lines, and source lines."""
        self.ppmu_set_vbl(bls, vbl)
        self.ppmu_set_vsl(sls, vsl)
        self.ppmu_set_vwl(wls, vwl)
        self.ppmu_set_vwl(self.wl_unsel, vwl_unsel)

    def _print_measurement_results(self, wls, bls, print_info):
        """                 Print the measurement results defined by the formatted measurements              """
        """Default True to First dictionary value, all is values, and a list of strings for specific results."""
        if not print_info:
            return
        if isinstance(print_info, bool) and print_info:
            print_info = [list(self.formatted_measurement.keys())[0]]
        elif isinstance(print_info, str):
            print_info = [print_info]
        
        if "all" in print_info:
            index = print_info.index("all")
            print_info = print_info[:index] + list(self.formatted.keys()) + print_info[index+1:]
        
        for prnt in print_info:
            print(f"{self.measurement_names[prnt]}:\n{pd.DataFrame(self.formatted_measurement[prnt],wls,bls)}\n")

    def _record_measurement_results(self, wls, bls, check):
        with open(self.datafile_path, "a", newline='') as file_object:
            datafile = csv.writer(file_object)
            for wl,wl_bls in zip(wls,bls):
                for bl in wl_bls:
                    if check:
                        if self.res_array.loc[wl, bl] < self.set_target_res:
                            check_on = "set"
                        elif self.res_array.loc[wl, bl] > self.reset_target_res:
                            if self.res_array.loc[wl, bl] < 200_000:
                                check_on = "reset"
                            else:
                                check_on = "unformed"
                        else:
                            check_on = "unknown"
                    print(f"checking ({wl}, {bl}): {self.res_array.loc[wl, bl]} | {check_on}")
                    datafile.writerow([self.chip, self.device, "READ", wl, bl, self.res_array.loc[wl, bl], self.cond_array.loc[wl, bl], self.meas_i_array.loc[wl, bl], self.meas_v_array.loc[wl, bl], check_on])      

    def _settle(self,duration):
        """A more accurate sleep function to get sub-ms settling time"""
        """ Time.sleep had a min of 10 ms, so this is a workaround """
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass    


    """ ================================================================= """
    """                   Setting voltages and currents                   """
    """ Serially setting voltages and currents for VBL, VSL, ISL, and VWL """
    """                PPMU and Digital sources are defined               """
    """ ================================================================= """
    # def set_to_off(self,channels,name=None, sort=True,debug=None):
    
    #     if type(channels) is not list:
    #         channels = [channels]
    #     if type(channels[0]) is list and sort==True:
    #         if type(channels[0][0]) is int or type(channels[0][0]) is np.uint8:
    #             channels = [[f"{name[channels.index[channel]]}_{chan}" for chan in channel]for channel in channels]
            
    #         channels = self._flatten(channels)

    #     if type(channels[0]) is int or type(channels[0]) is np.uint8:
    #         channels = [f"{name}_{chan}" for chan in channels]
    #     self.digital_patterns.set_channel_mode("off", pins=channels,sessions=None,sort=sort,debug=debug)

    def set_to_ppmu(self,channels,name=None, sort=True,debug=None):
    
        if type(channels) is not list:
            channels = [channels]
        if type(channels[0]) is list and sort==True:
            if type(channels[0][0]) is int or type(channels[0][0]) is np.uint8:
                channels = [[f"{name[channels.index[channel]]}_{chan}" for chan in channel]for channel in channels]
            
            channels = self._flatten(channels)

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        self.digital_patterns.set_channel_mode("ppmu", pins=channels,sessions=None,sort=sort,debug=debug)

    def ppmu_set_voltage(self, v, channels, name, sort=True,source=True):
        """
        PPMU Set Voltage: Set voltages v for given channels across
        multiple sessions. 

        Parameters:
        v: float or list of floats
            Voltage to set for each channel
        channels: str or list of str
            Channel names to set voltage for
        name: str
            Name of the channel (BL, SL, WL, Body)
        sort: bool
            Sort the channels before setting voltage

        Returns:
            None
        """

        # Check if channels is a list, if not convert it to a list
        if not isinstance(channels, list):
            channels = [channels]
        if len(channels)<1:
            return
        # Check if channels are integers, if yes convert them to string format
        if isinstance(channels[0], (int, np.uint8)):
            channels = [f"{name}_{chan}" for chan in channels]

        # Check if all channels are valid
        all_sel_channels = self.settings["device"][f"all_{name}S"]
        for chan in channels:
            if chan not in all_sel_channels:
                raise NIRRAMException(f"Invalid V{name} channel {chan}. \nChannel not in all_{name}S.")

        # Check if v is a list, if not convert it to a list
        if not isinstance(v, list):
            v = [v]

        # Check if the number of voltages matches the number of channels
        if len(v) == 1:
            v = v * len(channels)

        if len(v) != len(channels):
            raise NIRRAMException(f"Number of V{name} channels ({len(channels)}) does not match number of V{name} voltages ({len(v)}).")

        # Check if the voltage values are within the valid range
        if np.any((np.array(v) > 6) | (np.array(v) < -2)):
            raise NIRRAMException(f"Invalid V{name} voltage(s) in {v}. Voltage must be between -2V and 6V.")

        # Set the voltage levels using the digital patterns
        if max(v) > 3 or min(v) < -3:
            for i in range(10):
                v_inter = list((i-1)*(np.array(v)-1)/(10-1)+1)
                self.digital_patterns.ppmu_set_voltage(pins=channels, voltage_levels=v_inter, sessions=None, sort=sort, source=source)
                self._settle(1e-5)
        else:        
            self.digital_patterns.ppmu_set_voltage(pins=channels, voltage_levels=v, sessions=None, sort=sort, source=source)



    def measure_iv(self, wl, bl, vwl, vbl, vsl=0, vwl_unsel = 0, plot=True,relayed=True):
        """Measure the current between the bitline and the gate."""
        if not isinstance(vwl, list) and not isinstance(vwl, np.ndarray):
            vwl = [vwl]
        if not isinstance(vbl, list) and not isinstance(vbl, np.ndarray):
            vbl = [vbl]
        if self.relays is not None:
            wl, _ = self.relay_switch(wl, relayed=relayed)
            # _,_ = self.relay_switch(self.all_wls, relayed=relayed)
        if isinstance(bl, list):
            bls = bl
        else:
            bls = [bl]
        sls = [f"SL_{chan[3:]}" for chan in bl]

        if not isinstance(wl, list): 
            wls = [wl]
        else:
            wls = wl
        for wl in wls:
            for bl,sl in zip(bls,sls):

                self.ppmu_set_vsl(self.sls, vsl,source=True)
                self.ppmu_set_vwl(["WL_UNSEL"], vwl_unsel, sort=True,source=True)

                IbVg = {}
                IwVg = {}
                for wordline_voltage in vwl:
                    IbVg[f"{wordline_voltage}"] = {}
                    IwVg[f"{wordline_voltage}"] = {}
                    for bitline_voltage in vbl:
                        self.ppmu_set_vwl(wl, wordline_voltage)
                        self.ppmu_set_vbl(bl, bitline_voltage)
                        self._settle(2e-3)
                        _, _, Isl = self.digital_patterns.measure_current([[bl], [], []], sort=False)
                        self._settle(2e-3)
                        IbVg[f"{wordline_voltage}"][f"{bitline_voltage}"] = [abs(i) for i in Isl]
                        _, _, Iwl = self.digital_patterns.measure_current([[], [], [wl]], sort=False)
                        self._settle(2e-3)
                        IwVg[f"{wordline_voltage}"][f"{bitline_voltage}"] = Iwl
                
                self.ppmu_set_vwl(wl, 0)
                self.ppmu_set_vbl(bl, 0)
                self.ppmu_set_vwl(["WL_UNSEL"], 0, sort=True)
                if plot:
                    # Plot for IblVwl (X-axis: VWL, Y-axis: IBL, Multiple lines for different VBL)
                    plt.figure(figsize=(14, 10))
                    plt.subplot(2, 2, 1)
                    for bitline_voltage in vbl:
                        ibl_values = [IbVg[str(wordline_voltage)][str(bitline_voltage)] for wordline_voltage in vwl]
                        plt.plot(np.array(vwl)-vsl, ibl_values, label=f'VBL = {bitline_voltage} V')
                    plt.xscale('linear')
                    plt.yscale('log')
                    # plt.yscale('log')
                    plt.title('Ibl vs VWL')
                    plt.xlabel('VWL-VSL (V)')
                    plt.ylabel('Ibl (A)')

                    # Plot for IblVbl (X-axis: VBL, Y-axis: IBL, Multiple lines for different VWL)
                    plt.subplot(2, 2, 2)
                    for wordline_voltage in vwl:
                        ibl_values = [IbVg[str(wordline_voltage)][str(bitline_voltage)] for bitline_voltage in vbl]
                        plt.plot(np.array(vbl)-vsl, ibl_values, label=f'VWL = {wordline_voltage} V')
                    plt.title('Ibl vs VBL')
                    plt.xlabel('VBL-VSL (V)')
                    plt.ylabel('Ibl (A)')

                    # Plot for IwlVbl (X-axis: VBL, Y-axis: IWL, Multiple lines for different VWL)
                    plt.subplot(2, 2, 3)
                    for wordline_voltage in vwl:
                        iwl_values = [IwVg[str(wordline_voltage)][str(bitline_voltage)] for bitline_voltage in vbl]
                        plt.plot(np.array(vbl)-vsl, iwl_values, label=f'VWL = {wordline_voltage} V')
                    plt.title('Iwl vs VBL')
                    plt.xlabel('VBL-VSL (V)')
                    plt.ylabel('Iwl (A)')

                    # Plot for IwlVwl (X-axis: VWL, Y-axis: IWL, Multiple lines for different VBL)
                    plt.subplot(2, 2, 4)
                    for bitline_voltage in vbl:
                        iwl_values = [IwVg[str(wordline_voltage)][str(bitline_voltage)] for wordline_voltage in vwl]
                        plt.plot(np.array(vwl)-vsl, iwl_values, label=f'VBL = {bitline_voltage} V')
                    plt.title('Iwl vs VWL')
                    plt.xlabel('VWL-VSL (V)')
                    plt.ylabel('Iwl (A)')

                    # Adjust layout and show the plots
                    plt.tight_layout()
                    date = datetime.now().strftime("%Y-%m-%d")
                    time = datetime.now().strftime("%H-%M-%S")
                    plt.savefig(f"{self.settings_manager.get_setting('path.data_header','data/')}IV/_{self.chip}_{self.device}_{wl}_{bl}_{date}_{time}.png")
                    plt.show()
                return wl

    def ppmu_set_vbl(self, vbl_chan, vbl,sort=True,source=True):
        """Set (active) VBL using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vbl,vbl_chan,"BL",sort=sort,source=source)
    
    def ppmu_set_vsl(self, vsl_chan, vsl,sort=True,source=True):
        """Set (active) VBL using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vsl,vsl_chan,"SL",sort=sort,source=source) 
    
    def ppmu_set_vwl(self, vwl_chan, vwl,sort=True,source=True):
        """Set (active) VWL using NI-Digital driver (inactive disabled)"""
        if self.relays is not None:
            name = "WL_IN"
        else:
            name = "WL"
        self.ppmu_set_voltage(vwl,vwl_chan,name,sort=sort,source=source)

    def ppmu_set_vbody(self, vbody_chan, vbody,sort=True,source=True):
        """Set (active) VBody using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vbody,vbody_chan,"Body",sort=sort,source=source)

    def ppmu_set_isl(self, isl_chan, isl):
        """Set ISL using NI-Digital driver"""
        # Verify that vbl_channel is formatted as list, even for single channel
        if type(isl_chan) is not list:
            isl_chan = [isl_chan]
        
        # Verify that vbl_channel is formatted as list of strings, even if given as integers
        if type(isl_chan[0]) is int or type(isl_chan[0]) is np.uint8:
            isl_chan = [f"SL_{chan}" for chan in isl_chan]
        
        # Verify that vbl_channels exist in all_BLs
        for chan in isl_chan:
            if chan not in self.all_sls:
                raise NIRRAMException(f"Invalid ISL channel {chan}. \nChannel not in all_SLS.")
        
        self.digital_patterns.ppmu_set_current(sessions=None,pins=isl_chan,current_levels=isl,source=True)

        assert(isl_chan in self.all_sls)
        for digital in self.digital:
            digital.channels[isl_chan].ppmu_current_level = isl
        for digital in self.digital:
            self.digital.channels[isl_chan].ppmu_source()



    def digital_set_voltage(self, channels, sessions=None, vi_lo=0, vi_hi=1, vo_lo=0, vo_hi=1, name=None, sort=True, debug=None):

        # Set the value for debug if not provided
        self.dbg.start_function_debug(debug)
        
        # Verfiy that any individually given channels are turned into a list to match the expected format
        channels = [channels] if not isinstance(channels,list) else channels
        sessions = [sessions] if not isinstance(sessions,list) else sessions
        
        # Channels may be given as integers, if so, convert to strings for nidigital
        #   Ex: channels = [0, 1, 2], name = DIO -> channels = ["DIO_0", "DIO_1", "DIO_2"]
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        # verify channels exist
        for chan in channels:
            if chan not in self.settings["device"][f"all_{name}S"]:
                raise NIRRAMException(f"Invalid V{name} channel {chan}. \nChannel not in all_{name}S.")
            
        instruments =  self.digital_patterns.settings["NIDigital"]

        for num, session in enumerate(sessions):
            if type(session) is int:
                if session not in range(len(self.digital)):
                    raise NIRRAMException(f"Invalid session {session}. \nSession not in range(len(self.digital)).")
            
            elif type(session) is str:
                if session in instruments["pingroups"]:
                    sessions[num] = self.digital[instruments["pingroups"].index(session)]
                elif session in self.all_channels_flat:
                    sessions[num] = self.digital[self.all_channels_flat.index(session)//32]
            
            elif type(session) != type(self.digital[0]):
                raise NIRRAMException(f"Invalid session {session}. \nSession not in range(len(self.digital)).")
            
        # Convert voltages into a list of voltages for easier debugging
        voltages = [vi_lo, vi_hi, vo_lo, vo_hi]

        # region Verify that the voltages are lists to allow for multiple voltages
        # If the voltage is a single value, repeat it for all channels
        for n, voltage in enumerate(voltages):
            if type(voltage) is not list:
                voltage = [voltage]
            if len(voltage) == 1:
                voltage = voltage * len(channels)
            voltages[n] = voltage
        if any(len(voltage) != len(channels) for voltage in voltages):
            raise NIRRAMException(f"Specified voltage levels must match number of channels. \nNum channels: {len(channels)} \nNum voltages: vi_lo: {len(vi_lo)}, vi_hi: {len(vi_hi)}, vo_lo: {len(vo_lo)}, vo_hi: {len(vo_hi)}")
        # endregion

        vi_lo, vi_hi, vo_lo, vo_hi = voltages
        
        # Set the voltages using the digital_set_voltages function
        self.digital_patterns.digital_set_voltages(pins=channels, sessions=sessions, vi_lo=vi_lo, vi_hi=vi_hi, vo_lo=vo_lo, vo_hi=vo_hi,sort=sort)

        self.dbg.end_function_debug()


    def set_vsl(self, vsl_chan, vsl_hi, vsl_lo, debug = None):
        # Debug Printout: Start and Internal
        debug = self.dbg.start_function_debug(debug)
        
        # Set VSL using NI-Digital Drivers
        self.digital_set_voltage(vsl_chan, "SL", vi_lo=vsl_lo, vi_hi=vsl_hi, vo_lo=vsl_lo, vo_hi=vsl_hi, name="SL", sort=True,debug=debug)
        
        # Debug Printout: End
        self.dbg.end_function_debug()


    def set_vbl(self, vbl_chan, vbl_hi, vbl_lo, debug = None):
        debug = self.dbg.start_function_debug(debug)
        
        # Set VSL using NI-Digital Drivers
        self.digital_set_voltage(vbl_chan, "BL", vi_lo=vbl_lo, vi_hi=vbl_hi, vo_lo=vbl_lo, vo_hi=vbl_hi, name="BL", sort=True,debug=debug)
        
        # Debug Printout: End
        self.dbg.end_function_debug()   

    def set_vwl(self, vwl_chan, vwl_hi, vwl_lo, debug = None):
        # Debug Printout: Start and Internal
        debug = self.dbg.start_function_debug(debug)
        
        # Set WL name based on if they are relayed
        if all(len(chan) > 6 for chan in vwl_chan):
            wl_name = "WL_IN"
        elif all(len(chan) < 7 for chan in vwl_chan):
            wl_name = "WL"
        else:
            raise NIRRAMException(f"Invalid VWL channel {vwl_chan}. \nChannel not in all_WL_IN or all_WLS.")
        # Set VWL using NI-Digital Drivers
        self.digital_set_voltage(vwl_chan, "WL", vi_lo=vwl_lo, vi_hi=vwl_hi, vo_lo=vwl_lo, vo_hi=vwl_hi, name=wl_name, sort=True,debug=debug)
        
        # Debug Printout: End
        self.dbg.end_function_debug()

    def set_to_digital(self,channels,name, sort=True,debug=None):
        
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]
        
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("digital", pins=channels,sessions=None,sort=sort,debug=debug)


    def set_to_off(self,channels,name, sort=True,debug=None):
        # print(f"Setting {name} channels {channels} to off")
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("off", pins=channels,sessions=None,sort=sort,debug=debug)

    def set_to_disconnect(self,channels,name, sort=True,debug=None):
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("disconnect", pins=channels,sessions=None,sort=sort,debug=debug)


    """ ================================================================= """
    """               Setting up the write pulse signals                  """
    """ ================================================================= """

    def direct_write(
        self,
        masks,
        sessions=None,
        pingroups=None,
        sort=True,
        mode="SET",
        wl=None,
        wl_bls=None,
        wl_sls=None,   
        wls=None,
        bls=None,
        sls=None,
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vsl_unsel=None,
        vwl_unsel_offset=None,
        v_base=None,
        pulse_len=None,
        high_z = None,
        debug = None,
        relayed=True,
        zeroes = None,
        pulse_lens = None,
        max_pulse_len = None,
        record=None,
        cells=None,
        print_data=None,
        target_res=None,
        WL_IN=None
        ):

        #TODO: Add toml parsing for the write pulse parameters

        vwl = vwl or self.op[mode][self.polarity]["VWL"]
        vbl = vbl or self.op[mode][self.polarity]["VBL"]
        vsl = vsl or self.op[mode][self.polarity]["VSL"]
        pulse_len = pulse_len or self.op[mode][self.polarity]["PW"]

        measurements = self.read_written_cells(mode, average_resistance=True,wls=wls,bls=bls,record=record,print_info=print_data)
        res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array = measurements
        cells_to_write = self.check_cell_resistance(res_array, wls, bls, sls, target_res, mode)
        if cells_to_write == "DONE":
            self._record_write_pulse(self,record,cells,mode,[res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array],success=pd.DataFrame(True,index=wls,columns=bls))
            
            self.dbg.end_function_debug() 
            # return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array
        
        wls,bls,sls = cells_to_write  

        if wl in wls and wl_bls in bls and wl_sls in sls:
            mask_list = Masks(
                sel_pins = [wl_bls,wl_sls,WL_IN], 
                pingroups = self.digital_patterns.pingroup_data, 
                all_pins = self.all_channels, 
                pingroup_names = self.digital_patterns.pingroup_names,
                sort=False,
                debug_printout = debug)
        
            masks = mask_list.get_pulse_masks()
            # Write the pulse

            print("Direct Write Values: VWL: ", vwl, "VBL: ", vbl, "VSL: ", vsl, "PW: ", pulse_len)
            self.write_pulse(
                masks, 
                sessions=sessions, 
                mode=mode, 
                bl_selected=wl_bls,
                sl_selected=wl_sls,
                vwl=vwl, 
                vbl=vbl, 
                vsl=vsl,
                vbl_unsel=vbl_unsel,
                vsl_unsel=vsl_unsel,
                vwl_unsel_offset=vwl_unsel_offset, 
                pulse_len=pulse_len, 
                high_z=None,
                debug=debug)

        return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array,cells_to_write
                      
                            
        
    def write_pulse(
        self,
        masks,
        sessions=None,
        pingroups=None,
        sort=True,
        mode="SET",
        bl_selected=None,
        sl_selected=None,   
        wls=None,
        bls=None,
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vsl_unsel=None,
        vwl_unsel_offset=None,
        v_base=None,
        pulse_len=None,
        high_z = None,
        debug = None,
        relayed=True,
        zeroes = None,
        pulse_lens = None,
        max_pulse_len = None
        ):

        # pulse_lens = pulse_lens or [self.prepulse_len, pulse_len, self.postpulse_len]
        pulse_lens = pulse_lens or [self.prepulse_len, self.wl_buffer, pulse_len, self.blsl_buffer, self.postpulse_len]
        max_pulse_len  = max_pulse_len or self.max_pulse_len

        # If masks is none or empty, and pingroups are not none, set masks to pingroups
        if masks is None:
            raise NIRRAMException("Masks cannot be None. Please provide a mask to write_pulse.")
        
        masks = masks
        # Get the Pulse Parameters
        vwl = vwl or self.op[mode][self.polarity]["VWL"]
        vbl = vbl or self.op[mode][self.polarity]["VBL"]
        vsl = vsl or self.op[mode][self.polarity]["VSL"]
        vbl_unsel = vbl_unsel or vsl + ((vbl - vsl) / 4.0)
        pulse_len = pulse_len or self.op[mode][self.polarity]["PW"] 

        # Set the base voltage relative to the selected mode
        if v_base is None:
            if mode == "SET":
                v_base = vsl
                
            elif mode == "FORM":
                v_base = vsl

            elif mode == "RESET":
                v_base = vbl
            
            else:
                raise NIRRAMException(f"Invalid mode: {mode}. Please select 'SET', 'RESET', or 'FORM'.")

        # Write Static (X) to all channels
        self.digital_patterns.write_static_to_pins(pins=self.all_channels,sort=False)

        # Set the selected word line to the desired voltage
        vwl_unsel_offset = vwl_unsel_offset or self.op[mode][self.polarity]["VWL_UNSEL_OFFSET"]
        vwl_unsel = v_base + vwl_unsel_offset

        # Debug Printout
        if self.debug:
            print(f"{mode} Pulse: VWL={vwl}, VBL={vbl}, VSL={vsl}, VBL_UNSEL={vbl_unsel}, VWL_UNSEL ={vwl_unsel}")

        # ------------------------- #
        #   Define WLS, BLS, SLS    #
        # ------------------------- #
        wls = self.wls if wls is None else wls     
        bls = self.bls if bls is None else bls
        sls = self.sls if bls is None else [f"SL_{bl[3:]}" for bl in bls]
            
        # ------------------------- #
        #       set voltages        #
        # ------------------------- #
        
        # Set ZERO Wordlines to the base voltage
        if zeroes is not None:
            self.set_vwl(["WL_ZERO"], vwl_hi=v_base, vwl_lo=v_base, debug = debug)
            # FIXME: WL_ZERO is not defined in the settings, or anywhere else in this file!!
            

        # Set SEL Wordlines to the desired voltage
        self.set_vwl(wls, vwl_hi=vwl, vwl_lo=v_base, debug=debug)
        
        # Set Bitlines to the desired voltage
        if bl_selected is not None:
            bls_unselected = [bl for bl in bls if bl not in bl_selected]
            self.set_vbl(bls, vbl, vbl_lo=v_base, debug = debug)
            if len(bls_unselected) > 0:
                self.set_vbl(bls_unselected, vbl_unsel, vbl_lo=v_base, debug = debug)
        else:
            self.set_vbl(bls, vbl_hi = vbl, vbl_lo=v_base, debug = debug)    


        # Set Sourcelines to the desired voltage
        if sl_selected is not None:
            sls_unselected = [sl for sl in sls if sl not in sl_selected]
            self.set_vsl(sls, vsl, vsl_lo=v_base, debug = debug)
            if len(sls_unselected) > 0:
                self.set_vsl(sls_unselected, vsl_unsel, vsl_lo=v_base, debug = debug)
        else:
            self.set_vsl(sls, vsl_hi = vsl, vsl_lo=v_base, debug = debug)

        # ----------------------------------- #
        #       Commit and send Pulse         #
        # ----------------------------------- #

        for session in self.digital_patterns.sessions:
            session.commit()
        
        self.set_to_ppmu(["WL_UNSEL"], ["WL"], sort=True)
        self.ppmu_set_vwl(["WL_UNSEL"], vwl_unsel)
        self.digital_patterns.pulse(masks,pulse_lens=pulse_lens,max_pulse_len=max_pulse_len, pulse_groups=[[],["WL_IN"],["BL","SL","WL_IN"],["WL_IN"],[]] )
        self.ppmu_set_vwl(["WL_UNSEL"], v_base)
        # ---------------------------------------- #
        #       Set to Off and Disconnect          #
        # ---------------------------------------- #

        # Set channels to 0V
        self.digital_patterns.digital_all_pins_to_zero(ignore_power=False)
        # Reset Channels in high_z to Hi-Z
        if high_z is not None:
            self.digital_patterns.set_channel_termination_mode("high-z",pins=high_z,sessions=None,sort=True)

    def select_memory_cells(self, cells=None, bls=None, bls_unselected=[], wls=None, debug=None):
        """
        Select Memory Cells: This function is used to select the channels to be pulsed/written to.
        The function takes in the cells to be pulsed, the BLs, WLs to be used, and the
        bls_unselected to be used for 1TNR. The function then returns the expected bls, bls_unselected,
        sls, and wls to be used for the pulse operation.
        """
        
        # Use either given bls, wls, or values from self if None
        wls = self.wls if wls is None else wls
        bls = self.bls if bls is None else bls
        bls_unselected = bls_unselected or []
        
        # Ensure wls is a list of strings
        if isinstance(wls, str):
            wls = [wls]
        
        # Ensure bls is a list of lists of strings or integers, matching the length of wls
        # print("bls: ", bls)
        bls_list = bls
        if not isinstance(bls[0], list):
            bls_list = [bls] * len(wls)
        
        # Set SLS as a list of lists of strings as SL_{BL#} based on bls
        if isinstance(bls_list[0][0], int) or isinstance(bls_list[0][0], np.uint8):
            sls = [[f"SL_{bl}" for bl in wl_bls] for wl_bls in bls_list]
        else:
            sls = [[f"SL{bl[2:]}" for bl in wl_bls] for wl_bls in bls_list]

        # Handle cells, avoiding repetition in wls and bls_list
        if cells is not None and len(cells) > 0 and all(len(cell) == 2 for cell in cells):
            for cell in cells:
                wl, bl = cell
                if wl not in wls:
                    wls.append(wl)
                    bls_list.append([bl])
                    sls.append([f"SL_{str(bl[3:])}" if isinstance(bl, str) else f"SL_{bl}"])
                elif bl not in bls_list[wls.index(wl)]:
                    bls_list[wls.index(wl)].append(bl)
                    sls[wls.index(wl)].append(f"SL_{str(bl[3:])}" if isinstance(bl, str) else f"SL_{bl}")
        
        # Define the cells as a list of tuples of WL and BL
        cells = [(wl, bl) for wl, wl_bls in zip(wls, bls_list) for bl in wl_bls]

        # Filter selected BLs excluding the unselected BLs
        selected_bls = [bl for bl in bls_list if bl not in bls_unselected]

        # Create an instance of RRAMCells with the updated parameters
        selected_memory_cells = RRAMCells(cells, wls, bls_list, bls_unselected, selected_bls, sls)

        return selected_memory_cells

    def update_memory_cells(self,selected_cells,add_cells=None, remove_cells=None, wls=None, bls=None, bls_unselected=[], replace_all=False):
        """
        Update Memory Cells: This function is used to update the selected memory cells
        with new cells. The function takes in the selected cells, the new cells, and the
        BLs and WLs to be used. The function then returns the expected bls, bls_unselected,
        sls, and wls to be used for the pulse operation.
        """
        if replace_all:
            selected_cells = self.select_memory_cells(add_cells,bls,bls_unselected,wls)
            return selected_cells
        
        if add_cells is not None and add_cells != selected_cells.cells:
            # If cells are given to add, update selected cells to include them in cells, wls, bls, and sls
            for cell in add_cells:
                wl, bl = cell
                if wl not in selected_cells.wls:
                    selected_cells.wls.append(wl)
                    selected_cells.bls.append([bl])
                    selected_cells.sls.append([f"SL_{str(bl[3:])}"])
                elif bl not in selected_cells.bls[selected_cells.wls.index(wl)]:
                    selected_cells.bls[selected_cells.wls.index(wl)].append(bl)
                    selected_cells.sls[selected_cells.wls.index(wl)].append(f"SL_{str(bl[3:])}")
        
        if remove_cells is not None and remove_cells != selected_cells.cells:
            # If cells are given to remove, update selected cells to remove them from cells, wls, bls, and sls
            for cell in remove_cells:
                wl, bl = cell
                if bl in selected_cells.bls[selected_cells.wls.index(wl)]:
                    selected_cells.bls[selected_cells.wls.index(wl)].remove(bl)
                    selected_cells.sls[selected_cells.wls.index(wl)].remove(f"SL_{str(bl[3:])}")
                if len(selected_cells.bls[selected_cells.wls.index(wl)]) == 0:
                    selected_cells.bls.remove(selected_cells.bls[selected_cells.wls.index(wl)])
                    selected_cells.sls.remove(selected_cells.sls[selected_cells.wls.index(wl)])
                    selected_cells.wls.remove(wl)
            
        return selected_cells
    


    def remove_cells_at_target_resistance(self,selected_cells, mode, average_resistance=False, target_res=None, record=True, print_data=True):
        measurements = self.read_written_cells(mode, average_resistance=average_resistance,wls=selected_cells.wls,bls=selected_cells.bls,record=record,print_info=print_data)
        res_array,_,_,_,_ = measurements
        cells_to_write = self.check_cell_resistance(res_array, selected_cells.wls, selected_cells.bls, selected_cells.sls, target_res, mode)
        if cells_to_write == "DONE":
            return cells_to_write, measurements
        
        selected_cells = self.update_memory_cells(selected_cells,wls=cells_to_write[0],bls=cells_to_write[1], replace_all=True)

        return "NOT DONE", selected_cells
        # Read given cells, if they are within target resistance,
        # remove them from the list of cells to be pulsed

    def define_voltages_to_be_pulsed(self, mode="SET", wl_bl_sl_voltages=None, vwl_unsel_offset=None, vbl_unsel=None):
            # Set the initial bias for BLS, WLS, SLS, based on settings or input
            vwl, vbl, vsl = wl_bl_sl_voltages
            vbl = vbl or self.op[mode][self.polarity]["VBL"]
            vsl = vsl or self.op[mode][self.polarity]["VSL"]
            vwl = vwl or self.op[mode][self.polarity]["VWL"]
            v_base = vbl if mode == "RESET" else vsl
            vbl_unsel = vbl_unsel or v_base + ((vbl - v_base) / 4.0)
            vwl_unsel_offset = vwl_unsel_offset or self.op[mode][self.polarity]["VWL_UNSEL_OFFSET"]
            vwl_unsel = v_base + vwl_unsel_offset

            return VoltageSettings(vbl, vbl_unsel, vsl, vwl, vwl_unsel, v_base)

    def setup_pulse(
            self, 
            masks, 
            mode="SET",
            bls=None,  # List of BLs used with every listed WL
            bls_unselected=[], # List of BLs not being written to in 1TNR
            wls=None, # List of WLs used with every listed BL
            cells=None, # List of individual cells [(WL,BL)] to pulse
            wl_bl_sl_voltages=None,
            vbl_unsel=None, 
            vwl_unsel_offset=None, 
            pulse_width=None, 
            init_setup = True,
            measure_res = True,
            target_res = None,
            print_data = True,
            average_resistance = False,
            record = True,
            debug = None,
        ):

        self.dbg.start_function_debug(debug)
        """
        Setup Pulse: This function is used to set up a pulse operation. This includes
            1) Defining the channels to be pulsed
                - Determined by function call or TOML settings
                - If cells are given, the BLs and WLs are determined by the cells in addition to BLs and WLs
                - If meas_res is given, BLs and WLs already in target resistance are removed from the list
            2) Setting the voltages for the pulse
                - Determined by function call or TOML settings
            3) Setting the mask for the pulse
                - Determined by function call or TOML settings
                - Set only if Mask is not already defined, otherwise uses the given mask

        Parameters:
        # region
        mask: Masks
            Mask to be used for the pulse, blocks all channels except pin groups where channesl are being pulsed
        mode: str
            Operation mode, either "SET", "RESET", or "FORM"
        bls: list of str or list of list of str
            List of BLs to be pulsed
        wls: list of str
            List of WLs to be pulsed
        cells: list of tuple of str
            List of cells to be pulsed, each cell is a tuple of WL and BL
        wl_bl_sl_voltages: list of list of float
            List of voltages for WL, BL, and SL
        vbl_unsel: float
            Voltage for unselected BLs
        vwl_unsel_offset: float
            Offset for unselected WLs
        pulse_len: float
            Length of the pulse
        high_z: list of str
            List of channels to set to high-z before the pulse
        init_setup: bool
            If True, the function will set up the pulse, if False, the function will only return the necessary parameters
        measure_res: bool
            If True, the function will measure the resistance of the cells before pulsing
        print_data: bool
            If True, the function will print the resistance, conductance, current, and voltage of the cells
        average_resistance: bool
            If True, the function will average the resistance of 3 cell measurements
        record: bool
            If True, the function will record the resistance, conductance, current, and voltage of the cells
        debug: bool
            If True, the function will print debug information
        # endregion
        """ 
        if init_setup:
            # Define the channels to be pulsed
            cells_to_pulse = self.select_memory_cells(cells,bls, bls_unselected, wls, debug=debug)   

            # Determine the target resistance, used to determine if pulse should occur

            # Define the voltages to be pulsed
            voltages_to_pulse = self.define_voltages_to_be_pulsed(mode, wl_bl_sl_voltages, vwl_unsel_offset, vbl_unsel)
        
        target_res = target_res or self.settings["target_res"][mode.upper()]
    # Check if the pulse is necessary by reading the cells and returning the resistance + cells that need to be pulsed
        # If no cells need to be pulsed, the function ends and the measurements are returned with the "DONE" flag
        if measure_res:
            read_results = self.remove_cells_at_target_resistance(cells_to_pulse, mode,average_resistance=average_resistance,target_res=target_res,record=record,print_data=print_data)
            if read_results[0]== "DONE":
                res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array = read_results[1][:]
                # Record the write pulse with the updated measurements
                self._record_write_pulse(record=record,cells=cells_to_pulse.cells,mode=mode,measurements=[res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array],voltages=wl_bl_sl_voltages, success=pd.DataFrame(True,index=wls,columns=bls))
                print("All cells are within target resistance. No pulse required.")
                
                self.dbg.end_function_debug()
                return "DONE", res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array
            
            cells_to_pulse = read_results[1]
            wls,bls,sls = cells_to_pulse.wls, cells_to_pulse.bls, cells_to_pulse.sls

            wls = self.relay_switch(wls)
        # If mask is None, make the mask using Mask class
        # if masks is None:
        #     # If only pulsing one Wordline, create a single mask for the wordline
        #     masks = []
        #     for wl, wl_bls, wl_sls in zip(wls,bls,sls):
        #             if isinstance(wl,str):
        #                 wl = [wl]
        #             masks.append(Masks(
        #                     sel_pins = [wl_bls,wl_sls,wl], 
        #                     pingroups = self.digital_patterns.pingroup_data, 
        #                     all_pins = self.all_channels_flat, 
        #                     pingroup_names = self.digital_patterns.pingroup_names,
        #                     sort=False,
        #                     debug_printout = debug))
        
        if init_setup or measure_res:
            pulse = RRAMPulseOperation(mode.upper(), cells_to_pulse, voltages_to_pulse, pulse_width, target_res)
            
        self.dbg.end_function_debug
        if masks:
            return pulse, [mask.get_pulse_masks() for mask in masks]
        else:
            return pulse, masks

    
    def set_pulse(
        self,
        mask=None,
        mode="SET",
        wls=None,
        bls=None,
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vwl_unsel_offset=None,
        pulse_len=None,
        high_z = None,
        debug=None
    ):
        """Perform a SET operation.
        To support 1TNR devices (1 WL, 1 SL, multiple BLs), have input
        "bl" selection parameter. If "bl" is not None, this specifies the
        selected "bl". For all other unselected BLs, by default set their
        value to an intermediate voltage V/4 (based on Hsieh et al, IEDM 2019)
        to reduce impact of oversetting/overreseting unselected devices.

        This voltage must be relative to value between VSL and VBL,
        not just VBL/4 because VSL is not necessarily 0 V, so just taking
        VBL/4 can increase voltage when VSL > VBL and VBL is stepped down
        (e.g. in the case of PMOS). So we want `VSL + (VBL - VSL)/4.0`
        Example for SET (VSL fixed, sweep VBL):
            VSL     VBL     VBL/4     VSL + (VBL - VSL)/4
            2.0     1.4      0.35          1.85      
            2.0     1.2      0.30          1.8
            2.0     1.0      0.25          1.75
        """
        pulse_setup = self.setup_pulse(mask, mode, bls=bls, wls=wls, wl_bl_sl_voltages=[vwl, vbl, vsl], vwl_unsel_offset=vwl_unsel_offset, pulse_width=pulse_len)
        if pulse_setup[0] == "DONE":
            return pulse_setup[1:]
        else:
            pulse, masks = pulse_setup
        
        self.write_pulse(
            masks, 
            mode=mode, 
            bl_selected=bls, 
            vwl=vwl, 
            vbl=vbl, 
            vsl=vsl, 
            pulse_len=pulse, 
            high_z=None,
            debug=debug)


    def reset_pulse(
        self,
        mask=None,
        mode="RESET",
        bl_selected=None, # selected BL
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vwl_unsel_offset=None,
        pulse_len=None,
        high_z = None
    ):
        """Perform a RESET operation.
        To support 1TNR devices (1 WL, 1 SL, multiple BLs), have input
        "bl" selection parameter. If "bl" is not None, this specifies the
        selected "bl". For all other unselected BLs, by default set their
        value to an intermediate voltage V/4 (based on Hsieh et al, IEDM 2019)
        to reduce impact of oversetting/overreseting unselected devices. 

        This voltage must be relative to value between VSL and VBL,
        not just VBL/4 because VSL is not necessarily 0 V, so just taking
        VBL/4 can increase voltage when VSL > VBL and VBL is stepped down
        (e.g. in the case of PMOS). So we want `VSL + (VBL - VSL)/4.0`
        Example for RESET (VBL fixed, sweep VSL):
            VSL     VBL     VBL/4     VSL + (VBL - VSL)/4
            1.4     2.0      0.5           1.55
            1.2     2.0      0.5           1.40
            1.0     2.0      0.5           1.25
        """
        self.setup_pulse(mask, mode, bl_selected, [vbl, vsl, vwl], vbl_unsel, vwl_unsel_offset, pulse_len, high_z)

        self.write_pulse(mask, mode, bl_selected, vwl, vbl, vsl, vbl_unsel, vwl_unsel_offset, pulse_len, high_z)

    def form_pulse(
        self,
        mask=None,
        mode="FORM",
        bl_selected=None, # selected BL
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vwl_unsel_offset=None,
        pulse_len=None,
        high_z = None
    ):

        """Perform a FORM operation.
        To support 1TNR devices (1 WL, 1 SL, multiple BLs), have input
        "bl" selection parameter. If "bl" is not None, this specifies the
        selected "bl". For all other unselected BLs, by default set their
        value to an intermediate voltage V/4 (based on Hsieh et al, IEDM 2019)
        to reduce impact of oversetting/overreseting unselected devices.

        This voltage must be relative to value between VSL and VBL,
        not just VBL/4 because VSL is not necessarily 0 V, so just taking
        VBL/4 can increase voltage when VSL > VBL and VBL is stepped down
        (e.g. in the case of PMOS). So we want `VSL + (VBL - VSL)/4.0`
        Example for SET (VSL fixed, sweep VBL):
            VSL     VBL     VBL/4     VSL + (VBL - VSL)/4
            2.0     1.4      0.35          1.85      
            2.0     1.2      0.30          1.8
            2.0     1.0      0.25          1.75
        """
        
        self.write_pulse(mask, mode, bl_selected, vwl, vbl, vsl, vbl_unsel, vwl_unsel_offset, pulse_len, high_z)

    
    # region TODO: Single Pulse Form, Reset, Set (with option to do dynamic writes)



    """ ================================================================= """
    """               Setting up the dynamic pulse signals                """
    """ ================================================================= """


    def read_written_cells(self,mode, average_resistance=True,wls=None,bls=None,record=False,print_info=True):
        if average_resistance:
            res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array = self.direct_read(wls=wls,bls=bls,record=False,relayed=True,print_info=True)
            if print_info:
                print(f"Operation {mode}, Resistances: {res_array}, Target Resistance:")
        else:
            res_array1, cond_array1, meas_i_array1, meas_v_array1, meas_i_leak_array1 = self.direct_read(wls=wls,bls=bls,record=False,relayed=True,print_info=False)
            res_array2, cond_array2, meas_i_array2, meas_v_array2, meas_i_leak_array2 = self.direct_read(wls=wls,bls=bls,record=False,relayed=True,print_info=False)
            res_array3, cond_array3, meas_i_array3, meas_v_array3, meas_i_leak_array3 = self.direct_read(wls=wls,bls=bls,record=False,relayed=True,print_info=False)
            
            res_array = pd.concat([res_array1,res_array2,res_array3]).groupby(level=0).mean()
            cond_array = pd.concat([cond_array1,cond_array2,cond_array3]).groupby(level=0).mean()
            
            meas_i_array = pd.concat([meas_i_array1,meas_i_array2,meas_i_array3]).groupby(level=0).mean()
            meas_v_array = pd.concat([meas_v_array1,meas_v_array2,meas_v_array3]).groupby(level=0).mean()
            meas_i_leak_array = pd.concat([meas_i_leak_array1,meas_i_leak_array2,meas_i_leak_array3]).groupby(level=0).mean()
        
        return res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array

    def check_leakage(self,wls,bls,sls,print_info=True):
        wl_inputs = self.relay_switch(wls,relayed=True)

        self.set_to_off([wl_inputs,bls,sls],["WL_IN","BL","SL"])
        self.set_to_off([["WL_UNSEL"]],["WL"])

        for bl,sl in zip(bls,sls):
            self.set_to_ppmu([[bl],[sl]],["BL","SL"])
            self.ppmu_set_vsl(sl,0)
            self.ppmu_set_vbl(bl,0)
            time.sleep(1e-3)
            self.ppmu_set_vbl(bl,0.7)
            time.sleep(1e-3)
            Ibl, Isl = self.digital_patterns.measure_current([bl,sl])[2]
            Vbl, Vsl = self.digital_patterns.measure_voltage([bl,sl])[2]

            Rbl_base = np.abs((Vbl-Vsl)/Ibl)
            Rsl_base = np.abs((Vbl-Vsl)/Ibl)

            self.set_to_ppmu([["WL_UNSEL"]],["WL"])
            self.ppmu_set_vwl(["WL_UNSEL"],2)
            
            Rbl = Rbl_base
            Rsl = Rsl_base
            
            for wl in wls:
                sorted_wls = []
                num_relays = len(self.relays)
                for i in range(num_relays):
                    # Sort the WL channels by relay 0-65 for relay 1, 66-131 for relay 2, (sending 0-65 for each relay)
                    sorted_wls.append([(int(w[3:])-66*i) for w in wl if int(w[3:])//66 == i])
                self.digital_patterns.disconnect_relays(self.relays,sorted_wls)
                time.sleep(2e-3)
                
                # Maybe decompose more, can be used in other sections as well...



    def check_cell_resistance(self,res_array, wls, bls, sls, target_res, mode,print_info=True,debug=None):
        # Remove every cell that is in target resistance
        if mode.upper() == "RESET":
            for wl,wl_bls,wl_sls in zip(wls,bls, sls):
                print(f"Checking resistance for {wl} with BLs {wl_bls}")
                for bl in wl_bls:
                    if print_info:
                        print(res_array)
                    if res_array.at[wl,bl] >= target_res:
                        # print(f"bl {bl}, bls {bls}, wl {wl}, res {res_array.at[wl,bl]} >= target_res {target_res}")
                        wl_bls.remove(bl)
                        wl_sls.remove(f"SL_{str(bl[3:])}")
                        if len(wl_bls) == 0:
                            wls.remove(wl)
                            if len(wls) == 0:
                                # If no cells remain, return True: 
                                # All cells are set to desired resistance range
                                return "DONE"
                    

        if mode.upper() == "SET" or mode.upper() == "FORM":
            for wl,wl_bls,wl_sls in zip(wls,bls,sls):
                print(f"Checking resistance for {wl} with BLs {wl_bls}")
                for bl in wl_bls:
                    if print_info:
                        print(res_array)
                    if res_array.at[wl,bl] <= target_res:
                        # print(f"bl {bl}, bls {bls}, wl {wl}, res {res_array.at[wl,bl]} <= target_res {target_res}")
                        wl_bls.remove(bl)
                        wl_sls.remove(f"SL_{str(bl[3:])}")
                        if len(wl_bls) == 0:
                            wls.remove(wl)
                            if len(wls) == 0:
                                # If no cells remain, return True: 
                                # All cells are set to desired resistance range
                                return "DONE"
                            
        # print(f"Cells to write: {wls, bls, sls}")
        return wls,bls,sls
    

    def _record_write_pulse(self,record, cells, mode, measurements, voltages, success):
        if record:
            with open(self.datafile_path, "a", newline='') as file_object:
                writer = csv.writer(file_object)
                for cell in cells:
                    pass# writer.writerow([self.chip, self.device, cell[0], cell[1]] + measurements + [mode, f"{mode}:{success[cell[0]][cell[1]]}"]+voltages)
        return None


    def dynamic_pulse(self, sessions=None, cells=None, bls=None, wls=None, mode="RESET", print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, voltages=[None,None,None],relayed=False,reset_after=False,debug=None):
        
        """
        Dynamic Pulse: Performs increasingly more aggressive RESET or SET pulses on the given cells.
        This function runs until the target resistance is reached or a maximum number of pulses is reached.
        This function will try to set either the provided cells, or all cells in self.bls and self.wls.
        
        Important Args:
        cells: list of tuples of strings
            List of cells to form, in the form of (BL_#, WL_#)
        bls: list of lists of strings
            List of BL channels to form per word line WL1 [BL1, BL2, ...], WL2 [BL1, BL2, ...] etc.
        wls: list of strings
            List of WL channels to form
        mode: str or list of str
            Mode of operation (RESET or SET)
        """
        # Check for debug printout
        self.dbg.start_function_debug(debug)

        # Initial Pulse Setup
        pulse_setup = self.setup_pulse(
                        masks=False,
                        mode=mode,
                        bls=bls,
                        wls=wls,
                        cells=cells,
                        wl_bl_sl_voltages=voltages,
                        vbl_unsel=None,
                        vwl_unsel_offset=None,
                        pulse_width=None,
                        init_setup=True,
                        measure_res=True,
                        print_data=print_data,
                        average_resistance=average_resistance,
                        record=record,
                        debug=debug
                    )
        if pulse_setup[0] == "DONE":
            return pulse_setup[1:]
        else:
            pulse, masks = pulse_setup
        
        
        # ------------------------- #
        # Configure Dynamic Pulse   #
        # ------------------------- #
        cfg = self.op[mode][self.polarity]

        # Set the initial pulse parameters
        wls,bls,sls = [pulse.cells.wls, pulse.cells.bls, pulse.cells.sls]
        # print("WLS: ", wls, "BLS: ", bls, "SLS: ", sls)

        #vbl, vsl = [pulse.voltages.vbl, pulse.voltages.vsl]
        target_res = pulse.target
        
        # Set the pulse width and word line voltage sweep based on settings or input
        pw_start, pw_stop, pw_step = [cfg["PW_start"], cfg["PW_stop"], cfg["PW_steps"]]
        vwl_start, vwl_stop, vwl_step = [cfg["VWL_start"], cfg["VWL_stop"], cfg["VWL_step"]]
        vbl_unsel = cfg["VBL_UNSEL"]
        vsl_unsel = cfg["VSL_UNSEL"]
        vwl_unsel_offset = cfg["VWL_UNSEL_OFFSET"]

        pdb.set_trace()
        
        # Set the bitline and source line voltages nased on settings/input given the mode
        if mode.upper() == "SET" or mode.upper() == "FORM":
            # If we are running a set operation, we iterate the bit line voltage, 
            # keeping source line constant
            vbl_start, vbl_stop, vbl_step = [cfg["VBL_start"], cfg["VBL_stop"], cfg["VBL_step"]]
            vsl = cfg["VSL"]
            vsl_start, vsl_stop, vsl_step = [vsl, vsl+1, 2]
       
        elif mode.upper() == "RESET":
            # If we are running a reset operation, we iterate the source line voltage, 
            # keeping bit line constant
            vsl_start, vsl_stop, vsl_step = [cfg["VSL_start"],cfg["VSL_stop"], cfg["VSL_step"]]
            vbl = cfg["VBL"]
            vbl_start, vbl_stop, vbl_step = [vbl, vbl+1, 2]
        
        else:
            raise NIRRAMException(f"Invalid mode: {mode}: Please use 'SET', 'RESET', or 'FORM'")
    

        # Need to be redone to actually iterate through multiple WLs, currently can only iterate through one WL
        # Success condition has an early return, can be fixed but requires some WL check reworking
        for wl,wl_bls,wl_sls in zip(wls,bls,sls):

            # Connect the relay and change the name of the word line signal
            if self.relays:
                WL_IN,_ = self.relay_switch([wl], relayed=True, debug = debug)
                # _,_ =self.relay_switch(self.all_wls,relayed=True)
            else:
                WL_IN = [wl]
            
            self.wls = WL_IN
            self.bls = wl_bls
            self.sls = wl_sls
            for pw in np.arange(pw_start,pw_stop,pw_step):
                for vsl in np.arange(vsl_start,vsl_stop,vsl_step):
                    for vbl in np.arange(vbl_start,vbl_stop,vbl_step):
                        for vwl in np.arange(vwl_start,vwl_stop,vwl_step):
                            res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array,cells_to_write = self.direct_write(
                                masks, 
                                sessions=sessions, 
                                mode=mode,
                                wl=wl, 
                                wl_bls=wl_bls,
                                wl_sls=wl_sls,
                                wls=wls,
                                bls=bls,
                                sls=sls,
                                vwl=vwl, 
                                vbl=vbl, 
                                vsl=vsl,
                                vbl_unsel=vbl_unsel,
                                vsl_unsel=vsl_unsel,
                                vwl_unsel_offset=vwl_unsel_offset, 
                                pulse_len=pw, 
                                high_z=None,
                                debug=debug,
                                record=record,
                                cells=cells,
                                print_data=print_data,
                                target_res=target_res,
                                WL_IN=WL_IN)
                            time.sleep(1) 

                            # TODO: Update VBL, VSL, VWL, PW after dynamic pulse... for use in subsequent direct writes

                            if cells_to_write == "DONE":
                                return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array

        self.dbg.end_function_debug()
        return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array

    def single_pulse(self, sessions=None, cells=None, bls=None, wls=None, mode="RESET", print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, voltages=[None,None,None],relayed=False,reset_after=False,debug=None):
        
        """
        Single Pulse
        TODO: documentation
        """
        # Check for debug printout
        self.dbg.start_function_debug(debug)

        # Initial Pulse Setup
        pulse_setup = self.setup_pulse(
                        masks=False,
                        mode=mode,
                        bls=bls,
                        wls=wls,
                        cells=cells,
                        wl_bl_sl_voltages=voltages,
                        vbl_unsel=None,
                        vwl_unsel_offset=None,
                        pulse_width=None,
                        init_setup=True,
                        measure_res=True,
                        print_data=print_data,
                        average_resistance=average_resistance,
                        record=record,
                        debug=debug
                    )
        if pulse_setup[0] == "DONE":
            return pulse_setup[1:]
        else:
            pulse, masks = pulse_setup
        
        
        # ------------------------- #
        # Configure Dynamic Pulse   #
        # ------------------------- #
        cfg = self.op[mode][self.polarity]

        # Set the initial pulse parameters
        p_wls,p_bls,p_sls = [pulse.cells.wls, pulse.cells.bls, pulse.cells.sls]
        # print("WLS: ", wls, "BLS: ", bls, "SLS: ", sls)

        #vbl, vsl = [pulse.voltages.vbl, pulse.voltages.vsl]
        target_res = pulse.target
        
        # Set the pulse width and word line voltage sweep based on settings or input
        vwl_unsel_offset = cfg["VWL_UNSEL_OFFSET"]
        vbl_unsel = cfg["VBL_UNSEL"]
        vsl_unsel = cfg["VSL_UNSEL"]

        pdb.set_trace()
    

        # Need to be redone to actually iterate through multiple WLs, currently can only iterate through one WL
        # Success condition has an early return, can be fixed but requires some WL check reworking
        for wl,wl_bls,wl_sls in zip(p_wls,p_bls,p_sls):

            # Connect the relay and change the name of the word line signal
            if self.relays:
                WL_IN,_ = self.relay_switch([wl], relayed=True, debug = debug)
                # _,_ =self.relay_switch(self.all_wls,relayed=True)
            else:
                WL_IN = [wl]
            
            self.wls = WL_IN
            # self.bls = wl_bls
            # self.sls = wl_sls
            res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array,cells_to_write = self.direct_write(
                masks, 
                sessions=sessions, 
                mode=mode,
                wl=wl, 
                wl_bls=wl_bls,
                wl_sls=wl_sls,
                wls=p_wls,
                bls=p_bls,
                sls=p_sls,
                vbl_unsel=vbl_unsel,
                vsl_unsel=vsl_unsel,
                vwl_unsel_offset=vwl_unsel_offset, 
                high_z=None,
                debug=debug,
                record=record,
                cells=cells,
                print_data=print_data,
                target_res=target_res,
                WL_IN=WL_IN)
            time.sleep(1) 

            # TODO: Update VBL, VSL, VWL, PW after dynamic pulse... for use in subsequent direct writes

            if cells_to_write == "DONE":
                return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array

        self.dbg.end_function_debug()
        return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array


    # def dynamic_set(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug=None):
    #     return self.dynamic_pulse(sessions, cells, bls, wls, mode="SET", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug=debug)
    
    # def dynamic_reset(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug=None):
    #     return self.dynamic_pulse(sessions, cells, bls, wls, mode="RESET", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug=debug)

    # def dynamic_form(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug=None):
    #     return self.dynamic_pulse(sessions, cells, bls, wls, mode="FORM", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug=debug)
    

    """ =================================================== """
    """         Other Bookkeeping Functions:                """           
    """             - Update Data Log                       """
    """             - Define Target Resistance              """
    """             - Relay Switch                          """
    """ =================================================== """
    #region Other Bookkeeping Functions
    def update_data_log(self, date, time, filename, location, notes):
        
        """
        Update the CSV with information on what files were written to,
        what information they contained, and where they are stored.
        The function then returns an incrementing identifier (####)
        that resets each day.
        """

        # Path to the CSV file
        test_log_path = self.settings["path"].get("test_log_file", "data/test_log.csv")

        # Read the last row of the CSV file to get the last identifier
        last_hash = "0000"
        try:
            with open(test_log_path, "r") as test_log:
                reader = csv.reader(test_log)
                last_row = list(reader)[-1]  # Get the last row
                last_date = last_row[0]  # Get the date from the last row
                last_name = last_row[2]  # Get the filename from the last row
                if last_date == date and last_name == filename:  # Check if the last date matches the current date
                    last_hash = str(int(last_row[4]) + 1).zfill(4)  # Increment the last identifier by 1
        except FileNotFoundError:
            # If the file doesn't exist, this is the first entry of the day
            pass

        # Write the new row with the updated identifier
        with open(test_log_path, "a", newline="") as test_log:
            writer = csv.writer(test_log)
            writer.writerow([date, time, filename, location, last_hash, notes])

        # Return the updated identifier
        return last_hash   

    def def_target_res(self, mode, target_res,debug=None):
        self.dbg.start_function_debug(debug)
        
        if mode.lower() == "form":
            self.form_target_res = target_res
        elif mode.lower() == "reset":
            self.reset_target_res = target_res
        elif mode.lower() == "set":
            self.set_target_res = target_res
        else:
            raise NIRRAMException("Invalid mode. Please select 'form', 'reset', or 'set'.")
        
        self.dbg.end_function_debug()

    def relay_switch(self, wls, relayed=True, debug = None):
        self.dbg.start_function_debug(debug)

        for wl in wls: 
            assert(wl in self.all_wls), f"Invalid WL channel {wl}: Please make sure the WL channel is in the all_WLS list."
        
        if self.relays is None:
            raise NIRRAMException("Relay card not found in settings.")

        num_relays = len(self.relays)

        sorted_wls = []
        
        for i in range(num_relays):
            # Sort the WL channels by relay 0-65 for relay 1, 66-131 for relay 2, (sending 0-65 for each relay)
            sorted_wls.append([(int(wl[3:])-66*i) for wl in wls if int(wl[3:])//66 == i])        

        wl_input_signals = [f"WL_IN_{int(wl[3:])%24}"for wl in wls] 
        
        # Switch the relays at the given WL channels, separated by relay.
        if relayed and sorted_wls != self.closed_relays:
            pdb.set_trace()
            # print(f"Connecting WL {sorted_wls[0]} and {list(np.array(sorted_wls[1])+66)}")
            self.digital_patterns.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug)
            self.closed_relays = sorted_wls
        all_wls = self.settings["device"]["WL_IN"]
        
        self.dbg.end_function_debug()
        return wl_input_signals, all_wls
    
    def _flatten(self, nested_list):
        """Recursively flattens a list of lists to any depth."""
        flattened = []
        for item in nested_list:
            if isinstance(item, list):
                flattened.extend(self._flatten(item))
            else:
                flattened.append(item)
        return flattened
    
    #endregion other bookkeeping functions


    # region Unimplemented Functions
    def read_1tnr(        
            self,
            vbl=None,
            vsl=None,
            vwl=None,
            vwl_unsel_offset=None,
            vb=None,
            record=False,
            check=True,
            dynam_read=False,
        wl_name = None
        ):
            print("No 1TNR Read Functionality, will be implemented in the future")
            # ============================= #
            # TODO: 1TNR Read Functionality #
            # ============================= #
            return None

    # endregion Unimplemented Functions

    def format_output(self):
        dir_path = os.path.dirname(self.datafile_path)
        filename = os.path.basename(self.datafile_path)

        formatted_dir = os.path.join(dir_path,"formatted")
        os.makedirs(formatted_dir, exist_ok=True)

        formatted_file_path = os.path.join(formatted_dir,filename)
        data = pd.read_csv(self.datafile_path,header=None)

        if data.shape[1] < 6:
            raise ValueError("IN too short")
        row_names = data.iloc[:,3]
        column_names = data.iloc[:,4]
        values = data.iloc[:,5]

        formatted_data = pd.DataFrame({col: [val] for col, val in zip(column_names, values)}, index=row_names)
        formatted_data.to_csv(formatted_file_path, index=True)

def arg_parse():
    parser = argparse.ArgumentParser(description="NIRRAM Abstracted Class")
    parser.add_argument("--chip", type=str, help="Chip ID", default="chip")
    parser.add_argument("--device", type=str, help="Device ID", default="device")
    parser.add_argument("--polarity", type=str, help="Polarity of the device", default="PMOS")
    parser.add_argument("--settings", type=str, help="Path to the settings file", default="settings/MPW_Direct_Write.toml")
    parser.add_argument("--test_type", type=str, help="Type of test to run", default="single")
    parser.add_argument("--additional_info", type=str, help="Additional information", default="NIRRAM Direct Write Test")
    parser.add_argument("--measurement",type=str,help="Measurement run",default="rr")
    parser.add_argument("--iter", type=int,help="Number of Reads", default=1)
    args = parser.parse_args()
    return args


def single_pulse_test(wls=None,bls=None,sls=None,IV=False,args=None):
    # initialize the NIRRAM object
    rram = NIRRAM(args.chip, args.device, polarity=args.polarity, settings=args.settings, 
                  test_type=args.test_type, additional_info=args.additional_info)
    print("NIRRAM Abstracted Class Loaded Successfully.")

    all_bls = []
    all_wls = []
    for i in range(128):
        all_wls.append(f"WL_{i}")
        if i >= 0 and i < 32:
            all_bls.append(f"BL_{i}")
    #remove_bias=[f"WL_{i}" for i in [23,34,47,54,60,81,83,102,105,113,114,123]]
    #all_wls = [wl for wl in all_wls if wl not in [remove_bias]]
    if wls is None:
        top_wls = all_wls
    else:
        top_wls = wls
    if bls is None:
        top_bls = all_bls
    else: 
        top_bls = bls
    
    '''
    vwl = np.arange(-1,2,0.2)
    vbl = np.arange(-1,2,0.1)
    vsl=0
    IV = False
    if IV:
        for wl in wls:
            for bl in bls:
                rram.ppmu_set_vwl(["WL_UNSEL"],0)
                rram.measure_iv(wl=[wl], bl=[bl], vwl=vwl, vbl=vbl, vsl=vsl, vwl_unsel=0, relayed=True)
        quit()
    '''
    x = args.measurement
    
    # print(f"Running single pulse test with operations: {x}")
    iterations = args.iter
    for oper in x:
        print(f"Running single pulse test with operation: {oper} for {iterations} iterations")
        test_wls = copy.deepcopy(top_wls)
        test_bls = copy.deepcopy(top_bls)
        if oper == "r":
            for i in range(iterations): #ususally just 1
                vwl_unsel_offset = rram.op["READ"][rram.polarity]["VWL_UNSEL_OFFSET"] 
                # print(f"BLS: {bls}, WLS: {wls}, VWL_UNSEL_OFFSET: {vwl_unsel_offset}")
                rram.direct_read(wls=test_wls, bls=test_bls, remove_bias=[],vwl_unsel_offset=vwl_unsel_offset, record=True, relayed=True, print_info=["res"])
            rram.format_output()
        elif oper in ["F","S","R"]:
            if oper == "F":
                oper = "FORM"
            elif oper == "S":
                oper = "SET"
            elif oper == "R":
                oper = "RESET"
            target_res = rram.target_res[oper.upper()]
            for wl in test_wls:
                rram.single_pulse(wls=[wl], bls=test_bls, mode=oper.upper(), record=True, print_data=True, target_res=target_res, average_resistance=False, debug=False)

        else:
            raise NIRRAMException(f"Invalid operation: {oper}. Please use 'r' (read), 'S' (set), 'R' (reset), or 'F' (form) for dynamic pulse.")
    # # quit()


def dynamic_pulse_test(wls=None,bls=None,sls=None,IV=False,args=None):
    # initialize the NIRRAM object
    rram = NIRRAM(args.chip, args.device, polarity=args.polarity, settings=args.settings, 
                  test_type=args.test_type, additional_info=args.additional_info)
    print("NIRRAM Abstracted Class Loaded Successfully.")

    all_bls = []
    all_wls = []
    for i in range(128):
        all_wls.append(f"WL_{i}")
        if i >= 0 and i < 32:
            all_bls.append(f"BL_{i}")
    #remove_bias=[f"WL_{i}" for i in [23,34,47,54,60,81,83,102,105,113,114,123]]
    #all_wls = [wl for wl in all_wls if wl not in [remove_bias]]
    if wls is None:
        top_wls = all_wls
    else:
        top_wls = wls
    if bls is None:
        top_bls = all_bls
    else: 
        top_bls = bls
    
    '''
    vwl = np.arange(-1,2,0.2)
    vbl = np.arange(-1,2,0.1)
    vsl=0
    IV = False
    if IV:
        for wl in wls:
            for bl in bls:
                rram.ppmu_set_vwl(["WL_UNSEL"],0)
                rram.measure_iv(wl=[wl], bl=[bl], vwl=vwl, vbl=vbl, vsl=vsl, vwl_unsel=0, relayed=True)
        quit()
    '''
    x = args.measurement
    for oper in x:
        test_wls = copy.deepcopy(top_wls)
        test_bls = copy.deepcopy(top_bls)
        if oper in ["F","S","R"]:
            if oper == "F":
                oper = "FORM"
            elif oper == "S":
                oper = "SET"
            elif oper == "R":
                oper = "RESET"
            target_res = rram.target_res[oper.upper()]
            for wl in test_wls:
                rram.dynamic_pulse(wls=[wl], bls=test_bls, mode=oper.upper(), record=True, print_data=True, target_res=target_res, average_resistance=False, debug=False)
        else:
            raise NIRRAMException(f"Invalid operation: {oper}. Please use 'S' (set), 'R' (reset), or 'F' (form) for dynamic pulse.")

def main(wls=None,bls=None,sls=None):
    # Parse arguments and initialize the NIRRAM object
    args = arg_parse()

    print("NIRRAM Abstracted Class Loaded Successfully.")
    if args.test_type == "single":
        single_pulse_test(wls=wls,bls=bls,sls=sls,args=args)
    elif args.test_type == "dynamic":
        dynamic_pulse_test(wls=wls,bls=bls,sls=sls,args=args)
    else:
        raise NIRRAMException(f"Invalid operation: {args.test_type}. Please use 'single' or 'dynamic' for testing.")

if __name__ == "__main__":
    wls = ["WL_0"]
    bls = [["BL_0"]]
    sls = [["SL_0"]]
    # bls = [f"BL_{b}" for b in [3,7,11,15,19,23,27,31]]
    main(wls=wls,bls=bls,sls=sls)
    # dynamic_pulse_test(wls=wls,bls=bls)
    # single_pulse_test(wls=wls,bls=bls)


# example flow:


# DYNAMIC PULSE TEST:
# python nirram_abstracted.py --chip chip1 --device device1 --polarity NMOS --settings settings/MPW_Direct_Write.toml --test_type dynamic --additional_info "NIRRAM Direct Write Test" --measurement "FRS" --iter 1

# MANUALLY UPDATE TOML FILE

# SINGLE PULSE TEST:
# python nirram_abstracted.py --chip chip1 --device device1 --polarity NMOS --settings settings/MPW_Direct_Write.toml --test_type single --additional_info "NIRRAM Direct Write Test" --measurement "rFrRrSr" --iter 1
# region Import necessary libraries
import pdb
import tomli
import time
from dataclasses import dataclass
import sys
from os.path import abspath
from os import getcwd
from os import remove as remove_file
import nidigital
import numpy as np
import pandas as pd
import csv
from datetime import date, datetime
from BitVector import BitVector

sys.path.append(getcwd() + '\\SourceScripts')
from masks import Masks
from digital_pattern import DigitalPattern
from settings_util import SettingsUtil


# endregion
@dataclass
class RRAMOperationResult:
    """Data class to store measured parameters from an RRAM operation
    (e.g. set, reset, form, etc.)
    """
    chip: str
    device: str
    mode: str
    wl: str
    bl: str
    res: float
    cond: float
    i: float
    v: float
    vwl: float
    vsl: float
    vbl: float
    pw: float
    success: bool

class NIRRAMException(Exception):
    """Exception produced by the NIRRAM class"""
    def __init__(self, msg):
        super().__init__(f"NIRRAM: {msg}")

def printdb(text):
    print(f"\n\n\n{text}\n\n\n")
    return 1
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


    def __init__(
            self,
            chip,
            device,
            polarity = "PMOS",
            settings = "settings/MPW_Direct_Write.toml",
            debug_printout = False,
            test_type = "Default",
            additional_info = ""
            ):
        # flag for indicating if connection to ni session is open
        self.closed = True
        
        
        # If settings is a string, load as TOML file
        if isinstance(settings, str):
            with open(settings, "rb") as settings_file:
                settings = tomli.load(settings_file)
        
        # Ensure settings is a dict
        if not isinstance(settings, dict):
            raise NIRRAMException(f"Settings should be a dict, got {repr(settings)}.")

        self.settings = settings

        # Convert NIDigital spec paths to absolute paths
        settings["NIDigital"]["specs"] = [abspath(path) for path in settings["NIDigital"]["specs"]]
        self.debug_printout = debug_printout
        
        # Initialize RRAM logging
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        hash = self.update_data_log(current_date, current_time, f"chip_{chip}_device_{device}", test_type, additional_info)
        self.datafile_path = settings["path"]["data_header"] + f"/{test_type}/{current_date}_{chip}_{device}_{hash}.csv"
        
        self.file_object = open(self.datafile_path, "a", newline='')
        self.datafile = csv.writer(self.file_object)

        self.datafile.writerow(["Chip_ID", "Device_ID", "OP", "Row", "Col", "Res", "Cond", "Meas_I", "Meas_V", "Success/State", "Prog_VBL", "Prog_VSL", "Prog_VWL", "Prog_Pulse"])
        self.file_object.close()

        self.chip = chip
        self.device = device
        self.polarity = polarity
        self.load_settings(settings)
        self.load_session(settings)
        
        self.bl_dev = []
        self.sl_dev = []
        self.wl_dev = []
        self.zero_rows = None
        self.NC_rows = None
 
    def load_settings(self,settings, debug_printout = None):
        if debug_printout is None: debug_printout = self.debug_printout

        if isinstance(settings, str):
            with open(settings, "rb") as settings_file:
                settings = tomli.load(settings_file)

        if not isinstance(settings, dict):
            raise ValueError(f"Settings should be a dict, got {repr(settings)}.")

        settings["NIDigital"]["specs"] = [abspath(path) for path in settings["NIDigital"]["specs"]]
        
        # Store/initialize parameters
        self.target_res = settings["target_res"]
        self.op = settings["op"] # operations

        # body voltages, str name => body voltage
        if "body" in settings["device"]:
            self.body = settings["device"]["body"]
        else: self.body = None
        
        # Define all_bl, all_sl, all_wl from toml file
        self.all_wls = settings["device"]["all_WLS"]
        self.all_bls = settings["device"]["all_BLS"]
        self.all_sls = settings["device"]["all_SLS"]

        # Define bl, sl, and wl from toml file
        self.wls = settings["device"]["WLS"]

        if "WL_SIGNALS" in settings["device"]:
            self.wl_signals = settings["device"]["WL_SIGNALS"]

        self.bls = settings["device"]["BLS"]
        self.sls = settings["device"]["SLS"]
        self.wl_unsel = settings["device"]["WL_UNSEL"]

        if "all_WL_SIGNALS" in settings["device"]:
            self.all_wl_signals = settings["device"]["all_WL_SIGNALS"]

        self.relays = None
        if "NISwitch" in settings:
            assert "deviceID" in settings["NISwitch"], "NISwitch deviceID not found in settings"
            self.relays = settings["NISwitch"]["deviceID"]
        # Set rows to avoid for WLs
        if "zero_rows" in settings["device"]:
            self.zero_rows = settings["device"]["zero_rows"] if len(settings["device"]["zero_rows"]) > 0 else None
        if "NC_rows" in settings["device"]:
            self.NC_rows = settings["device"]["NC_rows"] if len(settings["device"]["NC_rows"]) > 0 else None
        
        if self.relays is None:
            self.all_channels = self.all_bls + self.all_sls + self.all_wls
        else:
            self.all_channels = self.all_bls + self.all_sls + self.all_wl_signals

        #Set the target resistance for the device
        self.def_target_res("set", settings["target_res"]["SET"])
        self.def_target_res("reset", settings["target_res"]["RESET"])
        self.def_target_res("form", settings["target_res"]["FORM"])

        # Set the pulse lengths for the device
        if "PULSE" in settings:
            if "prepulse_len" in settings["PULSE"]:
                self.prepulse_len = settings["PULSE"]["prepulse_len"]
            if "postpulse_len" in settings["PULSE"]:
                self.postpulse_len = settings["PULSE"]["postpulse_len"]
        if "max_pulse_len" in settings["PULSE"]:
            self.max_pulse_len = settings["PULSE"]["max_pulse_len"]
        else:
            self.max_pulse_len = 1e+4
            

    def load_session(self,settings,debug_printout = None):  
        if debug_printout is None: debug_printout = self.debug_printout
        
        # Only works for 1T1R arrays, sets addr idx and prof
        self.addr_idxs = {}
        self.addr_prof = {}

        for wl in self.wls:
            self.addr_idxs[wl] = {}
            self.addr_prof[wl] = {}
            for i in range(len(self.bls)):
                bl = self.bls[i]
                
                # temporary fix for 1TNR: if bls and sls len not equal, just use sl0
                if len(self.sls) == len(self.bls):
                    sl = self.sls[i]
                else:
                    sl = self.sls[0]
                self.addr_idxs[wl][bl] = (bl, sl, wl)
                self.addr_prof[wl][bl] = {"FORMs": 0, "READs": 0, "SETs": 0, "RESETs": 0} 

        # Load NIDigital session

        self.digital_patterns = DigitalPattern(self.settings)
        self.digital = self.digital_patterns.sessions

        self.digital_patterns.configure_read(sessions=None,pins=[self.bls,self.sls],sort=False)

        self.digital_patterns.digital_all_pins_to_zero()
        self.digital_patterns.commit_all()

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
        meas_vsls=False,
        meas_vwls=False,
        meas_isls=True,
        meas_ibls=False,
        meas_i_gate=True,
        record=False,
        check=True,
        print_info = True,
        debug_printout = None,
        relayed=False
    ):
        """Perform a READ operation. This operation works for single 1T1R devices and 
        arrays of devices, where each device has its own WL/BL.
        Returns list (per-bitline) of tuple with (res, cond, meas_i, meas_v)"""
        if debug_printout is None: debug_printout = self.debug_printout

        wls = self.wls if wls is None else wls
        bls = self.bls if bls is None else bls

        if type(bls[0]) is not list:
            bls = [bls]*len(wls)

        if bls is None: sls = self.sls
        elif type(bls[0]) is int or type(bls[0]) is np.uint8:
            sls = [[f"SL_{bl}" for bl in wl_bls] for wl_bls in bls]
        else:
            sls = [[f"SL{bl[2:]}" for bl in wl_bls] for wl_bls in bls]

        
        # Set the read voltage parameters based on settings or parameter inputs
        vbl = self.op["READ"][self.polarity]["VBL"] if vbl is None else vbl
        vwl = self.op["READ"][self.polarity]["VWL"] if vwl is None else vwl
        vsl = self.op["READ"][self.polarity]["VSL"] if vsl is None else vsl
        vb = self.op["READ"][self.polarity]["VB"] if vb is None else vb

        if debug_printout:
            print(f"Direct Read: VBL={vbl}, VWL={vwl}, VSL={vsl}, VB={vb}, VWL_UNSEL_OFFSET={vwl_unsel_offset}")

        # Dataframes to store measurement results, resistance, conductance, current, voltage
        # print(f"BLs: {bls}")
        if type(bls[0])==list:
            res_array_bls = list(set(np.concatenate(bls).tolist()))
            res_array_bls = sorted(res_array_bls, key=lambda s: int(s.split('_')[1]))
        else:
            res_array_bls = sorted(bls, key=lambda s: int(s.split('_')[1]))
                               

        res_array = pd.DataFrame(np.zeros((len(wls), len(res_array_bls))), wls, res_array_bls)
        cond_array = pd.DataFrame(np.zeros((len(wls), len(res_array_bls))), wls, res_array_bls)
        meas_v_array = pd.DataFrame(np.zeros((len(wls), len(res_array_bls))), wls, res_array_bls)
        meas_i_array = pd.DataFrame(np.zeros((len(wls), len(res_array_bls))), wls, res_array_bls)
        meas_i_leak_array = pd.DataFrame(np.zeros((len(wls), len(res_array_bls))), wls, res_array_bls)
        # Set the voltage for unselected word lines
        if vwl_unsel_offset is None:
            if "VWL_UNSEL_OFFSET" in self.op["READ"][self.polarity]:
                vwl_unsel_offset = self.op["READ"][self.polarity]["VWL_UNSEL_OFFSET"]
            else:
                vwl_unsel_offset = 0.0

        if debug_printout:
            print(f"Direct Read: VBL={vbl}, VWL={vwl}, VSL={vsl}, VB={vb}, VWL_UNSEL_OFFSET={vwl_unsel_offset}")
        
        # let the supplies settle for accurate measurement
        time.sleep(self.op["READ"]["settling_time"]) 
        

        if self.op["READ"]["mode"] != "digital":
            NIRRAMException("READ mode must be set to 'digital' in settings.")

        if remove_bias is None:
            remove_bias = []
        
        if self.relays is not None:
            self.wl_signals = self.settings["device"]["all_WL_SIGNALS"]

        formatted_r = []   
        formatted_c = []
        formatted_i = []
        formatted_v = []

        for wl,wl_bls,wl_sls in zip(wls,bls,sls):
            if self.relays is not None:
                wl_entry = wl
                wl,all_wls = self.relay_switch([wl]+remove_bias,relayed=relayed,debug_printout=False)
                wl = wl[0]

            for wl_i in all_wls:
                if wl_i in wl:
                    self.ppmu_set_vwl(wl_i, vwl)
                elif wl_i in remove_bias:
                    self.ppmu_set_vwl(wl_i, vsl)
                else:
                    self.ppmu_set_vwl(wl_i, vsl + vwl_unsel_offset)
                    
            
            self.digital_patterns.ppmu_source([[],[],[all_wls]], sort=False)

            self.ppmu_set_vbl(self.bls,vbl)
            self.ppmu_set_vsl(self.sls,vsl)
            self.set_to_ppmu([self.bls,self.sls],["BL","SL"])

            #Let the supplies settle for accurate measurement
            time.sleep(self.op["READ"]["settling_time"])

            # Measure selected voltage. Default is to measure VBL
            if meas_vbls:
                meas_bls_v_by_session,dict_meas_bls_v,meas_bls_v = self.digital_patterns.measure_voltage([wl_bls,[],[]],sort=False)
            
                # if debug_printout:
                #     if meas_vbls:
                #         print([f"{bl} = {meas_bl_v}" for bl, meas_bl_v in zip(wl_bls, meas_bls_v)])
        

            if meas_vsls:
                meas_sls_v_by_session,dict_measure_sls_v,meas_sls_v = self.digital_patterns.measure_voltage([[],wl_sls,[]],sort=False)

                # if debug_printout:
                #     print([f"{sl} = {meas_sl_v}" for sl, meas_sl_v in zip(sls, meas_sls_v)])

            if meas_vwls:
                meas_wls_v_by_session,dict_meas_sls_v,meas_wls_v = self.digital_patterns.measure_voltage([[],[],wls],sort=False)

                # if debug_printout:
                #     print([f"{wl} = {meas_wl_v}" for wl, meas_wl_v in zip(wls, meas_wls_v)])

            # Measure selected current, default is to measure ISL and I gate
            if meas_isls: 
                _,_,meas_sls_i = self.digital_patterns.measure_current([[],wl_sls,[]],sort=False)

                # if debug_printout:
                #     print([f"{sl} = {meas_sl_i}" for sl, meas_sl_i in zip(wl_sls, meas_sls_i)])

            if meas_ibls:
                _,_,meas_bls_i = self.digital_patterns.measure_current([[],[],wl_bls],sort=False)

                # if debug_printout:
                #     print([f"{bl} = {meas_bl_i}" for bl, meas_bl_i in zip(wl_bls, meas_bls_i)])

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

                # if debug_printout:
                #     print([f"{wl} = {meas_wl_i}" for wl, meas_wl_i in zip(wls, meas_wls_i)])
        
            
            if self.relays is not None:
                self.digital_patterns.ppmu_set_pins_to_zero(sessions=None,pins=[self.bls,self.sls,self.wl_signals],sort=False)
            else:
                self.digital_patterns.ppmu_set_pins_to_zero(sessions=None,pins=[self.bls,self.sls,self.wls],sort=False)


            if meas_isls:
                if debug_printout:
                    print(f"measure ISL")
                r_wl = np.abs((self.op["READ"][self.polarity]["VBL"] - self.op["READ"][self.polarity]["VSL"])/np.array(meas_sls_i) - self.op["READ"]["shunt_res_value"])

            if meas_ibls:
                if debug_printout:
                    print("measure IBL")
                r_wl = np.abs((self.op["READ"][self.polarity]["VBL"] - self.op["READ"][self.polarity]["VSL"])/meas_bls_i - self.op["READ"]["shunt_res_value"])
            
            if not meas_isls and not meas_ibls:
                if meas_i_gate: 
                    print("Measuring I gate for resistance between gate and source")
                    r_wl = np.abs((self.op["READ"][self.polarity]["VWL"] - self.op["READ"][self.polarity]["VSL"])/meas_wls_i - self.op["READ"]["shunt_res_value"])
                else:
                    print("No current measurement selected, cannot calculate resistance")
                    r_wl = None

            wl = wl_entry if self.relays is not None else wl

            r_wl = np.array([None if res_bit not in wl_bls else r_wl[wl_bls.index(res_bit)] for res_bit in res_array_bls])

            for r in r_wl:
                if r <= 0:
                    r = 1e-12
            
            r_for_c = r_wl
            
            c_wl = 1/r_for_c if r_for_c is not None else None

            

            res_array.loc[wl] = r_wl
            cond_array.loc[wl] = c_wl
            meas_v_array.loc[wl] = meas_bls_v if meas_vbls else meas_sls_v
            meas_i_array.loc[wl] = meas_bls_i if meas_ibls else meas_sls_i
            meas_i_leak_array.loc[wl] = meas_i_gate if meas_i_gate else None

            formatted_r.append([f"{value/1000:.2f}kΩ" for value in r_wl])
            formatted_c.append([f"{value:.2e}S" for value in c_wl])
            formatted_i.append([f"{value:.2e}A" for value in meas_i_array.loc[wl]])
            formatted_v.append([f"{value:.2e}V" for value in meas_v_array.loc[wl]])

            self.all_wls = self.settings["device"]["all_WLS"]

        if print_info == True or type(print_info) is str:
        
            if print_info == True:
                print(f"Resistance:\n{pd.DataFrame(formatted_r),wls,bls}")
            
            if type(print_info) is str:
                if print_info == "all":
                    print(f"Resistance:\n{pd.DataFrame(formatted_r,wls,bls)}\n")
                    print(f"Conductance:\n{pd.DataFrame(formatted_c,wls,bls)}\n")
                    print(f"Current:\n{pd.DataFrame(formatted_i,wls,bls)}\n")
                    print(f"Voltage:\n{pd.DataFrame(formatted_v,wls,bls)}\n\n")
                
                if print_info == "res":
                    print(f"Resistance:\n{pd.DataFrame(formatted_r,wls,bls)}\n")
                if print_info == "cond":
                    print(f"Conductance:\n{pd.DataFrame(formatted_c,wls,bls)}\n")
                if print_info == "i":
                    print(f"Current:\n{pd.DataFrame(formatted_i,wls,bls)}\n")
                if print_info == "v":
                    print(f"Voltage:\n{pd.DataFrame(formatted_v,wls,bls)}\n")
            
            if type(print_info) is list:
                if "res" in print_info:
                    print(f"Resistance:\n{pd.DataFrame(formatted_r,wls,bls)}\n")
                if "cond" in print_info:
                    print(f"Conductance:\n{pd.DataFrame(formatted_c,wls,bls)}\n")
                if "i" in print_info:
                    print(f"Current:\n{pd.DataFrame(formatted_i,wls,bls)}\n")
                if "v" in print_info:
                    print(f"Voltage:\n{pd.DataFrame(formatted_v,wls,bls)}\n")
        
        
        if record:
            with open(self.datafile_path, "a", newline='') as file_object:
                datafile = csv.writer(file_object)
                for wl,wl_bls in zip(wls,bls):
                    for bl in wl_bls:
                        if check:
                            if res_array.loc[wl, bl] < self.set_target_res:
                                check_on = "set"
                            elif res_array.loc[wl, bl] > self.reset_target_res:
                                check_on = "reset"
                            else:
                                check_on = "unknown"
                        print(f"checking ({wl}, {bl}): {res_array.loc[wl, bl]} | {check_on}")
                        datafile.writerow([self.chip, self.device, "READ", wl, bl, res_array.loc[wl, bl], cond_array.loc[wl, bl], meas_i_array.loc[wl, bl], meas_v_array.loc[wl, bl], check_on])
        
   
        time.sleep(self.op["READ"]["settling_time"])

        return res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array        
    

    """ ================================================================= """
    """                   Setting voltages and currents                   """
    """ Serially setting voltages and currents for VBL, VSL, ISL, and VWL """
    """                PPMU and Digital sources are defined               """
    """ ================================================================= """

    def ppmu_set_voltage(self, v, channels, name, sort=True):
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

        # Check if channels are integers, if yes convert them to string format
        if isinstance(channels[0], (int, np.uint8)):
            channels = [f"{name}_{chan}" for chan in channels]

        # Check if all channels are valid
        all_channels = self.settings["device"][f"all_{name}S"]
        for chan in channels:
            if chan not in all_channels:
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
        self.digital_patterns.ppmu_set_voltage(pins=channels, voltage_levels=v, sessions=None, sort=sort, source=True)


    def ppmu_set_vbl(self, vbl_chan, vbl,sort=True):
        """Set (active) VBL using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vbl,vbl_chan,"BL",sort=sort)

    def ppmu_set_vsl(self, vsl_chan, vsl,sort=True):
        """Set (active) VBL using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vsl,vsl_chan,"SL",sort=sort) 
    
    def ppmu_set_vwl(self, vwl_chan, vwl,sort=True):
        """Set (active) VWL using NI-Digital driver (inactive disabled)"""
        if self.relays is not None:
            name = "WL_SIGNAL"
        else:
            name = "WL"
        self.ppmu_set_voltage(vwl,vwl_chan,name,sort=sort)

    def ppmu_set_vbody(self, vbody_chan, vbody):
        """Set (active) VBody using NI-Digital driver (inactive disabled)"""
        self.ppmu_set_voltage(vbody,vbody_chan,"Body",sort=True)

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

    def set_to_ppmu(self,channels,name, sort=True,debug_printout=None):
    
        if type(channels) is not list:
            channels = [channels]
        if type(channels[0]) is list and sort==True:
            if type(channels[0][0]) is int or type(channels[0][0]) is np.uint8:
                channels = [[f"{name[channels.index[channel]]}_{chan}" for chan in channel]for channel in channels]
            
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("ppmu", pins=channels,sessions=None,sort=sort,debug=debug_printout)


    def digital_set_voltage(self, channels, sessions=None, vi_lo=0, vi_hi=1, vo_lo=0, vo_hi=1, name=None, sort=True, debug_printout=None):

        # Set the value for debug_printout if not provided
        debug_printout = self.start_function_debug_printout(debug_printout, "digital_set_voltage")
        # Verfiy that any individually given channels are turned into a list to match the expected format
        if type(channels) is not list:
            channels = [channels]
        if type(sessions) is not list:
            sessions = [sessions]
        # Channels may be given as integers, if so, convert to strings for nidigital
        #   Ex: channels = [0, 1, 2], name = DIO -> channels = ["DIO_0", "DIO_1", "DIO_2"]
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        # region verify channels exist
        for chan in channels:
            if chan not in self.settings["device"][f"all_{name}S"]:
                raise NIRRAMException(f"Invalid V{name} channel {chan}. \nChannel not in all_{name}S.")
        #endregion
        instruments =  self.digital_patterns.settings["NIDigital"]

        for num, session in enumerate(sessions):
            if type(session) is int:
                if session not in range(len(self.digital)):
                    raise NIRRAMException(f"Invalid session {session}. \nSession not in range(len(self.digital)).")
            elif type(session) is str:
                if session in instruments["pingroups"]:
                    sessions[num] = self.digital[instruments["pingroups"].index(session)]
                elif session in self.all_channels:
                    sessions[num] = self.digital[self.all_channels.index(session)//32]
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

        self.internal_function_debug_printout(debug_printout, "Setting", ["vi_lo", "vi_hi", "vo_lo", "vo_hi"], voltages)
 
        vi_lo, vi_hi, vo_lo, vo_hi = voltages
        
        # Set the voltages using the digital_set_voltages function
        self.digital_patterns.digital_set_voltages(pins=channels, sessions=sessions, vi_lo=vi_lo, vi_hi=vi_hi, vo_lo=vo_lo, vo_hi=vo_hi,sort=sort)

        self.end_function_debug_printout(debug_printout, "digital_set_voltage")


    def set_vsl(self, vsl_chan, vsl_hi, vsl_lo, debug_printout = None):
        # Debug Printout: Start and Internal
        debug_printout = self.start_function_debug_printout(debug_printout, "set_vsl")
        self.internal_function_debug_printout(debug_printout, f"Setting VSL for {vsl_chan}", ["vsl_hi", "vsl_lo"], [vsl_hi, vsl_lo])
        
        # Set VSL using NI-Digital Drivers
        self.digital_set_voltage(vsl_chan, "SL", vi_lo=vsl_lo, vi_hi=vsl_hi, vo_lo=vsl_lo, vo_hi=vsl_hi, name="SL", sort=True,debug_printout=debug_printout)
        
        # Debug Printout: End
        self.end_function_debug_printout(debug_printout, "set_vsl")


    def set_vbl(self, vbl_chan, vbl_hi, vbl_lo, debug_printout = None):
        debug_printout = self.start_function_debug_printout(debug_printout, "set_vbl")
        self.internal_function_debug_printout(debug_printout, f"Setting VBL for {vbl_chan}", ["vbl_hi", "vsl_lo"], [vbl_hi, vbl_lo])
        
        # Set VSL using NI-Digital Drivers
        self.digital_set_voltage(vbl_chan, "BL", vi_lo=vbl_lo, vi_hi=vbl_hi, vo_lo=vbl_lo, vo_hi=vbl_hi, name="BL", sort=True,debug_printout=debug_printout)
        
        # Debug Printout: End
        self.end_function_debug_printout(debug_printout, "set_vsl")   


    def set_vwl(self, vwl_chan, vwl_hi, vwl_lo, debug_printout = None):
        # Debug Printout: Start and Internal
        debug_printout = self.start_function_debug_printout(debug_printout, "set_vwl")
        self.internal_function_debug_printout(debug_printout, f"Setting VWL for {vwl_chan}", ["vwl_hi", "vsl_lo"], [vwl_hi, vwl_lo])
        
        # Set WL name based on if they are relayed
        if all(len(chan) > 6 for chan in vwl_chan):
            wl_name = "WL_SIGNAL"
        elif all(len(chan) < 7 for chan in vwl_chan):
            wl_name = "WL"
        else:
            raise NIRRAMException(f"Invalid VWL channel {vwl_chan}. \nChannel not in all_WL_SIGNALS or all_WLS.")
        # Set VWL using NI-Digital Drivers
        self.digital_set_voltage(vwl_chan, "WL", vi_lo=vwl_lo, vi_hi=vwl_hi, vo_lo=vwl_lo, vo_hi=vwl_hi, name=wl_name, sort=True,debug_printout=debug_printout)
        
        # Debug Printout: End
        self.end_function_debug_printout(debug_printout, "set_vwl")

    def set_to_digital(self,channels,name, sort=True,debug_printout=None):
        
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]
        
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("digital", pins=channels,sessions=None,sort=sort,debug_printout=debug_printout)


    def set_to_off(self,channels,name, sort=True,debug_printout=None):
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("off", pins=channels,sessions=None,sort=sort,debug_printout=debug_printout)

    def set_to_disconnect(self,channels,name, sort=True,debug_printout=None):
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("disconnect", pins=channels,sessions=None,sort=sort,debug_printout=debug_printout)


    """ ================================================================= """
    """               Setting up the write pulse signals                  """
    """ ================================================================= """

    def write_pulse(
        self,
        masks,
        sessions=None,
        pingroups=None,
        sort=True,
        mode="SET",
        bl_selected=None,
        wls=None,
        bls=None,
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vwl_unsel_offset=None,
        pulse_len=None,
        high_z = None,
        debug_printout = None,
        relayed=True,
        pulse_lens = None,
        max_pulse_len = None
        ):

        pulse_lens = pulse_lens or [self.prepulse_len, pulse_len, self.postpulse_len]
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
        if mode == "SET":
            v_base = vsl
            
        elif mode == "FORM":
            v_base = vsl

        elif mode == "RESET":
            v_base = vbl
        
        else:
            raise NIRRAMException(f"Invalid mode: {mode}. Please select 'SET', 'RESET', or 'FORM'.")

        # Write Static (X) to all channels
        self.digital_patterns.write_static_to_pins(pins=self.all_channels,sort=True)

        # Set the selected word line to the desired voltage
        vwl_unsel_offset = vwl_unsel_offset or self.op[mode][self.polarity]["VWL_UNSEL_OFFSET"]
        vwl_unsel = v_base + vwl_unsel_offset

        # Debug Printout
        if self.debug_printout:
            print(f"{mode} Pulse: VWL={vwl}, VBL={vbl}, VSL={vsl}, VBL_UNSEL={vbl_unsel}, VWL_UNSEL ={vwl_unsel}")


        # ------------------------- #
        #        Define WLS         #
        # ------------------------- #
        wls = wls or self.wls
        
        if self.relays is not None:
            all_wls = self.all_wl_signals
            if len(wls[0]) < 7:
                wls = [f"WL_IN_{wl[3:]}" for wl in wls]
            
            all_wls = self.all_wl_signals + self.all_wls
        else:
            all_wls = self.all_wls
        
        if debug_printout:
            print(wls)
            
            
            
        # ------------------------- #
        #       set voltages        #
        # ------------------------- #

        # Set UNSEL Wordlines to the desired voltage
        self.set_vwl(["WL_UNSEL"], vwl_unsel, vwl_lo=v_base, debug_printout = debug_printout)
        if self.debug_printout: print(f"Setting UNSEL WLS to {vwl_unsel} V") 
        
        # Set SEL Wordlines to the desired voltage
        self.set_vwl(wls, vwl, vwl_lo=v_base, debug_printout = debug_printout)
        if self.debug_printout: print(f"Setting SEL WLS {wls} to {vwl} V")

        # Set Bitlines to the desired voltage
        if bl_selected is not None:
            bls_unselected = [bl for bl in self.bls if bl not in bl_selected]
            self.set_vbl(self.bls, vbl, vbl_lo=v_base, debug_printout = debug_printout)
            if len(bls_unselected) > 0:
                self.set_vbl(bls_unselected, vbl_unsel, vbl_lo=v_base, debug_printout = debug_printout)
            if debug_printout: print(f"Setting BLs {bls_unselected} to {vbl_unsel} V")
        else:
            self.set_vbl(self.bls, vbl_hi = vbl, vbl_lo=v_base, debug_printout = debug_printout)
        if debug_printout: print(f"Setting BLs {self.bls} to {vbl} V")
        
        # Set Source Lines to the Desired Voltage
        self.set_vsl(self.sls, vsl, vsl_lo=v_base, debug_printout = debug_printout)
        if debug_printout: print(f"Setting SLS {self.sls} to {vsl} V")

        # ----------------------------------- #
        #       Commit and send Pulse         #
        # ----------------------------------- #

        for session in self.digital_patterns.sessions:
            session.commit()
        
        self.digital_patterns.pulse(masks,pulse_lens=pulse_lens,max_pulse_len=max_pulse_len, pulse_groups=[["WL_IN"],["BL","SL","WL_IN"],["WL_IN"]] )

        # ---------------------------------------- #
        #       Set to Off and Disconnect          #
        # ---------------------------------------- #

        # Set channels to 0V
        self.digital_patterns.digital_all_pins_to_zero(ignore_power=False)
        # Reset Channels in high_z to Hi-Z
        if high_z is not None:
            self.digital_patterns.set_channel_termination_mode("high-z",pins=high_z,sessions=None,sort=True)

    def set_pulse(
        self,
        mask,
        mode="SET",
        bl_selected=None, # selected BL
        vwl=None,
        vbl=None,
        vsl=None,
        vbl_unsel=None,
        vwl_unsel_offset=None,
        pulse_len=None,
        high_z = None
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
        
        self.write_pulse(mask, mode, bl_selected, vwl, vbl, vsl, vbl_unsel, vwl_unsel_offset, pulse_len, high_z)

    def reset_pulse(
        self,
        mask,
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
        self.write_pulse(mask, mode, bl_selected, vwl, vbl, vsl, vbl_unsel, vwl_unsel_offset, pulse_len, high_z)

    def form_pulse(
        self,
        mask,
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
    
    def form_rram(self,sessions,cells=None,bls=None, wls=None,sort=True,reset=False,reset_threshold=None,dynamic=False,debug_printout=None):
        """
        Form RRAM: For the given sessions and cells (in the form of sets or BLs and WLs), form the given cells.
        If reset is True, check all cells and reset them if they are not in the safe reset resistance range.
        
        Parameters:
        sessions: list of NI-Digital sessions
            List of sessions to form the RRAM cells
        cells: list of tuples of strings
            List of cells to form, in the form of (BL_#, WL_#)
        bls: list of strings
            List of BL channels to form
        wls: list of strings
            List of WL channels to form
        sort: bool
            Sort the channels before forming the cells
        reset: bool
            Reset the cells if they are not in the safe reset resistance range
        reset_threshold: float
            Resistance threshold for resetting the cells
        dynamic: bool
            Run a dynamic Form RRAM operation
        debug_printout: bool
            Print debug information

        Returns:
            None
        """
        debug_printout = debug_printout or self.debug_printout

        cells = cells or []
        if cells != []:
            for cell in cells:
                if cell[0] in wls:
                    bls[wls.index(cell[0])].apppend(cell[1])
            else:
                wls.append(cell[0])
                bls.append([cell[1]])

        pass

    def set_rram():
        pass

    def reset_rram(self,sessions=None,cells=None,bls=None,wls=None,sort=True,debug_printout=None):
        pass

    # endregion


    """ ================================================================= """
    """               Setting up the dynamic pulse signals                """
    """ ================================================================= """


    def read_written_cells(self,average_resistance=True,wls=None,bls=None,record=False,print_info=False):
        if not average_resistance:
            res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array = self.direct_read(wls=wls,bls=bls,record=False,print_info=False)
            if print_info:
                print(f"VSL: {vsl}, VBL: {vbl}, VWL: {vwl}, PW: {pw}, Resistance: {res_array}")
        else:
            res_array1, cond_array1, meas_i_array1, meas_v_array1, meas_i_leak_array1 = self.direct_read(wls=wls,bls=bls,record=False,print_info=False)
            res_array2, cond_array2, meas_i_array2, meas_v_array2, meas_i_leak_array2 = self.direct_read(wls=wls,bls=bls,record=False,print_info=False)
            res_array3, cond_array3, meas_i_array3, meas_v_array3, meas_i_leak_array3 = self.direct_read(wls=wls,bls=bls,record=False,print_info=False)

            res_array = pd.concat([res_array1,res_array2,res_array3]).groupby(level=0).mean()
            cond_array = pd.concat([cond_array1,cond_array2,cond_array3]).groupby(level=0).mean()
            meas_i_array = pd.concat([meas_i_array1,meas_i_array2,meas_i_array3]).groupby(level=0).mean()
            meas_v_array = pd.concat([meas_v_array1,meas_v_array2,meas_v_array3]).groupby(level=0).mean()
            meas_i_leak_array = pd.concat([meas_i_leak_array1,meas_i_leak_array2,meas_i_leak_array3]).groupby(level=0).mean()

        return res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array

    def check_cell_resistance(self,res_array, wls, bls, sls, target_res,voltages, mode,writer=None,print_info=False,debug_printout=None):

        # Remove every cell that is in target resistance
        if mode.upper() == "RESET":
            for wl,wl_bls in zip(wls,bls):
                for bl in wl_bls:
                    if res_array.loc[wl,bl] >= target_res:
                        bls.remove(bl)
                        sls.remove("SL_" + str(bl[3:]))
                        if len(wl_bls) == 0:
                            wls.remove(wl)
                            if len(wls) == 0:
                                # If no cells remain, return True: 
                                # All cells are set to desired resistance range
                                return "DONE"
        
        if mode.upper() == "SET" or mode.upper() == "FORM":
            for wl,wl_bls in zip(wls,bls):
                for bl in wl_bls:
                    if print_info:
                        print(res_array)
                    if res_array.loc[wl,bl] <= target_res:
                        bls.remove(bl)
                        sls.remove("SL_" + str(bl[3:]))
                        if len(wl_bls) == 0:
                            wls.remove(wl)
                            if len(wls) == 0:
                                # If no cells remain, return True: 
                                # All cells are set to desired resistance range
                                return "DONE"
        return wls,bls,sls
    

    def record_write_pulse(self,record, cells, mode, measurements, voltages, success):
        if record:
            with open(self.datafile_path, "a", newline='') as file_object:
                writer = csv.writer(file_object)
                for cell in cells:
                    writer.writerow([self.chip_id, self.device_id, cell[0], cell[1]] + measurements + [mode, f"{mode}:{success[cell[0]][cell[1]]}"]+voltages)
        return None



    def dynamic_pulse(self, sessions=None, cells=None, bls=None, wls=None, mode="RESET", print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, voltages=[None,None,None],relayed=False,reset_after=False,debug_printout=None):
        
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
        debug_printout = debug_printout or self.debug_printout

        # Set WLS and BLS based on self or input
        wls = wls or self.wls

        bls = bls or self.bls
        

        # If the BLS is a list of strings, convert to list of lists copying for each WL
        if isinstance(bls[0], str):
            bls = [bls for _ in range(len(wls))]
        elif not isinstance(bls[0], list):
            raise NIRRAMException("Invalid BLS input: Please provide a list of strings or a list of lists of strings")

        # Set SLS as a list of lists of strings as SL_{BL#} based on bls
        sls = [["SL_" + str(bl[3:]) for bl in wl_bls] for wl_bls in bls]
        cfg = self.op[mode][self.polarity]

        # Set the initial bias for BLS, WLS, SLS, based on settings or input
        vbl, vsl, vwl = voltages
        vbl = vbl or self.op[mode][self.polarity]["VBL"]
        vsl = vsl or self.op[mode][self.polarity]["VSL"]
        vwl = vwl or self.op[mode][self.polarity]["VWL"]

        # Determine the target resistance
        target_res = target_res or self.settings["target_res"][mode.upper()]


        # Add additional cells based on cells (add new WLS BLS and SLS based on [(WL,BL)])
        if cells:
            for cell in cells:
                if cell[0] not in wls:
                    wls.append(cell[0])
                    bls.append([cell[1]])
                    sls.append(["SL_" + str(cell[1][3:])])
                else:
                    bls[wls.index(cell[0])].append(cell[1])
                    bls = [list(set(bl)) for bl in bls]
                    sls[wls.index(cell[0])].append("SL_" + str(cell[1][3:]))
                    sls = [list(set(sl)) for sl in sls]
    
        cells = [wls,bls]

        # Set the pulse width and word line voltage sweep based on settings or input
        pw_start = cfg["PW_start"]
        pw_stop = cfg["PW_stop"]
        pw_step = cfg["PW_steps"]

        vwl_start = cfg["VWL_start"]   
        vwl_stop = cfg["VWL_stop"]
        vwl_step = cfg["VWL_step"]

        # Set test given the mode provided
        if mode.upper() == "SET" or mode.upper() == "FORM":
            # If we are running a set operation, we iterate the bit line voltage, 
            # keeping source line constant
            vbl_start = cfg["VBL_start"]
            vbl_stop = cfg["VBL_stop"]
            vbl_step = cfg["VBL_step"]

            vsl_start = vsl
            vsl_stop = vsl + 1
            vsl_step = 2
        
            pulsetype = "SET"

        elif mode.upper() == "RESET":
            if debug_printout:
                print("Performing Dynamic RESET")
            # If we are running a reset operation, we iterate the source line voltage, 
            # keeping bit line constant
            vsl_start, vsl_stop, vsl_step = [cfg["VSL_start"],cfg["VSL_stop"], cfg["VSL_step"]]

            vbl_start = vbl
            vbl_stop = vbl + 1
            vbl_step = 2

            pulsetype = "RESET"
        else:
            raise NIRRAMException(f"Invalid mode: {mode}: Please use 'SET', 'RESET', or 'FORM'")

        measurements = self.read_written_cells(average_resistance=average_resistance,wls=wls,bls=bls,record=record,print_info=print_data)
        res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array = measurements
        cells_to_write = self.check_cell_resistance(res_array, wls, bls, sls, target_res, voltages, mode)
        
        if cells_to_write == "DONE":
            self.record_write_pulse(self,record,cells,mode,[res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array],success=pd.DataFrame(True,index=wls,columns=bls))
            return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array
        
        wls,bls,sls = cells_to_write
        
        for wl,wl_bls,wl_sls in zip(wls,bls,sls):

            # Connect the relay and change the name of the word line signal
            if self.relays:
                wl_signals,_ = self.relay_switch([wl], relayed=True, debug_printout = debug_printout)
            else:
                wl_signals = [wl]

            self.wls = wl_signals
            self.bls = wl_bls
            self.sls = wl_sls

            for vsl in np.arange(vsl_start,vsl_stop,vsl_step):
                for vbl in np.arange(vbl_start,vbl_stop,vbl_step):
                    for pw in np.arange(pw_start,pw_stop,pw_step):
                        for vwl in np.arange(vwl_start,vwl_stop,vwl_step):
                             # Set the masks for the cells that are not in target resistance
                            if self.relays is not None:
                                all_channels = [self.all_bls,self.all_sls,self.all_wl_signals]
                            else:
                                all_channels = [self.all_bls,self.all_sls,self.all_wls]
                            
                            mask_list = Masks(
                                sel_pins = [wl_bls,wl_sls,wl_signals], 
                                pingroups = self.digital_patterns.pingroup_data, 
                                all_pins = all_channels, 
                                pingroup_names = self.digital_patterns.pingroup_names,
                                sort=False,
                                debug_printout = debug_printout)
                            
                            
                            masks = mask_list.get_pulse_masks()
                            # Write the pulse

                            print("VWL: ", vwl, "VBL: ", vbl, "VSL: ", vsl, "PW: ", pw)
                            # for i in range(5):
                            #     print("Pulsing in ", 5-i)
                            #     time.sleep(1)

                            self.write_pulse(
                                masks, 
                                sessions=sessions, 
                                mode=mode, 
                                bl_selected=wl_bls, 
                                vwl=vwl, 
                                vbl=vbl, 
                                vsl=vsl, 
                                pulse_len=pw, 
                                high_z= None, 
                                debug_printout=debug_printout)
                            print("Pulsed ")
                            
                            measurements = self.read_written_cells(average_resistance=average_resistance,wls=wls,bls=bls,record=record,print_info=print_data)
                            res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array = measurements
                            cells_to_write = self.check_cell_resistance(res_array, wls, bls, sls, target_res, voltages, mode)
                            
                            if cells_to_write == "DONE":
                                self.record_write_pulse(self,record,cells,mode,[res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array],success=pd.DataFrame(True,index=wls,columns=bls))
                                return res_array,cond_array,meas_i_array,meas_v_array,meas_i_leak_array
                            
                            wls,bls,sls = cells_to_write     
        

    def dynamic_set(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug_printout=None):
        return self.dynamic_pulse(sessions, cells, bls, wls, mode="SET", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug_printout=debug_printout)
    
    def dynamic_reset(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug_printout=None):
        return self.dynamic_pulse(sessions, cells, bls, wls, mode="RESET", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug_printout=debug_printout)

    def dynamic_form(self, sessions=None, cells=None, bls=None, wls=None, print_data=True,record=True,target_res=None, average_resistance = False, is_1tnr=False,bl_selected=None, relayed=False,debug_printout=None):
        return self.dynamic_pulse(sessions, cells, bls, wls, mode="FORM", print_data=print_data,record=record,target_res=target_res, average_resistance=average_resistance, is_1tnr=is_1tnr,bl_selected=bl_selected, relayed=relayed,debug_printout=debug_printout)
    

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

        if type(self.settings) is str:
            with open(self.settings, "rb") as settings_file:
                settings = tomli.load(settings_file)
        elif type(self.settings) is dict:
            settings = self.settings
        else:
            raise ValueError(f"Settings should be a dict or a string, got {repr(settings)}.")
        
        if not isinstance(settings, dict):
            raise ValueError(f"Settings should be a dict, got {repr(settings)}.")

        test_log_path = settings["path"]["test_log_file"]

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

    

    def def_target_res(self, mode, target_res):
        if mode.lower() == "form":
            self.form_target_res = target_res
        elif mode.lower() == "reset":
            self.reset_target_res = target_res
        elif mode.lower() == "set":
            self.set_target_res = target_res
        else:
            raise NIRRAMException("Invalid mode. Please select 'form', 'reset', or 'set'.")
  
    def relay_switch(self, wls, relayed=True, debug_printout = None):
        if debug_printout is None: debug_printout = self.debug_printout

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
        if relayed:
            self.digital_patterns.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug_printout)
        all_wls = self.settings["device"]["WL_SIGNALS"]
        return wl_input_signals, all_wls
    
    #endregion other bookkeeping functions


    # region Debugging Functions  
    def start_function_debug_printout(self, debug_printout, current_function):
        if debug_printout is None:
            debug_printout = self.debug_printout 
        if debug_printout:
            dash = "-"*len(current_function)
            print("\n\n--------",dash)
            print(f"Running {current_function}...")
            print(dash,"------\n")
            del(dash)
        return debug_printout

    def internal_function_debug_printout(self, debug_printout, internal, variables, values):
        if debug_printout:
            print(f"{internal} variables: {variables}:\n")
            for variable, value in zip(variables, values):
                print(f"{variable}: {value}")
            return 0


    def end_function_debug_printout(self, debug_printout, current_function):
        if debug_printout:
            print("\n\n ---------------------------------")
            print(f"Finished {current_function}...")
            print(" ---------------------------------\n")
            return 0
    # endregion

    
if __name__ == "__main__":
    rram = NIRRAM("chip", "device",settings="settings/MPW_Direct_Write.toml", test_type="debug", additional_info="Debugging NIRRAM Pulse Operation.")

    # rram.relay_switch(["WL_0","WL_127"])
    print("NIRRAM Abstracted Class Loaded Successfully.")

    # rram.direct_read(wls=["WL_4"],bls=["BL_0","BL_7","BL_15"],record=True,check=True,print_info="all",debug_printout=False,relayed=True)
    
    print("NIRRAM Read Operation Completed Successfully.")
    
    # rram.ppmu_set_vbl(["BL_0","BL_7","BL_15"],vbl=0.5)
    # rram.digital_patterns.commit_all()
    # time.sleep(10)
    rram.dynamic_pulse(wls=["WL_0"],bls=["BL_0"],mode="SET",record=True,print_data=True,target_res=None,average_resistance=True,debug_printout=False)
    
    print("NIRRAM Dynamic Pulse Operation Completed Successfully.")
    
    quit()
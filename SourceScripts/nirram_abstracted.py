# Import necessary libraries
import pdb
import tomli
import time
from dataclasses import dataclass
import sys
from os.path import abspath
from os import getcwd
import nidigital
import numpy as np
import pandas as pd
import csv
from datetime import date, datetime
from BitVector import BitVector

sys.path.append(getcwd())
from masks import Masks
from digital_pattern import DigitalPattern
import load_settings

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
            polarity = "NMOS",
            settings = "settings/default.toml",
            debug_printout = False,
            slow = False,
            test_type = "Default",
            additional_info = ""
            ):
        # flag for indicating if connection to ni session is open
        self.closed = True
        self.slow=slow
        
        
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
        self.mlogfile = open(settings["path"]["master_log_file"], "a")
        self.plogfile = open(settings["path"]["prog_log_file"], "a")
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        hash = self.update_data_log(current_date, current_time, f"chip_{chip}_device_{device}", test_type, additional_info)
        self.datafile_path = settings["path"]["data_header"] + f"/{test_type}/{current_date}_{chip}_{device}_{hash}.csv"
        
        self.file_object = open(self.datafile_path, "a", newline='')
        self.datafile = csv.writer(self.file_object)

        self.datafile.writerow(["Chip_ID", "Device_ID", "OP", "Row", "Col", "Res", "Cond", "Meas_I", "Meas_V", "Prog_VBL", "Prog_VSL", "Prog_VWL", "Prog_Pulse", "Success/State"])
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

        if "all_WL_Signals" in settings["device"]:
            self.all_wl_signals = settings["device"]["all_WL_Signals"]

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
        debug_printout = None
    ):
        """Perform a READ operation. This operation works for single 1T1R devices and 
        arrays of devices, where each device has its own WL/BL.
        Returns list (per-bitline) of tuple with (res, cond, meas_i, meas_v)"""
        if debug_printout is None: debug_printout = self.debug_printout

        wls = self.wls if wls is None else wls
        bls = self.bls if bls is None else bls

        if bls is None: sls = self.sls
        elif type(bls[0]) is int or type(bls[0]) is np.uint8:
            sls = [f"SL_{bl}" for bl in bls]
        else:
            sls = [f"SL{bl[2:]}" for bl in bls]

        
        # Set the read voltage parameters based on settings or parameter inputs
        vbl = self.op["READ"][self.polarity]["VBL"] if vbl is None else vbl
        vwl = self.op["READ"][self.polarity]["VWL"] if vwl is None else vwl
        vsl = self.op["READ"][self.polarity]["VSL"] if vsl is None else vsl
        vb = self.op["READ"][self.polarity]["VB"] if vb is None else vb

        if debug_printout:
            print(f"Direct Read: VBL={vbl}, VWL={vwl}, VSL={vsl}, VB={vb}, VWL_UNSEL_OFFSET={vwl_unsel_offset}")

        # Dataframes to store measurement results, resistance, conductance, current, voltage
        res_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        cond_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        meas_v_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        meas_i_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
        meas_i_leak_array = pd.DataFrame(np.zeros((len(wls), len(bls))), wls, bls)
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
            self.wl_signals = self.settings["device"]["all_WL_Signals"]

        formatted_r = []   
        formatted_c = []
        formatted_i = []
        formatted_v = []

        for wl in wls:
            if self.relays is not None:
                wl_entry = wl
                wl,all_wls = self.relay_switch([wl]+remove_bias,debug_printout=False)
                wl = wl[0]
            
            for wl_i in all_wls:
                if wl_i in wl:
                    print(f"Setting {wl_i} to {vwl} V")
                    self.ppmu_set_vwl(wl_i, vwl)
                elif wl_i in remove_bias:
                    self.ppmu_set_vwl(wl_i, vsl)
                else:
                    self.ppmu_set_vwl(wl_i, vsl + vwl_unsel_offset)
                    
            
            self.digital_patterns.ppmu_source([[],[],[all_wls]], sort=False)
            # pdb.set_trace()

            self.ppmu_set_vbl(self.bls,vbl)
            self.ppmu_set_vsl(self.sls,vsl)
            self.set_to_ppmu([self.bls,self.sls],["BL","SL"])

            #Let the supplies settle for accurate measurement
            time.sleep(self.op["READ"]["settling_time"])

            # Measure selected voltage. Default is to measure VBL
            if meas_vbls:
                meas_bls_v_by_session,dict_meas_bls_v,meas_bls_v = self.digital_patterns.measure_voltage([bls,[],[]],sort=False)
            
                if debug_printout:
                    print([f"{bl} = {meas_bl_v}" for bl, meas_bl_v in zip(bls, meas_bls_v)])

            if meas_vsls:
                meas_sls_v_by_session,dict_measure_sls_v,meas_sls_v = self.digital_patterns.measure_voltage([[],sls,[]],sort=False)

                if debug_printout:
                    print([f"{sl} = {meas_sl_v}" for sl, meas_sl_v in zip(sls, meas_sls_v)])

            if meas_vwls:
                meas_wls_v_by_session,dict_meas_sls_v,meas_wls_v = self.digital_patterns.measure_voltage([[],[],wls],sort=False)

                if debug_printout:
                    print([f"{wl} = {meas_wl_v}" for wl, meas_wl_v in zip(wls, meas_wls_v)])

            # Measure selected current, default is to measure ISL and I gate
            if meas_isls: 
                _,_,meas_sls_i = self.digital_patterns.measure_current([[],sls,[]],sort=False)
                print(f"meas_sls_i: {meas_sls_i}")

                if debug_printout:
                    print([f"{sl} = {meas_sl_i}" for sl, meas_sl_i in zip(sls, meas_sls_i)])

            if meas_ibls:
                _,_,meas_bls_i = self.digital_patterns.measure_current([[],[],bls],sort=False)

                if debug_printout:
                    print([f"{bl} = {meas_bl_i}" for bl, meas_bl_i in zip(bls, meas_bls_i)])

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

                if debug_printout:
                    print([f"{wl} = {meas_wl_i}" for wl, meas_wl_i in zip(wls, meas_wls_i)])
        
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
                for wl in wls:
                    for bl in bls:
                        if check:
                            if res_array.loc[wl, bl] < self.set_target_res:
                                check_on = "set"
                            elif res_array.loc[wl, bl] > self.reset_target_res:
                                check_on = "reset"
                            else:
                                check_on = "unknown"

                        datafile.writerow([self.chip, self.device, "READ", wl, bl, res_array.loc[wl, bl], cond_array.loc[wl, bl], meas_i_array.loc[wl, bl], meas_v_array.loc[wl, bl], check_on])
        
        if self.relays is not None:
            self.digital_patterns.ppmu_set_pins_to_zero(sessions=None,pins=[self.bls,self.sls,self.wl_signals],sort=False)
        else:
            self.digital_patterns.ppmu_set_pins_to_zero(sessions=None,pins=[self.bls,self.sls,self.wls],sort=False)
        time.sleep(self.op["READ"]["settling_time"])

        return res_array, cond_array, meas_i_array, meas_v_array, meas_i_leak_array        
    



    """ ================================================================= """
    """                   Setting voltages and currents                   """
    """ Serially setting voltages and currents for VBL, VSL, ISL, and VWL """
    """                PPMU and Digital sources are defined               """
    """ ================================================================= """

    def ppmu_set_voltage(self, v, channels, name, sort=True):
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        for chan in channels:
            if chan not in self.settings["device"][f"all_{name}S"]:
                raise NIRRAMException(f"Invalid V{name} channel {chan}. \nChannel not in all_{name}S.")
            
        if type(v) is not list:
            v = [v]
        
        if len(v) == 1:
            v = v * len(channels)
        
        if len(v) != len(channels):
            raise NIRRAMException(f"Number of V{name} channels ({len(channels)}) does not match number of V{name} voltages ({len(v)}).")
        
        for voltage in v:
            if voltage > 6 or voltage < -2:
                raise NIRRAMException(f"Invalid V{name} voltage {v} at channel {channels}. \nVoltage must be between -2V and 6 V.")
        
        self.digital_patterns.ppmu_set_voltage(pins=channels,voltage_levels=v,sessions=None,sort=sort,source=True)


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
        
        self.digital_patterns.set_channel_mode("ppmu", pins=channels,sessions=None,sort=sort,debug_printout=debug_printout)




    def digital_set_voltage(self, channels, vi_lo, vi_hi, vo_lo, vo_hi, name, sort=True):
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        for chan in channels:
            if chan not in self.settings["device"][f"all_{name}S"]:
                raise NIRRAMException(f"Invalid V{name} channel {chan}. \nChannel not in all_{name}S.")
        
        if type(vi_lo) is not list: vi_lo = [vi_lo]
        if type(vi_hi) is not list: vi_hi = [vi_hi]
        if type(vo_lo) is not list: vo_lo = [vo_lo]
        if type(vo_hi) is not list: vo_hi = [vo_hi]

        if len(vi_lo) == 1: vi_lo = vi_lo * len(channels)
        if len(vi_hi) == 1: vi_hi = vi_hi * len(channels)
        if len(vo_lo) == 1: vo_lo = vo_lo * len(channels)
        if len(vo_hi) == 1: vo_hi = vo_hi * len(channels)

        if len(vi_lo) != len(channels) or len(vi_hi) != len(channels) or len(vo_lo) != len(channels) or len(vo_hi) != len(channels):
            raise NIRRAMException(f"Number of V{name} channels ({len(channels)}) does not match number of V{name} voltages ({len(vi_lo)}, {len(vi_hi)}, {len(vo_lo)}, {len(vo_hi)}).")

        self.digital_patterns.set_voltage_levels(sessions=None,pins=channels,vi_lo=vi_lo,vi_hi=vi_hi,vo_lo=vo_lo,vo_hi=vo_hi,sort=sort,source=True)    

    def set_vsl(self, vsl_chan, vsl, vsl_lo, debug_printout = None):
        if debug_printout is None: debug_printout = self.debug_printout
        
        """Set VSL using NI-Digital driver"""
        self.digital_set_voltage(vsl_chan, vsl_lo, vsl_lo, vsl, vsl, "SL", sort=True)
        
        if debug_printout: print("Setting VSL: " + str(vsl) + " on chan: " + str(vsl_chan))

    def set_vbl(self, vbl_chan, vbl, vbl_lo, debug_printout = None):
        if debug_printout is None: debug_printout = self.debug_printout
        
        """Set VBL using NI-Digital driver"""
        self.digital_set_voltage(vbl_chan, vbl_lo, vbl_lo, vbl, vbl, "BL", sort=True)
        
        if debug_printout: print("Setting VBL: " + str(vbl) + " on chan: " + str(vbl_chan))
    
    def set_vwl(self, vwl_chan, vwl, vwl_lo, debug_printout = None):
        if debug_printout is None: debug_printout = self.debug_printout
        
        """Set VWL using NI-Digital driver"""
        self.digital_set_voltage(vwl_chan, vwl_lo, vwl_lo, vwl, vwl, "WL", sort=True)
        
        if debug_printout: print("Setting VWL: " + str(vwl) + " on chan: " + str(vwl_chan))

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
        
    def relay_switch(self, wls,debug_printout = None):
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
        self.digital_patterns.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug_printout)
        all_wls = self.settings["device"]["WL_SIGNALS"]
        return wl_input_signals, all_wls

if __name__ == "__main__":
    rram = NIRRAM("chip", "device",settings="settings/MPW_Direct_Write.toml", test_type="debug", additional_info="Debugging NIRRAM Read Operation.")

    # rram.relay_switch(["WL_0","WL_127"])

    rram.direct_read(wls=["WL_2","WL_126"],bls=["BL_0","BL_7","BL_15"],record=True,check=True,print_info="all",debug_printout=False)

    print("NIRRAM Abstracted Class Loaded Successfully.")
    
    quit()

"""
nirram.py
A description of the NI RRAM Controller Class
Reading, Writing, and Measuring RRAM devices using NI PXIe-657(0/1) Digital I/O
This class is a generalization of the NIRRAM class written by Akash Levy
"""

# Import necessary libraries
import pdb
import tomli
import time
import warnings
from dataclasses import dataclass
from os.path import abspath
import nidigital
import numpy as np
import pandas as pd
import csv
from datetime import date, datetime, time
from .mask import RRAMArrayMask
import niswitch
from BitVector import BitVector

# Warnings become errors
warnings.filterwarnings("error")

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
        self.settings = settings
        # If settings is a string, load as TOML file
        if isinstance(settings, str):
            with open(settings, "rb") as settings_file:
                settings = tomli.load(settings_file)

        # Ensure settings is a dict
        if not isinstance(settings, dict):
            raise NIRRAMException(f"Settings should be a dict, got {repr(settings)}.")

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

        self.datafile.writerow(["Chip_ID", "Device_ID", "OP", "Row", "Col", "Res", "Cond", "Meas_I", "Meas_V", "Prog_VBL", "Prog_VSL", "Prog_VWL", "Prog_Pulse", "Success"])
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

    
        """ ======================================================================= """
        """ The session creation occurs here, creating new sessions for each device """
        """ ======================================================================= """


        # =============================== #
        #    Load pin maps,and time set   #
        # =============================== #

        # Load Pin Maps
        """ DigitalPattern loads the pin maps, and timing """

        # Correct for relays so instead of all_wls it is all
        # WL Signals
        all_wls = self.all_wls
        all_blsl = self.all_bls + self.all_sls
            
        if self.relays is not None:
            all_wls = self.all_wl_signals

        # Set sessions based on pins into different sub_categories
        for digital in self.digital:
            self.bl_dev = [digital for digital in self.digital if any("BL" in channel.pin_name for channel in digital.get_pin_results_pin_information())]
            self.sl_dev = [digital for digital in self.digital if any("SL" in channel.pin_name for channel in digital.get_pin_results_pin_information())]
            self.wl_dev = [digital for digital in self.digital if any("WL" in channel.pin_name for channel in digital.get_pin_results_pin_information())]

        # This is a hacky way to get the correct all_channels for the sessions
        # IT IS HARDCODED FOR BLSL and WL, and will need to be changed if things
        # are going to be changed. This is because the all_channels is used to
        # set all the channel pins, which needs to be separated by session.

        # This is for the channel pins, (not correct, but is more specific than all pins)
        if len(session_names) > 1:
            self.all_channels = [all_blsl, all_wls]

        """DigitalPattern clears all patterns and sets all pins to zero (all pins not just channel pins)"""
            
            
        # Load patterns from the toml file, this will load each pattern
        # session by session so:
        # For Pattern 1: Load for Session 1, then Session 2, etc.
        # THEN For Pattern 2: Load for Session 1, then Session 2, etc.
        for pattern in self.patterns:
            for digital in self.digital:
                if debug_printout:
                    print(pattern[self.digital.index(digital)])
                digital.load_pattern(abspath(pattern[self.digital.index(digital)]))
        self.closed = False

        # Configure READ measurements
        if self.op["READ"]["mode"] == "digital":
            for digital in self.bl_dev:
                for bl in self.bls:
                # Configure NI-Digital current read measurements
                    digital.channels[bl].ppmu_aperture_time = self.op["READ"]["aperture_time"]
                    digital.channels[bl].ppmu_aperture_time_units = nidigital.PPMUApertureTimeUnits.SECONDS
                    digital.channels[bl].ppmu_output_function = nidigital.PPMUOutputFunction.VOLTAGE
                    digital.channels[bl].ppmu_current_limit_range = self.op["READ"]["current_limit_range"]
            
            for digital in self.sl_dev:    
                for sl in self.sls:
                    # Configure NI-Digital current read measurements
                    digital.channels[sl].ppmu_aperture_time = self.op["READ"]["aperture_time"]
                    digital.channels[sl].ppmu_aperture_time_units = nidigital.PPMUApertureTimeUnits.SECONDS
                    digital.channels[sl].ppmu_output_function = nidigital.PPMUOutputFunction.VOLTAGE
                    digital.channels[sl].ppmu_current_limit_range = self.op["READ"]["current_limit_range"]
       ## ** Here ** ##
        
        else:
            raise NIRRAMException("Invalid READ mode specified in settings")

        # set body voltages
        if self.body is not None:
            for body_i, vbody_i in self.body.items(): self.ppmu_set_vbody(body_i, vbody_i)

        # Set address and all voltages to 0
        for bl in self.all_bls: self.set_vbl(bl, 0.0, 0.0)
        for sl in self.all_sls: self.set_vsl(sl, 0.0, 0.0)
        for wl in all_wls: self.set_vwl(wl, 0.0, 0.0)
        
        for digital in self.digital:
            digital.commit()

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

    def read(
        self,
        vbl=None,
        vsl=None,
        vwl=None,
        vwl_unsel_offset=None,
        vb=None,
        record=False,
        check=True,
        dynam_read=False,
        wl_name = None,
        debug_printout = None
    ):
        
        """Perform a READ operation. This operation works for single 1T1R devices and 
        arrays of devices, where each device has its own WL/BL.
        Returns list (per-bitline) of tuple with (res, cond, meas_i, meas_v)"""
        
        if debug_printout is None: debug_printout = self.debug_printout

        # Increment the number of READs        
        # Set the read voltage levels
        vbl = self.op["READ"][self.polarity]["VBL"] if vbl is None else vbl
        vwl = self.op["READ"][self.polarity]["VWL"] if vwl is None else vwl
        vsl = self.op["READ"][self.polarity]["VSL"] if vsl is None else vsl
        vb = self.op["READ"][self.polarity]["VB"] if vb is None else vb

        '''Debug, print read values'''
        if debug_printout:
            print(f"READ @ vbl: {vbl}, vwl: {vwl}, vsl: {vsl}, vb: {vb}")
        
        # unselected WL bias parameter
        if vwl_unsel_offset is None:
            if "VWL_UNSEL_OFFSET" in self.op["READ"][self.polarity]:
                vwl_unsel_offset = self.op["READ"][self.polarity]["VWL_UNSEL_OFFSET"]
                #print(vwl_unsel_offset)
            else:
                vwl_unsel_offset = 0.0

        time.sleep(self.op["READ"]["settling_time"]) # let the supplies settle for accurate measurement
        
        # Measure
        res_array = pd.DataFrame(np.zeros((len(self.wls), len(self.bls))), self.wls, self.bls)
        cond_array = pd.DataFrame(np.zeros((len(self.wls), len(self.bls))), self.wls, self.bls)
        meas_i_array = pd.DataFrame(np.zeros((len(self.wls), len(self.bls))), self.wls, self.bls)
        meas_v_array = pd.DataFrame(np.zeros((len(self.wls), len(self.bls))), self.wls, self.bls)
        
        if self.op["READ"]["mode"] == "digital":
            # Measure with NI-Digital

            #set WL_UNSEL signal
            # for wl_unsel_signal in self.wl_unsel:
            #     self.ppmu_set_vwl(wl_unsel_signal, vsl + vwl_unsel_offset)
            
            if self.relays is not None:
                all_wls = self.settings["device"]["WL_INS"]
                wls, zero_in, NC_in = self.relay_switch(self.wls, zero_rows=self.zero_rows,NC_rows=self.NC_rows)
            else:
                wls = self.wls
                all_wls = self.all_wls
                zero_in = self.zero_rows
                NC_in = self.NC_rows
    
            """
            TODO: Implement the following:
                zero_in
                NC_in
            """

            for wl in wls:
                # sets all WL voltages in the array: read WL is VWL, all others are VSL
                for wl_i in all_wls: 
                    if wl_i == wl:
                        self.ppmu_set_vwl(wl_i, vwl)
                    else: # UNSELECTED WLs: set to ~vsl with some offset (to reduce bias)
                        self.ppmu_set_vwl(wl_i, vsl + vwl_unsel_offset)
                for digital in self.wl_dev:
                    digital.ppmu_source()

                if "BL_MULTI_READ" in self.bls:
                    bl = "BL_MULTI_READ"
                    self.ppmu_set_vbl(bl,vbl)
                    self.ppmu_set_vsl("SL_MULTI_READ",vsl)
                    for digital in self.bl_dev:
                        meas_i = digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)
                        meas_v = digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)
                else:
                    for bl in self.bls: 
                        self.ppmu_set_vbl(bl,vbl)
                        for digital in self.bl_dev:
                            digital.channels[bl].selected_function = nidigital.SelectedFunction.PPMU
                    for sl in self.sls: 
                        self.ppmu_set_vsl(sl,vsl)
                        for digital in self.sl_dev:
                            digital.channels[sl].selected_function = nidigital.SelectedFunction.PPMU
                       
                    time.sleep(self.op["READ"]["settling_time"]) #Let the supplies settle for accurate measurement
                
                for bl in self.bls:
                    # DEBUGGING: test each bitline 
                    if debug_printout:
                        meas_v = self.digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)[0]
                        meas_i = self.digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)[0]
                        meas_i_gate = self.digital.channels[wl].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)[0]
                        print(f"{bl} v: {meas_v} i: {meas_i} ig: {meas_i_gate}")
                        print(f"BL: {bl}") 
                        print(f"SL: {sl}")
                        print(f"VBL: {vbl}")
                        print(f"VSL: {vsl}")
                    
                    for digital in self.digital:
                        #meas_vsl = self.digital.channels[sl].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)
                        meas_v = digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)[0]
                        meas_i = digital.channels[bl].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)[0]
                    
                        # r = r[6:7]  + r[0:1] + r[5:6] + r[3:5]+ r[4:5] + r[7:] + r[2:3]
                        r = np.array(r)
                        c = [1/res if res != 0 else 1_000_000_000 for res in r]
                        meas_i = np.array(meas_i)
                        meas_v = np.array(meas_v)
                        np.set_printoptions(formatter={'float': '{:.2e}'.format})

                        headers = [" ", "BL_8", "BL_9", "BL_10", "BL_11", "BL_12", "BL_13", "BL_14", "BL_15"]

                        # Determine the maximum width needed for alignment based on the longest header name or value
                        max_width = max(max(len(str(x)) for x in headers), max(len(str(x)) for x in r))

                        # Print headers aligned
                        # print(" ".join(f"{header:^{max_width}}" for header in headers))
                        formatted_r = ["Res"] + [f"{value/1000:.2f}kΩ" for value in r]
                        formatted_v = ["VBL"] + [f"{value:.2f}V" for value in meas_v]
                        formatted_i = ["I"] + [f"{value:.2e}A" for value in meas_i]
                        # Print corresponding values aligned
                        print(" ".join(f"{(value):^{max_width}}" for value in formatted_r))
                        # print(" ".join(f"{(value):^{max_width}}" for value in formatted_v))
                        # print(" ".join(f"{(value):^{max_width}}" for value in formatted_i))




                        np.set_printoptions() 
                        self.ppmu_all_pins_to_zero()
                        time.sleep(self.op["READ"]["settling_time"]) # let the supplies settle
                        return r, c, meas_i, meas_v  
                    
                    #self.digital.channels[bl].selected_function = nidigital.SelectedFunction.DIGITAL

                    # self.addr_prof[wl][bl]["READs"] +=1
                    # Compute values
                    res = np.abs((self.op["READ"][self.polarity]["VBL"] - self.op["READ"][self.polarity]["VSL"])/meas_i - self.op["READ"]["shunt_res_value"])
                    cond = 1/res
                    meas_i_array.loc[wl,bl] = meas_i
                    meas_v_array.loc[wl,bl] = meas_v
                    res_array.loc[wl,bl] = res
                    cond_array.loc[wl,bl] = cond
                    if record:
                        self.file_object = open(self.datafile_path, "a", newline='')
                        self.datafile = csv.writer(self.file_object)
                        if wl_name is None:
                            self.datafile.writerow([self.chip, self.device, "READ", wl, bl, res, cond, meas_i, meas_v])
                        else: 
                            self.datafile.writerow([self.chip, self.device, "READ", wl_name, bl, res, cond, meas_i, meas_v])
                        if check:
                            if res < 40_000:
                                check_on = "set"
                            elif (res > 60_000):
                                check_on = "reset"
                            else:
                                check_on = "unknown"
                            if dynam_read:
                                print([f"WL: {wl}   ", f"VWL: {vwl}", f"Res: {res}"])
                            else:
                                pass
                                #print([self.chip, self.device, "READ", wl, bl, res, cond, meas_i, meas_v, meas_i_gate, check_on])
                        
                        else:
                            if dynam_read:
                                print([f"WL: {wl}   ", f"VWL: {vwl}", f"Res: {res}"])
                            else:
                                pass
                                #print([self.chip, self.device, "READ", wl, bl, res, cond, meas_i, meas_v, meas_i_gate])
                        self.file_object.close()
        else:
            raise NIRRAMException("Invalid READ mode specified in settings")

        # Disable READ, make sure all the supplies in off state for any subsequent operations
        # self.digital_all_off(self.op["READ"]["relaxation_cycles"])
        self.ppmu_all_pins_to_zero()
        time.sleep(self.op["READ"]["settling_time"]) # let the supplies settle
        # Log operation to master file
        # self.mlogfile.write(f"{self.chip},{time.time()},{self.addr},")
        # self.mlogfile.write(f"READ,{res},{cond},{meas_i},{meas_v}\n")
        # Return measurement results
        return res_array, cond_array, meas_i_array, meas_v_array

    def multi_bl_read(
        self,
        vbl=None,
        vsl=None,
        vwl=None,
        vwl_unsel_offset=None,
        vb=None,
        record=False,
        check=True,
        dynam_read=False,
        wl_name = None,
        wl = None
    ):
        print("Multiple Bit Line Read")
        
        if vwl_unsel_offset is None:
            if "VWL_UNSEL_OFFSET" in self.op["READ"][self.polarity]:
                vwl_unsel_offset = self.op["READ"][self.polarity]["VWL_UNSEL_OFFSET"]
                #print(vwl_unsel_offset)
            else:
                vwl_unsel_offset = 0.0

        vbl = self.op["READ"][self.polarity]["VBL"] if vbl is None else vbl
        vwl = self.op["READ"][self.polarity]["VWL"] if vwl is None else vwl
        vsl = self.op["READ"][self.polarity]["VSL"] if vsl is None else vsl
        vb = self.op["READ"][self.polarity]["VB"] if vb is None else vb
        
        self.ppmu_set_vwl("WL_UNSEL", vsl + vwl_unsel_offset)
        self.ppmu_set_vwl(wl, vwl)
        print(f"vsl {vsl}, vbl {vbl}, vwl {vwl}")
        self.digital.channels["BL_MULTI_READ"].ppmu_voltage_level = vbl
        self.digital.channels["SL_MULTI_READ"].ppmu_voltage_level = vsl
        meas_v = self.digital.channels["BL_MULTI_READ"].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)[0]
        meas_i = self.digital.channels["BL_MULTI_READ"].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)[0]
        self.ppmu_all_pins_to_zero()
        print(meas_v)
        print(meas_i)
        return meas_v, meas_i


    def write_pulse(        
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
        high_z = ["wl"]
        ):

        # ------------------------- #
        #      Get parameters       #
        # ------------------------- #
        vwl = vwl if vwl is not None else self.op[mode][self.polarity]["VWL"]
        vbl = vbl if vbl is not None else self.op[mode][self.polarity]["VBL"]
        vsl = vsl if vsl is not None else self.op[mode][self.polarity]["VSL"]
        vbl_unsel = vbl_unsel if vbl_unsel is not None else vsl + ((vbl - vsl) / 4.0)
        pulse_len = pulse_len if pulse_len is not None else self.op[mode][self.polarity]["PW"] 


        # ----------------------------------------------------- #
        # Set the base voltage relative to the selected  mode   #
        # ----------------------------------------------------- #
            
        if mode == "SET": # In SET mode, the base voltage is the source line voltage
            v_base = vsl
        elif mode == "RESET": # In RESET mode, the base voltage is the bit line voltage
            v_base = vbl
        else:
            raise NIRRAMException(f"Invalid mode: {mode}")
        
        for digital in self.digital:
            digital.channels[self.all_channels[self.digital.index(digital)]].write_static(nidigital.WriteStaticPinState.X)

        # --------------------------------- #
        # Set the Unselected Word Line bias #
        # --------------------------------- #
        if vwl_unsel_offset is None:
            if "VWL_UNSEL_OFFSET" in self.op[mode][self.polarity]:
                vwl_unsel_offset = self.op[mode][self.polarity]["VWL_UNSEL_OFFSET"]
                
                # Debug Info
            else:
                # Debug Info
                if self.debug_printout:
                    print("No VWL UNSEL OFFSET")
                vwl_unsel_offset = 0.0
            
        vwl_unsel = v_base + vwl_unsel_offset
        
        if self.debug_printout:
            print(f"VWL UNSEL OFFSET: {vwl_unsel_offset}")
            print(f"VWL UNSEL: {vwl_unsel_offset + v_base}")

        
        
        # ------------------------- #
        #       set voltages        #
        # ------------------------- #
        
        # Word Line Voltages 
        if self.relays is not None:
            wls, zero_in, NC_in = self.relay_switch(self.wls, zero_rows=self.zero_rows,NC_rows=self.NC_rows)
            wls = ["WL_IN_" + str(value) for value in wls]
            all_wls = self.all_wl_signals
        else:
            wls = self.wls
            all_wls = self.all_wls
            zero_in = self.zero_rows
            NC_in = self.NC_rows
        print(wls)
        for wl_i in all_wls: 
            if wl_i in wls:
                self.set_vwl(wl_i, vwl_hi = vwl, vwl_lo = v_base)
           
            # Debug Information
            if self.debug_printout:
                print(f"Setting WL {wl_i} to {vwl} V")

            else:
                self.set_vwl(wl_i, vwl_hi = v_base, vwl_lo = vwl_unsel)  # Unselected Wls add in bias
        
        # Bit Line Voltages
        for bl_i in self.bls:    
           
            # Debug Information
            if self.debug_printout:
                print(f"Setting BL {bl_i} to {vbl} V")

            # Check for 1TNR device programming
            if bl_selected is not None: # selecting specific bl, unselecting others
                vbl_i = vbl if bl_i == bl_selected else vbl_unsel
            else:
                vbl_i = vbl

            self.set_vbl(bl_i, vbl = vbl_i, vbl_lo = vsl)
        
        # Source Line Voltages
        for sl_i in self.sls:
            
            # Debug Information
            if self.debug_printout:
                print(f"Setting SL {sl_i} to {vsl} V")

            self.set_vsl(sl_i, vsl = vsl, vsl_lo = vsl)

        
        # --------------------------------------------------- #
        # Commit and pulse the voltages to all selected pins  #
        # --------------------------------------------------- #   
        
        for digital in self.digital:
            digital.commit()

        # Issue the pulse
        self.pulse(mask, pulse_len=pulse_len)

        # Turn everything off high Z
        # self.ppmu_all_pins_to_zero()
        self.digital_all_pins_to_zero()
        
        # reset to high Z
        if "wl" in high_z:
            for wl_i in self.wls:
                self.digital.channels[wl_i].termination_mode = nidigital.TerminationMode.HIGH_Z
        if "bl" in high_z:
            for bl_i in self.bls:
                self.digital.channels[bl_i].termination_mode = nidigital.TerminationMode.HIGH_Z
        if "sl" in high_z:
            for sl_i in self.sls:
                self.digital.channels[sl_i].termination_mode = nidigital.TerminationMode.HIGH_Z

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
        high_z = ["wl"]
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
        high_z = ["wl"]
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


    def dynamic_pulse(
        self,
        mode="SET",
        print_data=True,
        record=True,
        target_res=None, # target res, if None will use value in settings
        is_1tnr=False,
        bl_selected=None, # select specific bl for 1TNR measurements
        relayed=False,
        debug = False,
    ):
        
        """ 
        Performs SET pulses in increasing fashion until resistance reaches
        target_res (either input or in the `target_res` config).
        This will try to SET ALL CELLS in self.bls and self.wls.
        Returns tuple (res, cond, meas_i, meas_v, success).
        """
        datafile_path = self.settings["path"]["data_header"]+"set-file_"+ datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + str(self.chip) + "_" + str(self.device) + ".csv"

        #Record the resistance versus voltages and pulse widths in csv
        
        with open(datafile_path, "a", newline="") as resfile:
            writer = csv.writer(resfile)
            writer.writerow(["VWL", "VBL", "VSL", "PW", "Res"])

            # Get settings
            cfg = self.op[mode][self.polarity]
            target_res = target_res if target_res is not None else self.target_res[mode]

            if self.relays is not None:
                wls,_,_ = self.relay_switch(self.wls, zero_rows=self.zero_rows,NC_rows=self.NC_rows)
                all_wls = self.settings["device"]["WL_INS"]
                mask = RRAMArrayMask(wls, self.bls, self.sls, all_wls, self.all_bls, self.all_sls, self.polarity)
            else:   
                mask = RRAMArrayMask(self.wls, self.bls, self.sls, self.all_wls, self.all_bls, self.all_sls, self.polarity)
            
            # select read method
            read_pulse = self.read_1tnr if is_1tnr else self.read

            # Iterative pulse-verify
            success = False
            
            if mode == "SET" or mode == "FORM":
                # If we are running a set operation, we iterate the bit line voltage, 
                # keeping source line constant
                vbl_start = cfg["VBL_start"]
                vbl_stop = cfg["VBL_stop"]
                vbl_step = cfg["VBL_step"]

                vsl_start = vsl
                vsl_stop = vsl + 1
                vsl_step = 2
            
                pulsetype = "SET"

            elif mode == "RESET":
                if self.debug_printout or debug:
                    print("Performing Dynamic RESET")
                # If we are running a reset operation, we iterate the source line voltage, 
                # keeping bit line constant
                vsl_start = cfg["VSL_start"]
                vsl_stop = cfg["VSL_stop"]
                vsl_step = cfg["VSL_step"]

                vbl_start = vbl
                vbl_stop = vbl + 1
                vbl_step = 2

                pulsetype = "RESET"
            
            else:
                raise NIRRAMException(f"Invalid mode: {mode}")
            
            if self.debug_printout or debug:
                    print(f"Performing Dynamic {mode}")
            
            for vsl in np.arrange(vsl_start, vsl_stop, vsl_step):
                for vbl in np.arange(vbl_start, vbl_stop, vbl_step):
                    for pw in np.arange(cfg["PW_start"], cfg["PW_stop"], cfg["PW_steps"]):
                        for vwl in np.arange(cfg["VWL_SET_start"], cfg["VWL_SET_stop"], cfg["VWL_SET_step"]):
                            self.write_pulse(
                                mask,
                                mode=pulsetype,
                                bl_selected=bl_selected, # specific selected BL for 1TNR
                                vbl=vbl,
                                vsl=vsl,
                                vwl=vwl,
                                pulse_len=int(pw),
                            )
                            self.ppmu_all_pins_to_zero()
                            # pdb.set_trace()
                            
                            # use settling if parameter present, to discharge parasitic cap
                            if "settling_time" in self.op[mode]:
                                time.sleep(self.op[mode]["settling_time"])

                            # read result resistance
                            res_array1, cond_array1, meas_i_array1, meas_v_array1 = read_pulse()
                            res_array2, cond_array2, meas_i_array2, meas_v_array2 = read_pulse()
                            res_array3, cond_array3, meas_i_array3, meas_v_array3 = read_pulse()
                            
                            res_array = (res_array1 + res_array2 + res_array3)/3
                            cond_array = None
                            meas_i_array = (meas_i_array1 + meas_i_array2 + meas_i_array3)/3
                            meas_v_array = (meas_v_array1 + meas_v_array2 + meas_v_array3)/3
                            #print(res_array)
                            
                            if bl_selected is None: # use array success condition: all in array must hit target
                                for wl_i in self.wls:
                                    for bl_i in self.bls:
                                        if bl_i == "BL_MULTI_READ":
                                            for res in res_array:
                                                if (res <= target_res) and (mode != "RESET"):
                                                    print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                                    return None
                                                elif (res >= target_res) and (mode == "RESET"):
                                                    print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                                    return None
                                        else: 
                                            writer.writerow([vwl,vbl,vsl, pw, res_array.loc[wl_i, bl_i]])
                                            print(f"{res_array.loc[wl_i,bl_i]}")
                                            
                                            if ((res_array.loc[wl_i, bl_i] <= target_res) & mask.mask.loc[wl_i, bl_i]) and (mode != "RESET"):
                                                mask.mask.loc[wl_i, bl_i] = False

                                            elif ((res_array.loc[wl_i, bl_i] >= target_res) & mask.mask.loc[wl_i, bl_i]) and (mode == "RESET"):
                                                mask.mask.loc[wl_i, bl_i] = False
                                success = (mask.mask.to_numpy().sum()==0)
                            
                            else: # 1TNR success condition: check if selected 1tnr cell hit target
                                success = True
                                if mode == "SET" or mode == "RESET":
                                    for wl_i in self.wls:
                                        if (res_array.loc[wl_i, bl_selected] > target_res) & mask.mask.loc[wl_i, bl_selected]:
                                            success = False
                                            break
                                elif mode == "RESET":
                                    for wl_i in self.wls:
                                        if (res_array.loc[wl_i, bl_selected] < target_res) & mask.mask.loc[wl_i, bl_selected]:
                                            success = False
                                            break

                            if success:
                                print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                break
                        if success:
                            break
                    if success:
                        break
            
            # report final cell results
            all_data = []
            for wl in self.wls:
                for bl in self.bls:
                    if not bl=="BL_MULTI_READ":
                        cell_success = res_array.loc[wl,bl] <= target_res
                        cell_data = [self.chip, self.device, mode, wl, bl, res_array.loc[wl,bl], cond_array.loc[wl,bl], meas_i_array.loc[wl,bl], meas_v_array.loc[wl,bl], vwl, vsl, vbl, pw, cell_success]
                        if print_data: print(cell_data)
                        if record: self.datafile.writerow(cell_data)
                        all_data.append(cell_data)
                return all_data
            return None

    def dynamic_form(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(
            mode="FORM",
            target_res=target_res,
            is_1tnr=is_1tnr,
            bl_selected=bl_selected,
            relayed=relayed,
            debug=debug,
        )  
    
    def dynamic_set(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(mode="SET", target_res=target_res,is_1tnr=is_1tnr, bl_selected=bl_selected, relayed=relayed, debug=debug)

    def dynamic_reset(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(mode="RESET", target_res=target_res,is_1tnr=is_1tnr, bl_selected=bl_selected, relayed=relayed, debug=debug)
    
    def multi_set(self, vbl, vsl, vwl, pw):
        mask = RRAMArrayMask(self.wls, self.bls, self.sls, self.all_wls, self.all_bls, self.all_sls, self.polarity)
        self.set_pulse(
            mask,
            vbl=vbl,
            vsl=vsl,
            vwl=vwl,
            pulse_len=int(pw)
    )


    """ Digital and PPMU Pins to Zero in Digital Pattern"""
  
    

    def set_vbl(self, vbl_chan, vbl, vbl_lo):
        " Use DigitalPattern"

    def set_vsl(self, vsl_chan, vsl, vsl_lo):
        """Set VSL using NI-Digital driver"""
        

    def set_vwl(self, vwl_chan, vwl_hi, vwl_lo):
        """Set (active) VWL using NI-Digital driver (inactive disabled)"""
        
    def ppmu_set_vsl(self, vsl_chan, vsl):

    def ppmu_set_isl(self, isl_chan, isl):
        """Set ISL using NI-Digital driver"""
        assert(isl_chan in self.all_sls)
        for digital in self.digital:
            digital.channels[isl_chan].ppmu_current_level = isl
        for digital in self.digital:
            self.digital.channels[isl_chan].ppmu_source()

    def ppmu_set_vbl(self, vbl_chan, vbl):
        """Set (active) VBL using NI-Digital driver (inactive disabled)"""
        assert(vbl <= 6)
        assert(vbl >= -2)
        #assert(vbl_chan in self.all_bls)
        for digital in self.digital:
            digital.channels[vbl_chan].ppmu_voltage_level = vbl
        for digital in self.digital:
            digital.channels[vbl_chan].ppmu_source()

    def ppmu_set_vwl(self, vwl_chan, vwl):
        """Set VSL using NI-Digital driver"""
        assert(vwl <= 6)
        assert(vwl >= -2)
        assert(vwl_chan in self.all_wls)
        for digital in self.digital:
            digital.channels[vwl_chan].ppmu_voltage_level = vwl
        for digital in self.digital:
            digital.channels[vwl_chan].ppmu_source()
        #print("Setting VWL: " + str(vwl) + " on chan: " + str(vwl_chan))

    def ppmu_set_vbody(self, vbody_chan, vbody):
        """Set VBODY using NI-Digital driver"""
        assert(vbody <= 3)
        assert(vbody >= -1)
        assert(vbody_chan in self.body)
        for digital in self.digital:
            digital.channels[vbody_chan].ppmu_voltage_level = vbody
            digital.channels[vbody_chan].ppmu_current_limit_range = 32e-6
        for digital in self.digital:
            digital.channels[vbody_chan].ppmu_source()
        #print("Setting VSL: " + str(vsl) + " on chan: " + str(vsl_chan))

    def set_current_limit_range(self, channel=None, current_limit=1e-6):
        """ Set current limit for a given channel """
        for digital in self.digital:
            if channel is not None:
                if any(channel in pin.pin_name for pin in digital.get_pin_results_pin_information()):
                    digital.channels[channel].ppmu_current_limit_range = current_limit
        return

    def pulse(self, mask, pulse_len=10, prepulse_len=50, postpulse_len=50, max_pulse_len=10000, wl_first=True):
        """Create waveform for directly contacting the array BLs, SLs, and WLs, then output that waveform"""
        waveforms, pulse_width = self.build_waveforms(mask, pulse_len, prepulse_len, postpulse_len, max_pulse_len, wl_first)
        #WL_PULSE_DEC3.digipat or PULSE_MPW_ProbeCard.digipat as template file
        
        if self.pulse_pingroups is None:
            raise NIRRAMException("No pulse pin groups specified")
        for pingroup in self.pulse_pingroups:
            self.arbitrary_pulse(waveforms[self.pulse_pingroups.index(pingroup)], pin_group_name=pingroup, data_variable_in_digipat=f"{pingroup}_data", pulse_width=pulse_width)
        quit()
        self.digital.burst_pattern("PULSE_MPW_ProbeCard")
        return

    """ Need to figure out how to get the pattern pulse to work with NI-Tclk Sync"""

    def arbitrary_pulse(self, waveform, pin_group_name, data_variable_in_digipat,pulse_width=None):
        broadcast = nidigital.SourceDataMapping.BROADCAST
        self.digital[self.pulse_pingroups.index(pin_group_name)].pins[pin_group_name].create_source_waveform_parallel(data_variable_in_digipat, broadcast)
        self.digital[self.pulse_pingroups.index(pin_group_name)].write_source_waveform_broadcast(data_variable_in_digipat, waveform)
        if pulse_width:
            self.set_pw(pulse_width)
        return
    
    def build_waveforms(self, mask, pulse_len, prepulse_len, postpulse_len, max_pulse_len, wl_first, debug_printout = None):
        
        """Create pulse train. Format of bits is [BL SL] and . For an array
        with 2 BLs, 2 SLs, and 2 WLs, the bits are ordered:
            [ BL0 BL1 SL0 SL1 ], [ WL0 WL1 ]
        """
        
        if debug_printout is None:
            debug_printout = self.debug_printout

        #print(f"pulse_len = {pulse_len}, pulse_len < {prepulse_len}, max_pulse_len = {max_pulse_len}")
        if len(self.digital) > 1:
            bl_bits_offset = len(self.all_sls)
            sl_bits_offset = 0
        else:
            bl_bits_offset = len(self.all_wls) + len(self.all_sls)
            sl_bits_offset = len(self.all_wls)
        
        waveform = []
        if len(self.digital) == 1:
            for (wl_mask, bl_mask, sl_mask) in mask.get_pulse_masks():
                
                if debug_printout:
                    print(f"wl_mask = {wl_mask}")
                    print(f"bl_mask = {bl_mask}")
                    print(f"sl_mask = {sl_mask}")

                
                if not wl_first:
                    wl_pre_post_bits = BitVector(bitlist=(wl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    data_prepulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_pre_post_bits
                    data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_mask_bits
                    data_postpulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)  + wl_pre_post_bits
                else: 
                    bl_pre_post_bits = BitVector(bitlist=(bl_mask & False)).int_val()
                    sl_pre_post_bits = BitVector(bitlist=(sl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    data_prepulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset) + wl_mask_bits
                    data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_mask_bits
                    data_postpulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)  + wl_mask_bits
            
                if debug_printout:
                    print(f"data_prepulse = {data_prepulse:b}")
                    print(f"data = {data:b}")
                    print(f"data_postpulse = {data_postpulse:b}")

                waveform += [data_prepulse for i in range(prepulse_len)] + [data for i in range(pulse_len)] + [data_postpulse for i in range(postpulse_len)]
            
            

            #print waveform for debugging
            if debug_printout:
                for timestep in waveform:
                    print(bin(timestep))

            # zero-pad rest of waveform
            waveform += [0 for i in range(max_pulse_len*len(self.all_wls) - len(waveform))]
            pulse_width = prepulse_len + pulse_len + postpulse_len
            return waveform, pulse_width

        else:
            blsl_waveform = []
            wl_waveform = []
            waveforms = []
            for (wl_mask, bl_mask, sl_mask) in mask.get_pulse_masks():
                
                if debug_printout:
                    print(f"wl_mask = {wl_mask}")
                    print(f"bl_mask = {bl_mask}")
                    print(f"sl_mask = {sl_mask}")

                
                if not wl_first:
                    wl_pre_post_bits = BitVector(bitlist=(wl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    blsl_data_prepulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data_prepulse = wl_pre_post_bits
                    blsl_data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data = wl_mask_bits
                    blsl_data_postpulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data_postpulse = wl_pre_post_bits

                else: 
                    bl_pre_post_bits = BitVector(bitlist=(bl_mask & False)).int_val()
                    sl_pre_post_bits = BitVector(bitlist=(sl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    blsl_data_prepulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)
                    wl_data_prepulse = wl_mask_bits
                    
                    blsl_data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)  
                    wl_data = wl_mask_bits
                    
                    blsl_data_postpulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)
                    wl_data_postpulse = wl_mask_bits
            
                if debug_printout:
                    print(f"blsl_data_prepulse = {blsl_data_prepulse:b}")
                    print(f"blsl_data_prepulse = {wl_data_prepulse:b}")
                    print(f"wl_data = {blsl_data:b}")
                    print(f"wl_data = {wl_data:b}")
                    print(f"blsl_data_postpulse = {blsl_data_postpulse:b}")
                    print(f"wl_data_postpulse = {wl_data_postpulse:b}")

                blsl_waveform += [blsl_data_prepulse for i in range(prepulse_len)] + [blsl_data for i in range(pulse_len)] + [blsl_data_postpulse for i in range(postpulse_len)]
                wl_waveform += [wl_data_prepulse for i in range(prepulse_len)] + [wl_data for i in range(pulse_len)] + [wl_data_postpulse for i in range(postpulse_len)]
                waveforms.append(blsl_waveform)
                waveforms.append(wl_waveform)

            #print waveform for debugging
            if debug_printout:
                for timestep in waveform:
                    print(bin(timestep))

            # zero-pad rest of waveform
            for waveform in waveforms:
                waveform += [0 for i in range(max_pulse_len*len(self.all_wls) - len(waveform))]
            pulse_width = prepulse_len + pulse_len + postpulse_len
            return waveforms, pulse_width

    def set_pw(self, pulse_width):
        """Set pulse width"""
        pw_register = nidigital.SequencerRegister.REGISTER0
        self.digital.write_sequencer_register(pw_register, pulse_width)


    def relay_switch(self, sel_wls=None, zero_rows=None,NC_rows=None):
        assert(sel_wls is not None), "Please provide selected WLs to switch to"
        assert(sel_wls in self.all_wls), "Selected WLs must be in all WLs"
        
        # Set the outputs to empty arrays to allow for loop in operations
        zero_in = []
        wl_in = []
        NC_in = []

        if len(self.relays) == 2:
            with niswitch.Session(self.relays[0]) as relay0, niswitch.Session(self.relays[1]) as relay1:
                relay0.disconnect_all()
                relay1.disconnect_all()
                if type(sel_wls) == int:
                    sel_wls = "WL_" + str(sel_wls)
                sel_wls = [sel_wls]
                # Use the WL values to select the input (WL%24) and the relay (WL//66)
                wl_vals = np.array([np.uint8(wl[3:]) for wl in sel_wls])
                wl_vals_hi = wl_vals[wl_vals >= 66] - 66
                wl_vals_lo = wl_vals[wl_vals < 66] 
                wl_in = wl_vals % 24

                # Connect the selected COM -> NO in the relays for the given WLs
                for wl in wl_vals_lo:
                    if self.debug_printout:
                        print(f"Connecting WL_{wl}")
                    relay0.connect(f"com{wl}", f"no{wl}")
                for wl in wl_vals_hi:
                    if self.debug_printout:
                        print(f"Connecting WL_{wl+66}")
                    relay1.connect(f"com{wl}", f"no{wl}")

                # Check for WL that should be 0 and connect them to the corresponding WL_IN
                if zero_rows is not None:
                    zero_vals = np.array([np.uint8(wl[3:]) for wl in zero_rows])
                    zero_vals_hi = zero_vals[zero_vals >= 66] - 66
                    zero_vals_lo = zero_vals[zero_vals < 66]
                    zero_in = zero_vals % 24
                    for wl in zero_vals_lo:
                        if self.debug_printout:
                            print(f"Connecting WL_{wl}")
                        relay0.connect(f"com{wl}", f"no{wl}")
                    for wl in zero_vals_hi:
                        if self.debug_printout:
                            print(f"Connecting WL_{wl+66}")
                        relay1.connect(f"com{wl}", f"no{wl}")

                # Check for WL_IN that should be NC and connect them to the corresponnding WL_IN
                if NC_rows is not None:
                    NC_in = np.array([np.uint8(wl[3:]) for wl in NC_rows])
                    NC_vals_hi = NC_in[NC_in >= 66] - 66
                    NC_vals_lo = NC_in[NC_in < 66]
                    NC_in = NC_in % 24
                    for wl in NC_vals_lo:
                        if self.debug_printout:
                            print(f"Connecting WL_{wl}")
                        relay0.connect(f"com{wl}", f"no{wl}")
                    for wl in NC_vals_hi:
                        if self.debug_printout:
                            print(f"Connecting WL_{wl+66}")
                        relay1.connect(f"com{wl}", f"no{wl}")

            return wl_in, zero_in, NC_in


    def update_data_log(self, date, time, filename, location, notes):
        """
        Update the CSV with information on what files were written to,
        what information they contained, and where they are stored.
        The function then returns an incrementing identifier (####)
        that resets each day.
        """

        # Path to the CSV file

        if isinstance(self.settings, str):
            with open(self.settings, "rb") as settings_file:
                settings = tomli.load(settings_file)

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

        

if __name__ == "__main__":
    print("Hello World!")
    pass
import pdb
import numpy as np
import matplotlib.pyplot as plt
import argparse
from sys import path
from os import getcwd
import datetime as dt
import csv

path.append(getcwd())
from SourceScripts.digital_pattern import *
from SourceScripts.settings_util import *
from SourceScripts.debug_util import *



class CSAException(Exception):
    """Exception for CSA class"""
    def __init__(self, msg):
        super().__init__(f"CSA: {msg}")
    
class CSA:
    def __init__(self,chip,device,is_3D):
        self.settings = None
        self.debug = False
        self.chip = chip
        self.device = device
        self.is_3D = is_3D
        
        
    def initialize_settings(self, settings_file):
        self.settings_manager = SettingsUtil(settings_file)
        self.settings = self.settings_manager.settings
        self.settings_path = settings_file

        if self.settings is None:
            raise CSAException(f"Settings file {settings_file} not found")
        
    def initialize_session(self):
        self.digital_patterns = DigitalPattern(self.settings_manager)
        self.digital = self.digital_patterns.sessions
        
        self.digital_patterns.digital_all_pins_to_zero()
        self.digital_patterns.commit_all()

        # pdb.set_trace()
        self.digital_patterns.ppmu_set_voltage(["DIR_PERIPH_SEL"],0.0,source=True)
        self._load_relay_settings(self.settings_manager)

    def _load_relay_settings(self, settings_manager: SettingsUtil):
        """Load relay-specific settings from the provided settings manager."""
        self.relays = None
        self.relay_information = settings_manager.get_setting("NISwitch", default=None)
        
        if self.relay_information:
            self.relays = settings_manager.get_setting("NISwitch.deviceID", required=True)

    def broadcast_waveforms_from_file(self, source_waveforms=None, source_waveform_names=None, capture_waveforms=None, capture_waveform_names=None, pins=None):
        if source_waveforms is not None:
            if source_waveform_names is None:
                raise CSAException("Source waveform names not provided")
        if capture_waveforms is not None:
            if capture_waveform_names is None:
                raise CSAException("Capture waveform names not provided")
        if capture_waveform_names is not None and capture_waveforms is None:
            if pins is None:
                raise CSAException("Capture Pins not provided, and no file is given, cannot retrieve waveforms")
        if source_waveforms is not None or capture_waveforms is not None or capture_waveform_names is not None:
            print("I'm here!")
            self.digital_patterns.load_waveforms(source_waveforms, source_waveform_names, capture_waveforms, capture_waveform_names,pins) 
        
        self.digital_patterns.broadcast_waveforms()

    def read_captured_waveforms(self, pins=None, waveform_names=None):
        captured_waveforms = self.digital_patterns.fetch_waveforms(pins, waveform_names)
        for i in range(73):
            print(bin(list(captured_waveforms[0].values())[0][i]))
        return captured_waveforms
    
    def define_pins(self):
        self.pins = []
        pingroups = self.settings_manager.get_setting("device.pins")
        
        for session_pingroup in pingroups:
            session_pins = []  # Re-initialize here, once per session group
            for pingroup in session_pingroup:
                setting_pins = self.settings_manager.get_setting(f"device.{pingroup}")
                if isinstance(setting_pins, list):
                    session_pins.extend(setting_pins)  # Add all pins in the list
                elif isinstance(setting_pins, str):
                    session_pins.append(setting_pins)  # Add the single pin
                else:
                    raise CSAException(f"Invalid pin setting {pingroup}")
            self.pins.append(session_pins)  # Append the session pins to the overall list

    def set_to_off(self,channels,name, sort=True,debug=None):
        # print(f"Setting {name} channels {channels} to off")
        if type(channels) is not list:
            channels = [channels]
        
        if type(channels[0]) is list and sort==True:
            channels = [item for sublist in channels for item in sublist]

        if type(channels[0]) is int or type(channels[0]) is np.uint8:
            channels = [f"{name}_{chan}" for chan in channels]
        
        self.digital_patterns.set_channel_mode("off", pins=channels,sessions=None,sort=sort,debug=debug)

    def set_pin_voltages(self):

        vih = self.settings_manager.get_setting("voltages.vih", 1.8)
        vil = self.settings_manager.get_setting("voltages.vil", 0.0)
        voh = self.settings_manager.get_setting("voltages.voh", 1.8)
        vol = self.settings_manager.get_setting("voltages.vol", 0.0)

        # Non-traditional voltages
        #RMUX_EN = 5V on 0V off
        vih_rmuxen = self.settings_manager.get_setting("other_voltages.RMUX_EN.vih", 5)
        vil_rmuxen = self.settings_manager.get_setting("other_voltages.RMUX_EN.vil", 0)
        voh_rmuxen = self.settings_manager.get_setting("other_voltages.RMUX_EN.voh", 5)
        vol_rmuxen = self.settings_manager.get_setting("other_voltages.RMUX_EN.vol", 0)

        #VREAD = 0.3V on 0V off
        vih_vread = self.settings_manager.get_setting("other_voltages.VREAD.vih", 0.1)
        vil_vread = self.settings_manager.get_setting("other_voltages.VREAD.vil", 0)
        voh_vread = self.settings_manager.get_setting("other_voltages.VREAD.voh", 0.1)
        vol_vread = self.settings_manager.get_setting("other_voltages.VREAD.vol", 0)

        #WL_UNSEL = Hi on, Lo off (2 to 4V)
        vih_wlunsel = self.settings_manager.get_setting("other_voltages.WL_UNSEL.voh", 1.8)
        vil_wlunsel = self.settings_manager.get_setting("other_voltages.WL_UNSEL.vil", 0)
        voh_wlunsel = self.settings_manager.get_setting("other_voltages.WL_UNSEL.voh", 1.8)
        vol_wlunsel = self.settings_manager.get_setting("other_voltages.WL_UNSEL.vol", 0)
        # WL = Lo on, Hi off (-1 to -2V)
        vih_wlin = self.settings_manager.get_setting("other_voltages.WL_IN.voh", 1.8)
        vil_wlin = self.settings_manager.get_setting("other_voltages.WL_IN.vil", 0)
        voh_wlin = self.settings_manager.get_setting("other_voltages.WL_IN.voh", 1.8)
        vol_wlin = self.settings_manager.get_setting("other_voltages.WL_IN.vol", 0)

        # Outputs should be < 1.8V to trigger high
        vih_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vih", 1)
        vil_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vil", 0.3)
        voh_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.voh", 1)
        vol_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vol", 0.3)

        # Outputs should be < 1.8V to trigger high
        vih_sl = self.settings_manager.get_setting("other_voltages.SL.vih", 0)
        vil_sl = self.settings_manager.get_setting("other_voltages.SL.vil", 0)
        voh_sl = self.settings_manager.get_setting("other_voltages.SL.voh", 0)
        vol_sl = self.settings_manager.get_setting("other_voltages.SL.vol", 0)

        # Outputs should be < 1.8V to trigger high
        vih_colsel = self.settings_manager.get_setting("other_voltages.COL.vih", 3)
        vil_colsel = self.settings_manager.get_setting("other_voltages.COL.vil", 0)
        voh_colsel = self.settings_manager.get_setting("other_voltages.COL.voh", 3)
        vol_colsel = self.settings_manager.get_setting("other_voltages.COL.vol", 0)


        self.digital_patterns.digital_set_voltages(self.pins, vi_lo=vil, vi_hi=vih, vo_lo=vol, vo_hi=voh,sort=False)
        self.digital_patterns.digital_set_voltages([[],[],["RMUX_EN"]], vi_lo=vil_rmuxen, vi_hi=vih_rmuxen, vo_lo=vol_rmuxen, vo_hi=voh_rmuxen,sort=False)
        self.digital_patterns.digital_set_voltages([[],[],["VREAD"]], vi_lo=vil_vread, vi_hi=vih_vread, vo_lo=vol_vread, vo_hi=voh_vread,sort=False)
        if self.is_3D:
            self.digital_patterns.digital_set_voltages([[],[],["WL_IN_0","WL_IN_21","WL_IN_22","WL_IN_23"]],vi_lo=vil_wlin, vi_hi=vih_wlin, vo_lo=vol_wlin, vo_hi=voh_wlin,sort=False)
            self.digital_patterns.digital_set_voltages([[],[],["SA_CLK_EXT"]],vi_lo=vil_colsel, vi_hi=vih_colsel, vo_lo=vol_colsel, vo_hi=voh_colsel,sort=False)
            self.digital_patterns.digital_set_voltages([[],["SL_0", "SL_1","SL_2","SL_3","SL_29","SL_30","SL_31"],[]],vi_lo=vil_sl, vi_hi=vih_sl, vo_lo=vol_sl, vo_hi=voh_sl,sort=False)        
        else:
            self.digital_patterns.digital_set_voltages([[],[],["WL_IN_0"]],vi_lo=vil_wlin, vi_hi=vih_wlin, vo_lo=vol_wlin, vo_hi=voh_wlin,sort=False)            
        # self.digital_patterns.digital_set_voltages([[],[],["WL_UNSEL"]],vi_lo=vil_wlunsel, vi_hi=vih_wlunsel, vo_lo=vol_wlunsel, vo_hi=voh_wlunsel,sort=False)
        # Set WL_UNSEL to OFF to avoid leakage
        self.set_to_off([["WL_UNSEL"]],["WL"])

        if "DO_7" in self.digital_patterns.all_pins:
            self.digital_patterns.digital_set_voltages([[],[],["DO_7","DO_6","DO_5","DO_4","DO_3","DO_2","DO_1","DO_0","SA_RDY_7","SA_RDY_6","SA_RDY_5","SA_RDY_4","SA_RDY_3","SA_RDY_2","SA_RDY_1","SA_RDY_0"]], vi_lo=vil_do, vi_hi=vih_do, vo_lo=vol_do, vo_hi=voh_do,sort=False)
        else:
            self.digital_patterns.digital_set_voltages([[],[],["DO_1","DO_0","SA_RDY_1","SA_RDY_0"]], vi_lo=vil_do, vi_hi=vih_do, vo_lo=vol_do, vo_hi=voh_do,sort=False)        
        self.digital_patterns.commit_all()

    def set_channel_mode(self, pins=None, mode="DIGITAL"):
        if pins is None:
            pins = self.pins
        for session_pins in pins:
            self.digital_patterns.set_channel_mode(mode=mode,pins=session_pins)
    
    def check_leakage(self, pins = ["RMUX_EN","SA_CLK_EXT","DIR_PERIPH_SEL"], source_pins=["DIR_PERIPH_SEL"]):
        if pins == ["COL_SEL"]:
            pins = [f"COL_SEL_{i}" for i in range(16)]
                
        self.set_channel_mode(pins=pins, mode="PPMU")
        self.set_channel_mode(pins=source_pins, mode="PPMU")
        for i in [r*0.1 for r in range(51)]:
            self.digital_patterns.ppmu_set_voltage(pins=pins, voltage_levels = 0, source=True)
            time.sleep(10)

        # currents,_,_ = self.digital_patterns.measure_current(pins=source_pins)
        # currents = np.array(currents[2])
        # print(currents)

    def check_vread_current(self):
        pins= [f"COL_SEL_{i}" for i in range(4)] + ["BL_0"] + ["SL_0"] + ["DIR_PERIPH_SEL"]
        self.set_channel_mode(pins=pins, mode="PPMU")
        for i in range(4):
            self.digital_patterns.ppmu_set_voltage(pins=pins, voltage_levels = 0, source=True)
            self.digital_patterns.ppmu_set_voltage(pins=["BL_0"], voltage_levels = 0, source=True)
            self.digital_patterns.ppmu_set_voltage(pins=[f"COL_SEL_{i}"], voltage_levels = 1, source=True)
            time.sleep(1)
            currents,_,_ = self.digital_patterns.measure_current(pins=pins)
            time.sleep(1)
            self.digital_patterns.ppmu_set_voltage(pins=pins, voltage_levels = 0, source=True)
            print(currents)

    def save_captured_waveform(self, waveform_name=None, filename=None):
        if waveform_name is None:
            raise CSAException("Waveform name not provided")
        if filename is None:
            header = self.settings_manager.get_setting("path.data_header")
            date = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            test = self.settings_manager.get_setting("path.test_name","CONV")
            filename = f"{header}/{test}/{date}_{self.chip}_{self.device}_{waveform_name}.csv"
    
    def relay_switch(self, wls, relayed=True, debug = None):
        if self.relays is None:
            raise CSAException("No Relay Cards Found")

        num_relays = len(self.relays)

        sorted_wls = []
        
        for i in range(num_relays):
            # Sort the WL channels by relay 0-65 for relay 1, 66-131 for relay 2, (sending 0-65 for each relay)
            sorted_wls.append([(int(wl[3:])-66*i) for wl in wls if int(wl[3:])//66 == i])        

        wl_input_signals = [f"WL_IN_{int(wl[3:])%24}"for wl in wls] 
        # for wl_in in wl_input_signals:
            # if wl_in not in ["WL_IN_0","WL_IN_21","WL_IN_22","WL_IN_23"]:
                # raise CSAException(f"{wl_in} is out of bounds, please be sure the WL % 24 is 0, 21, 22 or 23")
        # Switch the relays at the given WL channels, separated by relay.
        self.digital_patterns.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug)
        
        # return       
    
def arg_parse():
    parser = argparse.ArgumentParser(description="Define a Chip")
    parser.add_argument("chip", help="Chip name for logging")
    parser.add_argument("device", help="Device name for logging")
    parser.add_argument("--CNT",help="Include if Chip is 3D CNT + RRAM", action="store_true")
    parser.add_argument("--polarity", help="Polarity of the device", default="NMOS")
    
    if parser.parse_args().CNT:
        parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_3D_CSA_Test.toml")
    else:
        parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_2D_CSA_Test.toml")
    
    parser.add_argument("--debug", help="Enable debug mode", action="store_true")
    parser.add_argument("--test_type", help="Type of test being performed", default="CSA")
    parser.add_argument("--comments", help="Additional information about the test", default="")
    parser.add_argument("--no_clk", help="Disable the clock", action="store_false")
    parser.add_argument("--clk_speed", help="Clock speed in Hz", default=1e7)
    parser.add_argument("--verbose", help="Enable verbose mode", action="store_true")
    parser.add_argument("-verbose", help="Enable verbose mode", action="store_true")
    parser.add_argument("-v", help="Enable verbose mode", action="store_true")
    parser.add_argument("--v", help="Enable verbose mode", action="store_true")
    parser.add_argument('--measure_iv', help='Measure IV characteristics', action='store_true')
    parser.add_argument('--no_input_measurement', help='Do not measure input pins', action='store_false')
    parser.add_argument('--no_sweep', help='Do not sweep the input pins', action='store_false')
    parser.add_argument('--measurement_number', help='Measurement number', default=1)
    parser.add_argument('--measurement_interval', help='Measurement interval', default=5e-5)
    parser.add_argument('--print', help='Print the measured values', action='store_true')
    args = parser.parse_args()

    return args

def main(args):
    connected_wl = 0
    csa = CSA(chip=args.chip, device = args.device, is_3D = args.CNT)
    csa.initialize_settings(args.settings)
    csa.initialize_session()
    csa.define_pins()
    csa.set_channel_mode()
    remove_bias=[]
    # remove_bias=[f"WL_{i}" for i in [23,34,47,54,60,81,83,102,105,113,114,123]]
    csa.relay_switch([f"wl_{connected_wl}"]+remove_bias,relayed=True,debug=False)
    # pdb.set_trace()
    csa.set_pin_voltages()
    # pdb.set_trace()
    for i in range(10000):
        csa.broadcast_waveforms_from_file()
    
    csa.read_captured_waveforms()
    # csa.check_leakage()


if __name__ == "__main__":
    args = arg_parse()
    main(args)
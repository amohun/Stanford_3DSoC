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



class ConvolutionException(Exception):
    """Exception for Convolution class"""
    def __init__(self, msg):
        super().__init__(f"CSA: {msg}")
    
class Convolution:
    def __init__(self,chip,device):
        self.settings = None
        self.debug = False
        self.chip = chip
        self.device = device
        
        
    def initialize_settings(self, settings_file):
        self.settings_manager = SettingsUtil(settings_file)
        self.settings = self.settings_manager.settings
        self.settings_path = settings_file

        if self.settings is None:
            raise ConvolutionException(f"Settings file {settings_file} not found")
        
    def initialize_session(self):
        self.digital_patterns = DigitalPattern(self.settings_manager)
        self.digital = self.digital_patterns.sessions
        
        self.digital_patterns.digital_all_pins_to_zero()
        self.digital_patterns.commit_all()

        # pdb.set_trace()
        self.digital_patterns.ppmu_set_voltage(["DIR_PERIPH_SEL"],0.0,source=True)

    def broadcast_waveforms_from_file(self, source_waveforms=None, source_waveform_names=None, capture_waveforms=None, capture_waveform_names=None, pins=None):
        if source_waveforms is not None:
            if source_waveform_names is None:
                raise ConvolutionException("Source waveform names not provided")
        if capture_waveforms is not None:
            if capture_waveform_names is None:
                raise ConvolutionException("Capture waveform names not provided")
        if capture_waveform_names is not None and capture_waveforms is None:
            if pins is None:
                raise ConvolutionException("Capture Pins not provided, and no file is given, cannot retrieve waveforms")
        if source_waveforms is not None or capture_waveforms is not None or capture_waveform_names is not None:
            self.digital_patterns.load_waveforms(source_waveforms, source_waveform_names, capture_waveforms, capture_waveform_names,pins) 
        
        self.digital_patterns.broadcast_waveforms()

    def read_captured_waveforms(self, chip,condition="None", pins=None, waveform_names=None):
        captured_waveforms = self.digital_patterns.fetch_waveforms(pins, waveform_names)
        OFMAP_LIST = []
        if condition != "None":
            import os
            os.makedirs(f"C:/c{chip}/{condition}",exist_ok=True)
            with open(f"C:/c{chip}/{condition}/0-23.txt","+a") as file:
                for i in range(98):
                    OFMAP_VALS = format(list(captured_waveforms[0].values())[0][i],'024b')[::-1]
                    file.write(f"0b{OFMAP_VALS}\n")

        for i in range(98):
            OFMAP_VALS = format(list(captured_waveforms[0].values())[0][i],'024b')[::-1]
            print("0b"+OFMAP_VALS)
            # print(bin(list(captured_waveforms[0].values())[0][i]))
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
                    raise ConvolutionException(f"Invalid pin setting {pingroup}")
            self.pins.append(session_pins)  # Append the session pins to the overall list

    def set_pin_voltages(self):

        vih = self.settings_manager.get_setting("voltages.vih", 1.8)
        vil = self.settings_manager.get_setting("voltages.vil", 0.0)
        voh = self.settings_manager.get_setting("voltages.voh", 1.8)
        vol = self.settings_manager.get_setting("voltages.vol", 0.0)

        # Non-traditional voltages

        # Outputs should be < 1.8V to trigger high
        vih_do = self.settings_manager.get_setting("other_voltages.OFMAP.vih", 1.0)
        vil_do = self.settings_manager.get_setting("other_voltages.OFMAP.vil", 0.0)
        voh_do = self.settings_manager.get_setting("other_voltages.OFMAP.voh", 1.0)
        vol_do = self.settings_manager.get_setting("other_voltages.OFMAP.vol", 0.0)

        
        self.digital_patterns.digital_set_voltages(self.pins, vi_lo=vil, vi_hi=vih, vo_lo=vol, vo_hi=voh,sort=False)
        self.digital_patterns.digital_set_voltages([["OFMAP_0", "OFMAP_1","OFMAP_2", "OFMAP_3","OFMAP_4", "OFMAP_5","OFMAP_6", "OFMAP_7",
                                                     "OFMAP_8", "OFMAP_9","OFMAP_10", "OFMAP_11","OFMAP_12", "OFMAP_13","OFMAP_14", "OFMAP_15",
                                                     "OFMAP_16", "OFMAP_17","OFMAP_18", "OFMAP_19","OFMAP_20", "OFMAP_21","OFMAP_22", "OFMAP_23"]
                                                    ,[],[]], vi_lo=vil_do, vi_hi=vih_do, vo_lo=vol_do, vo_hi=voh_do,sort=False)



        self.digital_patterns.digital_set_voltages(self.pins, vi_lo=vil, vi_hi=vih, vo_lo=vol, vo_hi=voh,sort=False)
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
 
        self.digital_patterns.digital_set_voltages([[],[],["WL_IN_0"]],vi_lo=vil_wlin, vi_hi=vih_wlin, vo_lo=vol_wlin, vo_hi=voh_wlin,sort=False)            
        # self.digital_patterns.digital_set_voltages([[],[],["WL_UNSEL"]],vi_lo=vil_wlunsel, vi_hi=vih_wlunsel, vo_lo=vol_wlunsel, vo_hi=voh_wlunsel,sort=False)

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

    def save_captured_waveform(self, waveform_name=None, filename=None):
        if waveform_name is None:
            raise ConvolutionException("Waveform name not provided")
        if filename is None:
            header = self.settings_manager.get_setting("path.data_header")
            date = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            test = self.settings_manager.get_setting("path.test_name","CONV")
            filename = f"{header}/{test}/{date}_{self.chip}_{self.device}_{waveform_name}.csv"
    
def arg_parse():
    parser = argparse.ArgumentParser(description="Define a Chip")
    parser.add_argument("chip", help="Chip name for logging")
    parser.add_argument("device", help="Device name for logging")
    parser.add_argument("--CNT",help="Include if Chip is 3D CNT + RRAM", action="store_true")
    parser.add_argument("--polarity", help="Polarity of the device", default="NMOS")
    
    if parser.parse_args().CNT:
        parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_3D_Conv_Test.toml")
    else:
        parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_2D_Conv_Test.toml")
    
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
    conv = Convolution(chip=args.chip, device = args.device)
    conv.initialize_settings(args.settings)
    conv.initialize_session()
    conv.define_pins()
    conv.set_channel_mode()
    # pdb.set_trace()
    conv.set_pin_voltages()
    pdb.set_trace()
    
    for i in range(100000):
        conv.broadcast_waveforms_from_file()
    
    conv.read_captured_waveforms(chip=4, condition="0 -255")


if __name__ == "__main__":
    args = arg_parse()
    main(args)
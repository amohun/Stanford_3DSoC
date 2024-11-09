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

    def read_captured_waveforms(self, pins=None, waveform_names=None):
        captured_waveforms = self.digital_patterns.fetch_waveforms(pins, waveform_names)
        for i in range(98):
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
    parser.add_argument("--polarity", help="Polarity of the device", default="NMOS")
    parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_Conv_Test.toml")
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
    # pdb.set_trace()
    for i in range(10):
        conv.broadcast_waveforms_from_file()
    
    conv.read_captured_waveforms()


if __name__ == "__main__":
    args = arg_parse()
    main(args)
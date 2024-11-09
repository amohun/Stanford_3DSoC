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
            raise CSAException(f"Settings file {settings_file} not found")
        
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
                raise CSAException("Source waveform names not provided")
        if capture_waveforms is not None:
            if capture_waveform_names is None:
                raise CSAException("Capture waveform names not provided")
        if capture_waveform_names is not None and capture_waveforms is None:
            if pins is None:
                raise CSAException("Capture Pins not provided, and no file is given, cannot retrieve waveforms")
        if source_waveforms is not None or capture_waveforms is not None or capture_waveform_names is not None:
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

        #RMUX_EN = 0.3V on 0V off
        vih_vread = self.settings_manager.get_setting("other_voltages.VREAD.vih", 0.3)
        vil_vread = self.settings_manager.get_setting("other_voltages.VREAD.vil", 0)
        voh_vread = self.settings_manager.get_setting("other_voltages.VREAD.voh", 0.3)
        vol_vread = self.settings_manager.get_setting("other_voltages.VREAD.vol", 0)

        # Outputs should be < 1.8V to trigger high
        vih_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vih", 1.5)
        vil_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vil", 0)
        voh_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.voh", 1.5)
        vol_do = self.settings_manager.get_setting("other_voltages.SARDY_DO.vol", 0)

        self.digital_patterns.digital_set_voltages(self.pins, vi_lo=vil, vi_hi=vih, vo_lo=vol, vo_hi=voh,sort=False)
        self.digital_patterns.digital_set_voltages([[],[],["RMUX_EN"]], vi_lo=vil_rmuxen, vi_hi=vih_rmuxen, vo_lo=vol_rmuxen, vo_hi=voh_rmuxen,sort=False)
        self.digital_patterns.digital_set_voltages([[],[],["VREAD"]], vi_lo=vil_vread, vi_hi=vih_vread, vo_lo=vol_vread, vo_hi=voh_vread,sort=False)
        self.digital_patterns.digital_set_voltages([[],[],["SA_RDY_0","SA_RDY_1","DO_0","DO_1"]], vi_lo=vil_do, vi_hi=vih_do, vo_lo=vol_do, vo_hi=voh_do,sort=False)

        
        
        self.digital_patterns.commit_all()

    def set_channel_mode(self, pins=None, mode="DIGITAL"):
        if pins is None:
            pins = self.pins
        for session_pins in pins:
            self.digital_patterns.set_channel_mode(mode=mode,pins=session_pins)
    
    def check_leakage(self, pins = ["COL_SEL"], source_pins=["VREAD"]):
        if pins == ["COL_SEL"]:
            pins = [f"COL_SEL_{i}" for i in range(16)]
                
        self.set_channel_mode(pins=pins, mode="PPMU")
        self.set_channel_mode(pins=source_pins, mode="PPMU")

        self.digital_patterns.ppmu_set_voltage(pins=pins, voltage_levels = 0, source=True)
        self.digital_patterns.ppmu_set_voltage(pins=source_pins, voltage_levels = 1.8, source=True)

        currents,_,_ = self.digital_patterns.measure_current(pins=pins)
        currents = np.array(currents[2])
        current_total = np.sum(currents)
        print(currents)
        print(current_total)

        currents,_,_ = self.digital_patterns.measure_current(pins=source_pins)
        currents = np.array(currents[2])
        current_total = np.sum(currents)
        print(currents)
        print(current_total)



    def save_captured_waveform(self, waveform_name=None, filename=None):
        if waveform_name is None:
            raise CSAException("Waveform name not provided")
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
    parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_CSA_Test.toml")
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
    conv = CSA(chip=args.chip, device = args.device)
    conv.initialize_settings(args.settings)
    conv.initialize_session()
    conv.define_pins()
    conv.set_channel_mode()

    # pdb.set_trace()
    conv.set_pin_voltages()
    # pdb.set_trace()
    for i in range(200):
        conv.broadcast_waveforms_from_file()
    
    conv.read_captured_waveforms()


if __name__ == "__main__":
    args = arg_parse()
    main(args)
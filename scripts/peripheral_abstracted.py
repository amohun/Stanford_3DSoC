"""Script to perform a read voltage sweep on a chip"""
import argparse
import pdb
import nidigital
import time
import numpy as np
from os import getcwd
from os.path import abspath
from sys import path
from datetime import date, datetime
from dataclasses import dataclass
import tomli
import csv

path.append(getcwd())
from SourceScripts.settings_util import *
import SourceScripts.masks as masks
from SourceScripts.digital_pattern import DigitalPattern
from SourceScripts.string_util import *
from SourceScripts.debug_util import DebugUtil

@dataclass
class PeripheralOperationresults:
    '''Data class to store measured parameters from a CSA operation'''
    chip: str
    device: str
    mode: str
    csa: int
    wl: str
    bl: str
    clk_en: bool


class PeripheralException(Exception):
    """Exception produced by the CSA_Abstracted class"""
    def __init__(self, msg):
        super().__init__(f"CSA: {msg}")

class PeripheralAbstracted:
    def __init__(
                 self, 
                 settings_file = './settings/peripheral_settings.toml', 
                 debug=False
                ):
        
        # Initialize Debug Utility
        self.debug = debug
        self.dbg = DebugUtil(debug)
        self.dbg.start_function_debug(debug)

        # Load settings from file
        self.settings = load_settings(settings_file)

        self.pattern = DigitalPattern(self.settings['digital_pattern'])
        self.pattern.load_pattern()

        self.results = []

    def run(self):
        self.debug.print("PeripheralAbstracted: Running")
        self.debug.print("PeripheralAbstracted: Done")

    def run_dnn(self, filepath, debug=None):
        self.debug.print("PeripheralAbstracted: Running DNN")
        self.debug.print("PeripheralAbstracted: Done")

    def run_top_level(self):
        self.debug.print("PeripheralAbstracted: Running Top Level")
        self.debug.print("PeripheralAbstracted: Done")

    def save_results(self, file_name):
        self.debug.print(f"PeripheralAbstracted: Saving results to {file_name}")
        with open(file_name, 'w', newline='') as csvfile:
            fieldnames = ['Chip', 'Device', 'Mode', 'CSA', 'WL', 'BL', 'ClkEn']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in self.results:
                writer.writerow(result.__dict__)

    """ ====================================================== """
    """                    CSA Test Cleanup                    """
    """ ====================================================== """

    def close_sessions(self,debug=None):
        """
        Close Sessions: Close the NI Digital and NI System sessions

        Returns:
        None
        """
        
        self.dbg.start_function_debug(debug)
        
        self.digital_patterns.close()
        
        self.dbg.end_function_debug()
    
    def __del__(self):
        """
        Destructor: Close the sessions when the object is deleted
        """
        #End the clock if it is enabled
        if self.clock_enable:
            self.digital_patterns.end_clock()
        
        # Set all pins to zero, then Hi-Z
        self.digital_patterns.ppmu_set_pins_to_zero()
        self.digital_patterns.set_channel_termination_mode()

        # Close the sessions
        self.close_sessions()

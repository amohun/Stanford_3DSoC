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
from SourceScripts.load_settings import *
import SourceScripts.masks as masks
from SourceScripts.digital_pattern import DigitalPattern
from SourceScripts.string_util import *
from SourceScripts.debug_util import DebugUtil

# region Other Classes
@dataclass
class CSAOperationresults:
    '''Data class to store measured parameters from a CSA operation'''
    chip: str
    device: str
    mode: str
    csa: int
    wl: str
    bl: str
    clk_en: bool


class CSAException(Exception):
    """Exception produced by the CSA_Abstracted class"""
    def __init__(self, msg):
        super().__init__(f"CSA: {msg}")

# endregion

class CSA_Abstracted:
    def __init__(
            self,
            chip,
            device,
            polarity = "NMOS",
            settings = "settings/MPW_CSA_Test.toml",
            debug = False,
            test_type = "Default",
            additional_info = "",
            clock_enable = False,
            clock_speed = 2.5e7
            ):
        
        # Define the debug utility
        self.dbg = DebugUtil(debug)
        self.dbg.start_function_debug(debug)
        
        # Set a flag for ni session connection
        self.connection_closed = True
       
        # Set the class variables
        self.chip = chip
        self.device = device
        self.polarity = polarity
        self.debug = debug
        self.test_type = test_type
        self.additional_info = additional_info

        self.clock_enable = clock_enable
        self.clock_speed = clock_speed

        # Load the settings file
        settings, settings_filepath = self.load_settings_file(settings)

        # Load the log file to store data
        self.init_log_file()
        
        # Set the number of CSAs based on device polarity
        self.set_n_csas()

        self.dbg.operation_debug("Setting", ["Chip", "Device", "Polarity", "Settings", "Debug", "Test Type", "Additional Info", "Clock Enable", "Clock Speed"], [self.chip, self.device, self.polarity, self.settings_path, self.debug, self.test_type, self.additional_info, self.clock_enable, self.clock_speed])

        # Get BLS based on col_idx
        self.bls = self.set_col_sel_idx_bls(0, self.n_csas)

        # Start Sessions

        # End function debug
        self.dbg.end_function_debug()


    """ ====================================================== """
    """                    CSA Test Setup                      """
    """ ====================================================== """
    # region
    
    def load_settings_file(self, settings,debug=None):
        """
        Load Settings: Load the settings from the settings file

        Args:
        settings (str/dict): Path to the settings file

        Returns:
        dict: Dictionary containing the settings
        
        """
        
        self.dbg.start_function_debug(debug)
        
        # Load the settings from a toml file
        self.settings_path = settings if type(settings) is str else None
        self.settings = load_settings(settings)
        settings = self.settings
        settings["NIDigital"]["specs"] = [abspath(path) for path in self.settings["NIDigital"]["specs"]]

        self.op = settings["operations"]
        
        self.dbg.end_function_debug()
        
        return self.settings, self.settings_path
   
    def start_sessions(self,debug=None):
        """
        Start Sessions: Start the NI Digital and NI System sessions

        Returns:
        None
        
        """
        
        self.dbg.start_function_debug(debug)
        
        # Start the NI Digital session
        self.digital_patterns = DigitalPattern(self.settings)
        self.digital = self.digital_patterns.digital

        self.digital_patterns.configure_read()
        self.digital_patterns.commit_all()

        self.dbg.end_function_debug()


    def set_n_csas(self, polarity=None,debug=None):
        """
        Set N CSAs: Set the number of CSAs based on the device polarity
        8 for PMOS and 2 for NMOS

        Args:
        polarity (str): Polarity of the device (default: None)

        Returns:
        int: Number of CSAs
        
        """
        
        self.dbg.start_function_debug(debug)
        
        if polarity is None:
            polarity = self.polarity
        
        if polarity.upper() == "NMOS" or polarity.upper() == "N":
            self.n_csas = 2
        elif polarity.upper() =="PMOS" or polarity.upper() == "P":
            self.n_csas = 8
        else:
            raise CSAException("Invalid polarity expected NMOS or PMOS")

        self.dbg.debug_message(f"Setting the number of CSAs based on polarity: {self.polarity}\nNumber of CSAs: {self.n_csas}")
        self.dbg.end_function_debug()     

        return self.n_csas

    def set_col_sel_idx_bls(self, col_sel_idx, n_csas,debug=None):
        """
        From rram_csa_3d_readout_full_tb: 
        The first CSA is connected to RRAM cells <31> to <28>, 
        the second is connected to RRAM cells <27> to <24>, 
        and so on....
        """
        bls = [f"BL_{32-int(32/n_csas)*(i+1)+col_sel_idx}" for i in range(n_csas)] 
        return bls
   
    def set_sources(self, sources=None):
        if sources is None:
            sources = self.settings["NIDigital"]["sources"]
   
    # endregion

    

    def print_waveform(self, results_dict, bl_idxs, polarity="NMOS", debug=None):
        """
        Print Waveform: Print the waveform for the given results dictionary
        and bitline indices. The function prints the SA_RDY and DO signals

        Args:
        results_dict (dict): Dictionary containing the results of the test
        bl_idxs (list): List of bitline indices to print
        polarity (str): Polarity of the device (default: "NMOS")

        Returns:
        None
        """
        
        self.dbg.start_function_debug(debug)

        for wl_name in results_dict:
            print("Waveform: ", wl_name)
            for idx,_ in enumerate(bl_idxs):
                sa_rdy_waveform = [int(x[f"SA_RDY_{idx}"]) for x in results_dict[wl_name]]
                do_waveform = [int(x[f"DO_{idx}"]) for x in results_dict[wl_name]]
                print(f"SA_RDY_{idx}:\t{sum(sa_rdy_waveform)}")
                print(f"DO_{idx}:\t\t{sum(do_waveform)}")

        self.dbg.end_function_debug()



    """ ====================================================== """
    """ Util Functions for Bookkeeping, Debugging, and Logging """
    """ ====================================================== """
    # region
    
    def init_log_file(self, debug=None):
        """
        Initialize Log File: Initialize the log file for the test
        """
        self.dbg.start_function_debug(debug)
        # Initialize CSA Logging
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")
        hash = self.update_data_log(current_date, current_time, f"chip_{self.chip}_device_{self.device}", self.test_type, self.additional_info)
        self.datafile_path = self.settings["path"]["data_header"] + f"/{self.test_type}/{current_date}_{self.chip}_{self.device}_{hash}.csv"

        self.dbg.operation_debug("Setting", ["Date", "Time", "Filename", "Location", "Notes"], [current_date, current_time, f"chip_{self.chip}_device_{self.device}", self.test_type, self.additional_info])

        with open(self.datafile_path, "a", newline='') as file_object:
            datafile = csv.writer(file_object)
            datafile.writerow(["Chip_ID", "Device_ID", "MODE", "Time", "OP"])
        
        self.dbg.end_function_debug()



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

    # endregion
    
def main():
    parser = argparse.ArgumentParser(description="Define a Chip")
    parser.add_argument("chip", help="Chip name for logging")
    parser.add_argument("device", help="Device name for logging")
    parser.add_argument("--polarity", help="Polarity of the device", default="NMOS")
    parser.add_argument("--settings", help="Path to the settings file", default="settings/MPW_CSA_Test.toml")
    parser.add_argument("--debug", help="Enable debug mode", action="store_true")
    parser.add_argument("--test_type", help="Type of test being performed", default="CSA")
    parser.add_argument("--comments", help="Additional information about the test", default="")
    parser.add_argument("--no_clk", help="Enable the clock", action="store_false")
    parser.add_argument("--clk_speed", help="Clock speed in Hz", default=2.5e7)
    parser.add_argument("--verbose", help="Enable verbose mode", action="store_true")
    parser.add_argument("-verbose", help="Enable verbose mode", action="store_true")
    parser.add_argument("-v", help="Enable verbose mode", action="store_true")
    parser.add_argument("--v", help="Enable verbose mode", action="store_true")
    
    args = parser.parse_args()
    if args.verbose or args.v:
        args.debug = True
    
    csa = CSA_Abstracted(args.chip, args.device, args.polarity, args.settings, args.debug, args.test_type, args.comments, args.no_clk, args.clk_speed)


if __name__ == '__main__':
    main()
# region Import necessary libraries
import pdb
import argparse
import time
from dataclasses import dataclass, asdict
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


sys.path.append(getcwd())
from SourceScripts.masks import Masks
from SourceScripts.digital_pattern import DigitalPattern
from SourceScripts.settings_util import SettingsUtil
from SourceScripts.debug_util import DebugUtil

class TDMSWaveformException(Exception):
    """Exception produced by the TDMSWaveform class"""
    def __init__(self, msg):
        super().__init__(f"TDMSWaveform: {msg}")

@dataclass
class TestMetadata:
    date: str
    time: str
    chip: str
    device: str
    polarity: str
    test_type: str
    additional_info: str

class TDMSWaveform:
    def __init__(
            self,
            chip,
            device,
            polarity = "NMOS",
            settings = "settings/TDMS_Wavform.toml",
            test_type = "Debug",
            additional_info = "",
            waveform_files = [],
            max_cycles = 100,
            debug = False
            ):
        
        self.dbg = DebugUtil(debug)
        self.dbg.start_function_debug(debug)

        # Flag for indicating if conenciton to ni session is open
        self.closed = True
        self.MAX_CYCLES = max_cycles
        # Initialize settings
        self.initialize_settings(settings, debug)
        self.define_test_metadata(chip, device, polarity, test_type, additional_info)
        self.initialize_logging_file(debug)

        print("TDMSWaveform object created")
        time.sleep(1)

    # region Setup Program
    def initialize_settings(self, settings,debug = None):
        """
        Initialize Settings:
        - Load settings as a dictionary, either from input or from file
        - Convert NIDigital spec paths to absolute paths

        Args: 
        settings (Union[dict, str]): The settings data as a dictionary or the path to a TOML file.
        debug (bool): Flag to enable debug printouts
        """

        self.dbg.start_function_debug(debug)

        # Load settings utility object, settings dictionary, and settings path 
        # from either settings dictionary or toml filepath
        self.settings_manager = SettingsUtil(settings)
        self.settings = self.settings_manager.settings
        self.settings_path = self.settings_manager.settings_path

        # Convert NIDigital spec paths to absolute paths
        self.settings["NIDigital"]["specs"] = [abspath(path) for path in self.settings["NIDigital"]["specs"]]

        # If TDMS Waveform files are listed in settings, convert them to absolute paths
        if "Waveform" in self.settings and "files" in self.settings["Waveform"]:
            self.settings["Waveform"]["files"] = [abspath(path) for path in self.settings["Waveform"]["files"]]

        self.dbg.end_function_debug()
    
    def define_test_metadata(self, chip, device, polarity, test_type, additional_info):
        """
        Define Test Metadata:
        - Define the metadata for the test based on the input parameters

        Args:
        chip (str): The chip name
        device (str): The device name
        polarity (str): The polarity of the device (NMOS or PMOS)
        test_type (str): The type of test being run
        additional_info (str): Additional information about the test
        """

        # Set current date and time
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        # Define the test metadata
        self.test_metadata = TestMetadata(
            date = current_date,
            time = current_time,
            chip = chip,
            device = device,
            polarity = polarity,
            test_type = test_type,
            additional_info = additional_info
        )

    def initialize_logging_file(self, debug = None):
        """
        Initialize Logging:
        - Initialize TDMS Waveform logging

        Args:
        debug (bool): Flag to enable debug printouts
        """
        self.dbg.start_function_debug(debug)
        
        # Set data log based on chip, device, test type, and additional info
        test = self.test_metadata
        hash = self.update_data_log(test.date, test.time, f"chip_{test.chip}_test_{test.device}", test.test_type, test.additional_info)

        # Set datafile path based on test and logfile hash
        self.datafile_path = self.settings["path"]["data_header"] + f"/{test.test_type}/{test.date}_{test.chip}_{test.device}_{hash}.csv"

        self.file_object = open(self.datafile_path, "a", newline='')
        self.datafile = csv.writer(self.file_object)

        for key,value in zip(asdict(self.test_metadata).keys(), asdict(self.test_metadata).values()):
            self.datafile.writerow([key, value])
        
        self.datafile.writerow("")

        timestamps = [f"T{i}" for i in range(1, 2*self.MAX_CYCLES + 1)]
        self.datafile.writerow(["Waveform","R/W/RW"]+timestamps)

        self.dbg.end_function_debug()

    def update_data_log(self, date, time, filename, location, notes,debug=None):
        
        """
        Update the CSV with information on what files were written to,
        what information they contained, and where they are stored.
        The function then returns an incrementing identifier (####)
        that resets each day.
        """

        self.dbg.start_function_debug(debug)

        # Path to the CSV file
        test_log_path = self.settings["path"]["test_log_file"]

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
        self.dbg.end_function_debug()
        return last_hash
    


# endregion

    # region Setup Device
    def load_session(self,debug = None):  
        self.dbg.start_function_debug(debug)
        
        # Load NIDigital session

        self.digital_patterns = DigitalPattern(self.settings_manager)
        self.digital = self.digital_patterns.sessions

        self.digital_patterns.digital_all_pins_to_zero()
        self.digital_patterns.commit_all()

        self.dbg.end_function_debug()
    # endregion

    def get_waveform_data(self, waveform_files,debug = None):
        """
        Get Waveform Data:
        - Load the waveform data from the input files

        Args:
        waveform_files (List[str]): List of paths to the waveform files
        debug (bool): Flag to enable debug printouts
        """

        self.dbg.start_function_debug(debug)

        # If waveform files are not provided, use the files from settings
        if not waveform_files:
            self.waveform_files = self.settings["Waveforms"]["files"]

        self.dbg.end_function_debug()


    def write_waveform_from_file(self,debug = None):
        self.dbg.start_function_debug(debug)

        self.digital_patterns.define_waveforms_from_files(self.files)
        self.digital_patterns.broadcast_waveforms()
       
        self.dbg.end_function_debug()


    # region close and del functions
    def close(self):
        """
        Close the TDMSWaveform object:
        - Close the logging file
        - Close the NI Digital session
        """
        self.file_object.close()
        self.dbg.end_function_debug()

    def __del__(self):

        if not self.closed:
            self.close()
        self.dbg.end_function_debug()

# endregion
  

if __name__ == '__main__':
    test_setup = TDMSWaveform("testchip", "testdevice", settings="settings/MPW_Direct_Write.toml",waveform_files=[],test_type="Debug", debug=False)
    test_setup.load_session()
    test_setup.get_waveform_data([])
    test_setup.write_waveform_from_file()
    print("Done")
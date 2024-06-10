import argparse
import nidigital
import pdb
import time
from os import getcwd
from os.path import abspath
from sys import path
import numpy as np
import tomli
from datetime import date, datetime

path.append(getcwd())
import SourceScripts.load_settings as load_settings
from masks import Masks
from digital_pattern import DigitalPattern
from BitVector import BitVector

class CSAException(Exception):
    """Exception produced by the Current Sense Amp Testing class"""
    def __init__(self, msg):
        super().__init__(f"CSA: {msg}")

class CSA:
    def __init__(
            self,
            chip,
            device,
            polarity = "NMOS",
            settings = "settings/csa_test.toml",
            debug_printout = False,
            test_type = "Default",
            additional_info = ""
        ):

        # region CSA class variables
        self.chip = chip
        self.device = device
        self.polarity = polarity
        self.settings = settings
        self.debug_printout = debug_printout
        self.test_type = test_type
        self.additional_info = additional_info
        # endregion

        self.verify_init()
        
        try:
            self.settings = load_settings.load_settings(self.settings)
        except:
            raise CSAException(f"Could not load settings file {self.settings}")


        # Convert NIDigital spec paths to absolute paths
        settings["NIDigital"]["specs"] = [abspath(path) for path in settings["NIDigital"]["specs"]]
        

        # flag for indicating if connection to ni session is open
        self.closed = True

        pass

    def verify_init(self):
        if self.polarity.upper() not in ["NMOS","PMOS","N","P"]:
            raise CSAException("Invalid polarity: {self.polarity} must be 'NMOS' or 'PMOS'")
        
        if self.test_type not in self.settings["test_types"]:
            raise CSAException(f"Invalid test type: {self.test_type} not in {self.settings['test_types']}")

    def init_measurement_log(self):
        # Initialize CSA logging
        self.mlogfile = open(self.settings["path"]["master_log_file"], "a")
        self.plogfile = open(self.settings["path"]["prog_log_file"], "a")
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

    def setup_device():
        pass

    def alter_settings():
        pass  

    def print_waveform():
        pass

    def col_sel_idx_bls():
        pass

    def set_and_source_voltage():
        pass

    def measure_iv():
        pass

    def CSA_read():
        pass

    def build_CSA_read_waveform():
        pass

    def interpret_CSA():
        pass

def main():
    pass
        
if __name__ == "__main__":
    main()



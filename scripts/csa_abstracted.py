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
from SourceScripts.settings_util import SettingsUtil
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
            clock_speed = 2.5e6,
            measure_iv = False,
            relayed = True,
            sweep = True,
            measure_inputs = True,
            measurement_number = 1,
            measurement_interval = 5e-5,
            send_to_terminal = True
            ):
        
        # Define the debug utility
        self.dbg = DebugUtil(debug)
        self.dbg.start_function_debug(debug)
        
        # Set a flag for ni session connection
        self.connection_closed = True
       
        # region Set the class variables
        self.chip = chip
        self.device = device
        self.polarity = polarity
        self.debug = debug
        self.test_type = test_type
        self.additional_info = additional_info

        self.clock_enable = clock_enable
        self.clock_speed = clock_speed
        
        self.relayed = relayed
        self.measure_iv = measure_iv
        self.sweep = sweep
        self.measure_inputs = measure_inputs

        self.measurement_number = measurement_number
        self.measurement_interval = measurement_interval
        self.send_to_terminal = send_to_terminal
        # endregion
        
        # Load the settings file
        settings, settings_filepath, settings_manager = self.load_settings_file(settings)
        
        # Set the Sense Amp Circuit based on given polarity and Col-Sel
        self.define_csa_circuit()

        self.dbg.operation_debug("Setting", ["Chip", "Device", "Polarity", "Settings", "Debug", "Test Type", "Additional Info", "Clock Enable", "Clock Speed"], [self.chip, self.device, self.polarity, self.settings_path, self.debug, self.test_type, self.additional_info, self.clock_enable, self.clock_speed])

        self.pins = self.settings["pins"]

        # Start Sessions
        self.start_sessions()

        # Define Session I/O
        self.input_pins, self.input_values, self.output_pins = self.define_io()

        # Load the log file to store data
        self.init_log_file()

        # Configure the digital pattern for reading
        self.digital_patterns.configure_read()

        # Set non-sourced pins to VTERM
        self.set_pins()

        pdb.set_trace()

        # Set the clock
        self.set_clock(speed=self.clock_speed)
        pdb.set_trace()
        # set enable and disable signals
        self.digital_patterns.ppmu_set_voltage(pins=list(self.settings["pins"]["enable"].keys()), voltage_levels=list(self.settings["pins"]["enable"].values()), source=True, debug=debug)
        self.digital_patterns.ppmu_set_voltage(pins=list(self.settings["pins"]["disable"].keys()), voltage_levels=list(self.settings["pins"]["disable"].values()), source=True,debug=debug)
        

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
        self.settings_manager = SettingsUtil(settings)
        self.settings = self.settings_manager.settings
        self.settings_path = self.settings_manager.settings_path
        
        self.settings["NIDigital"]["specs"] = [abspath(path) for path in self.settings["NIDigital"]["specs"]]

        self.op = self.settings["op"]
        
        # Set the relay up if relayed is True
        if self.relayed:
            self.relays = self.settings["NISwitch"]["deviceID"]

        self.dbg.end_function_debug()
        
        return self.settings, self.settings_path, self.settings_manager


    def define_csa_circuit(self, debug=None):
        """
        Define CSA Circuit: Define the CSA circuit including
        Number of CSAs and the bitlines being set based on Col Select
        """
        
        self.dbg.start_function_debug(debug)
        
        # Define the number of sense amps based on the device polarity
        self.set_n_csas()

        # Define the bitlines read to by column select
        self.device_loc = list(self.settings["pins"]["device"].keys())
        self.col_sel = [val for val in self.device_loc if val in self.settings["pins"]["COL_SEL"]][0]
        self.col_sel_idx = int(text_after(self.col_sel, "COL_SEL_"))
        self.bls = self.set_col_sel_idx_bls(self.col_sel_idx, self.n_csas)

        return self.n_csas, self.bls

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
   

    def start_sessions(self,debug=None):
        """
        Start Sessions: Start the NI Digital and NI System sessions

        Returns:
        None
        
        """
        self.dbg.start_function_debug(debug)
        
        # Start the NI Digital session
        self.digital_patterns = DigitalPattern(self.settings)
        self.digital = self.settings["NIDigital"]

        self.digital_patterns.configure_read()
        self.digital_patterns.commit_all()
        self.start_time = time.time_ns()
        self.dbg.end_function_debug()

    def set_pins(self, pins=None,debug=None):
        """
        Set Pins to Vterm: Set the pins to Vterm

        Args:
        pins (list): List of pins to set to Vterm

        Returns:
        None
        
        """
        
        self.dbg.start_function_debug(debug)
        
        self.digital_patterns.set_channel_termination_mode()

        if pins is None:
            pins = list(self.pins["output"].keys()) + self.settings["pins"]["SL"] + self.settings["pins"]["BL"]

        
        self.digital_patterns.set_channel_termination_mode(mode="Vterm", pins=pins)

    def set_clock(self, enable=None, speed=None,debug=None):
        """
        Set Clock: Set the clock for the test

        Args:
        enable (bool): Enable the clock
        speed (float): Clock speed in Hz

        Returns:
        None
        
        """

        self.dbg.start_function_debug(debug)
        
        enable = self.clock_enable if enable is None else enable
        speed = self.clock_speed if speed is None else speed

        if enable:
            self.digital_patterns.set_clock(frequency=speed)
        
        self.dbg.end_function_debug()

    def set_sources(self, sources=None, levels=None):
        if sources is None:
            sources = self.input_pins

        # sources = self.fix_wls_for_2571(sources)

        if levels is None:
            levels = self.input_values
        
        self.digital_patterns.ppmu_set_voltage(pins=sources, voltage_levels=levels,source=True)

    def define_io(self, input_pins=None, levels=None, output_pins=None, combine=True, measure_inputs=None, exclude_device_pins=False, debug=None):
        """
        Define IO: Define the input and output pins for the test

        Args:
        input_pins (list): List of input pins
        levels (list): List of levels for the input pins
        output_pins (list): List of output pins
        combine (bool): Combine provided and settings-defined pins
        read_inputs (bool): Read the input pins in addition to output pins

        Returns:
        input_pins (list): List of input pins to be driven
        levels (list): List of levels for the input pins
        output_pins (list): List of output pins to be read from, including input pins if read_inputs is True
                            If input pins are included order is [input_pins, output_pins]
                            Duplicates are removed keeping only the first instance of the pin
        """

        self.dbg.start_function_debug(debug)

        # Get the input and output pins from the settings
        self.input = self.pins["input"]
        self.output = self.pins["output"]

        measure_inputs = self.measure_inputs if measure_inputs is None else measure_inputs

        # Set input pins that will be driven
        if input_pins is None:
            input_pins = list(self.input.keys())
            input_levels = [self.input[pin] for pin in input_pins]
        elif combine:
            input_pins = input_pins + list(self.input.keys())
            input_levels = input_levels + [self.input[pin] for pin in list(self.input.keys())]
        
        if not exclude_device_pins:
            input_pins = input_pins + self.device_loc
            input_levels = input_levels + [self.settings["pins"]["device"][pin] for pin in self.device_loc]
        
        if len(input_pins) != len(input_levels):
            raise CSAException("Number of input pins and levels do not match")

        # Set output pins that will be read from
        if output_pins is None:
            output_pins = list(self.output.keys())
        elif combine:
            output_pins = output_pins + list(self.output.keys())
        
        if measure_inputs:
            output_pins = input_pins + [pin for pin in output_pins if pin not in input_pins]

        # Verify each of the pins exist
        all_pins = input_pins + output_pins
        all_pins = self.fix_wls_for_2571(all_pins)
        all_pins = self.digital_patterns.sort_pins(all_pins)
        
        self.dbg.end_function_debug()

        return input_pins, input_levels, output_pins

    def source_and_measure(self, sweep=None, zero_after=True, debug=None):
        """
        Source and Measure: Source the pins and measure the results
        """
        self.dbg.start_function_debug(debug)

        if sweep is None:
            sweep = self.sweep

        if sweep:
            self.inputs= [pin for pin in self.input_pins if pin not in self.settings["pins"]["sweep"]]
            v_set = self.pins["sweep"]
        
        else: #Define a range using the first input so we can reuse sweep code
            v_set = {self.input_pins[0]: [self.input_values[0],self.input_values[0]+0.01, 0.02]}
            self.inputs = self.input_pins[1:]

        sweep_pins = list(v_set.keys())
        sweep_values = list(v_set.values())
        measurement_name = "V" if not self.measure_iv else "I/V"
        
        # Initialize all set/measurement values for input_pins and output_pins {pin: [set, measure I, measure V]}
        # All pins that are not input are set at 0
        v_set_keys = self.input_pins + self.output_pins if not self.measure_inputs else self.output_pins
        output_list_dict = {key:[0,0,0] for key in v_set_keys}
        output_list_dict.update({key:[self.input_values[i],0,0] for i,key in enumerate(self.input_pins)})

        self.inputs = self.fix_wls_for_2571(self.input_pins)
        self.outputs = self.fix_wls_for_2571(self.output_pins)
        self.set_sources(sources=self.inputs, levels=self.input_values)
        

        for sweep_pins, sweep_values in zip(sweep_pins, sweep_values):
            for val in np.arange(float(sweep_values[0]), float(sweep_values[1]), float(sweep_values[2])):
                self.digital_patterns.ppmu_set_voltage(pins=sweep_pins, voltage_levels=[val])
                output_list_dict.update({sweep_pins:[val,0,0]})
                for i in range(self.measurement_number):
                    t = time.time_ns() - self.start_time
                    v_data = self.digital_patterns.measure_voltage(pins=self.outputs)
                    i_data = self.digital_patterns.measure_current(pins=self.outputs) if self.measure_iv else [[0]*len(self.outputs)]*3

                    output_list_dict.update({key:[output_list_dict[key][0],i_data[2][i],v_data[2][i]] for i,key in enumerate(self.output_pins)})
                    if self.measure_iv:
                        value_list = [item for sublist in output_list_dict.values() for item in sublist]  
                    else:
                        value_list = [item for sublist in output_list_dict.values() for item in sublist if sublist.index(item)%3 != 1]
                    
                    line = [t/1e9, self.chip, self.device, self.polarity, measurement_name] + value_list
                    self.write_data_line(line)
                    
                    time.sleep(self.measurement_interval)
                    
                    if self.send_to_terminal:
                        print(v_set)
                        print(v_data[1])

        if zero_after:
            self.digital_patterns.ppmu_set_voltage(pins=self.inputs, voltage_levels=[0]*len(self.inputs), source=True)



        self.dbg.end_function_debug()
        return 0 

        

    def print_waveform(self, results_dict, bl_idxs, polarity="NMOS", debug=None):
        """
        Print Waveform: Print the waveform for the given results dictionary
        and bitline indices. The function prints the SA_RDY and DO signals

        Args:
        results_dict (dict): Dictionary containing the results of the test
        bl_idxs (list): List of bitline indices to print
        polarity (str): Polarity of the device (default: "NMOS")
        """
        # Beginning function debug print
        self.dbg.start_function_debug(debug)

        
        for wl_name in results_dict:
            print("Waveform: ", wl_name)
            for idx,_ in enumerate(bl_idxs):
                sa_rdy_waveform = [int(x[f"SA_RDY_{idx}"]) for x in results_dict[wl_name]]
                do_waveform = [int(x[f"DO_{idx}"]) for x in results_dict[wl_name]]
                print(f"SA_RDY_{idx}:\t{sum(sa_rdy_waveform)}")
                print(f"DO_{idx}:\t\t{sum(do_waveform)}")

        # End function debug
        self.dbg.end_function_debug()

        return 0

    def fix_wls_for_2571(self,pins,relayed=None, debug=None):
        """
        Fix WLs for 2571: Fix the WLs for the 2571 CSA

        Args:
        wls (list): List of WLs to fix

        Returns:
        list: Fixed list of WLs
        
        """
        
        # Start function debug
        self.dbg.start_function_debug(debug)

        # Check for relayed override
        if relayed is None: relayed = self.relayed
        
        # If not relayed, return just pins
        if not relayed:
            self.dbg.end_function_debug()
            return pins

        # If relatd, switch the relays and return the modified signal    
        return_pins = []
        for pin in pins:
            if pin in self.settings["pins"]["WL"]:
                return_pins.append(self.relay_switch(pin)[0])
            else:
                return_pins.append(pin)
        
        self.dbg.end_function_debug()
        return return_pins



    def relay_switch(self, wls, relayed=True, debug = None):
        """
        Relay switch, switch relays and return modified WL signal

        Args:
        wls (list): List of WLs to switch
        relayed (bool): Relay the WLs

        Returns:
        list: Modified list of WLs
        """

        # Start function debug
        self.dbg.start_function_debug(debug)

        # Check for a single wordline, if so, convert to list to match formatting
        if type(wls) is not list:
            wls = [wls]
        
        # Check that the WLs are valid
        for wl in wls: 
            assert(wl in self.settings["pins"]["WL"]), f"Invalid WL channel {wl}: Please make sure the WL channel is in the all_WLS list."
        
        # If no relays are found, raise an exception
        if self.relays is None:
            raise CSAException("Relay card not found in settings.")


        sorted_wls = []
        
        for i,_ in enumerate(self.relays):
            # Sort the WL channels by relay 0-65 for relay 1, 66-131 for relay 2, (sending 0-65 for each relay)
            sorted_wls.append([(int(wl[3:])-66*i) for wl in wls if int(wl[3:])//66 == i])        

        wl_input_signals = [f"WL_IN_{int(wl[3:])%24}"for wl in wls] 
        
        # Switch the relays at the given WL channels, separated by relay.
        if relayed:
            self.digital_patterns.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug)
        
        
        self.dbg.end_function_debug()
        
        return wl_input_signals

    """ ====================================================== """
    """ Util Functions for Bookkeeping, Debugging, and Logging """
    """ ====================================================== """
    # region
    def write_data_line(self, line:list, debug=None): 
        """
        Update Data Log: Update the data log with the given line

        Args:
        line (list): List of data to write to the log
        """
        
        # Start function debug
        self.dbg.start_function_debug(debug)
        
        # Write the line to the csv data log
        with open(self.datafile_path, "a", newline='') as file_object:
            datafile = csv.writer(file_object)
            datafile.writerow(line)

        self.dbg.end_function_debug()


    def init_log_file(self, debug=None):
        """
        Initialize Log File: Initialize the log file for the test
        """
        # Start function debug
        self.dbg.start_function_debug(debug)

        # Get the current date and time
        current_date = date.today().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        # Set a number for the file to reference in test_log.csv
        hash = self.update_data_log(current_date, current_time, f"chip_{self.chip}_device_{self.device}", self.test_type, self.additional_info)
        
        # Define the new datafile path
        self.datafile_path = self.settings["path"]["data_header"] + f"/{self.test_type}/{current_date}_{self.chip}_{self.device}_{hash}.csv"

        # If debug is enabled, print the datafile path
        self.dbg.operation_debug("Setting", ["Date", "Time", "Filename", "Location", "Notes"], [current_date, current_time, f"chip_{self.chip}_device_{self.device}", self.test_type, self.additional_info])

        # Write the datafile header, [Time, Chip_ID, Device_ID, Polarity, Measurement, {Set V, measured I,measured V} for each source if measure_IV otherwise {Set V, measured V}]
        with open(self.datafile_path, "a", newline='') as file_object:
            datafile = csv.writer(file_object)
            if self.measure_iv:
                title_row_source_names = [[f"{source} Set V", f"{source} I", f"{source} V"]  for source in self.output_pins]
                title_row_source_names = [item for sublist in title_row_source_names for item in sublist]               
                datafile.writerow(["Time", "Chip_ID", "Device_ID", "Polarity","Measurement"]+title_row_source_names)
            else:
                title_row_source_names = [[f"{source} Set V", f"{source} V"]  for source in self.output_pins]
                title_row_source_names = [item for sublist in title_row_source_names for item in sublist]
                datafile.writerow(["Time", "Chip_ID", "Device_ID", "Polarity","Measurement"]+title_row_source_names)
        
        # End function debug
        self.dbg.end_function_debug()
        return 0

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

        # Return 
        # the updated identifier
        return last_hash

   

    # endregion



    """ ====================================================== """
    """                    CSA Test Cleanup                    """
    """ ====================================================== """
    # region

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
        

    # endregion

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
    
    if args.verbose or args.v:
        args.debug = True

    return args

def main(args, iv_measurement=False):
    csa = CSA_Abstracted(args.chip, args.device, args.polarity, args.settings, args.debug, args.test_type, args.comments, args.no_clk, args.clk_speed, args.measure_iv, sweep=args.no_sweep, measure_inputs=args.no_input_measurement, measurement_number=int(args.measurement_number), measurement_interval=float(args.measurement_interval), send_to_terminal=args.print)
    
    iv_measurement = args.measure_iv or iv_measurement
    csa.source_and_measure()



if __name__ == '__main__':
    args = arg_parse()
    main(args)
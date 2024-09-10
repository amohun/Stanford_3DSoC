# region Import Libraries
import numpy as np
import sys
from os import getcwd
import os
import nidigital
import niswitch
import nitclk
from BitVector import BitVector
from itertools import chain
import time
import pdb

sys.path.append(getcwd())
from SourceScripts.settings_util import SettingsUtil
from SourceScripts.masks import Masks
from SourceScripts.string_util import *
from SourceScripts.debug_util import DebugUtil
from scripts.excel_arbitrary_data import ExcelInterface
from SourceScripts.digital_pattern import DigitalPattern
# endregion

class ExcelPatternException(Exception):
    """Exception produced by the ExcelPattern class"""
    def __init__(self, msg):
        super().__init__(f"ExcelPattern: {msg}")

class ExcelPattern:
    
    def __init__(self, excel_file, settings_file=None, debug=False):
        self.debug = debug
        self.dbg = DebugUtil(self.debug)
        
        self.excel_file = excel_file
        self.settings = settings_file

        self.patterns = []
        self.debug = False
        self.dbg = DebugUtil(self.debug)
        self.dbg.start_function_debug(self.debug)
        self.load_file(self.excel_file)
        self.load_settings(self.settings)

    def load_file(self, file=None):
        if file is None:
            file = self.excel_file

        self.file = ExcelInterface(file)

    def define_frequency(self, frequency=None, period=None):
        if frequency is not None:
            self.frequency = float(frequency)
            return 0
        if period is not None:
            self.frequency = 1/float(period)
            return 0
        
        frequency_keywords = ['frequency', 'clk_frequency', 'freq', 'clk_freq','f', 'clk_f']
        period_keywords = ['period', 'clk_period', 'T', 'clk_T']
        
        for keyword in frequency_keywords:
            self.frequency = self.file.find_keyword_value(keyword)
            if self.frequency is not None:
                break
        if self.frequency is None:
            for keyword in period_keywords:
                period = self.file.find_keyword_value(keyword)
                if period is not None:
                    self.frequency = 1/float(period)
                    break
        if self.frequency is None:
            raise ExcelPatternException("Frequency not found in Excel file")

    def get_channels_from_excel_file(self, keywords=None, debug=None):
        """ =============================================== """
        """ Get Channels from Excel File                    """
        """ Searches for channels in the Excel file based  """
        """ on the provided keywords. Returns a dictionary  """
        """ of the channels found in the Excel file         """
        """ =============================================== """
        """ Inputs:                                         """
        """ keywords: List of keywords to search for in the """
        """ Excel file to find the channels                 """
        """                                                 """
        """ Outputs:                                        """
        """ Dictionary of channels found in the Excel file  """
        """ =============================================== """
        
        self.dbg.start_function_debug(debug)
        # Ensure the keywords are provided
        if keywords is None:
            raise ExcelPatternException("No keywords provided to search for channels")
        
        # Check if the channels are provided
        for keyword in keywords:
            channel_rows = self.file.get_rows_between_keyword_and_empty(keyword)
            if channel_rows is not None and channel_rows is not []:
                break
        
        # If channels are not provided, default to no channels in dictionary
        if channel_rows is None or channel_rows is []:
            print(f"{keywords} channels not found in Excel file")
            print(f"Defaulting to no channels related to {keywords}")
            
            # Return an empty dictionary
            self.dbg.end_function_debug()
            return dict({})
        
        else:
            # Return the channels as a dictionary
            self.dbg.end_function_debug()
            return self.file.rows_to_dict(channel_rows)
        

    def define_enable_and_disable_signals(self, enable=None, disable=None, from_toml=False):
        """ =============================================== """
        """ Define Enable and Disable Signals               """
        """ Makes a dictionary of enable and disable signals"""
        """ Checks file and function arguments for signals"""
        """ Inputs:                                         """
        """ enable: List of enable signals to add to xlsx   """
        """ disable: List of disable signals ro add to xlsx """
        """ from_toml: If True, use signals from toml file  """
        """ =============================================== """
        
        # Define Enable and Disable Keywords (All rows between keyword and empty row enabled/disabled)
        enable_keywords = ['enable', 'en', 'on']
        disable_keywords = ['disable', 'dis', 'off']
        
        self.enable = self.get_channels_from_excel_file(enable_keywords)
        self.disable = self.get_channels_from_excel_file(disable_keywords)


    def define_waveforms(self, keyword=None, add_channels:list=None, remove_channels:list=None):
        waveform_keywords = ['waveforms', 'waveform', 'patterns', 'pattern']
        
        if keyword is not None:
            if isinstance(keyword, str):
                waveform_keywords = [keyword]
        
        self.patterns = self.get_channels_from_excel_file(waveform_keywords)

        if add_channels is not None:
            for channel in add_channels:
                self.patterns[channel] = self.file.find_keyword_all_right(channel)
        
        if remove_channels is not None:
            for channel in remove_channels:
                self.patterns.pop(channel, None)
        
        self.channels = list(self.patterns.keys())
        self.waveforms = list(self.patterns.values())
    
    def convert_waveforms_to_bool(self):
        self.patterns_b = {}
        for key in self.patterns.keys():
            self.patterns_b[key] = [bool(int(x)) for x in self.patterns[key]]
            self.waveforms_b = list(self.patterns.values())

    
    # ================================ #
    # Load Digital Pattern Instrument  #
    # ================================ #
    def load_settings(self, settings):
        """
        Load Settings:
        Uses the SettingsUtil class to load settings from a TOML file or dictionary.

        Args:
            settings (Union[dict, str]): The settings data as a dictionary or the path to a TOML file.
        """
        
        # Define the settings manaager 
        self.settings_manager = SettingsUtil(settings)

        # Load the settings
        self.settings = self.settings_manager.settings

        #Define the settings path
        self.settings_path = self.settings_manager.settings_path

    def load_session(self):
        """
        Load Session:
        Load the NIDigital Session from the SettingsUtil class
        Keeps the settings file and path in case changes are needed
        """
        # Verify settings are loaded, can be removed if load_settings is in the init.
        self.dbg.start_function_debug()
        
        # Load the NIDigital Session
        self.pattern = DigitalPattern(self.settings_manager)
        self.relays = self.settings_manager.get_setting("NISwitch.deviceID")
        
        self.dbg.end_function_debug()
    
    def relay_switch(self, wls, relayed=True, debug = None):
        if debug is None: debug = self.debug

        for wl in wls: 
            assert(wl in self.all_wls), f"Invalid WL channel {wl}: Please make sure the WL channel is in the all_WLS list."
        
        if self.relays is None:
            raise ExcelPatternException("Relay card not found in settings.")

        num_relays = len(self.relays)

        sorted_wls = []
        
        for i in range(num_relays):
            # Sort the WL channels by relay 0-65 for relay 1, 66-131 for relay 2, (sending 0-65 for each relay)
            sorted_wls.append([(int(wl[3:])-66*i) for wl in wls if int(wl[3:])//66 == i])        

        wl_input_signals = [f"WL_IN_{int(wl[3:])%24}"for wl in wls] 
        
        # Switch the relays at the given WL channels, separated by relay.
        if relayed:
            self.pattern.connect_relays(relays=self.relays,channels=sorted_wls,debug=debug)
        all_wls = self.settings["device"]["WL_SIGNALS"]
        return wl_input_signals, all_wls
    
    
    def create_all_off_masks(self):
        """
        Create Session Masks:
        Create the masks for the NIDigital Session
        """
        self.dbg.start_function_debug()
        
        session_masks = []
        for session, session_names in zip(self.pattern.pingroup_data, self.pattern.pingroup_names):
            group_masks = []
            for group, names in zip(session,session_names):
                group_mask = {names: np.array([False]*len(group))}
                group_masks.append(group_mask)
            session_masks.append(group_masks)
        
        self.dbg.end_function_debug()
        return session_masks

       
    def create_masks(self):
        """
        Create Masks:
        Create the masks for the NIDigital Session
        """
        self.dbg.start_function_debug()
        
        waveform_masks = []
        for time in range(len(self.patterns_b.values())):
            step_mask = self.create_all_off_masks()
            for session in step_mask:
                for group in session:
                    for channel in group.keys():
                        if channel in self.patterns_b.keys():
                            group[channel] = self.patterns_b[channel][time]
            print(step_mask)
            waveform_masks.append(step_mask)
        print(waveform_masks)
        
        self.dbg.end_function_debug()
        return waveform_masks

if __name__ == '__main__':
    file = 'scripts/ArbitraryTestbench.xlsx'
    settings = "settings/MPW_Arbitrary_Test.toml"
    file = os.path.abspath(file)
    excel_pattern = ExcelPattern(excel_file=file, settings_file=settings)
    excel_pattern.load_file()
    excel_pattern.define_frequency()
    excel_pattern.define_waveforms()
    excel_pattern.convert_waveforms_to_bool()
    excel_pattern.define_enable_and_disable_signals()
    print("---------------------------------------------------------")
    print(excel_pattern.patterns)
    print(excel_pattern.frequency)
    print(excel_pattern.patterns_b)
    print(excel_pattern.enable)
    print(excel_pattern.disable)
    excel_pattern.load_session()
    print(excel_pattern.pattern.all_pins)
    excel_pattern.create_all_off_masks()
    excel_pattern.create_masks()
    print('Done')
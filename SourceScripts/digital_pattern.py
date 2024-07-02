""" ---------------------------------------------------------------- """
""" The DigitalPattern Class that controls the instrument drivers.   """
"""  This class has fewer functions than the original NIRRAM class   """
"""  but is more general. It can be used with any NI Digital Pattern """
"""  for any sessions using NiTClk, NiDigital, and NiSwitch          """
"""  --------------------------------------------------------------  """
"""  The class is designed to be used with the NI PXIe-6570/1 cards  """
"""  and the NI PXIe-2527 relay cards. Given the following:          """
"""    - Each session uses a single instrument                       """
"""    - pin_maps are specified in the same order for the sessions   """
""" ---------------------------------------------------------------- """

# region Import Libraries
import numpy as np
import sys
from os import getcwd
import nidigital
import niswitch
import nitclk
from BitVector import BitVector
from itertools import chain
import time
import pdb

sys.path.append(getcwd())
import SourceScripts.load_settings as load_settings
import SourceScripts.masks as masks
from SourceScripts.string_util import *
from SourceScripts.debug_util import DebugUtil
# endregion

class DigitalPatternException(Exception):
    """Exception produced by the DigitalPattern class"""
    def __init__(self, msg):
        super().__init__(f"DigitalPattern: {msg}")

class DigitalPattern:

    def __init__(
            self,
            settings="settings\default.toml",
            debug=False,
        ):

        if type(settings) is not dict:
            self.settings = load_settings.load_settings(settings)
        else:
            self.settings = settings
        settings = self.settings
        if "op" in settings:
            self.op = settings["op"]
        
        self.dbg = DebugUtil(debug)

        self.load_instruments()
        self.load_pin_maps()
        self.load_patterns()
        self.configure_timing()
        self.load_level_and_timing()
        self.ppmu_set_pins_to_zero()
        self.set_current_limit_range(self.all_pins, 2e-6, pin_sort=False)
        self.set_power(ignore_empty=True)

    """ ================================================= """
    """      Loading and Initialization of Functions      """
    """ ================================================= """
    # region    
    def load_instruments(self, instruments=None, debug=None):
        """
        Load instrument sessions based on provided settings.
        Initializes sessions for NiDigital and NiSwitch devices specified in settings.

        For NiDigital:
            - Creates a session for each device ID.
            - Sets sync flag to True if multiple devices are provided.
            - Raises ValueError if deviceID not found in settings.
        For NiSwitch:
            - Initializes session for specified device ID.
            - Raises ValueError if deviceID not found in settings.
        """
        self.relays = None
        self.sessions = None
        self.sync = False
        
        self.dbg.start_function_debug(debug)

        if instruments is None:
            try:
                # Load NiDigital sessions
                if "NIDigital" in self.settings:
                    import nidigital
                    device_ids = self.settings["NIDigital"].get("deviceID")
                    if device_ids:

                        # Ensure nidigital library if not already loaded
                        if not self.check_library_import("nidigital"):
                            import nidigital
                        
                        # Load NI Digital sessions
                        self.sessions = [nidigital.Session(device_id) for device_id in device_ids]
                        self.sync = len(self.sessions) > 1
                        
                        # Ensure nitclk library if sync is True
                        if self.sync and not self.check_library_import("nitclk"):
                            import nitclk
                    else:
                        raise ValueError("NIDigital specified but no deviceID found in settings.")
                
                # Load NiSwitch session
                if "NiSwitch" in self.settings:
                    import niswitch
                    if "deviceID" in self.settings["NiSwitch"]:

                        # Import niswitch library if not already imported
                        if not self.check_library_import("niswitch"): import niswitch

                        # Initialize session for specified device ID
                        self.relays = self.settings["NiSwitch"]["deviceID"]
                    
                    else:
                        raise ValueError("NiSwitch specified deviceID not found in settings.NiSwitch, \nPlease include a device ID for deviceID in NiSwitch")
            
            except Exception as e:
                raise ValueError(f"Error loading instruments: {str(e)}")
        
        else:
            if not isinstance(instruments, list):
                if isinstance(instruments, str):
                    instruments = instruments.split(", ")
                else:
                    raise ValueError("Instruments must be a list or a string. \nAlternatively, provide as None to load from settings toml file")
            
            self.sessions = []
            for instrument in instruments:
                if '6570' in instrument or '6571' in instrument:
                    if not self.check_library_import("nidigital"):
                        import nidigital
                    self.sessions.append(nidigital.Session(instrument))
                elif '2571' in instrument:
                    if not self.check_library_import("niswitch"):
                        import niswitch
                    self.relays = niswitch.Session(instrument)
            if len(self.sessions) > 1:
                if not self.check_library_import("nitclk"):
                    import nitclk
                self.sync = True
            elif not self.sessions:
                raise ValueError("No valid instruments provided. Please use device names with '6570', '6571', or '2571'. \nEnsure device names match those in NI MAX")

        self.dbg.end_function_debug()

    def load_pin_maps(self,sessions=None,pinmaps=None, pingroups=None, debug=None):
        """
        Load Pin Maps: Load pin maps for each session based on arguments or settings.
        Raises DigitalPatternException if pinmaps are not found in settings.

        Args:
            sessions (list): List of sessions to load pin maps for.
            pinmaps (list): List of pin maps to load for each session.
            debug (bool): Print debug information if True.
        """

        # Debug Printout
        self.dbg.start_function_debug(debug)
        
        self.dbg.debug_message("-------- Loading Pin Maps For Each Session --------")

        # If sessions and pinmaps are not provided, load from settings
        if sessions is None or pinmaps is None:
            if "NIDigital" not in self.settings:
                raise DigitalPatternException("No NIDigital settings found")
            digital = self.settings["NIDigital"]

        # Load sessions from settings if not provided and verify it is a list
        if sessions is None:
            if self.sessions is None:
                raise DigitalPatternException("No sessions provided")
            sessions = self.sessions
        if type(sessions) is not list:
            sessions = [sessions]

        # Load pinmaps from settings if not provided and verify it is a list
        if pinmaps is None:
            if "pinmap" in digital:
                pinmaps = digital["pinmap"]
            else:
                raise DigitalPatternException("No pin maps provided") 
        if type(pinmaps) is not list:
            pinmaps = [pinmaps]

        # Verify that the number of pinmaps matches the number of sessions
        if len(pinmaps) != len(sessions): 
            raise DigitalPatternException("Number of pin maps must match number of sessions")
    
        # Load pin maps for each session
        for session,pinmap in zip(sessions,pinmaps):
            session.load_pin_map(pinmap)

        # Debug Printout
        self.dbg.debug_message([f"Loading Pinmaps {pinmaps} for Sessions {sessions}","-------- Pin Maps Loaded For Each Session --------"])
        
        self.dbg.debug_message("-------- Loading Pin Groups For Each Session --------")
        
        # Define Pingroups for patterns and multi-pin operations
        self.pingroups = []

        if pingroups is None:
            if "pingroups"in digital:
                self.pingroups = digital["pingroups"]
            if "pingroup_names" in digital:
                self.pingroup_names = digital["pingroup_names"]
            if "pingroup_data" in digital: 
                self.pingroup_data = [[self.settings["device"][group] for group in session] for session in digital["pingroup_data"]]

        else: self.pingroups = pingroups

        if len(self.pingroups) == 1 and type(self.pingroups[0]) is list:
            self.pingroups = self.pingroups[0]

        # Define the pins given for each session
        self.all_pins_dict = {
            digital["deviceID"][self.sessions.index(session)]: [channel.pin_name for channel in session.get_pin_results_pin_information()]
            for session in self.sessions
        }
        
        self.all_pins = [
            [channel.pin_name for channel in session.get_pin_results_pin_information()]
            for session in self.sessions
        ]
        
        self.all_pins_flat = list(chain.from_iterable(self.all_pins))

        self.dbg.debug_message([f"Loading Pin Groups {self.pingroups} for Sessions {sessions}","-------- Pin Groups Loaded For Each Session --------"])
        self.dbg.end_function_debug()

    def load_patterns(self,patterns=None,sessions=None, debug=None):
        """
        Load Patterns: Load patterns for each session based on settings.
        Raises DigitalPatternException if patterns are not found in settings.
        
        Args:
            patterns (list): List of patterns to load. If not provided, 
            patterns are loaded from settings.
            
        """
        self.dbg.start_function_debug(debug)

        # Define the digital specifications
        digital = self.settings["NIDigital"]
        
        if sessions is None:
            sessions = self.sessions

        # Check if there are any sessions
        if sessions is not None:
            # Check if patterns are provided in settings
            if patterns is None:
                if "patterns" in digital:
                    self.patterns = digital["patterns"]
                    patterns = self.patterns
                else:
                    # Raise error if no pattern is provided
                    raise DigitalPatternException("No patterns provided")
            else:
                # Patterns are provided as an argument, use patterns provided
                if type(patterns) is str: patterns = [patterns]
                if type(patterns) is not list: raise DigitalPatternException("Patterns must be a list or a string")
                if len(patterns) != len(sessions): raise DigitalPatternException("Number of patterns must match number of sessions")
            
            for session, session_pattern in zip(sessions, patterns):
                self.dbg.debug_message(f"Loading pattern {session_pattern} for session {session}")
                session.unload_all_patterns()
                session.load_pattern(session_pattern)
                session.commit()
        else:
            raise DigitalPatternException("No sessions provided")
        
        if "pattern_names" in digital:
            self.pattern_names = digital["pattern_names"]
        else:
            self.pattern_names = [text_between(pattern,"patterns/",".digipat") for pattern in self.patterns]

        self.dbg.end_function_debug()

    def load_level_and_timing(self,sessions=None,debug = None):
        """
        Load Level and Timing:
        Load levels and timing for each session based on settings.

        Args:
            sessions (list): List of sessions to load levels and timing for.
            debug (bool): Print debug information if True
        Returns:
            None
        """

        self.dbg.start_function_debug(debug)

        digital = self.settings["NIDigital"]

        sessions = sessions or self.sessions
        if sessions is not None: 
            for session_index, session in enumerate(self.sessions):
                session_levels = digital["levels"][session_index]
                session_timing = digital["timing"][session_index]
                session_specs = digital["specs"]
                
                session.load_specifications_levels_and_timing(session_specs, session_levels, session_timing)
                session.apply_levels_and_timing(session_levels, session_timing)
                session.load_pattern

        self.dbg.end_function_debug()

    def set_power(self,pins=None,power_levels=None,sort=True,ignore_empty=False, debug=None):
        """
        Set Power: Set power levels for each session based on settings.
        Raises ValueError if power pins are not found in settings.

        Args:
            pins (list): List of pins to set power levels for.
            power_levels (list): List of power levels to set for each pin.
            sort (bool): Sort pins based on the order of the sessions.
            ignore_empty (bool): Ignore empty power pins if True.
        """

        self.dbg.start_function_debug(debug)

        if self.sessions is not None:
            if pins is None:
                device = self.settings["device"]
                if "power_pins" in device:
                    pins = device["power_pins"].keys()
                else:
                    if ignore_empty:
                        return
                    raise ValueError("Power pins not found in settings nor were they provided")
            
            if power_levels is None:
                power_levels = []
                device = self.settings["device"]
                if "power_pins" in device:
                    for pin in pins:
                        power_levels.append(device["power_pins"][pin])
                else:
                    raise ValueError("Power levels not set under power-pins in settings nor were they provided")
            
                self.ppmu_set_voltage(self,pins,power_levels,sort=False,source=True)
                self.power_pins = pins

        self.dbg.end_function_debug()

    # endregion


    """ ================================================= """
    """      Utility Functions for Digital Patterns       """
    """ ================================================= """
    # region
    def configure_timing(self,sessions=None, timing=None, debug=None):
        """
        Configure Timing: Load timing sets for each session based on settings.
        Raises DigitalPatternException if timing sets are not found in settings.
        
        Args:
            sessions (list): List of sessions to configure timing for.
            timing (list): List of timing sets to load for each session.
            debug (bool): Print debug information if True.
        """
        self.dbg.start_function_debug(debug)
        self.dbg.debug_message("-------- Configuring Timing For Each Session --------")

        # Load Timing Sets
        time_sets = self.settings["TIMING"] if timing is None else timing
        
        if sessions is None: sessions = self.sessions
        
        # Configure Timing for Each Session
        if sessions is not None:
            for condition in time_sets:
                for session in sessions:
                    session.create_time_set(condition)
                    session.configure_time_set_period(condition,time_sets[condition])
        else: 
            print("No sessions provided, timing not applied.")
        
        # Debug Printout
        self.dbg.debug_message([f"Timing Sets: {time_sets}","-------- Timing Configured For Each Session --------"])

        # Debug Printout        
        self.dbg.end_function_debug()

    def configure_read(self, sessions=None, pins=None, sort=True, debug=None):
        """
        Configure Read: Set the voltage and current levels for reading on the given sesions and pins.
            sessions: List of sessions to configure.
            pins: List of pins to configure or a list of lists of pins sorted by session.
            sort: Sort the pins based on the order of the sessions.
        """

        self.dbg.start_function_debug(debug)

        # Configure sessions and pins
        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort)

        if self.op["READ"]["mode"] == "digital":
            for session, session_pins in zip(sessions,pins):
                for pin in session_pins:
                # Configure NI-Digital current read measurements
                    session.channels[pin].ppmu_aperture_time = self.op["READ"]["aperture_time"]
                    session.channels[pin].ppmu_aperture_time_units = nidigital.PPMUApertureTimeUnits.SECONDS
                    session.channels[pin].ppmu_output_function = nidigital.PPMUOutputFunction.VOLTAGE
                    session.channels[pin].ppmu_current_limit_range = self.op["READ"]["current_limit_range"]
        else:
            raise DigitalPatternException("Invalid READ mode specified in settings")

        self.dbg.end_function_debug()


    def clear_patterns(self, debug=None):
        """
        Clear Patterns: Unload all patterns from each session.
        """

        self.dbg.start_function_debug(debug)

        if self.sessions is not None:
            for session in self.sessions:
                session.unload_all_patterns()

        self.dbg.end_function_debug()

    # endregion

    """ ================================================= """
    """      Utility Functions for Digital Channels       """
    """ ================================================= """
    # region
    def set_channel_mode(self, mode, pins=None,sessions=None,sort=True,debug=None):
        self.dbg.start_function_debug(debug)

        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort)
        
        if mode.lower() == "digital":
            for session,session_pins in zip(self.sessions,pins):
                for pin in session_pins:
                    session.channels[pin].selected_function = nidigital.SelectedFunction.DIGITAL

        elif mode.lower() == "ppmu":
            for session,session_pins in zip(self.sessions,pins):
                for pin in session_pins:
                    session.channels[pin].selected_function = nidigital.SelectedFunction.PPMU
            
        elif mode.lower() == "off":
            for session,session_pins in zip(self.sessions,pins):
                for pin in session_pins:
                    session.channels[pin].selected_function = nidigital.SelectedFunction.OFF

        elif mode.lower() == "disconnect":
            for session,session_pins in zip(self.sessions,pins):
                for pin in session_pins:
                    session.channels[pin].selected_function = nidigital.SelectedFunction.DISCONNECT
        else:
            raise ValueError("Invalid mode specified, please use 'digital', 'ppmu', 'off', or 'disconnect'")

        self.dbg.debug_message(f"Setting mode to nidigital.SelectedFunction.{mode.upper()} for pins {pins}")

        self.dbg.end_function_debug()

    def set_channel_termination_mode(self, mode="Hi-Z", pins=None,sessions=None,sort=True,debug=None):
        self.dbg.start_function_debug(debug)

        sessions,pins = self.format_sessions_and_pins(sessions,pins,sort)

        mode = mode.lower()
        mode.replace("_","-")

        if mode == "hi-z" or mode == "z" or mode == "high-z" or mode == "highz":
            for session,session_pins in zip(sessions,pins):
                session.channels[session_pins].termination_mode = nidigital.TerminationMode.HIGH_Z

        self.dbg.end_function_debug()
    # endregion

    """ ================================================= """
    """   NiDigital Sweeping and Static Voltages/Current  """
    """ ================================================= """
    # region

    # PPMU Voltage and Current Functions
    def ppmu_set(self, pins, levels, mode="voltage", sessions=None, sort=True, source=False, debug=None):
        """
        This function will set the voltage or current levels for the specified pins.  
        """

        self.dbg.start_function_debug(debug)

        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort)

        if sessions is not None:
            for session_num, session in enumerate(sessions):
                for pin, level in zip(pins[session_num], levels):
                    if mode == "voltage":
                        session.channels[pin].ppmu_voltage_level = level
                    elif mode == "current":
                        session.channels[pin].ppmu_current_level = level
        if source:
            self.ppmu_source(pins, sessions, sort=False, debug=debug)

        self.dbg.end_function_debug()
   
    def ppmu_set_voltage(self, pins,voltage_levels,sessions = None, sort=True,source=False, debug=None):
        """
        PPMU Set Voltage: Set the voltage levels for each session and pin.
        Assures that the voltage levels are within the range of -2V to 6V.

        Args:
            pins (list): List of pins to set voltage levels for.
            voltage_levels (list): List of voltage levels to set for each pin.
            sessions (list): List of sessions to set voltage levels for.
            sort (bool): Sort the pins based on the order of the sessions.
            source (bool): Source the voltage levels if True.
            debug (bool): Print debug information if True.
        """
        
        self.dbg.start_function_debug(debug)

        # Verify voltage levels are within -2V to 6V
        for v in voltage_levels:
            assert v >= -2 and v <= 6, "Voltage levels must be between -2V and 6V"
 
        # Set voltage levels for each session and pin
        self.ppmu_set(pins,voltage_levels,mode="voltage",sessions=sessions,sort=sort,source=source)

        self.dbg.end_function_debug()
        return 0

    def ppmu_set_current(self,pins,current_levels,sessions=None, sort=True, debug=None, source=False):
            """
            PPUM Set Current: Set the current levels for each session and pin.
            
            Args:
                pins (list): List of pins to set current levels for.
                current_levels (list): List of current levels to set for each pin.
                sort (bool): Sort the pins based on the order of the sessions.
                debug (bool): Print debug information if
            """
            self.dbg.start_function_debug(debug)
            
            self.ppmu_set(pins,current_levels,mode="voltage",sessions=sessions,sort=sort,source=source)

            self.dbg.end_function_debug()
            return 0

    def ppmu_source(self,pins, sessions=None, sort=True, debug=None):
        """
        PPMU Source: Source the voltage levels for each session and pin.

        Args:
            pins (list): List of pins to source voltage levels for.
            sort (bool): Sort the pins based on the order of the sessions.
            debug (bool): Print debug information if True.
        """
        self.dbg.start_function_debug(debug)
        
        if sort:
            pins = self.sort_pins(pins)
        for session,session_pins in zip(self.sessions,pins):
            session.channels[session_pins].ppmu_source()
        
        self.dbg.end_function_debug()
        return 0

    def ppmu_set_pins_to_zero(self,sessions=None,pins=None,sort=True,delay=False, ignore_power=False, ignore_clock=False, exclude_pins = [], debug=None):
        """ 
        Cleans up after PPMU operation 
        (otherwise levels default when going back digital)
        """
        self.dbg.start_function_debug(debug)

        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort)

        if ignore_power:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["power_pins"]
        
        if ignore_clock:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["clock_pins"]

        for session, session_pins in zip(sessions,pins):
            for pin in session_pins:
                if pin not in exclude_pins:
                    session.channels[pin].ppmu_voltage_level = 0
                
                if delay:
                    time.sleep(2)
            session.ppmu_source()
        
        self.dbg.end_function_debug()

        return 0


    # Digital Voltage Functions
    def digital_set_voltages(self, pins, sessions=None, vi_lo=0, vi_hi=0, vo_lo=0, vo_hi=0, sort=True, exclude_pins=None, debug=None):
        """
        Digital Set Voltages:
        Set the voltage levels for the specified pins on each session.

        Args:
            pins (list): List of pins to set voltage levels for.
            vi_lo (float): Low input voltage level.
            vi_hi (float): High input voltage level.
            vo_lo (float): Low output voltage level.
            vo_hi (float): High output voltage level.
            sort (bool): Sort the pins based on the order of the sessions.
        """
        self.dbg.start_function_debug(debug)

        # Organize voltages into list for easy iteration

        voltages = [vi_lo, vi_hi, vo_lo, vo_hi]

        # Verify voltages are lists
        for m, voltage in enumerate(voltages): 
            if type(voltage) is not list:
                voltage = [voltage]
            if len(voltage) == 1:
                voltage = voltage * len(pins)
            voltages[m] = voltage  
        
        # Verify all voltage lists are the same length
        exp_len = len(voltages[0])
        for voltage in voltages:
            if len(voltage) != exp_len:
                raise ValueError("Voltage levels must be the same length")
        # Verify all voltage lists are the same length as pins
        if len(voltages[0]) != len(pins):
            raise ValueError("Voltage levels must be the same length as pins")
        
        # Sort pins if needed
        sessions,pins = self.format_sessions_and_pins(sessions,pins,sort)

        vi_lo, vi_hi, vo_lo, vo_hi = voltages               
    
        for session,session_pins,vo_high,vo_low, vi_high, vi_low in zip(sessions,pins,vo_hi,vo_lo,vi_hi,vi_lo): 
            for pin in session_pins:
                if pin not in exclude_pins:
                    self.dbg.debug_message(f"Pin: {pin} Input Voltage: {vi_low} to {vi_high} Output Voltage: {vo_low} to {vo_high}")
                    session.channels[pin].configure_voltage_levels(vi_low, vi_high, vo_low, vo_high, 0.0)
        
        self.dbg.end_function_debug()
        
        return 0

    def digital_pins_to_zero(self,sessions=None,pins=None,  ignore_power=False, ignore_clock=False, exclude_pins = [], sort=True,keep_power=True, debug=None):
        """
        High z down to zero
        """
        self.dbg.start_function_debug(debug)

        if ignore_power:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["power_pins"]
        
        if ignore_clock:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["clock_pins"]

        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort)
        if pins == self.all_pins and len(exclude_pins)== 0:
            self.digital_all_pins_to_zero(keep_power=keep_power)
            return
        else:
            self.write_static_to_pins(sessions=sessions,pins=pins)
            self.digital_set_voltages(pins, 0, 0, sort=False, exclude_pins=exclude_pins)
        
        self.dbg.end_function_debug()
        return

    def digital_all_pins_to_zero(self, debug=None, ignore_power=False, ignore_clock=False, exclude_pins = [],):
        """
        High z down to zero
        """
        self.dbg.start_function_debug(debug)
        
        all_pins = self.all_pins
        
        if ignore_power:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["power_pins"]
        
        if ignore_clock:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["clock_pins"]

        for digital in self.sessions:
            digital.channels[self.all_pins[self.sessions.index(digital)]].write_static(nidigital.WriteStaticPinState.X)
       

        self.digital_set_voltages(all_pins, sessions=None, vi_lo=0, vi_hi=0, vo_lo=0, vo_hi=0, sort=False, exclude_pins=exclude_pins)
        
        self.dbg.end_function_debug()
        return


    # Write Static to Pins
    def write_static_to_pins(self, sessions=None, pins=None, sort=True,state='X', ignore_power=False, ignore_clock=False, exclude_pins = [], debug=None):
        
        self.dbg.start_function_debug(debug)
        
        sessions, pins = self.format_sessions_and_pins(sessions=sessions,pins=pins,sort=sort)

        if ignore_power:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["power_pins"]
        
        if ignore_clock:
            exclude_pins = exclude_pins + self.settings["NIDigital"]["clock_pins"]

        for num, session_pins in enumerate(pins):
            pins[num] = [pin for pin in session_pins if pin not in exclude_pins]

        if state == 'X':
            for session, session_pins in zip(sessions,pins):
                session.channels[session_pins].write_static(nidigital.WriteStaticPinState.X)
        elif state == '0':
            for session, session_pins in zip(sessions,pins):
                session.channels[session_pins].write_static(nidigital.WriteStaticPinState.ZERO)
        
        self.dbg.end_function_debug()

        return 0

    # Commit to all Pins
    def commit_all(self, debug=None):
        """
        NIDigital commit for all sessions
        """
        self.dbg.start_function_debug(debug)
        for session in self.sessions:
            session.commit()
        self.dbg.end_function_debug()
   
    # endregion

    """ ================================================= """
    """         NiDigital Voltage Pulse Functions         """
    """ ================================================= """
    # region

    def pulse(self, masks, pulse_lens=[50,10,50], max_pulse_len=[10_000], pulse_groups=None, sessions=None, pingroups=None, sort=True, digipat_prefix="", digipat_suffix="", patterns=None,debug=None):
        """
        A function for creating an arbitrary pulse based on given pulse groups and pulse lengths.
        The pulse is created by combining the pulse groups and pulse lengths to create a waveform.
        The waveform is then broadcasted to the given sessions and pin groups.

        Args:
            masks (list): List of masks to create waveforms for.
            pulse_lens (list): List of pulse lengths for each pulse group.
            max_pulse_len (list): List of maximum pulse lengths for each pulse group.
            pulse_groups (list): List of pulse groups to create waveforms for.
            sessions (list): List of sessions to broadcast waveforms to.
            pingroups (list): List of pin groups to broadcast waveforms to.
            sort (bool): Sort the pin groups based on the order of the sessions.
            digipat_prefix (str): Prefix for the digital pattern variable.
            digipat_suffix (str): Suffix for the digital pattern variable.
            patterns (list): List of patterns to load for each session.
            debug (bool): Print debug information if True.

        Returns:
            None
        """
        
        self.dbg.start_function_debug(debug)
        
        # ============= Load Sessions ================ #
        # - Get sessions from list or class attribute  #
        # - Verify sessions are provided as a list     #
        # ============================================ #
        sessions = sessions or self.sessions
        
        if sessions is None:
            raise DigitalPatternException("No sessions provided")
        
        if not isinstance(sessions, list):
            sessions = [sessions]
        
        # ============= Load Pin Groups ================ #
        # - Get pin groups from list or class attribues #
        # - Verify pin groups are provided as a list    #
        # ============================================== #
        
        pingroups = pingroups or self.pingroups
        if pingroups is None:
            raise DigitalPatternException("No pin groups provided")
       
        if not isinstance(pingroups, list):
            pingroups = [pingroups]
        
        # ============= Load Patterns ================ #
        # - Get patterns from list or class attribute  #
        # - Verify patterns are provided as a list     #
        # ============================================ #

        patterns = patterns or self.patterns
        if patterns is None:
            raise DigitalPatternException("Please specify patterns in settings or in function call")
        
        if not isinstance(patterns, list):
            patterns = [patterns]

        # ======================= Verify Setup ========================= #
        # - Verify the number of patterns matches the number of sessions #
        # - Verify pin groups are sorted properly                        #
        # - Verify pin groups are provided as a list of lists of strings #
        # - Verify patterns are provided as a list of strings            #
        # - Verify sessions are provided as a list of nidigital.Session  #
        # ============================================================= #

        if len(patterns) != len(sessions):
            raise DigitalPatternException("Number of patterns must match number of sessions")

        if sort:
            if pingroups != self.pingroups:
                pingroups = self.sort_pins(pingroups)


        if not (type(pingroups) is list and type(pingroups[0]) is str and sort or type(pingroups[0]) is list and not sort):
            raise DigitalPatternException("Please provide pin groups as list of lists of strings")
        if not (type(patterns) is list and type(patterns[0]) is str):
            raise DigitalPatternException("Pleasae provide patterns as list of strings")
        if not (type(sessions) is list and type(sessions[0]) is nidigital.Session):
            raise DigitalPatternException("Please provide sessions as list of nidigital.Session objects")
        
        
        # ============= Build Waveforms ================ #
        self.dbg.debug_message(f"Masks: {masks}")
        waveforms, pulse_width = self.build_waveforms(masks, pulse_lens=pulse_lens, max_pulse_len=max_pulse_len, pulse_groups=pulse_groups, debug=debug)
        #WL_PULSE_DEC3.digipat or PULSE_MPW_ProbeCard.digipat as template file
        # Verify that the number of pin groups matches the number of waveforms
        if not len(pingroups) == len(waveforms):
            raise DigitalPatternException("Number of pin groups must match number of waveforms")
        
        # ============= Pulse Waveforms ================ #
        self.dbg.debug_message(f"Sessions:{sessions}")
        for waveform_session_index,waveform_session_value in enumerate(waveforms):
            self.dbg.debug_message([f"Waveform Session Index: {waveform_session_index}", f"Waveform Session Value: {waveform_session_value}"])

            self.arbitrary_pulse(sessions[waveform_session_index],waveform_session_value, session_pingroups=self.pingroup_names[waveform_session_index], data_variable_prefix=digipat_prefix,data_variable_suffix=digipat_suffix, pulse_width=pulse_width)
            
        if len(sessions) == 1:
            sessions[0].burst_pattern(self.pattern_names[0])

        # Synchronize Pulses using NITClk
        else:
            for session_num, session in enumerate(sessions):
                session.start_label = self.pattern_names[session_num]
                session.configure_pattern_burst_sites()
            _, nitclk_session_list = nitclk.configure_for_homogeneous_triggers(sessions)
            nitclk.synchronize(sessions,200e-8)
            sessions[0].burst_pattern_synchronized(nitclk_session_list, self.pattern_names[0][:-3])
            nitclk.wait_until_done(sessions,10)
        self.dbg.end_function_debug()
        return 

    def arbitrary_pulse(self, session, waveform, session_pingroups, data_variable_prefix, data_variable_suffix, pulse_width=None,debug=None):
        self.dbg.start_function_debug(debug)
        broadcast = nidigital.SourceDataMapping.BROADCAST
        for group,wave in zip(session_pingroups,waveform):
            data_variable_in_digipat = f"{data_variable_prefix}{group}{data_variable_suffix}"
            session.pins[group].create_source_waveform_parallel(data_variable_in_digipat, broadcast)
        for group,wave in zip(session_pingroups,waveform):
            self.dbg.debug_message(f"Waveform Size: {len(wave)} for group {group}")
            session.write_source_waveform_broadcast(data_variable_in_digipat, wave)
        
        if pulse_width:
            self.set_pw(pulse_width,session)
        
        self.dbg.end_function_debug()
        return

    def set_clock(self, sessions=None, pins=None, sort=True, v_hi=1.8, v_lo=0, frequency=None, period=None, debug=None):
        self.dbg.start_function_debug(debug)
        if frequency == None:
            if period == None or period == 0:
                raise DigitalPatternException("Frequency or period must be provided and > 0")
            else:
                frequency = 1/period
        self.clock_frequency = frequency

        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort=sort,debug=debug)

        for session,session_pins in zip(session,pins):
            session.channels[session_pins].clock_generator_generate_clock(frequency=frequency,select_digital_function=True)

        self.dbg.end_function_debug()
        return frequency

    def end_clock(self, sessions=None, pins=None, sort=True, debug=None):
        self.dbg.start_function_debug(debug)
        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort=sort,debug=debug)

        for session, session_pins in zip(sessions, pins):
            session.channels[session_pins].clock_generator_abort()

        self.dbg.end_function_debug()
    # endregion
    
    """ ================================================= """ 
    """     NiDigital Voltage Pulse Utility Functions     """
    """ ================================================= """
    # region

    def build_temporal_mask(self, pulse_groups, debug=None):
        
        """ 
        Create a temporal mask for each session based on the pulse groups provided.
        The temporal mask is created by checking if the pulse group is in the session group.
        The mask is then formatted to be used in the build_waveforms function.

        Args:
            pulse_groups (list): List of pulse groups to create temporal masks for.
            debug (bool): Print debug information if True.

        Returns:
            list: Temporal mask for each session.
        """

        self.dbg.start_function_debug(debug)
        
        temporal_mask = []
        for pulse in pulse_groups:
            temporal_mask.append([[int(group in pulse) for group in session_groups]for session_groups in self.pingroup_names])
        
        self.dbg.end_function_debug()
        return(temporal_mask)

    def build_waveforms(self, masks, pulse_lens, pulse_groups, max_pulse_len, debug=None):
    
        """ Create a pulse train. Formatted for each of the
        masks already defined, so that each mask can be driven
        at the desired pulse step for the desired pulse length
        
        Ex: Masks = [[[1011]],[[1101]],[1011],[1]]
            pulse_lens = [1,3,5] 
            pulse_groups = [[[1],[0],[0,0]],[[1],[1],[1,1]], [[0],[0],[0,0]]]
                        drives the first group, all groups, then no groups
            Ex for group 1, pulse 1,2,3
              | 1 |   2   |     3     |
            M | 1 | 1 1 1 | 0 0 0 0 0 |
            a | 0 | 0 0 0 | 0 0 0 0 0 |
            s | 1 | 1 1 1 | 0 0 0 0 0 |
            k | 1 | 1 1 1 | 0 0 0 0 0 |
                --------- Time -------->
        
            Running Serially 1011,1011,1011,1011,0000,0000,0000,0000
        Pad with 0s to max_pulse_len

        Returns:
            list: waveforms
            int:  pulse_width   
        """

        self.dbg.start_function_debug(debug)

        pingroup_names = self.pingroup_names
        if pingroup_names is not None:
            pingroup_names_flattened = list(chain.from_iterable(pingroup_names))
        else:
            pingroup_names_flattened = []     
        
        create_temporal_mask = False
        for session in pulse_groups:
            if any(group in pingroup_names_flattened for group in session):
                create_temporal_mask = True
        if create_temporal_mask:
            pulse_groups = self.build_temporal_mask(pulse_groups)  
        
        waveforms = []
        for session_num, session_masks in enumerate(masks):
            session_waveforms = []
            for group_num, group_masks in enumerate(session_masks):
                group_waveform = []
                for pulse_len,step_included in zip(pulse_lens,pulse_groups):
                    group_waveform = group_waveform + [BitVector(bitlist = group_masks & step_included[session_num][group_num]).int_val()]*pulse_len
                
                self.dbg.debug_message(f"Group Waveform: {group_waveform}")
                
                waveform_len = len(group_waveform)
                group_waveform = group_waveform + [0]*(max_pulse_len-waveform_len)

                session_waveforms.append(group_waveform)
            waveforms.append(session_waveforms)
        
        self.dbg.end_function_debug()

        return waveforms, sum(pulse_lens)
    
    def set_pw(self, pulse_width, session=None, debug=None):
        """
        Set pulse width: Set the pulse width for the given session to REGISTER0.
        Args:
            pulse_width (int): Pulse width to set.
            session (nidigital.Session): Session to set the pulse width for.
            debug (bool): Print debug information if True.
        
        returns: None
        """
        self.dbg.start_function_debug(debug)
        pw_register = nidigital.SequencerRegister.REGISTER0
        if session is None:
            for session in self.sessions:
                self.dbg.debug_message(f"Setting pulse width to {pulse_width} for session {session}")
                session.write_sequencer_register(pw_register, pulse_width)
        else:
            self.dbg.debug_message(f"Setting pulse width to {pulse_width} for session {session}")
            session.write_sequencer_register(pw_register, pulse_width)
        
        self.dbg.end_function_debug()
        
        return 0

    # endregion


    """ ================================================= """
    """              NiDigital Read Functions             """
    """ ================================================= """
    # region
    def set_current_limit_range(self, channel=None, current_limit=1e-6, pin_sort=True, debug=None):
        """ Set current limit for a given channel """
        
        self.dbg.start_function_debug(debug)
        if pin_sort:
            channel  = self.sort_pins(channel)
        
        for digital,dev_pins in zip(self.sessions, channel):
            if dev_pins is not None:
                digital.channels[dev_pins].ppmu_current_limit_range = current_limit
        
        self.dbg.end_function_debug()
        
        return

    def measure_voltage(self, pins=None, sessions=None, sort=True,debug=None):
        """
        Measure Voltage: Performs a voltage measurement on the specified
        pins, returning the measured voltages, a dictionary of the pins and
        their measured voltages, and a list of all measured voltages.

        Args:
            pins (list): List of pins to measure.
            sessions (list): List of sessions to measure.
            sort (bool): Sort the pins based on the order of the sessions.

        Returns:
            measured_voltages (list): List of measured voltages for each session.
            dict: Dictionary of pins and their measured voltages.
            list: List of all measured voltages.
        
        """
        self.dbg.start_function_debug(debug)

        # Check if sessions and pins are None, if so, use the class attributes
        sessions, pins = self.format_sessions_and_pins(sessions=sessions,pins=pins,sort=sort)

        # Initialize a list to store the measured voltages for each session
        measured_voltages = []
        
        # Iterate over each session and read the voltage of the pins in that session
        for session, session_pins in zip(sessions, pins):
            # Measure the voltage for each pin in the session
            session_voltages = []
            if len(session_pins) > 0:
                session_voltages = session.channels[session_pins].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)
            # Append the measured voltages for the session to the list
            measured_voltages.append(session_voltages)
        
        # Flatten the list of pins and measured voltages to remove session sorting
        flattened_pins = list(chain.from_iterable(pins))
        flattened_voltages = list(chain.from_iterable(measured_voltages))
        
        self.dbg.end_function_debug()
        # Return the measured voltages, a dictionary of pins and their measured voltages, and a list of all measured voltages
        return measured_voltages, dict(zip(flattened_pins,flattened_voltages)), list(chain.from_iterable(measured_voltages))

    def measure_current(self, pins=None, sessions=None, sort=True, debug=None):
        """
        Measure Current: Performs a current measurement on the specified
        pins, returning the measured currents, a dictionary of the pins and
        their measured currents, and a list of all measured currents.

        Args:
            pins (list): List of pins to measure.
            sessions (list): List of sessions to measure.
            sort (bool): Sort the pins based on the order of the sessions.
        
        Returns:
            measured_currents (list): List of measured currents for each session.
            dict: Dictionary of pins and their measured currents.
            list: List of all measured currents.
        """
        self.dbg.start_function_debug(debug)
        sessions, pins = self.format_sessions_and_pins(sessions=sessions,pins=pins,sort=sort)

        measured_currents = []

        for session, session_pins in zip(sessions, pins):
            # Measure the current for each pin in the session
            session_currents = [] 
            if len(session_pins) > 0:
                session_currents = session.channels[session_pins].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)
            measured_currents.append(session_currents)
        # Flatten the list of pins and measured currents to remove session sorting
        flattened_pins = list(chain.from_iterable(pins))

        # Flatten the list of measured currents to remove session sorting
        flattened_currents = list(chain.from_iterable(measured_currents))
        
        self.dbg.end_function_debug()
        return measured_currents, dict(zip(flattened_pins,flattened_currents)), list(chain.from_iterable(measured_currents))
    
    # endregion


    """ ================================================= """
    """              NiSwitch Relay Functions             """
    """ ================================================= """
    #region
    
    def connect_relays(self, relays=None, channels=None,debug=None):
        """
        Connect to specified channels on a relay module.

        This method iterates over the provided list of channels and establishes connections
        using the relay module's `connect` method, provided the relay module is initialized (`self.relays` is not `None`).

        Args:
            channels (list): A list of channels to connect.

        Raises:
            ValueError: If channels is not a list or if self.relays is not initialized.
        """
        self.dbg.start_function_debug(debug)
        if relays is None: relays = self.relays
        if channels is None: raise DigitalPatternException("No channels/pins provided")

        if isinstance(relays, str):
            relays = [relays]
        if not isinstance(relays, list):
            raise ValueError("Relays must be a list, or a string if only one relay is used")
        
        if isinstance(channels, str):
            channels = [[channels]]
        elif not isinstance(channels[0], list):
            if len(channels) > 0:
                channels = [channels]
            else:
                raise ValueError("Channels must be provided")
        for relay, channel in zip(relays, channels):
            with niswitch.Session(relay) as relay_session:
                relay_session.disconnect_all()
                for ch in channel:
                    self.dbg.debug_message(f"Connecting com{ch} to no{ch} on {relay}")
                    relay_session.connect(f"com{ch}",f"no{ch}")
        
        self.dbg.end_function_debug()
        return 0

    #endregion


    def format_sessions_and_pins(self, sessions=None, pins=None, sort = True, debug=None):
        self.dbg.start_function_debug(debug)

        if sessions is None:
            if self.sessions is None:
                raise DigitalPatternException("No sessions provided")
            sessions = self.sessions
        if not isinstance(sessions, list):
            sessions = [sessions]
        
        if pins is None:
            if self.all_pins is None:
                raise DigitalPatternException("No pins provided")
            pins = self.all_pins
            self.dbg.debug_message("Using all pins: sort turned off")
            sort = False
        
        if sort:
            # Sort the pins into a list to match the order of the sessions
            if type(pins) is not list:
                if type(pins) is str:
                    if ", " in pins:
                        pins = pins.split(", ")
                    else:
                        pins = [pins]
                else:
                    raise DigitalPatternException("Pins must be a list or a string separated by ', '")
            pins = self.sort_pins(pins=pins,sessions=sessions)
        
        # Verify that specified pins are in all valid pins
        for session_pins in pins:
            for pin in session_pins:
                if pin not in self.all_pins_flat:
                    raise DigitalPatternException(f"Invalid pin provided: {pin} not found in all pins\n{self.all_pins_flat}")

        self.dbg.end_function_debug()
        
        return sessions, pins


    """ ================================================= """
    """              Utility Functions                    """
    """ ================================================= """
    def check_library_import(self, lib_name):
        """
        Checks if library is imported in the current environment.
        Returns True if so, False otherwise.
        """
        return lib_name in sys.modules

    def sort_pins(self,pins,sessions=None, all_pins=None, debug=None):
        """
        Sort Pins: Sort pins into a list of lists based on the order of the sessions.
        Raises ValueError if no sessions are provided or if no pins are provided

        Args:
            pins (list): List of pins to sort.
            sessions (list): List of sessions to sort pins for.
            all_pins (list): List of all pins to sort.
            debug (bool): Print debug information if True.
        
        Returns:
            sorted_pins (list): List of lists of pins sorted by session.
        """

        # Set Debug Printout
        self.dbg.start_function_debug(debug)

        # Set sessions based on argument or settings
        sessions = sessions or self.sessions
        if sessions is None:
            raise ValueError("No sessions provided")

        # Verify pins exist, 
        if all_pins is None:
            if self.all_pins is None:
                raise ValueError("No pins provided")
            elif sessions == self.sessions:
                all_pins = self.all_pins
            else:
                all_pins = [[channel.pin_name for channel in session.get_pin_results_pin_information()] for session in sessions]

        sorted_pins = []
        for session in all_pins:
            session_pins=[]
            for pin in pins:
                if pin in session:
                    session_pins.append(pin)
            sorted_pins.append(session_pins)
        
        # Debug Printout
        self.dbg.debug_message(f"For sessions {sessions} \nSorted Pins: {sorted_pins}")
        self.dbg.end_function_debug()

        return sorted_pins         

    """ Need to figure out how to get the pattern pulse to work with NI-Tclk Sync"""


    def match_dimensions(self,list_of_lists, list_of_strings, debug=None):
        """
        Match Dimensions: Appends a string to each sublist in a list of lists.
        Used to match a list of strings to a list of lists with the same length.

        Args:
            list_of_lists (list): List of lists to append strings to.
            list_of_strings (list): List of strings to append to each sublist.
        
        Returns:
            list: List of lists with strings appended to each sublist.
        """
        self.dbg.start_function_debug(debug)
        
        # Make a copy of the list of lists to preserve the original
        result = [sublist[:] for sublist in list_of_lists]
        
        # Iterate over both lists simultaneously
        for sublist, string in zip(result, list_of_strings):
            # Append the string to the sublist
            sublist.append(string)
        
        self.dbg.end_function_debug()
        
        return result

    def close(self):
        """
        Close sessions and disconnect relays.

        This method first checks if any sessions are open (`self.sessions` is not `None`),
        then iterates through each session and closes it.
        Additionally, if relays are initialized (`self.relays` is not `None`),
        it iterates through each relay, disconnects it, and closes the relay session.

        """
        if self.sessions:
            self.ppmu_set_pins_to_zero()

        if self.relays:
            for relay in self.relays:
                try:
                    with niswitch.Session(relay) as relay_session:
                        relay_session.disconnect_all()
                except Exception as e:
                    print(f"Error disconnecting relay {relay}: {e}")

    def __del__(self):
        """Make sure to automatically close connection in destructor."""
        self.close()

if __name__ == "__main__":
    digital = DigitalPattern()
    digital.close()
    print("Done")
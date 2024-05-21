""" The DigitalPattern Class that controls the instrument drivers.   """
"""  This class has fewer functions than the original NIRRAM class   """
"""  but is more general. It can be used with any NI Digital Pattern """
"""  for any sessions using NiTClk, NiDigital, and NiSwitch          """
"""  --------------------------------------------------------------  """
"""  The class is designed to be used with the NI PXIe-6570/1 cards  """
"""  and the NI PXIe-2527 relay cards. Given the following:          """
"""    - Each session uses a single instrument                       """
"""    - pin_maps are specified in the same order for the sessions    """

import numpy as np
import sys
from os import getcwd
import nidigital
import niswitch
import nitclk
from BitVector import BitVector
from itertools import chain

sys.path.append(getcwd())
import SourceScripts.load_settings as load_settings
import SourceScripts.masks as masks
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
        self.debug = debug

        self.load_instruments()
        self.load_pin_maps()
        self.load_patterns()
        self.configure_timing()
        self.ppmu_set_pins_to_zero()
        self.clear_patterns()
        self.set_current_limit_range(self.all_pins, 2e-6, pin_sort=False)
        self.set_power(ignore_empty=True)
        
        
    def load_instruments(self,instruments=None):
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
        
        if instruments is None:
            try:
                # Load NiDigital sessions
                if "NIDigital" in self.settings:
                    if "deviceID" in self.settings["NIDigital"]:
                        import nidigital
                        # Import nidigital library if not already imported
                        if not self.check_library_import("nidigital"): import nidigital

                        # Create Session for each device    
                        self.sessions = []
                        for device_id in self.settings["NIDigital"]["deviceID"]:
                            self.sessions.append(nidigital.Session(device_id))

                        # self.sessions = [nidigital.Session(device_id) for device_id in self.settings["NIDigital"]["deviceID"]]
                        
                        # Set sync flag if multiple devices are provided
                        self.sync = len(self.sessions) > 1
                        
                        # Import nitclk library if not already imported
                        if self.sync and not self.check_library_import("nitclk"): import nitclk
                    
                    else:
                        raise ValueError("NiDigital deviceID not found in settings")
                
                # Load NiSwitch session
                if "NiSwitch" in self.settings:
                    import niswitch
                    if "deviceID" in self.settings["NiSwitch"]:

                        # Import niswitch library if not already imported
                        if not self.check_library_import("niswitch"): import niswitch

                        # Initialize session for specified device ID
                        self.relays = self.settings["NiSwitch"]["deviceID"]
                    
                    else:
                        raise ValueError("NiSwitch deviceID not found in settings")
            
            except Exception as e:
                # Handle any potential errors
                # Raise ValueError with error message if there is an exception
                raise ValueError(f"Error loading instruments: {str(e)}")

        else:
            # Use session list to load nidigital or niswitch instruments based on device ID string
            if not isinstance(instruments, list):
                raise ValueError("Instruments must be a list or provided as None to load from settings")
            sessions = []
            for instrument in instruments:
                if '6570' in instrument or '6571' in instrument:
                    if not self.check_library_import("nidigital"): import nidigital
                    self.sessions.append(nidigital.Session(instrument))
                elif '2571' in instrument:
                    if not self.check_library_import("niswitch"): import niswitch
                    self.relays = niswitch.Session(instrument)
            if len(sessions) > 1:
                if not self.check_library_import("nitclk"): import nitclk
                self.sync = True
            elif len(sessions) < 1:
                raise ValueError("No valid instruments provided,\n please use device names with '6570', '6571', or '2571' \nand ensure they match in NiMAX")

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
        if debug is None: debug = self.debug
        if debug: print("-------- Loading Pin Maps For Each Session --------")

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
        if debug: 
            print(f"Load Pinmaps {pinmaps} for Sessions {sessions}")
            print("-------- Pin Maps Loaded For Each Session --------")
        
        # Define Pingroups for patterns and multi-pin operations
        self.pingroups = []

        if pingroups is None:
            if "pingroups"in digital:
                self.pingroups = digital["pingroups"]
            if "pulse_pingroups" in digital:
                self.pingroups.append(digital["pulse_pingroups"])
        else: self.pingroups = pingroups

        if len(self.pingroups) == 1 and type(self.pingroups[0]) is list:
            self.pingroups = self.pingroups[0]

        # Define the pins given for each session
        self.all_pins_dict = {digital["deviceID"][self.sessions.index(session)]:[channel.pin_name for channel in session.get_pin_results_pin_information()] for session in self.sessions}
        self.all_pins = [[channel.pin_name for channel in session.get_pin_results_pin_information()] for session in self.sessions]
        self.all_pins_flat = list(chain.from_iterable(self.all_pins))


    def load_patterns(self,patterns=None,sessions=None):
        """
        Load Patterns: Load patterns for each session based on settings.
        Raises DigitalPatternException if patterns are not found in settings.
        
        Args:
            patterns (list): List of patterns to load. If not provided, 
            patterns are loaded from settings.
            
        """
        # Define the digital specifications
        digital = self.settings["NIDigital"]
        
        if sessions is None:
            sessions = self.sessions

        # Check if there are any sessions
        if sessions is not None:
            # Check if patterns are provided in settings
            if patterns is None:
                if "patterns" in digital:
                    patterns = digital["patterns"]
                else:
                    # Raise error if no pattern is provided
                    raise DigitalPatternException("No patterns provided")
            else:
                # Patterns are provided as an argument, use patterns provided
                if type(patterns) is str: patterns = [patterns]
                if type(patterns) is not list: raise DigitalPatternException("Patterns must be a list or a string")
                if len(patterns) != len(sessions): raise DigitalPatternException("Number of patterns must match number of sessions")

                for session, session_pattern in zip(sessions, patterns):
                    session.load_pattern(session_pattern)
        else:
            raise DigitalPatternException("No sessions provided")

    def load_level_and_timing(self):

        digital = self.settings["NIDigital"]

        if self.sessions is not None: 
            for session in self.sessions:
                session_levels = digital["levels"][self.sessions.index(session)]
                session_timing = digital["timing"][self.sessions.index(session)]
                session_specs = digital["specs"]
                
                session.load_specifications_levels_and_timing(session_specs, session_levels, session_timing)
                session.apply_levels_and_timing(session_levels, session_timing)

    def configure_timing(self,sessions=None, timing=None, debug=None):
        """
        Configure Timing: Load timing sets for each session based on settings.
        Raises DigitalPatternException if timing sets are not found in settings.
        
        Args:
            sessions (list): List of sessions to configure timing for.
            timing (list): List of timing sets to load for each session.
            debug (bool): Print debug information if True.
        """
        if debug is None: debug = self.debug
        if debug: print("-------- Configuring Timing For Each Session --------")

        # Load Timing Sets
        time_sets = self.settings["TIMING"] if timing is None else timing
        
        if sessions is None: sessions = self.sessions
        
        # Debug Printout
        if debug:
            print(f"Timing Sets: {time_sets}")
        
        # Configure Timing for Each Session
        if sessions is not None:
            for condition in time_sets:
                for session in sessions:
                    session.create_time_set(condition)
                    session.configure_time_set_period(condition,time_sets[condition])
        else: 
            print("No sessions provided, timing not applied.")

        # Debug Printout        
        if debug: print("-------- Timing Configured For Each Session --------")

    def configure_read(self, sessions=None, pins=None, sort=True):
        """
        Configure Read: Set the voltage and current levels for reading on the given sesions and pins.
            sessions: List of sessions to configure.
            pins: List of pins to configure or a list of lists of pins sorted by session.
            sort: Sort the pins based on the order of the sessions.
        """

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

    def set_channel_mode(self, mode, pins=None,sessions=None,sort=True,debug_printout=None):
        if debug_printout is None: debug_printout = self.debug

        if sessions is None:
            if self.sessions is None:
                raise ValueError("No sessions provided")
            sessions = self.sessions
        if pins is None:
            if self.all_pins is None:
                raise ValueError("No pins provided")
            pins = self.all_pins
            if debug_printout:
                print("Using all pins: sort turned off")
            sort = False

        if sort:
            pins = self.sort_pins(pins)
        
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

        if debug_printout:
            print(f"Setting mode to nidigital.SelectedFunction.{mode.upper()} for pins {pins}")


    def ppmu_set_pins_to_zero(self,sessions=None,pins=None,sort=True,relayed=True):
        """ 
        Cleans up after PPMU operation (otherwise levels default when going back digital)
        """
        sessions, pins = self.format_sessions_and_pins(sessions,pins,sort,relayed=relayed)
        for session, session_pins in zip(sessions,pins):
            for pin in session_pins:
                session.channels[pin].ppmu_voltage_level = 0
            session.ppmu_source()
        return

    def digital_all_pins_to_zero(self,keep_power=False):
        """
        High z down to zero
        """
        all_pins = self.all_pins
        if keep_power:
            for session in all_pins:
                for pin in self.power_pins:
                    if pin in session:
                        session.remove(pin)

        for digital in self.sessions:
            digital.channels[self.all_pins[self.sessions.index(digital)]].write_static(nidigital.WriteStaticPinState.X)
       
        self.digital_set_voltages(all_pins, 0, 0, sort=False)
        
        return

    def clear_patterns(self):
        if self.sessions is not None:
            for session in self.sessions:
                session.unload_all_patterns()

    def sort_pins(self,pins,sessions=None, all_pins=None):
        if sessions is None:
            if self.sessions is None:
                raise ValueError("No sessions provided")
            else:
                sessions = self.sessions

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
        return sorted_pins
                
    def set_power(self,pins=None,power_levels=None,sort=True,ignore_empty=False):
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


    """ Need to figure out how to get the pattern pulse to work with NI-Tclk Sync"""

    def pulse(self, masks, pulse_len=10, prepulse_len=50, postpulse_len=50, max_pulse_len=10000, wl_first=True, sessions=None, pingroups=None, sort=True, patterns=None ):
        """Create waveform for directly contacting the array BLs, SLs, and WLs, then output that waveform"""
        
        if sessions is None:
            try:
                sessions = self.sessions
                if type(self.sessions) is not list:
                    sessions = [self.sessions]
            except:
                raise DigitalPatternException("No sessions provided")
        
        if pingroups is None:
            try:
                pingroups = self.pingroups
            except:
                try:
                    pingroups = self.settings["NIDigital"]["pingroups"]
                except:
                    raise DigitalPatternException("No pin groups provided")

        if patterns is None:
            try:
                patterns = self.settings["NIDigital"]["patterns"]
            except:
                raise DigitalPatternException("Please specify patterns in settings or in function call")
            if type(self.settings["NIDigital"]["patterns"]) is not list:
                raise DigitalPatternException("Please specify patterns as list")

        if not (type(pingroups) is list and type(pingroups[0]) is str and sort or type(pingroups[0]) is list and not sort):
            raise DigitalPatternException("Please provide pin groups as list of strings")
        if not (type(patterns) is list and type(patterns[0]) is str):
            raise DigitalPatternException("Pleasae provide patterns as list of strings")
        if not (type(sessions) is list and type(sessions[0]) is nidigital.Session):
            raise DigitalPatternException("Please provide sessions as list of nidigital.Session objects")
        
        if sort:
            pingroups = self.sort_pins(pingroups)
        
        waveforms, pulse_width = self.build_waveforms(masks, pulse_len, prepulse_len, postpulse_len, max_pulse_len, wl_first, sessions = sessions, pingroups=pingroups)
        #WL_PULSE_DEC3.digipat or PULSE_MPW_ProbeCard.digipat as template file
        
        
        
        if not len(pingroups) == len(waveforms) and len(pingroups) == len(patterns):
            raise DigitalPatternException("Number of pin groups must match number of waveforms and patterns")
        
        for pingroup in pingroups:
            self.arbitrary_pulse(sessions[pingroups.index(pingroup)],waveforms[pingroups.index(pingroup)], pin_group_name=pingroup, data_variable_in_digipat=f"{pingroup}_data", pulse_width=pulse_width)

        if len(self.sessions) == 1:
            self.sessions[0].burst_pattern(patterns[0])
        else:
            for session in self.sessions:
                session.load_pattern(patterns[self.sessions.index(session)])
            nitclk.configure_for_homogeneous_triggers(self.sessions)
            nitclk.synchronize(self.sessions,200e-8)
            nitclk.initiate(self.sessions)
            nitclk.wait_until_done(self.sessions,10)
        return

    def arbitrary_pulse(self, session, waveform, pin_group_name, data_variable_in_digipat,pulse_width=None):
        broadcast = nidigital.SourceDataMapping.BROADCAST
        
        session[self.pulse_pingroups.index(pin_group_name)].pins[pin_group_name].create_source_waveform_parallel(data_variable_in_digipat, broadcast)
        session[self.pulse_pingroups.index(pin_group_name)].write_source_waveform_broadcast(data_variable_in_digipat, waveform)
        
        if pulse_width:
            self.set_pw(pulse_width)
        return


    def build_waveforms(self, masks, pulse_len, prepulse_len, postpulse_len, max_pulse_len, debug_printout = None, sessions=None, pingroups = None, patterns = None, sort_pingroups=True):
    
        """Create pulse train. Format of bits is [BL SL] and . For an array
        with 2 BLs, 2 SLs, and 2 WLs, the bits are ordered:
            [ BL0 BL1 ] ,  [ SL0 SL1 ], [ WL0 WL1 ]
        """
        
        if debug_printout is None:
            debug_printout = self.debug_printout


        if sessions is None:
            sessions = self.sessions
        if pingroups is None:
            pingroups = self.pingroups
        if patterns is None:
            patterns = self.patterns


        pingroup_offsets = []
        
        """
        Develop the waveforms for each of the sessions, by creating
        and offsetting the waveforms for each of the pingroups in
        each of the sessions.
        """


        if sort_pingroups == False:
            assert len(sessions) == len(pingroups), "Number of sessions and pingroups do not match"
            assert type(pingroups) == list and type(pingroups[0] == list), "Pingroups must be a list of lists of strings to match every session"  


        else:
            assert len(pingroups) == len(mask), "Number of pingroups and masks do not match"
            assert type(pingroups) == list and type(pingroups[0] == str), "Pingroups must be a list of lists of strings"
        
        
        self.pingroup_pre_post_bits = []
        self.pingroup_offsets = []
        self.data_prepulses = []
        self.data = []
        self.data_postpulses = []


        for session, session_pingroups, session_masks in zip(sessions,pingroups, masks):
            
            if debug_printout:
                print(f"Session {session}")


            session_pingroup_pre_post_bits = []
            
            if len(session_masks) != len(session_pingroups):
                    raise ValueError("Mask and pingroup lengths do not match")
            
            session_pingroup_offsets = [sum(len(mask) for mask in session_masks[i+1:]) for i in range(len(session_masks))]
            session_pingroup_pre_post_bits.append([[BitVector(bitlist=(mask & False)).int_val()] for mask in session_masks])
            session_pingroup_mask_bits = [BitVector(bitlist=mask).int_val() for mask in session_masks]
        
            if debug_printout:
                for mask,pingroup in zip(session_pingroup_mask_bits,session_pingroups):
                    print(f"{pingroup} mask = {mask:b}")


            self.pingroup_offsets.append(session_pingroup_offsets)
            self.pingroup_pre_post_bits.append(session_pingroup_pre_post_bits)
            
        waveforms = []
        for session, session_pingroups, session_masks in zip(sessions,pingroups, masks):
            waveform = []
            if debug_printout:
                print(f"Session {session}")
            
            session_data_prepulse = sum([(mask << offset) for mask,offset in zip(session_pingroup_mask_bits,session_pingroup_offsets)])
            session_data = sum([(mask << offset) for mask,offset in zip(session_pingroup_mask_bits,session_pingroup_offsets)])
            session_data_postpulse = sum([(mask << offset) for mask,offset in zip(session_pingroup_mask_bits,session_pingroup_offsets)])


            if debug_printout:
                print(f"data_prepulse = {session_data_prepulse:b}")
                print(f"data = {session_data:b}")
                print(f"data_postpulse = {session_data_postpulse:b}")


            self.data_prepulses.append(session_data_prepulse)
            self.data.append(session_data)
            self.data_postpulses.append(session_data_postpulse)


            waveform += [session_data_prepulse for i in range(prepulse_len)] + [session_data for i in range(pulse_len)] + [session_data_postpulse for i in range(postpulse_len)]
            
            if debug_printout:
                for timestep in waveform:
                    print(bin(timestep))
        
            waveform += [0 for i in range(max_pulse_len - len(waveform))]
            
            pulse_width = prepulse_len + pulse_len + postpulse_len
            
            waveforms.append(waveform)
            
        return waveforms, pulse_width

    def set_pw(self, pulse_width):
        """Set pulse width"""
        pw_register = nidigital.SequencerRegister.REGISTER0
        for session in self.sessions:
            session.write_sequencer_register(pw_register, pulse_width)



    def ppmu_set_voltage(self, pins,voltage_levels,sessions = None, sort=True,source=False):
        if sessions is None:
            sessions = self.sessions
        
        if sessions is not None:
            for v in voltage_levels:
                assert v >= -2 and v <= 6, "Voltage levels must be between -2V and 6V"
            if sort:
                pins = self.sort_pins(pins)
            for session in sessions:
                for pin, level in zip(pins[sessions.index(session)],voltage_levels):
                    session.channels[pin].ppmu_voltage_level = level
            if source:
                for session,session_pins in zip(sessions,pins):
                    session.channels[session_pins].ppmu_source() 

    def ppmu_set_current(self,pins,current_levels,sort=True):
            if sort:
                pins = self.sort_pins(pins)            
            for session in self.sessions:
                for pin, level in zip(pins[self.sessions.index(session)],current_levels  ):
                    session.channels[pin].ppmu_current_level = level
            for session in self.sessions:
               session.channels[pins].ppmu_source() 

    def ppmu_source(self,pins,sort=True):
        if sort:
            pins = self.sort_pins(pins)
        for session,session_pins in zip(self.sessions,pins):
            session.channels[session_pins].ppmu_source()

    def set_current_limit_range(self, channel=None, current_limit=1e-6, pin_sort=True):
        """ Set current limit for a given channel """
        if pin_sort:
            channel  = self.sort_pins(channel)
        for digital,dev_pins in zip(self.sessions, channel):
            if dev_pins is not None:
                digital.channels[dev_pins].ppmu_current_limit_range = current_limit
        return


    def digital_set_voltages(self, pins, v_hi, v_lo, sort=True):
        if self.sessions is not None:
            if sort:
                pins = self.sort_pins(pins)
            
            for session in self.sessions:
                for pin in pins[self.sessions.index(session)]:
                    session.channels[pin].configure_voltage_levels(v_lo, v_hi, v_lo, v_hi, 0)
        return

    

    def measure_voltage(self, pins=None, sessions=None, sort=True):
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
        # Check if sessions and pins are None, if so, use the class attributes
        if sessions is None:
            sessions = self.sessions
        if pins is None:
            pins = self.all_pins
        
        # Sort the pins if sort is True
        if sort:
            pins = self.sort_pins(pins)
        
        # Initialize a list to store the measured voltages for each session
        measured_voltages = []
        
        # Iterate over each session and its corresponding pins
        for session, session_pins in zip(sessions, pins):
            session_voltages = []
            
            # Measure the voltage for each pin in the session
            for pin in session_pins:
                session_voltages.append(session.channels[pin].ppmu_measure(nidigital.PPMUMeasurementType.VOLTAGE)[0])
            
            # Append the measured voltages for the session to the list
            measured_voltages.append(session_voltages)
        
        # Flatten the list of pins and measured voltages to remove session sorting
        flattened_pins = list(chain.from_iterable(pins))
        flattened_voltages = list(chain.from_iterable(measured_voltages))
        
        # Return the measured voltages, a dictionary of pins and their measured voltages, and a list of all measured voltages
        return measured_voltages, dict(zip(flattened_pins,flattened_voltages)), list(chain.from_iterable(measured_voltages))

    def measure_current(self, pins=None, sessions=None, sort=True):
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
    
        if sessions is None:
            # If sessions is not provided, use the sessions stored in the class instance
            sessions = self.sessions
        
        if pins is None:
            # If pins is not provided, use all_pins stored in the class instance
            pins = self.all_pins
        
        if sort:
            # Sort the pins based on the order of the sessions
            pins = self.sort_pins(pins)
        
        measured_currents = []
        for session, session_pins in zip(sessions, pins):
            session_currents = []
            for pin in session_pins:
                # Measure the current for each pin in the session
                session_currents.append(session.channels[pin].ppmu_measure(nidigital.PPMUMeasurementType.CURRENT)[0])
            measured_currents.append(session_currents)
        
        # Flatten the list of pins and measured currents to remove session sorting
        flattened_pins = list(chain.from_iterable(pins))

        # Flatten the list of measured currents to remove session sorting
        flattened_currents = list(chain.from_iterable(measured_currents))
        
        return measured_currents, dict(zip(flattened_pins,flattened_currents)), list(chain.from_iterable(measured_currents))



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
        if debug is None: debug = self.debug
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
                    if debug:
                        print(f"Connecting com{ch} to no{ch} on {relay}")
                    relay_session.connect(f"com{ch}",f"no{ch}")

    def format_sessions_and_pins(self, sessions=None, pins=None, sort = True,relayed=True,debug=None):
        if debug is None: debug = self.debug
        if debug: print("-------- Formatting Sessions and Pins --------")

        if sessions is None:
            if self.sessions is None:
                raise DigitalPatternException("No sessions provided")
            sessions = self.sessions
        
        if pins is None:
            if self.all_pins is None:
                raise DigitalPatternException("No pins provided")
            pins = self.all_pins
            if debug:
                print("Using all pins: sort turned off")
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

        if debug: print("--------Sessions and Pins Formatted--------")
        
        return sessions, pins

    def check_library_import(self, lib_name):
        """
        Checks if library is imported in the current environment.
        Returns True if so, False otherwise.
        """
        return lib_name in sys.modules

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

        if debug is None: debug = self.debug
        if debug: print("-------- Matching Dimensions --------")
        
        # Make a copy of the list of lists to preserve the original
        result = [sublist[:] for sublist in list_of_lists]
        
        # Iterate over both lists simultaneously
        for sublist, string in zip(result, list_of_strings):
            # Append the string to the sublist
            sublist.append(string)
        
        if debug: print("-------- Dimensions Matched --------")
        
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
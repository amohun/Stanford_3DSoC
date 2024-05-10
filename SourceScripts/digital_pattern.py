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

sys.path.append(getcwd())
import SourceScripts.load_settings as load_settings

class DigitalPattern:
    def __init__(
            self,
            settings="settings\default.toml",
            debug=False,
        ):

        self.settings = load_settings.load_settings(settings)
        settings = self.settings
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

    def load_pin_maps(self):
        
        digital = self.settings["NIDigital"]

        if self.sessions is not None:
            for session in self.sessions:
                session_pin_map = digital["pinmap"][self.sessions.index(session)]
                session.load_pin_map(session_pin_map)
        
            if "pingroups"in digital:
                self.pingroups = digital["pingroups"]

            self.all_pins_dict = {digital["deviceID"][self.sessions.index(session)]:[channel.pin_name for channel in session.get_pin_results_pin_information()] for session in self.sessions}
            self.all_pins = [[channel.pin_name for channel in session.get_pin_results_pin_information()] for session in self.sessions]
    
    def load_patterns(self):
        digital = self.settings["NIDigital"]
        if self.sessions is not None:
            if "patterns" in digital:
                for session in self.sessions:
                    session_pattern = digital["patterns"][self.sessions.index(session)]
                    session.load_pattern(session_pattern)

    def load_level_and_timing(self):

        digital = self.settings["NIDigital"]

        if self.sessions is not None: 
            for session in self.sessions:
                session_levels = digital["levels"][self.sessions.index(session)]
                session_timing = digital["timing"][self.sessions.index(session)]
                session_specs = digital["specs"]
                
                session.load_specifications_levels_and_timing(session_specs, session_levels, session_timing)
                session.apply_levels_and_timing(session_levels, session_timing)

    def configure_timing(self):
        # Load Timing Sets
        time_sets = self.settings["TIMING"]
        if self.sessions is not None:
            for condition in time_sets:
                for session in self.sessions:
                    session.create_time_set(condition)
                    session.configure_time_set_period(condition,time_sets[condition])

    def ppmu_set_pins_to_zero(self,pins=None,sort=True):
        if self.sessions is not None:
            if pins is None:
                sort = False
                pins = self.all_pins
        if sort:
            pins = self.sort_pins(pins)        
        for session, dev in zip(self.sessions, pins):
            session.channels[dev].write_static(nidigital.WriteStaticPinState.ZERO)

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

    def sort_pins(self,pins):
        if self.sessions is not None:
            sorted_pins = []
            for session in self.all_pins:
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
            
                self.ppmu_set_voltage(self,pins,power_levels,sort=False)
                self.power_pins = pins


    """ Need to figure out how to get the pattern pulse to work with NI-Tclk Sync"""

    # def arbitrary_pulse(self, waveform, pin_group_name, data_variable_in_digipat,pulse_width=None):
    #     broadcast = nidigital.SourceDataMapping.BROADCAST
        
    #     if self.sessions is not None:
    #         for session in self.sessions:
    #             session
    #     self.digital[self.pulse_pingroups.index(pin_group_name)].pins[pin_group_name].create_source_waveform_parallel(data_variable_in_digipat, broadcast)
    #     self.digital[self.pulse_pingroups.index(pin_group_name)].write_source_waveform_broadcast(data_variable_in_digipat, waveform)
    #     if pulse_width:
    #         self.set_pw(pulse_width)
    #     return


    def ppmu_set_voltage(self,pins,voltage_levels,sort=True):
        if self.sessions is not None:
            for v in voltage_levels:
                assert v >= -2 and v <= 6, "Voltage levels must be between -2V and 6V"
            if sort:
                pins = self.sort_pins(pins)
            for session in self.sessions:
                for pin, level in zip(pins[self.sessions.index(session)],voltage_levels):
                    session.channels[pin].ppmu.voltage_level = level
            for session in self.sessions:
               session.channels[pins].ppmu_source() 

    def ppmu_set_current(self,pins,current_levels,sort=True):
            if sort:
                pins = self.sort_pins(pins)            
            for session in self.sessions:
                for pin, level in zip(pins[self.sessions.index(session)],current_levels  ):
                    session.channels[pin].ppmu_current_level = level
            for session in self.sessions:
               session.channels[pins].ppmu_source() 

    def digital_set_voltages(self, pins, v_hi, v_lo, sort=True):
        if self.sessions is not None:
            if sort:
                pins = self.sort_pins(pins)
            
            for session in self.sessions:
                for pin in pins[self.sessions.index(session)]:
                    session.channels[pin].configure_voltage_levels(v_lo, v_hi, v_lo, v_hi, 0)
        return

    def set_current_limit_range(self, channel=None, current_limit=1e-6, pin_sort=True):
        """ Set current limit for a given channel """
        if pin_sort:
            channel  = self.sort_pins(channel)
        for digital,dev_pins in zip(self.sessions, channel):
            if dev_pins is not None:
                digital.channels[dev_pins].ppmu_current_limit_range = current_limit
        return
    
    
    def connect_relays(self, relays, channels):
        """
        Connect to specified channels on a relay module.

        This method iterates over the provided list of channels and establishes connections
        using the relay module's `connect` method, provided the relay module is initialized (`self.relays` is not `None`).

        Args:
            channels (list): A list of channels to connect.

        Raises:
            ValueError: If channels is not a list or if self.relays is not initialized.

        """
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
        for relay, channel in relays, channels:
            with niswitch.Session(relay) as relay_session:
                relay_session.disconnect_all()
                for ch in channel:   
                    relay_session.connect(relay, ch)



    def check_library_import(self, lib_name):
        """
        Checks if library is imported in the current environment.
        Returns True if so, False otherwise.
        """
        return lib_name in sys.modules

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
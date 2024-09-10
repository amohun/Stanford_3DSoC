import numpy as np
import pandas as pd
from itertools import chain
import pdb

class MasksException(Exception):
    """Exception produced by the ArrayMask class"""
    def __init__(self, msg):
        super().__init__(f"ArrayMask: {msg}")

class Masks:
    """
    Class for masking specific WLs, BLs for programming pulses.
    Indicates mask of bits that need further programming.
    As we run a programming pulses, when specific WL/BL combinations
    hit their target resistance, we can mask them off to skip them and
    only continue to program cells that have not hit target yet.
    """

    def __init__(
            self,
            sel_pins=None,   # List of selected pins by the user, if None, all pins are selected, either sorted by session or not
            pingroups=None,  # List of pins, separated by pin groups to be selected sorted by session
            all_pins=None,   # List of all pins, used for verifying pins and pingroups are correct
            pingroup_names=None, # List of names for the pin groups
            init_state=None, # Initial state of the mask, if None, all bits are unmasked
            sort=True, # If true, sort the pins by session
            debug_printout=False # If true, print debug information
    ):
        self.sel_pins = sel_pins
        self.pingroups = pingroups
        self.all_pins = all_pins
        self.pingroup_names = pingroup_names
        self.init_state = init_state
        self.sort = sort
        self.debug_printout = debug_printout
        self.pingroup_names = pingroup_names

        self.ensure_all_required_arguments()
        self.sort_pins()
        self.verify_pins_in_pingroups()
        self.sort_pins_by_pingroup()
        self.masks = init_state
        if init_state is None:
            self.masks_and_flattened_masks = self.define_masks()
        self.masks, self.masks_df_list, self.flattened_masks_df = self.masks_and_flattened_masks
    
    
    def ensure_all_required_arguments(self):

        if self.sel_pins is None:
            raise MasksException("Must provide a list of pins to be selected")

        if self.all_pins is None:
            raise MasksException("Must provide a list of all pins")

        if not isinstance(self.all_pins[0], list):
            self.all_pins = [self.all_pins]

        if self.pingroups is None:
            raise MasksException("Must provide a list of pin groups used for the Digital Pattern Editor")

        if isinstance(self.all_pins[0], list) and len(self.all_pins) > 1:
            if not self.sort and not isinstance(self.sel_pins[0], list):
                raise MasksException("If not sorting pins by session, must provide a list of pins for each included session")
            if self.sort and isinstance(self.sel_pins[0], list):
                raise MasksException("If sorting pins by session, please provide pins as a single list of strings")

        self.pingroups_missing_sessions = len(self.pingroups) != len(self.all_pins)

        
    
    def sort_pins(self):
        """
        Sorts the pins and pingroups by sessions
        """

        if self.debug_printout:
            print("Sorting pins and pin groups by session")
        
        if self.sort:
            self.sel_pins = [[pin for pin in session if pin in self.sel_pins] for session in self.all_pins]


    def verify_pins_in_pingroups(self):
        """
        Verifies that all pins in the pin groups are in the list of all pins
        """
        self.pingroups_flattened_by_session = list(chain.from_iterable(self.pingroups))

        for pin_session,group_session in zip(self.sel_pins,self.pingroups):
            for pin in pin_session:
                if pin not in list(chain.from_iterable(group_session)):
                    raise MasksException(f"Pin {pin} is not found in session pingroups despite being in session")


    def sort_pins_by_pingroup(self):
        """
        Sorts the pins by pin group
        """
        pins_sorted_by_pingroup = []
        
        for pin_session,group_session in zip(self.sel_pins,self.pingroups):
            
            if self.debug_printout:
                print(f"Sorting pins by pin group for session {group_session}")
            
            group_pins = [[pin for pin in pin_session if pin in group]for group in group_session]
            
            pins_sorted_by_pingroup.append(group_pins)

            self.sel_pins = pins_sorted_by_pingroup

    def define_masks(self):
        """
        Defines the initial mask state based on the available pingroups
        and the selected pins. Selected pins will be True (1) while remaining
        pins will be False (0). The masks will be sorted by group, by session.
        """   

        # Initialize an empty list to store the masks for each session
        self.masks = []
        
        # Iterate through each session's groups and selected pins
        for session_groups, session_pins in zip(self.pingroups, self.sel_pins):
            
            # For each group in the session, create a mask array where each pin's mask
            # is True if it is selected, otherwise False
            session_masks = [
                np.array([pin in sel_pins for pin in group]) 
                for group, sel_pins in zip(session_groups, session_pins)
            ]
            
            # Append the mask for this session to the overall masks list
            self.masks.append(session_masks)
        
        # Flatten the list of masks across all sessions into a single list
        masks_flattened = list(chain.from_iterable(list(chain.from_iterable(self.masks))))
        
        # Flatten the list of all pin groups across all sessions into a single list
        bits_flattened = list(chain.from_iterable(list(chain.from_iterable(self.pingroups))))

        # Create a list of DataFrames, one for each session
        # Each DataFrame contains the pin names and their corresponding mask values
        self.masks_df_list = [
            pd.DataFrame({"Pin": [pin for pin in group], 
                        "Mask": [pin in group_sel_pins for pin in group]}) 
            for group_sel_pins, group in zip(session_pins, session_groups)
        ]
        
        # Create a single DataFrame combining all pins and masks across all sessions
        self.flattened_masks_df = pd.DataFrame({
            "Pin": bits_flattened,
            "Mask": masks_flattened
        })

        # Return the masks list, the list of session DataFrames, and the flattened DataFrame
        return self.masks, self.masks_df_list, self.flattened_masks_df


    def get_pulse_masks(self):
        """
        Returns the masks as a list of lists of numpy arrays
        """
        if self.debug_printout:
            print(f"Returning masks {self.pingroup_names or ''}\n{self.masks}")
        return self.masks
    
    
    def alter_masks(self, add_pins, remove_pins):
        """
        Alters the masks based on the mask_changes dictionary
        """
        for session in self.pingroups:
            for group in session:
                self.masks[session][group].update({pin: True for pin in add_pins if pin in group})
                self.masks[session][group].update({pin: False for pin in remove_pins if pin in group})

"""
Module for RRAM memory array masking.
Keep this separate from nirram so we can unit test this without requiring
importing all the ni digital system packages.
"""
import numpy as np
import pandas as pd
from itertools import chain

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
        polarity,
        all_pins=None,
        sel_pins=None,
        sort=True,
        init_state=None,
    ):
        if sel_pins is None:
            raise MasksException("Masks Error: No pins selected")
        if all_pins is None:
            raise MasksException("Masks Error: No pins available")
        if type(all_pins) is not list:
            raise MasksException("Masks Error: all_pins must be a list")
        if type(all_pins[0]) is not list:
            all_pins = [all_pins]
        # To get this to work with multiple pingroups in multiple sessions, we need to pass sorted pins for all_pins
        # or we need to make sure the pins are sorted in the session to the correct session
        self.all_pins = all_pins

        for pin in sel_pins:
            if pin not in list(chain.from_iterable(all_pins)):
                raise MasksException(f"Masks Error: Selected pin {pin} not in all pins")
        if sort:
            # Convert all_pins to sets for faster membership checks
            sel_pins = [[pin for pin in sel_pins if pin in group] for group in all_pins]

        if init_state is None:
            self.masks = []
            for group,sel_group in zip(all_pins,sel_pins):
                group_mask = pd.DataFrame({"mask": np.array([pin in sel_group for pin in group]).astype(bool), "pins": group})
                self.masks.append(group_mask)
                # Goal: Create a mask which has the n dimensions for n groups of pins with overlap for all the available pins...
        else:
            self.masks = init_state
        
        self.polarity = polarity
        

    
    def get_pulse_masks(self):
        
        # masks = [mask for mask in self.masks]
        masks = []
        for mask in self.masks:
            masks.append(pd.Series.to_numpy(mask["mask"]))
        return masks
    


    def alter_mask(self, add_pins, remove_pins,sort=True):
        if sort:
            add_pins = [[pin for pin in add_pins if pin in group] for group in self.all_pins]
            remove_pins = [[pin for pin in remove_pins if pin in group] for group in self.all_pins]

        for mask,add,remove in zip(self.masks,add_pins,remove_pins):
            mask["mask"] = mask["mask"] | np.array([pin in add for pin in mask["pins"]])
            mask["mask"] = mask["mask"] & np.array([not (pin in remove) for pin in mask["pins"]])




    def update_mask(self, failing):
        self.mask = failing


if __name__ == "__main__":
    all_pins = [['A','B','C','D','E','F'],['G','H','I','J','K','L','M','N'],['O','P','Q','R','S','T','U','V','W','X','Y','Z']]
    sel_pins = ['A','B','C','D','E','F','P','Q','V','X']
    masks = Masks(1,all_pins,sel_pins)
    print(all_pins)
    print([[str(int(x)) for x in mask] for mask in masks.get_pulse_masks()])
    masks.alter_mask(['R','N'],[])
    print([[str(int(x)) for x in mask] for mask in masks.get_pulse_masks()])
    masks.alter_mask([],['A','B'])
    print([[str(int(x)) for x in mask] for mask in masks.get_pulse_masks()])

    title = str(all_pins)

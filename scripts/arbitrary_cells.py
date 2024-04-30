import argparse
from source.nirram import NIRRAM
from time import sleep
import numpy as np
from checkerboard import checkerboard
import tomli
from pandas import read_excel
import os

reset = "RESET"
set = "SET"
none = "NONE"
read = "READ"
form = "FORM"
checker = "CHECKERBOARD"
invchecker = "INVERSE_CHECKERBOARD"

import os
import tomli
from pandas import read_excel

class Arbitrary_Cells:
    """
    A class for manipulating and organizing cell information from various inputs such as 
    direct cell coordinates, wordlines, bitlines, and Excel files. It supports loading settings 
    from a TOML file to configure the device's wordlines and bitlines.
    
    Attributes:
        cells (list): Initial list of cell coordinates (tuples).
        wordlines (list): List of wordline indices.
        bitlines (list): List of bitline indices.
        array (list): Reserved for future use.
        file_path (str): Path to an Excel file containing cell information.
        arbcells (list): Aggregated list of cell coordinates after processing.
        order (list): Order of processing for the different input methods.
        all_wls (list): All wordlines from settings file.
        all_bls (list): All bitlines from settings file.
    """

    def __init__(self, cells=None, wls=None, bls=None, arr=None, file=None, commands=None, settings='settings/default.toml', order=["cells","wordlines","bitlines","file"], run=False): 
        """
        Initializes the Arbitrary_Cells class with various inputs for cell manipulation.
        
        Parameters:
            cells (list, optional): A list of tuples specifying cell coordinates.
            wordlines (list, optional): A list of integers specifying wordlines.
            bitlines (list, optional): A list of integers specifying bitlines.
            array (list, optional): Reserved for future expansion.
            file (str, optional): The path to an Excel file containing cell coordinates.
            settings (str, optional): Path to the TOML configuration file for device settings.
            order (list, optional): The order in which to process the inputs.
        """
        self.cells = cells if cells is not None else []
        self.wordlines = wls if wls is not None else []
        self.bitlines = bls if bls is not None else []
        self.array = arr if arr is not None else []
        self.file_path = file
        self.arbcells = []
        self.order = order

        # Load settings from the specified TOML file.
        with open(settings,'rb') as settings_file:
            settings = tomli.load(settings_file)
            self.all_wls = settings["device"]["all_WLS"]
            self.all_bls = settings["device"]["all_BLS"]

        # Populate the order of operations based on provided inputs.
        for operation in self.order:
            if getattr(self, operation, None) is not None:  
                self.order.append(operation)

        # Process inputs according to the specified order.
        self._process_inputs()

    def _process_inputs(self):
        """
        Processes the inputs (cells, wordlines, bitlines, file) according to the specified order,
        appending the resulting cell coordinates to self.cells.
        """
        for append_next in self.order:
            if append_next == "cells":
                self.arbcells.extend(self.cells)  # Assuming cells is a list of tuples.
            
            elif append_next == "wordlines":
                self._process_wordlines()
            
            elif append_next == "bitlines":
                self._process_bitlines()
            
            elif append_next == "file":
                self._process_file()

    def _process_wordlines(self):
        """Processes wordlines, pairing each with all bitlines, and appends them to self.cells."""
        for wl in self.wordlines:
            for bl in self.all_bls:
                self.arbcells.append((wl,bl))

    def _process_bitlines(self):
        """Processes bitlines, pairing each with all wordlines, and appends them to self.cells."""
        for bl in self.bitlines:
            for wl in self.all_wls:
                self.arbcells.append((wl,bl))

    def _process_file(self):
        """Reads cell coordinates from an Excel file and appends them to self.cells."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"The file at {self.file_path} does not exist.")
        df = read_excel(self.file_path, engine='openpyxl')
        for _, row in df.iterrows():
            self.arbcells.append((row['WL'], row['BL']))

    
    def operation_setup(self, cells, operations):
        """
        operation_setup: A function designed to take keywords and generate a pattern of cells for given functions
        Current kewords are: CHECKERBOARD,  INVERSE_CHECKERBOARD which generate a checkerboard pattern of cells
        """
        
        # Check for checkerboard
        if checker in operations or invchecker in operations:
            rows = set([tpl[0] for tpl in cells])
            cols = set([tpl[1] for tpl in cells])
            height = len(set(rows))
            width = len(set(cols))

        # Get number of cells operated on
        num_cells = len(cells)

        #Repeat cells for number of operations you want to do
        cells = cells * len(operations)

        # Repeat function for every cell in the cells list
        func_raw = [operation for operation in operations for _ in range(num_cells)]   
        func = []
        
        
        # Create a generator expression to iterate over the original list checking for checkerboard
        gen_expr = (
            checkerboard(width=width, height=height,odd=0) if func_raw[i:i+num_cells] == [checker] * num_cells else [func_raw[i]]
            for i in range(len(func_raw))
        )

        func_raw = [item for sublist in gen_expr for item in sublist]
        func_raw = [element for element in func_raw if element != checker]
        
        # Create a generator expression to iterate over the modified list checking for inverse checkerboard
        gen_expr = (
            checkerboard(width=width, height=height,odd=1) if func_raw[i:i+num_cells] == [invchecker] * num_cells else [func_raw[i]]
            for i in range(len(func_raw))    
        )

        # Use list comprehension to flatten the generator expression into a list
        func = [item for sublist in gen_expr for item in sublist]  
        func = [element for element in func if element != invchecker]
        
        # Return the cells and functions lists
        return cells, func




"""
Core functionality of the arbitrary cells file, the arbitrary cells class is 
not yet finished.
"""



def bl_operation(self, nisys, bl, operations):
    cells = []
    for wl in self:
        cells = cells + [("WL_"+str(wl),f"BL_{bl}")]
    cells,func = self.operation_setup(nisys, cells, operations)
    read_array = arb_cells(nisys, cells, funcs=func)
    return read_array

def reset_bl(self,nisys, bl):
    """
    reset_bl: A function to reset the entirety of a bitline given a bitline number (int). Works for all defined wordlines.
    This function takes in a NIRRAM object, and a bitline name (e.g. "BL_0") and returns a list of the resistance 
    values of the cells in that bitline.
    """
    operations = [reset]
    read_array = self.bl_operation(nisys, bl, operations)
    return read_array

def read_bl(self,nisys, bl):
    """
    read_bl: A function to read the entirety of a bitline given a bitline name. Works for all defined wordlines.
    This function takes in a NIRRAM object, and a bitline name (e.g. "BL_0") and returns a list of the resistance 
    values of the cells in that bitline.
    """
    operations = [read]
    read_array = self.bl_operation(nisys, bl, operations)
    return read_array

def set_bl(self,nisys, bl): 
    """
    set_bl: A function to set the entirety of a bitline given a bitline name. Works for all defined wordlines.
    This function takes in a NIRRAM object, and a bitline name (e.g. "BL_0") and returns a list of the resistance 
    values of the cells in that bitline.
    """
    operations = [set]
    read_array = self.bl_operation(nisys, bl, operations)
    return read_array

def read_bls(self,nisys, bls):

    """
    read_bls: A function to read the entirety of a list of bitlines given a bitline name. 
    Works for all defined wordlines/bitlines
    """

    if isinstance(bls,int):
        bls = [bls]
    for bl in bls:
        print(f"BL_{bl}")
        read_array = self.read_bl(nisys, bl)
        print(" ")
    return read_array

def read_die(self,nisys):
    read_array = read_bls(nisys, self.all_bls)
    return read_array  


def arb_cells(nisys, cells, funcs,vwl_range=np.linspace(-2,4,25)):
    cellsave = [("WL_999", "BL_99")]
    read_array = []

    # Decrease relay switching by only switching when wl changes
    # Check if need to switch relays
    for cell, func in zip(cells, funcs):
        wl_name = cell[0]
        if cell != cellsave and cell[0] != cellsave[0]:
            cellsave = cell
            wl, bl, sl = cell[0], cell[1], "SL"+cell[1][2:]

        #Check if it needs to switch bl and sl
        elif cell[0] == cellsave[0] and cell[1] != cellsave[1]:
            cellsave = cell
            bl = cell[1]
            sl = "SL"+cell[1][2:]

        #cells is a list of tuples (wl, bl, sl)
        #save original wls, bls, sls
        wls, bls, sls = (nisys.wls, nisys.bls, nisys.sls)

        #Set the correct realy to NO-COM, get signals for wl, bl, sl
        nisys.wls = [wl]
        nisys.bls = [bl]
        nisys.sls = [sl]

        #Perform the function
        if func == "SET":
            result = nisys.dynamic_set(relayed=True)

        elif func == "FORM":
            result = nisys.dynamic_form(relayed=True)
        
        elif func == "RESET":
            result = nisys.dynamic_reset(relayed=True)
        
        elif func == "READ":
            res_array, cond_array, meas_i_array, meas_v_array = nisys.read(record=True, wl_name = wl_name)
            if not(bl in ["BL_MULTI_READ"]):
                read_array.append(res_array.loc[wl,bl])
            else:
                for res in res_array:
                    read_array.append(res)

        elif func == "MULTI_BL_READ":
            nisys.multi_bl_read(record=True, wl_name = wl_name,wl=wl)
        
        elif func == "NONE":
            pass
        
        else:
            raise ValueError(f"Invalid function {func}")
        
        #restore original wls, bls, sls
        nisys.wls, nisys.bls, nisys.sls = wls, bls, sls

    return read_array



def print_cells(read_dict):
    sorted_dict = sorted(read_dict.items(), key=lambda x: x[1], reverse=True)
    for cell, r in sorted_dict:
        print(f"{cell}: {r/1e3:.3f} kohms")

    


if __name__ == "__main__":
    
    cells = None
    # Get arguments
    parser = argparse.ArgumentParser(description="RESET a chip.")
    parser.add_argument("chip", help="chip name for logging")
    parser.add_argument("device", help="device name for logging")
    args = parser.parse_args()
    polarity = "PMOS"
    
    # Initialize NI system
    # For CNFET: make sure polarity is 
    nisys = NIRRAM(args.chip, args.device, settings="settings/MPW_ProbeCard.toml", polarity=polarity,slow=False)
    nisys.digital.channels["WL_UNSEL"].ppmu_current_limit_range = 2e-6

    bl_sl_idxs = range(8,16)
    nisys.bls = [f"BL_{i}" for i in bl_sl_idxs]
    nisys.sls = [f"SL_{i}" for i in bl_sl_idxs]
    wl = "WL_0"
    nisys.wls = wl
    nisys.multi_set(vbl=2, vsl=-0.5, vwl=-1.5, pw=1000)

    """
    cells = []
    bl_idxs = [8,9,10,11]
    wl_idxs = [0]
    operations =[READ]
    for wl_idx in wl_idxs:
        for bl_idx in bl_idxs:
            cells.append((f"WL_{wl_idx}", f"BL_{bl_idx}"))    
    cells, func = operation_setup(nisys, cells, operations)

    read_array = arb_cells(nisys, cells, funcs=func)
    """
    
    
    # # # reset_bl(nisys,10)
    # operations =[READ]
    # # cells = [("WL_2", "BL_14")]
    # # cells=[('WL_2',"BL_MULTI_READ")]
    
    # cells = []
    # wl_idxs = ALL_WLS
    # for wl_idx in wl_idxs:
    #     cells.append((f"WL_{wl_idx}", f"BL_MULTI_READ"))    
    # cells, func = operation_setup(nisys, cells, operations)



    # if cells is not None:
    #     if cells[0][1] == "BL_MULTI_READ":
    #         assert(polarity == "PMOS"), "BL_MULTI_READ only works for PMOS"
    #         assert FORM not in operations, "BL_MULTI_READ does not support FORM"
    #         cells, func = operation_setup(nisys, cells, operations)
    #         print("---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
    #         read_array=arb_cells(nisys, cells, funcs=func)
    #         print("---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
        
    #     else:
    #         cells, func = operation_setup(nisys, cells, operations)
    #         read_array = arb_cells(nisys, cells, funcs=func)
    # # read_bl(nisys,8)
    # # read_die(nisys)

    nisys.close()


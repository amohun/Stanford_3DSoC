import pdb
from os import getcwd
from sys import path
import sys
import argparse
from dataclasses import dataclass

path.append(getcwd())
from SourceScripts import nirram_abstracted

@dataclass
class paired_cells:
    """ 
    Cells that will be operated on in parallel.
    Typically 1 WL and n BLs. WLS, BLS, and Cells are broken down
    into a list of strings, and bls/wls will match listed cells.
    """
    bls: list
    wls: list
    cells: list

@dataclass
class operations:
    """
    Operations that will be performed in series.
    While different operations can be performaed in parallel,
    this dataclass allows for repetition of operations across cells and
    cells across operations.
    """
    operations: list
    repeat_operations: bool
    repeat_cells: bool

def parse_args():
    parser = argparse.ArgumentParser(description='Stanford 3DSoC Direct Write')
    parser.add_argument('--settings', type=str, default='.\\settings\\MPW_Direct_Write.toml', help='Settings file')
    parser.add_argument('--device', type=str, default='test', help='Device Number')
    parser.add_argument('--chip', type=str, default='test', help='Chip Number')
    parser.add_argument('--type', type=str, default='nmos', help='Type of Device (nmos or pmos)')
    parser.add_argument('--test', type=str, default='Default', help='Test Type (Default, Debug, CSA, Dir_Write, or DNN)')
    parser.add_argument('--comment', type=str, default='', help='Comment for the run')
    parser.add_argument('--debug', type=bool, default=False, help='Debug Mode')
    parser.add_argument('--verbose', type=bool, default=False, help='Verbose Mode')
    return vars(parser.parse_args())


def arbitrary_cells(arb_cells):
    new_cells = []
    for wl in arb_cells.wls:
        for bl in arb_cells.bls:
            new_cells.append((bl,wl))
    arb_cells.cells = arb_cells.cells + new_cells

    bls = [arb_cell[0] for arb_cell in arb_cells.cells]
    wls = [arb_cell[1] for arb_cell in arb_cells.cells]

    return paired_cells(bls=bls, wls=wls, cells=arb_cells.cells)

def arbitrary_operations(functions, cells):
    new_operations = []
    if functions.repeat_operations:
        for operation in functions.operations:
            for _ in cells.cells:
                new_operations.append(operation)
    if functions.repeat_cells:
        cells.cells = cells.cells * len(functions.operations)
    
    functions = new_operations
    return cells, functions


def main():
    #pdb.set_trace()
    test_info = parse_args()

    nirram = nirram_abstracted.NIRRAM(
        chip=test_info["chip"], 
        device=test_info["device"], 
        polarity=test_info["type"].upper(), 
        settings=test_info["settings"], 
        debug_printout=test_info["debug"],
        test_type=test_info["test"],
        additional_info=test_info["comment"]
        )
    
    nirram.dynamic_set(wls=["WL_5"],bls=["BL_0"],print_data=True, record=True,target_res=None,average_resistance=True,debug_printout=False)

if __name__ == '__main__':

    cells = paired_cells(bls=["BL_0"], wls=["WL_5"], cells=[])
    functions = operations(operations=["SET", "RESET"], repeat_operations=True, repeat_cells=True)
    cells = arbitrary_cells(cells)
    cells, functions = arbitrary_operations(functions, cells)
    
    print([cells.bls, cells.wls, cells.cells])
    print([functions.operations, functions.repeat_operations, functions.repeat_cells])
    quit()
    
    main()

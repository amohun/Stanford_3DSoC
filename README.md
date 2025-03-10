# Stanford_3DSoC
A selection of python scripts to use the NI PXIe 6570/6571 to program ReRAM, modified from a directory by Akash Levy and Robert Radway

## Pip environment
Install: nidigital, niswitch, nitclk, numpy, matplotlib

## Project environment config
On the NI System Windows OS the environment can be loaded using ./Source/Scripts/Activate.ps1

## Scripts
- digital_pattern.py: Basic functions for interacting with nidigital and niswitch
    This program serves as a buffer between specific programs and the nidigital library. It also allows for synchronization across the
    PXIe 6570 and PXIe 6571 
- nirram_abstracted.py: Interaction with RRAM/The RRAM array. This program can interact with any RRAM but is tailored for the MPW 3DSoC array
- csa_tb.py: This program runs the CSA testbench files in the settings/patterns folder. It is a brute force approach to running patterns
- convolution_tb.py THis program runs the convolution testbench files in the settings/patterns folder. It is a brute force approach to running patterns.

When running the program, make sure to specify the chip/device you are runnign with.

=======
# Stanford_3DSoC
A selection of python scripts to use the NI PXIe 6570/6571 to program ReRAM, modified from a directory by Akash Levy and Robert Radway
>>>>>>> origin/main

"""Script to perform a read voltage sweep on a chip"""
import argparse
from digitalpattern.nirram import NIRRAM
import pdb
import nidigital
import time
import numpy as np
from os import getcwd
from sys import path

path.append(getcwd())
import SourceScripts.load_settings as load_settings
import SourceScripts.masks as masks
from digital_pattern import DigitalPattern

def print_waveform(results_dict, bl_idxs, si_selectors=False):
    if si_selectors:
        n_csas = 2
    else:
        n_csas = 8
    assert(len(bl_idxs) == n_csas)
    for wl_name in results_dict:
        print(wl_name)
        for idx,bl in enumerate(bl_idxs):
            sa_rdy_waveform = [int(x[f"SA_RDY_{idx}"]) for x in results_dict[wl_name]]
            do_waveform = [int(x[f"DO_{idx}"]) for x in results_dict[wl_name]]
            print(f"SA_RDY_{idx}:\t{sum(sa_rdy_waveform)}")
            print(f"DO_{idx}:\t\t{sum(do_waveform)}")

def col_sel_idx_bls(col_sel_idx,si_selectors):
    if si_selectors:
        n_csas = 2
    else:
        n_csas = 8
    return [f"BL_{32-int(32/n_csas)*(i+1)+col_sel_idx}" for i in range(n_csas)] #from rram_csa_3d_readout_full_tb: The first CSA is connected to RRAM cells <31> to <28>, the second is connected to RRAM cells <27> to <24>, and so on.

def set_and_source_voltage(nisys, voltages, scalar=1):
    for channel in voltages:
        nisys.digital.channels[channel].ppmu_voltage_level = voltages[channel]*scalar
        if channel in ['VDD','VSA','VSS']:
            nisys.digital.channels[channel].ppmu_current_limit_range = 32e-3
        else:
            nisys.digital.channels[channel].ppmu_current_limit_range = 32e-3
        nisys.digital.channels[channel].ppmu_source()
    time.sleep(0.01)

def measure_iv(nisys, sources, channels_to_measure):
    all_channels = list(sources.keys()) + channels_to_measure
    for channel in all_channels:
        nisys.digital.channels[channel].ppmu_aperture_time_units = nidigital.PPMUApertureTimeUnits.SECONDS
        nisys.digital.channels[channel].ppmu_aperture_time = nisys.op["READ"]["aperture_time"]
        print(f"{channel}: {nisys.digital.channels[channel].ppmu_measure(measurement_type=nidigital.PPMUMeasurementType.VOLTAGE)[0]:.1f}V, {nisys.digital.channels[channel].ppmu_measure(measurement_type=nidigital.PPMUMeasurementType.CURRENT)[0]:.2E}A")


# Get arguments
if __name__ == "__main__":
    # Get arguments for the chip and the device
    parser = argparse.ArgumentParser(description="RESET a chip.")
    parser.add_argument("chip", help="chip name for logging")
    parser.add_argument("device", help="device name for logging")
    args = parser.parse_args()
    

    # Initialize the NI-Digital pattern instrument
    digital_patterns = DigitalPattern(settings="settings/MPW_CSA_Test.toml")



    #ensure high Z for non-driving pins
    nisys.digital.termination_mode = nidigital.TerminationMode.VTERM
    for line in ['SA_RDY_0','SA_RDY_1','DO_0','DO_1']:
        nisys.digital.channels[line].termination_mode = nidigital.TerminationMode.VTERM
    for line in nisys.sls:
        nisys.digital.channels[line].termination_mode = nidigital.TerminationMode.VTERM
    for line in nisys.bls:
        nisys.digital.channels[line].termination_mode = nidigital.TerminationMode.VTERM
    
    si_selectors=False
    #if si_selectors, col_sel_idx is hardwired
    col_sel_idx=0
    bls = col_sel_idx_bls(col_sel_idx, si_selectors=si_selectors)    
    
    #WL_0, BL_8 thru BL_15 is formed. so COL_SEL must be 8 thru 15 (group of 8 on the right)
    wl, bl, sl = relay_switch("WL_0", "BL_11", "SL_11", nisys)

    #get IV of voltage sources
    #if 

    sources = {
        "VDD": 5,
        "VSA": 5,
        "VSS": 0,
        "MUX_SEL_CONV_CLK": 0,
        "MUX_SEL_WT": 0,
    }
    
    run_measure_iv=True
    if run_measure_iv:
        test_sources = {
            "RMUX_EN": 5,
            "VREAD": 0.3,
            "SA_EN": 5,
            "WL_UNSEL": 0,
            wl: 0.3,
            "SA_CLK": 5,
            "COL_SEL": 5,
        }
        sources = {**sources, **test_sources}

        sweep=False
        if not sweep:
            set_and_source_voltage(nisys, sources)
            time.sleep(1)
            measure_iv(nisys, sources, channels_to_measure=['SA_RDY_0','SA_RDY_1','DO_0','DO_1'])
        else:
            channel = 'VSA'
            measure_channel = "SA_RDY_1"
            nisys.digital.channels[channel].ppmu_aperture_time_units = nidigital.PPMUApertureTimeUnits.SECONDS
            nisys.digital.channels[channel].ppmu_aperture_time = 0.001
            print(f'{channel}_set,  {channel},  {channel}_I,    {measure_channel}_V,    {measure_channel}_I')
            results={channel:{'V':[],'A':[]},measure_channel:{'V':[],'A':[]}}
            for v in np.arange(0,5.01,0.2):
                sources[channel] = v
                set_and_source_voltage(nisys, sources)
                for chan in [channel, measure_channel]:
                    results[chan]['V']=nisys.digital.channels[chan].ppmu_measure(measurement_type=nidigital.PPMUMeasurementType.VOLTAGE)[0]
                    results[chan]['A']=nisys.digital.channels[chan].ppmu_measure(measurement_type=nidigital.PPMUMeasurementType.CURRENT)[0]
                print(f"{v:.1f},    {results[channel]['V']:.1f}V,   {results[channel]['A']:.2E}A,   {results[measure_channel]['V']:.1f}V,   {results[measure_channel]['A']:.2E}A")
            
    else:
        set_and_source_voltage(nisys, sources)

        #pw max: 65535 cycles
        results_dict = nisys.csa_read(wls=[wl],vread=0.1,vwl=2.2,pw=65535,col_sel_idx=col_sel_idx,vwl_unsel=0,si_selectors=si_selectors)

        #boundary resistor is currently 12.546 kohms (5.646+6.9) at COL_SEL_5 (BL_8+col_sel_idx)
        print_waveform(results_dict,bls,si_selectors=si_selectors)
    set_and_source_voltage(nisys, sources, scalar=0)
    time.sleep(1)

    

    nisys.close()










    def csa_read(
        self,
        wls,
        vread=None,
        vwl=None,
        pw=1,
        col_sel_idx=None,
        vwl_unsel=None,
        si_selectors=True
    ):
        """Perform a READ operation with all 2 or 8 SAs at once. Returns 2-or-8-entry dict (per-SA) of results and associated BLs"""
        # Set the read voltage levels
        vread = (self.op["READ"][self.polarity]["VBL"] - self.op["READ"][self.polarity]["VSL"]) if vread is None else vread
        vwl = self.op["READ"][self.polarity]["VWL"] if vwl is None else vwl
        vwl_unsel = (self.op["READ"][self.polarity]["VWL_UNSEL_OFFSET"] - self.op["READ"][self.polarity]["VSL"]) if vwl_unsel is None else vwl_unsel


        time.sleep(self.op["READ"]["settling_time"]) # let the supplies settle for accurate measurement

        # set voltage levels
        v_rmux_en = 5
        v_col_sel = 5
        self.digital.configure_voltage_levels(0, 1.8, 0.5, 0.7, 0)
        self.digital.channels["VREAD"].configure_voltage_levels(0, vread, 0, vread, 0)
        self.digital.channels["COL_SEL"].configure_voltage_levels(0, v_col_sel, 0, v_col_sel, 0)
        self.digital.channels["RMUX_EN"].configure_voltage_levels(0, v_rmux_en, 0, v_rmux_en, 0)
        
        for wl_i in self.all_wls:
                self.digital.channels[wl_i].configure_voltage_levels(vwl_unsel, vwl, vwl_unsel, vwl, 0)

        # Update the voltages    
        self.digital.commit()
        self.set_pw(pw)

        results_dict = {}
        for wl in wls:
            # Define and setup outputs
            waveform = self.build_CSA_Read_waveform(wl, col_sel_idx, pw,si_selectors)
            self.arbitrary_pulse(waveform, pin_group_name="WLS_COL_SEL", data_variable_in_digipat="wl_col_data")

            # Define and setup inputs
            self.digital.pins["SA_RDY_DO"].create_capture_waveform_parallel("sa_data")

            # Run the pattern and store results
            if si_selectors:
                self.digital.burst_pattern("CSA_Read_Si")
            else:
                self.digital.burst_pattern("CSA_Read")
            wl_results = self.digital.fetch_capture_waveform("sa_data", pw*2)[0]
            wl_results = [wl_results[i] for i in range(0,pw*2)] #convert from memoryview to list
            signals_over_time = self.interpret_csa(wl_results, col_sel_idx, si_selectors)

            # dict(zip(bls,wl_results))
            #wl_results is an int: convert to list of bool
            
            results_dict[wl] = signals_over_time
        
        return results_dict

    def build_CSA_Read_waveform(self, wl, col_sel_idx, pw,si_selectors):
        """Create pulse train for CSA read. Format of bits is [WLS COL_SEL_0 ... COL_SEL_3]."""
        col_sel_cycles_before_wl = 3 #don't change unless you also change CSA_Read.digipat: this is the number of cycles of 'D' before the loop
        #build masks
        wl_mask = [wl==wl_i for wl_i in self.all_wls]
        if si_selectors:
            col_sel_only =  BitVector(bitlist=[False]*len(wl_mask)).int_val()
            col_sel_and_wl = BitVector(bitlist=wl_mask).int_val()
        else:
            col_sel_mask = [False]*4
            col_sel_mask[col_sel_idx] = True
        
            col_sel_only = BitVector(bitlist=([False]*len(wl_mask)+col_sel_mask)).int_val()
            col_sel_and_wl = BitVector(bitlist=(wl_mask + col_sel_mask)).int_val()
        waveform = [col_sel_only]*col_sel_cycles_before_wl + [col_sel_and_wl]*pw*2
        return waveform


    def interpret_csa(self, wl_results, col_sel_idx, si_selectors):
        """Interpret DO and SA_RDY signals by reading DO when corresponding SA_RDY goes high"""
        if si_selectors:
            n_csas=2
        else:
            n_csas=8
        #BL names used only for logging purposes. formula from how CSAs are hardwired to BLs
        bls = [f"BL_{int(32/n_csas*i+col_sel_idx)}" for i in range(n_csas)]

        #value of wl_result[0] is 1 if DO_7 is high and 2^15 if SA_RDY_0 is high. Defined in the pinmap
        name_order = [f"DO_{n_csas-1-i}" for i in range(n_csas)] + [f"SA_RDY_{n_csas-1-i}" for i in range(n_csas)]

        signals_over_time = []
        for timestep in wl_results:
            signal_values = [bool(timestep & (1<<i)) for i in range(16)]
            signals = dict(zip(name_order, signal_values))
            signals_over_time.append(signals)
        return signals_over_time
    
        #TODO: read DO when corresponding SA_RDY goes high
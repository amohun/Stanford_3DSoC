        # set body voltages
        if self.body is not None:
            for body_i, vbody_i in self.body.items(): self.ppmu_set_vbody(body_i, vbody_i)

        # Set address and all voltages to 0
        for bl in self.all_bls: self.set_vbl(bl, 0.0, 0.0)
        for sl in self.all_sls: self.set_vsl(sl, 0.0, 0.0)
        for wl in all_wls: self.set_vwl(wl, 0.0, 0.0)
        
        for digital in self.digital:
            digital.commit()

    def read_1tnr(        
            self,
        vbl=None,
        vsl=None,
        vwl=None,
        vwl_unsel_offset=None,
        vb=None,
        record=False,
        check=True,
        dynam_read=False,
        wl_name = None
        ):
            print("No 1TNR Read Functionality, will be implemented in the future")
            # ============================= #
            # TODO: 1TNR Read Functionality #
            # ============================= #
            return None


    def dynamic_pulse(
        self,
        mode="SET",
        print_data=True,
        record=True,
        target_res=None, # target res, if None will use value in settings
        is_1tnr=False,
        bl_selected=None, # select specific bl for 1TNR measurements
        relayed=False,
        debug = False,
    ):
        
        """ 
        Performs SET pulses in increasing fashion until resistance reaches
        target_res (either input or in the `target_res` config).
        This will try to SET ALL CELLS in self.bls and self.wls.
        Returns tuple (res, cond, meas_i, meas_v, success).
        """
        datafile_path = self.settings["path"]["data_header"]+"set-file_"+ datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + str(self.chip) + "_" + str(self.device) + ".csv"

        #Record the resistance versus voltages and pulse widths in csv
        
        with open(datafile_path, "a", newline="") as resfile:
            writer = csv.writer(resfile)
            writer.writerow(["VWL", "VBL", "VSL", "PW", "Res"])

            # Get settings
            cfg = self.op[mode][self.polarity]
            target_res = target_res if target_res is not None else self.target_res[mode]

            if self.relays is not None:
                wls,_,_ = self.relay_switch(self.wls, zero_rows=self.zero_rows,NC_rows=self.NC_rows)
                all_wls = self.settings["device"]["WL_INS"]
                mask = RRAMArrayMask(wls, self.bls, self.sls, all_wls, self.all_bls, self.all_sls, self.polarity)
            else:   
                mask = RRAMArrayMask(self.wls, self.bls, self.sls, self.all_wls, self.all_bls, self.all_sls, self.polarity)
            
            # select read method
            read_pulse = self.read_1tnr if is_1tnr else self.read

            # Iterative pulse-verify
            success = False
            
            if mode == "SET" or mode == "FORM":
                # If we are running a set operation, we iterate the bit line voltage, 
                # keeping source line constant
                vbl_start = cfg["VBL_start"]
                vbl_stop = cfg["VBL_stop"]
                vbl_step = cfg["VBL_step"]

                vsl_start = vsl
                vsl_stop = vsl + 1
                vsl_step = 2
            
                pulsetype = "SET"

            elif mode == "RESET":
                if self.debug_printout or debug:
                    print("Performing Dynamic RESET")
                # If we are running a reset operation, we iterate the source line voltage, 
                # keeping bit line constant
                vsl_start = cfg["VSL_start"]
                vsl_stop = cfg["VSL_stop"]
                vsl_step = cfg["VSL_step"]

                vbl_start = vbl
                vbl_stop = vbl + 1
                vbl_step = 2

                pulsetype = "RESET"
            
            else:
                raise NIRRAMException(f"Invalid mode: {mode}")
            
            if self.debug_printout or debug:
                    print(f"Performing Dynamic {mode}")
            
            for vsl in np.arrange(vsl_start, vsl_stop, vsl_step):
                for vbl in np.arange(vbl_start, vbl_stop, vbl_step):
                    for pw in np.arange(cfg["PW_start"], cfg["PW_stop"], cfg["PW_steps"]):
                        for vwl in np.arange(cfg["VWL_SET_start"], cfg["VWL_SET_stop"], cfg["VWL_SET_step"]):
                            self.write_pulse(
                                mask,
                                mode=pulsetype,
                                bl_selected=bl_selected, # specific selected BL for 1TNR
                                vbl=vbl,
                                vsl=vsl,
                                vwl=vwl,
                                pulse_len=int(pw),
                            )
                            self.ppmu_all_pins_to_zero()
                            # pdb.set_trace()
                            
                            # use settling if parameter present, to discharge parasitic cap
                            if "settling_time" in self.op[mode]:
                                time.sleep(self.op[mode]["settling_time"])

                            # read result resistance
                            res_array1, cond_array1, meas_i_array1, meas_v_array1 = read_pulse()
                            res_array2, cond_array2, meas_i_array2, meas_v_array2 = read_pulse()
                            res_array3, cond_array3, meas_i_array3, meas_v_array3 = read_pulse()
                            
                            res_array = pd.add(res_array1, res_array2, res_array3)/3
                            cond_array = None
                            meas_i_array = (meas_i_array1 + meas_i_array2 + meas_i_array3)/3
                            meas_v_array = (meas_v_array1 + meas_v_array2 + meas_v_array3)/3
                            #print(res_array)
                            
                            if bl_selected is None: # use array success condition: all in array must hit target
                                for wl_i in self.wls:
                                    for bl_i in self.bls:
                                        if bl_i == "BL_MULTI_READ":
                                            for res in res_array:
                                                if (res <= target_res) and (mode != "RESET"):
                                                    print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                                    return None
                                                elif (res >= target_res) and (mode == "RESET"):
                                                    print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                                    return None
                                        else: 
                                            writer.writerow([vwl,vbl,vsl, pw, res_array.loc[wl_i, bl_i]])
                                            print(f"{res_array.loc[wl_i,bl_i]}")
                                            
                                            if ((res_array.loc[wl_i, bl_i] <= target_res) & mask.mask.loc[wl_i, bl_i]) and (mode != "RESET"):
                                                mask.mask.loc[wl_i, bl_i] = False

                                            elif ((res_array.loc[wl_i, bl_i] >= target_res) & mask.mask.loc[wl_i, bl_i]) and (mode == "RESET"):
                                                mask.mask.loc[wl_i, bl_i] = False
                                success = (mask.mask.to_numpy().sum()==0)
                            
                            else: # 1TNR success condition: check if selected 1tnr cell hit target
                                success = True
                                if mode == "SET" or mode == "RESET":
                                    for wl_i in self.wls:
                                        if (res_array.loc[wl_i, bl_selected] > target_res) & mask.mask.loc[wl_i, bl_selected]:
                                            success = False
                                            break
                                elif mode == "RESET":
                                    for wl_i in self.wls:
                                        if (res_array.loc[wl_i, bl_selected] < target_res) & mask.mask.loc[wl_i, bl_selected]:
                                            success = False
                                            break

                            if success:
                                print(f"PW = {pw}, Vwl = {vwl}, VBL-VSL = {vbl-vsl}")
                                break
                        if success:
                            break
                    if success:
                        break
            
            # report final cell results
            all_data = []
            for wl in self.wls:
                for bl in self.bls:
                    if not bl=="BL_MULTI_READ":
                        cell_success = res_array.loc[wl,bl] <= target_res
                        cell_data = [self.chip, self.device, mode, wl, bl, res_array.loc[wl,bl], cond_array.loc[wl,bl], meas_i_array.loc[wl,bl], meas_v_array.loc[wl,bl], vwl, vsl, vbl, pw, cell_success]
                        if print_data: print(cell_data)
                        if record: self.datafile.writerow(cell_data)
                        all_data.append(cell_data)
                return all_data
            return None

    def dynamic_form(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(
            mode="FORM",
            target_res=target_res,
            is_1tnr=is_1tnr,
            bl_selected=bl_selected,
            relayed=relayed,
            debug=debug,
        )  
    
    def dynamic_set(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(mode="SET", target_res=target_res,is_1tnr=is_1tnr, bl_selected=bl_selected, relayed=relayed, debug=debug)

    def dynamic_reset(
        self,
        target_res=None,
        is_1tnr=False,
        bl_selected=None,
        relayed=False,
        debug=False,
    ):
        return self.dynamic_pulse(mode="RESET", target_res=target_res,is_1tnr=is_1tnr, bl_selected=bl_selected, relayed=relayed, debug=debug)
    
    def multi_set(self, vbl, vsl, vwl, pw):
        mask = RRAMArrayMask(self.wls, self.bls, self.sls, self.all_wls, self.all_bls, self.all_sls, self.polarity)
        self.set_pulse(
            mask,
            vbl=vbl,
            vsl=vsl,
            vwl=vwl,
            pulse_len=int(pw)
    )



    def pulse(self, mask, pulse_len=10, prepulse_len=50, postpulse_len=50, max_pulse_len=10000, wl_first=True):
        """Create waveform for directly contacting the array BLs, SLs, and WLs, then output that waveform"""
        waveforms, pulse_width = self.build_waveforms(mask, pulse_len, prepulse_len, postpulse_len, max_pulse_len, wl_first)
        
        #WL_PULSE_DEC3.digipat or PULSE_MPW_ProbeCard.digipat as template file
        
        if self.pulse_pingroups is None:
            raise NIRRAMException("No pulse pin groups specified")
        for pingroup in self.pulse_pingroups:
            self.arbitrary_pulse(waveforms[self.pulse_pingroups.index(pingroup)], pin_group_name=pingroup, data_variable_in_digipat=f"{pingroup}_data", pulse_width=pulse_width)
        self.digital.burst_pattern("PULSE_MPW_ProbeCard")
        return

    """ Need to figure out how to get the pattern pulse to work with NI-Tclk Sync"""

    def arbitrary_pulse(self, waveform, pin_group_name, data_variable_in_digipat,pulse_width=None):
        broadcast = nidigital.SourceDataMapping.BROADCAST
        self.digital[self.pulse_pingroups.index(pin_group_name)].pins[pin_group_name].create_source_waveform_parallel(data_variable_in_digipat, broadcast)
        self.digital[self.pulse_pingroups.index(pin_group_name)].write_source_waveform_broadcast(data_variable_in_digipat, waveform)
        if pulse_width:
            self.set_pw(pulse_width)
        return
    
    def build_waveforms(self, mask, pulse_len, prepulse_len, postpulse_len, max_pulse_len, wl_first, debug_printout = None):
        
        """Create pulse train. Format of bits is [BL SL] and . For an array
        with 2 BLs, 2 SLs, and 2 WLs, the bits are ordered:
            [ BL0 BL1 SL0 SL1 ], [ WL0 WL1 ]
        """
        
        if debug_printout is None:
            debug_printout = self.debug_printout

        #print(f"pulse_len = {pulse_len}, pulse_len < {prepulse_len}, max_pulse_len = {max_pulse_len}")
        if len(self.digital) > 1:
            bl_bits_offset = len(self.all_sls)
            sl_bits_offset = 0
        else:
            bl_bits_offset = len(self.all_wls) + len(self.all_sls)
            sl_bits_offset = len(self.all_wls)
        
        waveform = []
        if len(self.digital) == 1:
            for (wl_mask, bl_mask, sl_mask) in mask.get_pulse_masks():
                
                if debug_printout:
                    print(f"wl_mask = {wl_mask}")
                    print(f"bl_mask = {bl_mask}")
                    print(f"sl_mask = {sl_mask}")

                
                if not wl_first:
                    wl_pre_post_bits = BitVector(bitlist=(wl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    data_prepulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_pre_post_bits
                    data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_mask_bits
                    data_postpulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)  + wl_pre_post_bits
                else: 
                    bl_pre_post_bits = BitVector(bitlist=(bl_mask & False)).int_val()
                    sl_pre_post_bits = BitVector(bitlist=(sl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    data_prepulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset) + wl_mask_bits
                    data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset) + wl_mask_bits
                    data_postpulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)  + wl_mask_bits
            
                if debug_printout:
                    print(f"data_prepulse = {data_prepulse:b}")
                    print(f"data = {data:b}")
                    print(f"data_postpulse = {data_postpulse:b}")

                waveform += [data_prepulse for i in range(prepulse_len)] + [data for i in range(pulse_len)] + [data_postpulse for i in range(postpulse_len)]
            
            

            #print waveform for debugging
            if debug_printout:
                for timestep in waveform:
                    print(bin(timestep))

            # zero-pad rest of waveform
            waveform += [0 for i in range(max_pulse_len*len(self.all_wls) - len(waveform))]
            pulse_width = prepulse_len + pulse_len + postpulse_len
            return waveform, pulse_width

        else:
            blsl_waveform = []
            wl_waveform = []
            waveforms = []
            for (wl_mask, bl_mask, sl_mask) in mask.get_pulse_masks():
                
                if debug_printout:
                    print(f"wl_mask = {wl_mask}")
                    print(f"bl_mask = {bl_mask}")
                    print(f"sl_mask = {sl_mask}")

                
                if not wl_first:
                    wl_pre_post_bits = BitVector(bitlist=(wl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    blsl_data_prepulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data_prepulse = wl_pre_post_bits
                    blsl_data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data = wl_mask_bits
                    blsl_data_postpulse = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)
                    wl_data_postpulse = wl_pre_post_bits

                else: 
                    bl_pre_post_bits = BitVector(bitlist=(bl_mask & False)).int_val()
                    sl_pre_post_bits = BitVector(bitlist=(sl_mask & False)).int_val()

                    wl_mask_bits = BitVector(bitlist=wl_mask).int_val()
                    bl_mask_bits = BitVector(bitlist=bl_mask).int_val()
                    sl_mask_bits = BitVector(bitlist=sl_mask).int_val()

                    blsl_data_prepulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)
                    wl_data_prepulse = wl_mask_bits
                    
                    blsl_data = (bl_mask_bits << bl_bits_offset) + (sl_mask_bits << sl_bits_offset)  
                    wl_data = wl_mask_bits
                    
                    blsl_data_postpulse = (bl_pre_post_bits << bl_bits_offset) + (sl_pre_post_bits << sl_bits_offset)
                    wl_data_postpulse = wl_mask_bits
            
                if debug_printout:
                    print(f"blsl_data_prepulse = {blsl_data_prepulse:b}")
                    print(f"blsl_data_prepulse = {wl_data_prepulse:b}")
                    print(f"wl_data = {blsl_data:b}")
                    print(f"wl_data = {wl_data:b}")
                    print(f"blsl_data_postpulse = {blsl_data_postpulse:b}")
                    print(f"wl_data_postpulse = {wl_data_postpulse:b}")

                blsl_waveform += [blsl_data_prepulse for i in range(prepulse_len)] + [blsl_data for i in range(pulse_len)] + [blsl_data_postpulse for i in range(postpulse_len)]
                wl_waveform += [wl_data_prepulse for i in range(prepulse_len)] + [wl_data for i in range(pulse_len)] + [wl_data_postpulse for i in range(postpulse_len)]
                waveforms.append(blsl_waveform)
                waveforms.append(wl_waveform)

            #print waveform for debugging
            if debug_printout:
                for timestep in waveform:
                    print(bin(timestep))

            # zero-pad rest of waveform
            for waveform in waveforms:
                waveform += [0 for i in range(max_pulse_len*len(self.all_wls) - len(waveform))]
            pulse_width = prepulse_len + pulse_len + postpulse_len
            return waveforms, pulse_width

    def set_pw(self, pulse_width):
        """Set pulse width"""
        pw_register = nidigital.SequencerRegister.REGISTER0
        self.digital.write_sequencer_register(pw_register, pulse_width)        

if __name__ == "__main__":
    print("Hello World!")
    pass
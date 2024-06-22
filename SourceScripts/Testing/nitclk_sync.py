import nidigital
import nitclk
import time
import os
import sys
import pdb
sys.path.append(os.getcwd())


# Initialize the NI-Digital pattern instrument

# Get Both Sessions
session1 = nidigital.Session("PXI6571Slot4")
session2 = nidigital.Session("PXI6571Slot5")
session3 = nidigital.Session("PXI6570Slot8")



session_list = [session1, session2, session3]

for session in session_list:
    session.selected_function = nidigital.SelectedFunction.DISCONNECT

specs_filename = os.path.join('settings/Stanford_3DSoC/MPW_3DSoC.specs')

bl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_BL.digilevels')
sl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_SL.digilevels')
wl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_WL.digilevels')

levels = [bl_levels_filename, sl_levels_filename, wl_levels_filename]


bl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_BL.digitiming')
sl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_SL.digitiming')
wl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_WL.digitiming')

timing = [bl_timing_filename, sl_timing_filename, wl_timing_filename]

bl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_BL.pinmap')
sl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_SL.pinmap')
wl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_WL.pinmap')

pinmap = [bl_pinmap_filename, sl_pinmap_filename, wl_pinmap_filename]

bl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_BL.digipat')
sl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_SL.digipat')
wl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_WL.digipat')

pattern = [bl_pattern_filename, sl_pattern_filename, wl_pattern_filename]

channel_names = ["BL_0", "SL_0", "WL_IN_0"]
start_labels = ["MPW_SyncTest_BL", "MPW_SyncTest_SL", "MPW_SyncTest_WL"]
for num, session in enumerate(session_list):
    
    session.load_pin_map(pinmap[num])
    session.create_time_set("sync")
    session.configure_time_set_period("sync", 2e-5)
    session.unload_all_patterns()
    session.load_pattern(pattern[num])
    session.load_specifications_levels_and_timing(specs_filename, levels[num], timing[num])
    session.apply_levels_and_timing(levels[num], timing[num])
    session.channels[channel_names[num]].configure_voltage_levels(0,1,0,1,0)
    session.start_label = start_labels[num]
    session.selected_function = nidigital.SelectedFunction.DIGITAL


# session1.selected_function = nidigital.SelectedFunction.DIGITAL
# session1.load_pin_map(bl_pinmap_filename)
# session1.create_time_set("sync")
# session1.configure_time_set_period("sync", 2e-5)
# session1.channels["BL_0"].configure_voltage_levels(0,2,0,2,0)
# session1.unload_all_patterns()
# session1.load_pattern(bl_pattern_filename)
# session1.load_specifications_levels_and_timing(specs_filename, bl_levels_filename, bl_timing_filename)
# session1.apply_levels_and_timing(bl_levels_filename, bl_timing_filename)
# # session1.start_trigger_type = nidigital.TriggerType.NONE
# session1.start_label = "MPW_SyncTest_BL"
# session1.commit()

# # session1.initiate()
# # session1.send_software_edge_trigger(nidigital.SoftwareTrigger.START,"")
# session2.selected_function = nidigital.SelectedFunction.DIGITAL
# session2.load_pin_map(sl_pinmap_filename)
# session2.create_time_set("sync")
# session1.configure_time_set_period("sync", 2e-5)
# session2.channels["SL_0"].configure_voltage_levels(0,2,0,2,0)
# session2.unload_all_patterns()
# session2.load_pattern(sl_pattern_filename)
# session2.load_specifications_levels_and_timing(specs_filename, sl_levels_filename, sl_timing_filename)
# session2.apply_levels_and_timing(sl_levels_filename, sl_timing_filename)
# session2.start_label = "MPW_SyncTest_SL"
# session2.commit()

# session3.selected_function = nidigital.SelectedFunction.DIGITAL
# session3.load_pin_map(wl_pinmap_filename)
# session3.create_time_set("sync")
# session3.configure_time_set_period("sync", 2e-5)
# session3.channels["WL_IN_0"].configure_voltage_levels(0,2,0,2,0)
# session3.unload_all_patterns()
# session3.load_pattern(wl_pattern_filename)
# session3.load_specifications_levels_and_timing(specs_filename, wl_levels_filename, wl_timing_filename)
# session3.apply_levels_and_timing(wl_levels_filename, wl_timing_filename)
# session3.start_label = "MPW_SyncTest_WL"
# session3.commit()

# session_list = [session1, session2, session3]

for i in range(100):
    nitclk.configure_for_homogeneous_triggers(session_list)
    nitclk.synchronize(session_list,200e-8)
    nitclk.initiate(session_list)
    nitclk.wait_until_done(session_list,10)


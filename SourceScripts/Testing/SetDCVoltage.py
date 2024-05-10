import nidigital
import nitclk
import time
import os
import sys
import pdb
sys.path.append(os.getcwd())
from SourceScripts.nirram import NIRRAM

# Initialize the NI-Digital pattern instrument

# nisys = NIRRAM("chip", "test_sync", settings="settings/MPW_Sync_Test.toml", polarity="PMOS",test_type="Debug", additional_info="Debugging NIRRAM for Clock Sync")

wl = "WL_IN_0"
bl = "BL_0"
sl = "SL_0"

# Get Both Sessions
session1 = nidigital.Session("PXI6571Slot4")
session2 = nidigital.Session("PXI6571Slot5")
session3 = nidigital.Session("PXI6570Slot8")

session_list = [session1, session2, session3]

specs_filename = os.path.join('settings/Stanford_3DSoC/MPW_3DSoC.specs')

bl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_BL.digilevels')
sl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_SL.digilevels')
wl_levels_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_WL.digilevels')

bl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_BL.digitiming')
sl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_SL.digitiming')
wl_timing_filename = os.path.join('settings/Stanford_3DSoC/MPW_SyncTest_WL.digitiming')

bl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_BL.pinmap')
sl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_SL.pinmap')
wl_pinmap_filename = os.path.join('settings/pinmap/MPW_SyncTest_WL.pinmap')

bl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_BL.digipat')
sl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_SL.digipat')
wl_pattern_filename = os.path.join('settings/patterns/MPW_SyncTest_WL.digipat')


session1.load_pin_map(bl_pinmap_filename)
session1.load_pattern(bl_pattern_filename)
session1.load_specifications_levels_and_timing(specs_filename, bl_levels_filename, bl_timing_filename)
session1.apply_levels_and_timing(bl_levels_filename, bl_timing_filename)
# session1.start_trigger_type = nidigital.TriggerType.NONE
session1.start_label = "MPW_SyncTest_BL"

# session1.initiate()
# session1.send_software_edge_trigger(nidigital.SoftwareTrigger.START,"")

session2.load_pin_map(sl_pinmap_filename)
session2.load_pattern(sl_pattern_filename)
session2.load_specifications_levels_and_timing(specs_filename, sl_levels_filename, sl_timing_filename)
session2.apply_levels_and_timing(sl_levels_filename, sl_timing_filename)
session2.start_label = "MPW_SyncTest_SL"

session3.load_pin_map(wl_pinmap_filename)
session3.load_pattern(wl_pattern_filename)

session3.load_specifications_levels_and_timing(specs_filename, wl_levels_filename, wl_timing_filename)
session3.apply_levels_and_timing(wl_levels_filename, wl_timing_filename)
session3.start_label = "MPW_SyncTest_WL"

for i in range(1000):
    nitclk.configure_for_homogeneous_triggers(session_list)
    nitclk.synchronize(session_list,200e-8)
    nitclk.initiate(session_list)
    nitclk.wait_until_done(session_list,10)
quit()
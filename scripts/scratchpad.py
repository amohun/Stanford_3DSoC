

# Get the pins sorted by session
# Replace any relayed pins with input signal
# - Have list of pingroup names sorted by session
# - have a list of pingroup names sorted by when they ware high
# - That is used to get a list of masks for when in the pulse pins are written to
# - Time based mapping of every pingroup (may not be necessary if done for every pin)

""" The Pulse Function Uses """
# 1) Masks of selected pins in each session
# 2) Masks for when pingroups are high
# 3) The pulse length for how long the function pulses

# Loop over each pulse length and corresponding pulse group
for pulse_len, step_included in zip(pulse_lens, pulse_groups):
    # Create the waveform for the current group using bitwise AND operation
    group_waveform = group_waveform + [BitVector(bitlist = group_masks & step_included[session_num][group_num]).int_val()]*pulse_len

"""
For each step in the pulse, it adds the pulsed values to be included, keeping the rest at zero.
"""
# Iterate through session by session
for session_num, session_masks in enumerate(masks):
    session_waveforms = []
    for group_num, group_masks in enumerate(session_masks):
        group_waveforms = []
    
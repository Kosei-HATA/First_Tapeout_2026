# overload detector: OVL_NOW from the count including the frame being taken in its input cycle (en), i.e. it rises
# (and falls) at the start of the code's input cycle instead of at the edge that takes the code
EDITS = [("eeg_ovl.sv", "assign ovl_now = (cnt >= OVL_THRESHOLD);", "assign ovl_now = ((en ? cnt_nxt : cnt) >= OVL_THRESHOLD);")]

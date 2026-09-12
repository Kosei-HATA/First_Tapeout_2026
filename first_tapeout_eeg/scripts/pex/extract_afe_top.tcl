# Magic extraction for eeg_afe_top (sky130A) — LVS netlist + .ext parasitic DB.
# Run from GDSII/pex/ so the .ext files land there:
#   cd GDSII/pex && ../../tools/magic/bin/magic -dnull -noconsole \
#       ../../scripts/pex/extract_afe_top.tcl
tech load /Users/noah/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.tech/magic/sky130A.tech
drc off
gds read /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/GDSII/eeg_afe_top.gds
load eeg_afe_top
extract do local
extract all
ext2spice lvs
ext2spice -o /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/GDSII/pex/eeg_afe_top.extracted.spice
ext2spice cthresh 0
exit

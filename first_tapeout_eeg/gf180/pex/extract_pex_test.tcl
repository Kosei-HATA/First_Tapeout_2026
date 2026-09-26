# Magic extraction for gf180_pex_test (GF180MCU-D) - LVS netlist + .ext parasitic DB.
# Run from gf180/pex/:
#   cd gf180/pex && ../../tools/magic/bin/magic -dnull -noconsole \
#       ../../gf180/pex/extract_pex_test.tcl
tech load /Users/noah/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/magic/gf180mcuD.tech
drc off
gds read /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/gds/gf180_pex_test.gds
load GF180_PEX_TEST
extract do local
extract all
ext2spice lvs
ext2spice -o /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/pex/gf180_pex_test.extracted.spice
ext2spice cthresh 0
exit

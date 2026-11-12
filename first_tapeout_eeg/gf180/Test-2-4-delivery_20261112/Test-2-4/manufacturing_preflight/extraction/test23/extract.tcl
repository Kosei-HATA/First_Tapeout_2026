drc off
crashbackups stop
gds read pad.gds
load pad_dut
select top cell
extract do local
extract all
ext2spice hierarchy off
ext2spice format ngspice
ext2spice cthresh 0.001
ext2spice merge conservative
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice -o pad_pex.spice
quit -noprompt

drc off
crashbackups stop
gds read input.gds
load two_mim_internal
select top cell
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
ext2spice hierarchy on
ext2spice format ngspice
ext2spice cthresh 0
ext2spice merge none
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice extresist off
ext2spice -o cap_hier.spice
ext2spice extresist on
ext2spice -o rc_hier.spice
quit -noprompt

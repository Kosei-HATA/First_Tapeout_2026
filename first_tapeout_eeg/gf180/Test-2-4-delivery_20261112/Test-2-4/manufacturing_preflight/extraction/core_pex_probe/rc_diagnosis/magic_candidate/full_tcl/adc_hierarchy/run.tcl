drc off
crashbackups stop
gds read input.gds
load adc_c2
select top cell
extract do local
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
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
ext2spice -o cap.spice
ext2spice extresist on
ext2spice -o rc.spice
quit -noprompt

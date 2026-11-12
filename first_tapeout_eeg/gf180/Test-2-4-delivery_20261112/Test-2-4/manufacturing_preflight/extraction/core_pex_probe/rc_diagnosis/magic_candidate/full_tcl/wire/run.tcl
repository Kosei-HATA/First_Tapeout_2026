drc off
crashbackups stop
gds read input.gds
load wire
select top cell
box values 1um 0.5um 1um 0.5um
label A center metal1
port make 1
box values 99um 0.5um 99um 0.5um
label B center metal1
port make 2

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
ext2spice -o cap.spice
ext2spice extresist on
ext2spice -o rc.spice
quit -noprompt

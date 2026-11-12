drc off
crashbackups stop
gds read input.gds
load mim_only
select top cell
box values 0.1um 0.1um 0.1um 0.1um
label TOP center mimcap
port make 1
box values -0.5um -0.5um -0.5um -0.5um
label BOT center metal4
port make 2

extresist threshold 100000
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
ext2spice -o cap_ports.spice
ext2spice extresist on
ext2spice -o rc_ports.spice
quit -noprompt

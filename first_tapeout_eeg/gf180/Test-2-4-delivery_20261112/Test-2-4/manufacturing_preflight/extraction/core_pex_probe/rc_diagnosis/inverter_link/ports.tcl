drc off
crashbackups stop
gds read input.gds
load inverter_link
select top cell
box values 0.87um 1.7um 0.87um 1.7um
label IN center metal1
port make 1
box values 101.43um 1.7um 101.43um 1.7um
label OUT center metal1
port make 2
box values 10.1um 1.7um 10.1um 1.7um
label AG1 center metal2
port make 3
box values 89.9um 1.7um 89.9um 1.7um
label AG2 center metal2
port make 4
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
ext2spice -o cap_ports.spice
ext2spice extresist on
ext2spice -o rc_ports.spice
quit -noprompt

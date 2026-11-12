ext2spice hierarchy on
ext2spice format ngspice
ext2spice cthresh 0
ext2spice merge none
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice extresist off
ext2spice -o cap.spice coupled_wires.ext
ext2spice extresist on
ext2spice -o rc.spice coupled_wires.ext
quit -noprompt

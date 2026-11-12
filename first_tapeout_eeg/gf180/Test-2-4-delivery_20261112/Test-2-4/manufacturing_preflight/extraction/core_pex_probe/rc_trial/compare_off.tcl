ext2spice hierarchy off
ext2spice extresist off
ext2spice format ngspice
ext2spice cthresh 0.001
ext2spice merge none
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice -o rc_disabled_flat.spice adc_c2.ext
quit -noprompt


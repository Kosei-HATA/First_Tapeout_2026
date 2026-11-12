drc off
crashbackups stop
gds read adc_c2.gds
load adc_c2
select top cell
extract do local
extract all
ext2spice hierarchy on
ext2spice format ngspice
ext2spice cthresh 0.001
ext2spice merge none
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice -o adc_c2_cap.spice
quit -noprompt

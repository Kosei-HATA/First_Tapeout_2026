# Magic script to extract SPICE netlist from GDS
tech load $::env(PDK_ROOT)/sky130A/libs.tech/magic/sky130A.tech
drc off
gds read /work/gds/opamp_adc.gds
load OPAMP_ADC_0
extract do local
extract all
ext2spice lvs
ext2spice -o /work/lvs_work/opamp_adc.extracted.spice
exit

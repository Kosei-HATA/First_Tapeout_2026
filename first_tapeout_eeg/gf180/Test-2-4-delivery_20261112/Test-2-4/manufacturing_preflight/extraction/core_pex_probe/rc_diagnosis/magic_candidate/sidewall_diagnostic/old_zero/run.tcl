tech load /work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis/magic_candidate/sidewall_diagnostic/old_zero/gf180mcuD.tech
drc off
crashbackups stop
gds read input.gds
load adc_flat
select top cell
box values 1.1um 0.5um 1.1um 0.5um
label TOP center metal4
port make 1
box values 0.5um 3.5um 0.5um 3.5um
label BOT center metal4
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

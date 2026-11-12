drc off
crashbackups stop
gds read labeled.gds
load eeg_adc_clk
select top cell
box values 12.24um 83.2um 12.24um 83.2um
label CHOP1 center metal3
port make 1
box values 27.44um 83.2um 27.44um 83.2um
label CIA center metal3
port make 2
box values 42.64000000000001um 83.2um 42.64000000000001um 83.2um
label NCIA center metal3
port make 3
box values 57.84um 83.2um 57.84um 83.2um
label CIB center metal3
port make 4
box values 73.03999999999999um 83.2um 73.03999999999999um 83.2um
label NCIB center metal3
port make 5
box values 88.24um 83.2um 88.24um 83.2um
label CDA center metal3
port make 6
box values 103.44um 83.2um 103.44um 83.2um
label NCDA center metal3
port make 7
box values 118.64um 83.2um 118.64um 83.2um
label CDB center metal3
port make 8
box values 133.84um 83.2um 133.84um 83.2um
label NCDB center metal3
port make 9
box values 144.20000000000002um 2um 144.20000000000002um 2um
label VDD center metal3
port make 10
box values 1.6um 2um 1.6um 2um
label VSS center metal3
port make 11
extract style ngspice(lrlc)
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

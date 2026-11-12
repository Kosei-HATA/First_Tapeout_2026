drc off
crashbackups stop
gds read actual.gds
load gf180mcu_fd_io__dvdd
select top cell
extract do local
extract all
ext2spice lvs
ext2spice hierarchy off
ext2spice global off
ext2spice scale off
ext2spice subcircuit top on
ext2spice -o actual.spice
quit -noprompt

drc off
crashbackups stop
gds read ../io_asig_lvs/actual.gds
load gf180mcu_fd_io__asig_5p0
select top cell
extract do local
extract all
ext2spice lvs
ext2spice hierarchy off
ext2spice global off
ext2spice -o actual.spice
quit -noprompt

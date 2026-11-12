from pathlib import Path
import re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction');o=p/'io_asig_magic';o.mkdir(exist_ok=True)
name='gf180mcu_fd_io__asig_5p0';ref=Path('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/spice/gf180mcu_fd_io.spice').read_text();s=re.search(r'(?im)^\.SUBCKT\s+'+name+r'\b.*?^\.ENDS\s*$',ref,re.S).group(0);(o/'reference.spice').write_text(s+'\n')
(o/'extract.tcl').write_text('''drc off
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
''')

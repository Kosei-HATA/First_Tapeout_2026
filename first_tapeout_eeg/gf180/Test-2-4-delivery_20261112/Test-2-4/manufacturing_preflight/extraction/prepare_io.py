from pathlib import Path
import klayout.db as k,json,re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction');l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');names=[c.name for c in l.each_cell() if 'asig' in c.name.lower()];print(names)
name='gf180mcu_fd_io__asig_5p0';c=l.cell(name);assert c is not None
out=p/'io_asig_lvs';out.mkdir(exist_ok=True);d=k.Layout();d.dbu=l.dbu;t=d.create_cell(name);t.copy_tree(c);d.write(str(out/'actual.gds'))
cdl=Path('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/cdl/gf180mcu_fd_io.cdl').read_text();m=re.search(r'(?im)^\.SUBCKT\s+'+name+r'\b.*?^\.ENDS\s*$',cdl,re.S);assert m;(out/'reference.cdl').write_text(m.group(0)+'\n')

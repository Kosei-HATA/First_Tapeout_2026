from pathlib import Path
import klayout.db as k,json,re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep');p.mkdir(exist_ok=True)
l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');ref=Path('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/spice/gf180mcu_fd_io.spice').read_text();available=set(re.findall(r'(?im)^\.subckt\s+(\S+)',ref));rows=[]
for c in l.each_cell():
 if not c.name.startswith('gf180mcu_fd_io__'):continue
 row={'cell':c.name,'has_pdk_reference':c.name in available,'direct_reference_count':sum(i.inst().na*i.inst().nb for i in c.each_parent_inst()),'bbox_um':str(c.dbbox())};rows.append(row)
 if c.name not in available or c.name.endswith('__asig_5p0'):continue
 out=p/c.name;out.mkdir(exist_ok=True);d=k.Layout();d.dbu=l.dbu;t=d.create_cell(c.name);t.copy_tree(c);d.write(str(out/'actual.gds'))
 m=re.search(r'(?im)^\.SUBCKT\s+'+re.escape(c.name)+r'\b.*?^\.ENDS\s*$',ref,re.S);assert m;(out/'reference.spice').write_text(m.group(0)+'\n')
(p/'inventory.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))

from pathlib import Path
import klayout.db as k,json,subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep');b=k.Layout();b.read('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/gds/gf180mcu_fd_io.gds');r={}
for name in ['gf180mcu_fd_io__fill1','gf180mcu_fd_io__fillnc']:
 a=k.Layout();a.read(str(p/name/'actual.gds'));ac=a.cell(name);bc=b.cell(name);assert a.dbu==b.dbu;layers=[]
 for info in set(a.layer_infos()+b.layer_infos()):
  left=k.Region(ac.begin_shapes_rec(a.layer(info)));right=k.Region(bc.begin_shapes_rec(b.layer(info)));delta=left^right
  if not delta.is_empty():layers.append({'layer':str(info),'xor_um2':delta.area()*a.dbu*a.dbu})
 r[name]={'polygon_geometry_identical_to_pdk':not layers,'differences':layers,'device_lvs':'not_applicable_empty_reference; no connectivity signoff inferred'}
(p/'empty_cells_geometry.json').write_text(json.dumps(r,indent=2));print(r)
d=p/'gf180mcu_fd_io__cor';s=(d/'reference_common_ground.spice').read_text();import re
m=re.search(r'c_width=([0-9.eE+-]+)',s);s=s[:m.start(1)]+str(float(m[1])*1.1)+s[m.end(1):];(d/'common_ground_negative.spice').write_text(s)
with (d/'common_ground_negative_netgen.log').open('w') as f:subprocess.run(['/foss/tools/netgen/bin/netgen','-batch','lvs','actual_normalized.spice '+d.name,'common_ground_negative.spice '+d.name,str(p.parent/'io_asig_magic/strict_setup.tcl'),'common_ground_negative_comparison.log'],cwd=d,stdout=f,stderr=subprocess.STDOUT)
print('cor negative property detected','Property errors were found.' in (d/'common_ground_negative_comparison.log').read_text())

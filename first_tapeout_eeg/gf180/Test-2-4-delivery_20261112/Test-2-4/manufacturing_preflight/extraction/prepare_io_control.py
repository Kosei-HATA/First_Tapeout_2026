from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction');name='gf180mcu_fd_io__asig_5p0';l=k.Layout();l.read('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/gds/gf180mcu_fd_io.gds');c=l.cell(name);d=k.Layout();d.dbu=l.dbu;t=d.create_cell(name);t.copy_tree(c);out=p/'io_asig_control';out.mkdir(exist_ok=True);d.write(str(out/'control.gds'))
a=k.Layout();a.read(str(p/'io_asig_lvs/actual.gds'));ac=a.cell(name);b=d;bc=t;r=[]
for li in a.layer_indices():
 info=a.get_info(li);left=k.Region(ac.begin_shapes_rec(li));right=k.Region(bc.begin_shapes_rec(b.layer(info)));delta=left^right
 r.append({'layer':str(info),'xor_um2':delta.area()*a.dbu*a.dbu,'equal':delta.is_empty()})
(p/'io_geometry_vs_pdk.json').write_text(json.dumps({'cell':name,'all_polygon_layers_identical':all(x['equal'] for x in r),'layers':r},indent=2));print('same polygons',all(x['equal'] for x in r))

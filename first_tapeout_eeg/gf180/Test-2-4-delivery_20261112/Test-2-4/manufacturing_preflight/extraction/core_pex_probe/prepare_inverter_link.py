from pathlib import Path
import klayout.db as k
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');d=p/'inverter_link';d.mkdir(exist_ok=True);l=k.Layout();l.read('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/gds/gf180mcu_fd_sc_mcu7t5v0.gds');src=l.cell('gf180mcu_fd_sc_mcu7t5v0__inv_1');o=k.Layout();o.dbu=l.dbu;c=o.create_cell('inverter_link')
for li in l.layer_indices():
 r=k.Region(src.begin_shapes_rec(li)).merged();c.shapes(o.layer(l.get_info(li))).insert(r);c.shapes(o.layer(l.get_info(li))).insert(r.transformed(k.Trans(round(100/l.dbu),0)))
def box(layer,x1,y1,x2,y2):c.shapes(o.layer(layer,0)).insert(k.DBox(x1,y1,x2,y2).to_itype(o.dbu))
box(34,1.3,1.55,100.95,1.85);box(36,10,1.55,90,1.85);o.write(str(d/'input.gds'))
s=(p/'coupled_wires/ports.tcl').read_text();start=s.index('box values');end=s.index('extresist threshold');ann=''
for i,(name,x,y,layer) in enumerate([('IN',.87,1.7,'metal1'),('OUT',101.43,1.7,'metal1'),('AG1',10.1,1.7,'metal2'),('AG2',89.9,1.7,'metal2')]):ann+=f'box values {x}um {y}um {x}um {y}um\nlabel {name} center {layer}\nport make {i+1}\n'
s=s[:start]+ann+s[end:];s=s.replace('load coupled_wires','load inverter_link');(d/'ports.tcl').write_text(s)

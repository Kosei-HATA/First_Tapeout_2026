from pathlib import Path
import klayout.db as k,json,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction')
r=[]
for tag,source in [('test23','/work/Test2-3/gds/Test2-3.gds'),('test24','/work/Test-2-4/gds/Test-2-4.gds')]:
 out=p/tag;out.mkdir(exist_ok=True);l=k.Layout();l.read(source);c=l.cell('Bondpad_5LM');d=k.Layout();d.dbu=l.dbu;t=d.create_cell('pad_dut');counts={}
 for li in l.layer_indices():
  reg=k.Region(c.begin_shapes_rec(li)).merged()
  if reg.is_empty():continue
  t.shapes(d.layer(l.get_info(li))).insert(reg);counts[str(l.get_info(li))]=reg.count()
 t.shapes(d.layer(81,10)).insert(k.Text('PAD',k.Trans(32000,32000)))
 d.write(str(out/'pad.gds'))
 tcl='''drc off
crashbackups stop
gds read pad.gds
load pad_dut
select top cell
extract do local
extract all
ext2spice hierarchy off
ext2spice format ngspice
ext2spice cthresh 0.001
ext2spice merge conservative
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice -o pad_pex.spice
quit -noprompt
'''
 (out/'extract.tcl').write_text(tcl)
 r.append({'tag':tag,'input_gds':source,'input_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'cell':'Bondpad_5LM','merged_shape_counts':counts})
(p/'pad_inputs.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

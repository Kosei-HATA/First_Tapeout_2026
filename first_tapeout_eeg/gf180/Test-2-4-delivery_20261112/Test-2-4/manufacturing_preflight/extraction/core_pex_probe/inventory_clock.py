from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');p.mkdir(exist_ok=True);l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');r=[]
for c in l.each_cell():
 if any(s in c.name.lower() for s in ['clk','slow']):
  labels=[]
  for li in l.layer_indices():
   for sh in c.shapes(li).each():
    if sh.is_text():labels.append({'layer':str(l.get_info(li)),'text':sh.text.string,'x_um':sh.text.x*l.dbu,'y_um':sh.text.y*l.dbu})
  r.append({'cell':c.name,'bbox':str(c.dbbox()),'parent_cells':[l.cell(i).name for i in c.each_parent_cell()],'instances':sum(1 for i in c.each_inst()),'direct_shapes':sum(c.shapes(li).size() for li in l.layer_indices()),'labels':labels})
(p/'inventory.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

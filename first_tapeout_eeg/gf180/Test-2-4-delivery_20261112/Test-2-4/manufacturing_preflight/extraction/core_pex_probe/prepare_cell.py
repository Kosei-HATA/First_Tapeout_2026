from pathlib import Path
import klayout.db as k,json,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');l=k.Layout();src=Path('/work/Test-2-4/gds/Test-2-4.gds');l.read(str(src));c=l.cell('adc_c2');d=k.Layout();d.dbu=l.dbu;t=d.create_cell(c.name);t.copy_tree(c);d.write(str(p/'adc_c2.gds'));r={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'cell':c.name,'bbox':str(c.dbbox()),'labels':[],'placements_in_core':[],'layers':[]}
for li in l.layer_indices():
 region=k.Region(c.begin_shapes_rec(li));r['layers'].append({'layer':str(l.get_info(li)),'area_um2':region.area()*l.dbu*l.dbu})
 it=c.begin_shapes_rec(li)
 while not it.at_end():
  s=it.shape()
  if s.is_text():
   text=s.text.transformed(it.trans());r['labels'].append({'layer':str(l.get_info(li)),'text':text.string,'x_um':text.x*l.dbu,'y_um':text.y*l.dbu})
  it.next()
def walk(cell,tr,path):
 if cell.name=='adc_c2':r['placements_in_core'].append({'path':path,'transform':str(tr),'matrix':[tr.mag,tr.angle,tr.is_mirror(),tr.disp.x,tr.disp.y]});return
 for i,inst in enumerate(cell.each_inst()):
  for sub in inst.cell_inst.each_cplx_trans():walk(inst.cell,tr*sub,path+'/'+inst.cell.name+'['+str(i)+']')
walk(l.cell('chip_top'),k.ICplxTrans(), 'chip_top');r['adc_parents']=[l.cell(x).name for x in l.cell('adc_top').each_parent_cell()];(p/'cell_evidence.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))



from pathlib import Path
import json,hashlib,time
import klayout.db as k
p=Path('/work/Test-2-4');out=p/'manufacturing_preflight/power_screen/local_geometry';src=p/'gds/Test-2-4.gds';t=time.time()
sha=hashlib.sha256(src.read_bytes()).hexdigest();assert sha=='7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755'
l=k.Layout();l.read(str(src));top=l.cell('chip_top');u=l.dbu
layers={'m2':36,'v2':38,'m3':42,'v3':40,'m4':46,'v4':41,'m5':81}
def box(x):return k.DBox(*x).to_itype(u)
def collect(name,bounds):
 it=top.begin_shapes_rec_overlapping(l.layer(layers[name],0),box(bounds));d={};raw=0
 while not it.at_end():
  s=it.shape()
  if s.is_box() or s.is_polygon() or s.is_path():
   q=s.polygon.transformed(it.trans());raw+=1;d[q.to_s()]=q
  it.next()
 return k.Region(list(d.values())),raw
roi=(3490,580,3567,2095);regions={n:collect(n,roi)[0].merged() for n in layers}
def cuts(name,bounds):
 r,raw=collect(name,bounds);b=box(bounds);items=[q for q in r.each() if (b & q.bbox()) == q.bbox()];unique=k.Region(items);sizes={str(round(q.bbox().width()*u,6))+'x'+str(round(q.bbox().height()*u,6)) for q in items}
 return {'raw_overlapping_occurrences':raw,'unique_fully_contained_cuts':len(items),'sizes_um':sorted(sizes),'bbox_um':str(unique.bbox().to_dtype(u)),'distinct_center_x_count':len({q.bbox().center().x for q in items}),'distinct_center_y_count':len({q.bbox().center().y for q in items}),'all_cuts_0p26_square':bool(items) and all(q.bbox().width()==260 and q.bbox().height()==260 and q.area()==260*260 for q in items)}
def vertical_sections(name,x,y1,y2):
 q=(regions[name]&k.Region(box((x,y1,x+u,y2)))).merged()
 return [[poly.bbox().bottom*u,poly.bbox().top*u] for poly in q.each()]
feeds=[]
for y1,y2 in [(594.86,667.14),(2004.86,2077.14)]:
 b=(3549,y1,3555,y2);v={n:cuts(n,b) for n in ['v2','v3','v4']};coverage={n:(k.Region(box(b))-regions[n]).area()*u*u for n in ['m2','m3','m4','m5']}
 feeds.append({'stack_box_um':b,'via_layers':v,'missing_metal_in_stack_area_um2':coverage,'m2_pad_finger_cross_section_at_x3555p25_um':vertical_sections('m2',3555.25,y1,y2)})
bridges=[]
for y1,y2 in [(596.86,606.86),(655.14,665.14),(2006.86,2016.86),(2065.14,2075.14)]:
 b=(3519,y1,3523,y2);bridges.append({'box_um':b,'missing_m5_um2':(k.Region(box(b))-regions['m5']).area()*u*u,'v4_in_gap':cuts('v4',(3520,y1,3522,y2))})
geom=json.loads((p/'baseline/pad_geometry.json').read_text());ties=[]
for pad in geom['pads']:
 if 'bidir' not in pad['inst']:continue
 y=pad['bbox'][1]+30
 if pad['side']!='east':continue
 b=(3522,y,3526,y+4);ties.append({'instance':pad['inst'],'box_um':b,'v4':cuts('v4',b),'missing_m4_um2':(k.Region(box(b))-regions['m4']).area()*u*u,'missing_m5_um2':(k.Region(box(b))-regions['m5']).area()*u*u})
r={'input_sha256':sha,'scope':'Local geometry only; no current sharing assumption or full-chip extraction','feeds':feeds,'bridges':bridges,'tie_anchors':ties,'m5_left_of_inner_trunk_sections_at_x3499p5_um':vertical_sections('m5',3499.5,580,2095),'m5_gap_sections_at_x3521_um':vertical_sections('m5',3521,580,2095),'seconds':round(time.time()-t,2)}
(out/'local_geometry.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

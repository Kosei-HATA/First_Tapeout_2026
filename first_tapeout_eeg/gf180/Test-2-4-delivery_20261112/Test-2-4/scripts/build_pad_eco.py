from pathlib import Path
import klayout.db as k,json,hashlib
p=Path('/work/Test-2-4');source=Path('/work/Test2-3/gds/Test2-3.gds');expected='1ec7bd329d5ee1ba7cf3ac39ab22a698fb91847c486b6ede2aa6c3fb2003277c'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert sha(source)==expected
l=k.Layout();l.read(str(source));c=l.cell('Bondpad_5LM');unit=l.dbu
r={'input_sha256':expected,'cell':c.name,'change':'Add metal within existing single-net bondpad only; retain vias, PAD opening, M5, and all other cells. Non-CUP candidate requiring assembly approval.','layers':[]}
for layer in [36,42,46]:
 li=l.layer(layer,0);before=k.Region(c.begin_shapes_rec(li)).merged();target=k.Region(k.DBox(3.34,1.27,62,62.205).to_itype(unit));added=target-before
 assert before.count()==1,(layer,before.count())
 assert not added.is_empty()
 for polygon in added.each():c.shapes(li).insert(polygon)
 after=k.Region(c.begin_shapes_rec(li)).merged();assert (before-after).is_empty();assert after.count()==1
 r['layers'].append({'layer':layer,'local_added_area_um2':added.area()*unit*unit,'local_added_bbox_um':str(added.bbox().to_dtype(unit)),'before_metal_components':before.count(),'after_metal_components':after.count()})
out=p/'gds/Test-2-4.gds';l.write(str(out));r['output_sha256']=sha(out);(p/'verification/build.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

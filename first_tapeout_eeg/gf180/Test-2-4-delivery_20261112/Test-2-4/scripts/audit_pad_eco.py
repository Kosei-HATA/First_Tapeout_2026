from pathlib import Path
import klayout.db as k,json,hashlib,xml.etree.ElementTree as E
p=Path('/work/Test-2-4');a=k.Layout();a.read('/work/Test2-3/gds/Test2-3.gds');b=k.Layout();b.read(str(p/'gds/Test-2-4.gds'));ac=a.cell('Bondpad_5LM');bc=b.cell('Bondpad_5LM');u=b.dbu
r={'input':'Test2-3','candidate':'Test-2-4','checks':{},'addition_by_layer':[]}
for layer in [36,42,46]:
 li=a.layer(layer,0);lj=b.layer(layer,0);old=k.Region(ac.begin_shapes_rec(li)).merged();new=k.Region(bc.begin_shapes_rec(lj)).merged();delta=new-old
 assert (old-new).is_empty()
 expected=k.Region(k.DBox(3.34,1.27,62,62.205).to_itype(u))-old
 assert (expected^delta).is_empty()
 # GDS may fracture added polygons or serialize rectangles as boxes.
 # Confirm every baseline direct shape survives, and only expected additive geometry remains.
 from collections import Counter
 old_shapes=list(ac.shapes(li).each()); old_counts=Counter(x.to_s() for x in old_shapes)
 new_counts=Counter(x.to_s() for x in bc.shapes(lj).each())
 assert not (old_counts-new_counts), 'Baseline direct shapes changed'
 bc.shapes(lj).clear()
 for shape in old_shapes:bc.shapes(lj).insert(shape)
 r['addition_by_layer'].append({'layer':layer,'area_um2':delta.area()*u*u,'single_component_before':old.count()==1,'single_component_after':new.count()==1})
r['checks']['all_other_geometry_hierarchy_and_properties_unchanged']=k.LayoutDiff().compare(a,b,k.LayoutDiff.BoxesAsPolygons,0)
assert r['checks']['all_other_geometry_hierarchy_and_properties_unchanged']
# Candidate is unmodified on disk. Analyze all bond openings, excluding seal ring.
t=a.cell('chip_top');pad=k.Region(t.begin_shapes_rec(a.layer(37,0))).merged();guard=k.Region(t.begin_shapes_rec(a.layer(167,5))).merged();bond=pad.not_interacting(guard)
# Only actual large bond windows; seal-ring edges are below this area.
bond=k.Region([q for q in bond.each() if q.area()*u*u>1000 and min(q.bbox().width(),q.bbox().height())*u>20])
r['bond_opening_count']=bond.count();r['bond_opening_area_um2']=bond.area()*u*u
for name,layer in [('comp',22),('poly2',30)]:
 active=k.Region(t.begin_shapes_rec(a.layer(layer,0)));r['checks'][name+'_overlap_bond_opening_um2']=(active&bond).area()*u*u
 assert (active&bond).is_empty()
m5=k.Region(t.begin_shapes_rec(a.layer(81,0)));r['checks']['top_metal_2um_enclosure_uncovered_area_um2']=(bond.sized(round(2/u))-m5).area()*u*u
r['checks']['focused_CUP_marker_count']=len(E.parse(p/'verification/cup.lyrdb').findall('.//items/item'))
r['limits']='No mechanical bonding, ESD, electromigration/current, parasitic or foundry signoff. CUP applicability depends on assembly conditions.'
(p/'verification/pad_eco_audit.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

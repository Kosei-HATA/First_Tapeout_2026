from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction');coef={36:(15.016,33.298),42:(10.094,30.021),46:(7.602,28.153),81:(5.798,30.386)};r={'style':'ngspice() nominal','coeff_units':['aF/um2','aF/um'],'extresist_performed':False,'note':'Area/perimeter diagnostic only. Products below omit shielding/overlap corrections and must not be summed as extracted total capacitance.','cases':{}}
for tag in ['test23','test24']:
 l=k.Layout();l.read(str(p/tag/'pad.gds'));c=l.top_cell();rows=[]
 for layer,(ac,pc) in coef.items():
  reg=k.Region(c.begin_shapes_rec(l.layer(layer,0))).merged();area=reg.area()*l.dbu*l.dbu;per=reg.perimeter()*l.dbu
  rows.append({'layer':layer,'area_um2':area,'perimeter_um':per,'area_coefficient':ac,'perimeter_coefficient':pc,'unshielded_area_term_fF':area*ac/1000,'unshielded_perimeter_term_fF':per*pc/1000})
 r['cases'][tag]=rows
(p/'area_perimeter_diagnostic.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

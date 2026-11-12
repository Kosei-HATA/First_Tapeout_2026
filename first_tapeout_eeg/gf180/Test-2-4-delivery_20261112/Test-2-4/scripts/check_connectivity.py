from pathlib import Path
import collections,json,hashlib
import klayout.db as k
p=Path(__file__).resolve().parents[1];path=p/'gds/Test-2-4.gds'
l=k.Layout();l.read(str(path));top=l.cell('chip_top');n=k.LayoutToNetlist('chip_top',l.dbu);layers={}
L={'metal1':(34,0),'via1':(35,0),'metal2':(36,0),'via2':(38,0),'metal3':(42,0),'via3':(40,0),'metal4':(46,0),'via4':(41,0),'metal5':(81,0)}
for name,li in L.items():
 r=k.Region(top.begin_shapes_rec(l.layer(*li)));n.register(r,name);layers[name]=r;n.connect(r);print('Loaded '+name,flush=True)
for i in range(1,5):n.connect(layers[f'metal{i}'],layers[f'via{i}']);n.connect(layers[f'via{i}'],layers[f'metal{i+1}'])
n.extract_netlist();points=[]
for pt in json.loads((p/'baseline/probes.json').read_text())['points']:
 pt=dict(pt);net=n.probe_net(layers[pt['layer']],k.DPoint(pt['x_um'],pt['y_um']));nid=net.cluster_id if net else None
 if callable(nid):nid=nid()
 pt['net']=nid;points.append(pt)
groups=collections.defaultdict(set);actual=collections.defaultdict(set)
for pt in points:
 groups[pt['expected']].add(pt['net'])
 if pt['net'] is not None:actual[pt['net']].add(pt['expected'])
opens={a:sorted(v,key=str) for a,v in groups.items() if len(v)!=1 or None in v};shorts={str(a):sorted(v) for a,v in actual.items() if len(v)>1}
r={'input_sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),'scope':'Metal1..5/Via1..4; 296 baseline probes, including supply pads, core rails, digital macro rails and selected signal/tie pins. Not device conduction or full-chip LVS.','point_count':len(points),'group_count':len(groups),'opens':opens,'shorts':shorts,'pass':not opens and not shorts,'points':points}
(p/'verification/connectivity.json').write_text(json.dumps(r,indent=2));print(json.dumps({a:b for a,b in r.items() if a!='points'},indent=2));assert r['pass']

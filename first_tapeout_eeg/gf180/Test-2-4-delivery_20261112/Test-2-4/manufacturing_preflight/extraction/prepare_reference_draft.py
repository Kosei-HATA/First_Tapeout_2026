from pathlib import Path
import ast,json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/reference_draft');p.mkdir(exist_ok=True);src=Path('/work/Test-2-4/source/layout/chip_lay.py');geom=Path('/work/Test-2-4/baseline/pad_geometry.json');s=src.read_text();tree=ast.parse(s)
def literal(n):
 if isinstance(n,ast.Constant):return n.value
 if isinstance(n,ast.Dict):return {literal(k):literal(v) for k,v in zip(n.keys,n.values)}
 if isinstance(n,ast.Tuple):return tuple(literal(x) for x in n.elts)
 if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='dict' and not n.args:return {k.arg:literal(k.value) for k in n.keywords}
 raise ValueError(ast.dump(n))
node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DPAD' for t in n.targets));digital=literal(node.value)
analog={0:'AVDD',1:'AVSS',2:'ELP',3:'ELP',4:'ELN',5:'ELN',6:'AVSS',7:'AVDD',8:'ATP',9:'VCM',10:'VREFP_PAD',11:'VREFN_PAD',12:'AVDD',13:'AVSS'}
d=json.loads(geom.read_text());lib=Path('/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/spice/gf180mcu_fd_io.spice').read_text();orders={m[1]:m[2].split() for m in re.finditer(r'(?im)^\.subckt\s+(\S+)\s+([^\n]+)',lib)}
def clean(x):return re.sub(r'[^A-Za-z0-9_]','_',x.replace('\\',''))
rows=[];ports=set(['AVDD','AVSS','DVDD','DVSS']);lines=['* INCOMPLETE PAD FRAGMENT ONLY. NOT a full-chip LVS reference or signoff.','* Excludes original core/tie cells, spacers, and analog/digital core.']
for pad in d['pads']:
 name=pad['inst'].replace('\\','');base=re.sub(r'\.pad$','',name);nets={k:({'VDD':'DVDD','VSS':'DVSS'}.get(v,v.replace('\\',''))) for k,v in pad['nets'].items()};origin='ODB sidecar pin nets'
 if base in digital:
  sig,sp,ties=digital[base];nets['PAD']=sig+'_PAD';nets[sp]=sig;ports.update([sig,sig+'_PAD'])
  for pin,net in ties.items():nets[pin]={0:'DVSS',1:'DVDD'}.get(net,net);ports.add(nets[pin])
  origin+=' plus chip_lay.py DPAD intent'
 if base.startswith('analog['):
  i=int(re.search(r'\[(\d+)\]',base)[1]);net=analog.get(i,'UNUSED_ANALOG_'+str(i));nets['ASIG5V']=net;ports.add(net);origin+=' plus analog routing intent for indices 0..13'
 order=orders[pad['cell']];missing=set(order)-nets.keys();assert not missing,(name,missing)
 rows.append({'instance':name,'cell':pad['cell'],'pins':nets,'source':origin});lines.append('X'+clean(name)+' '+' '.join(clean(nets[k]) for k in order)+' '+pad['cell'])
portlist=' '.join(sorted(clean(x) for x in ports));text=lines[:2]+['.subckt pad_fragment_only '+portlist]+lines[2:]+['.ends pad_fragment_only']
(p/'pad_fragment_incomplete.spice').write_text('\n'.join(text)+'\n')
r={'status':'incomplete_independent_intent_draft_not_for_LVS_signoff','sources':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [src,geom]],'no_GDS_extracted_netlist_used':True,'instances':rows,'counts_in_source':d['inst_kinds'],'unresolved':['Original 43 CORE, 9 TIEHIGH,45 TIELOW cells and their connections not enumerated in sidecar.','682 spacer instances require independently sourced placement/connectivity (counts are insufficient).','Full intended relation between retained tie cell outputs and chip_lay direct ties needs original padring synthesis netlist/ODB.','Core subcircuit instantiation and AVSS_CLK/DVSS substrate mapping must be specified explicitly.'],'required_input':'Original LibreLane RUN_2026-10-23_13-27-25 final netlist (and preferably ODB/config) or equivalent independent schematic; not a netlist derived from the candidate GDS.'}
(p/'intent_manifest.json').write_text(json.dumps(r,indent=2));print({'pad_instances':len(rows),'top_reference_complete':False})

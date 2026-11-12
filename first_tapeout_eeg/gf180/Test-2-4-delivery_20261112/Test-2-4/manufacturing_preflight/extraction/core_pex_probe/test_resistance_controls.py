from pathlib import Path
import klayout.db as k,subprocess,os,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');c=p/'rc_diagnosis/magic_candidate';out=c/'resistance_controls';out.mkdir(exist_ok=True);env=os.environ.copy();env['LD_LIBRARY_PATH']=str(c/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','');results={}
for name in ['via1','missing_via1','branch']:
 d=out/name;d.mkdir(exist_ok=True);l=k.Layout();l.dbu=.001;cell=l.create_cell(name)
 def box(layer,coords):cell.shapes(l.layer(layer,0)).insert(k.Box(*coords))
 if name=='branch':
  box(34,(0,0,100000,1000));box(34,(49500,0,50500,50000));ports=[('A',1,.5,'metal1'),('B',99,.5,'metal1'),('C',50,49,'metal1')]
 else:
  box(34,(0,0,10000,1000));box(36,(9000,0,20000,1000));ports=[('A',1,.5,'metal1'),('B',19,.5,'metal2')]
  if name=='via1':box(35,(9370,370,9630,630))
 l.write(str(d/'input.gds'))
 t='drc off\ncrashbackups stop\ngds read input.gds\nload '+name+'\nselect top cell\n'
 for i,(n,x,y,layer) in enumerate(ports,1):t+=f'box values {x}um {y}um {x}um {y}um\nlabel {n} center {layer}\nport make {i}\n'
 t+=(c/'full_tcl/wire/run.tcl').read_text().split('extresist threshold')[1];t=t.replace(' 0\nextresist minres','extresist threshold 0\nextresist minres',1)
 (d/'run.tcl').write_text(t)
 with (d/'run.log').open('w') as f:r=subprocess.run([str(c/'install_tcl/bin/magic'),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 s=(d/'rc.spice').read_text();rs=[]
 for line in s.splitlines():
  a=line.split()
  if a and re.match(r'^R\d',a[0]):rs.append((a[1],a[2],float(a[3])))
 def resistance(a,b):
  reachable={a}
  for _ in rs:
   for x,y,v in rs:
    if x in reachable:reachable.add(y)
    if y in reachable:reachable.add(x)
  if b not in reachable:return None
  nodes=sorted(reachable-{b});idx={x:i for i,x in enumerate(nodes)};g=np.zeros((len(nodes),len(nodes)));q=np.zeros(len(nodes));q[idx[a]]=1
  for x,y,v in rs:
   if x not in reachable or v<=0:continue
   for u in [x,y]:
    if u!=b:g[idx[u],idx[u]]+=1/v
   if x!=b and y!=b:g[idx[x],idx[y]]-=1/v;g[idx[y],idx[x]]-=1/v
  return float(np.linalg.solve(g,q)[idx[a]])
 results[name]={'returncode':r.returncode,'resistors':rs,'R_AB_ohm':resistance('A','B'),'R_AC_ohm':resistance('A','C') if name=='branch' else None,'ports':next(x for x in s.splitlines() if x.startswith('.subckt'))};print(name,results[name])
(out/'results.json').write_text(json.dumps(results,indent=2))

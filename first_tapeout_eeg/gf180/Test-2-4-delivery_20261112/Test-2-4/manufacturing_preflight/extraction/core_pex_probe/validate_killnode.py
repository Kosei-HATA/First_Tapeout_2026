from pathlib import Path
import json,re,collections,numpy as np,shlex
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis/magic_candidate/full_tcl/inverter_link');cap=(p/'cap.spice').read_text();rc=(p/'rc.spice').read_text()
def parse(s):
 C=[];R=[];X=[]
 for ln in s.splitlines():
  t=ln.split()
  if not t:continue
  if t[0].startswith('C'):
   m=re.fullmatch(r'([0-9.eE+-]+)([fpnum]?)',t[3]);v=float(m[1])*{'':1e15,'f':1,'p':1e3,'n':1e6,'u':1e9,'m':1e12}[m[2]];C.append((t[1],t[2],v))
  if t[0].startswith('R'):R.append((t[1],t[2],float(t[3])))
  if t[0].startswith('X'):X.append(t[1:])
 return C,R,X
baseC,_,baseX=parse(cap);base=set(n for a,b,v in baseC for n in [a,b]);base.update(n for x in baseX for n in x[:4]);killed=[shlex.split(ln)[1] for ln in (p/'inverter_link.res.ext').read_text().splitlines() if ln.startswith('killnode')]
def canonical(n):
 if n=='AG1':return 'AG2'
 if n in base:return n
 m=re.match(r'^(.*)\.[nt]\d+$',n)
 if m:
  for q in [m[1],m[1]+'#']:
   if q in base:return q
 raise ValueError(n)
def evaluate(s):
 C,R,X=parse(s);unknown=[]
 try:
  names=sorted(base);idx={n:i for i,n in enumerate(names)}
  def matrix(rows):
   m=np.zeros((len(names),len(names)))
   for a,b,v in rows:
    i,j=idx[canonical(a)],idx[canonical(b)];m[i,i]+=v;m[j,j]+=v;m[i,j]-=v;m[j,i]-=v
   return m
  err=float(np.max(abs(matrix(C)-matrix(baseC))))
  parent={}
  def find(x):
   parent.setdefault(x,x)
   if parent[x]!=x:parent[x]=find(parent[x])
   return parent[x]
  for a,b,v in R:parent[find(a)]=find(b)
  groups=collections.defaultdict(set)
  for x in X:
   for n in x[:4]:groups[canonical(n)].add(find(n))
  connected=all(len(v)==1 for v in groups.values())
  topology=sorted(tuple(canonical(n) for n in x[:4])+tuple(x[4:]) for x in X)==sorted(tuple(x) for x in baseX)
  stale=[n for a,b,v in C for n in [a,b] if n in killed]
  return {'matrix_max_error_fF':err,'all_device_terminals_connected_per_original_net':connected,'collapsed_device_topology_and_parameters_match':topology,'stale_killed_endpoints':stale,'pass':err<.0001 and connected and topology and not stale}
 except ValueError as e:return {'pass':False,'unknown_node':str(e)}
r={'killed_nodes':killed,'positive':evaluate(rc),'negative':{}}
lines=rc.splitlines();line=next(x for x in lines if x.startswith('C') and 'AG2' in x and 'a_244_68.n1' in x)
cases={'missing_reconnected_cap':rc.replace(line+'\n',''),'stale_killed_endpoint':rc.replace(line,line.replace('a_244_68.n1','a_244_68#')),'broken_internal_resistor':re.sub(r'^R0 .*\n','',rc,flags=re.M)}
for n,s in cases.items():(p/(n+'.spice')).write_text(s);r['negative'][n]=evaluate(s)
r['all_negative_detected']=all(not x['pass'] for x in r['negative'].values());r['scope']='Complete new Tcl build; actual GDS-extracted killnode and remapped cap records. Matrix comparison is after collapsing resistive subdivisions; not distributed-frequency accuracy.';(p/'killnode_validation.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

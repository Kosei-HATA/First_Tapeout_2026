from pathlib import Path
import re,json,collections
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe')
def flatten(path):
 subs={};cur=None
 for line in path.read_text().splitlines():
  t=line.split()
  if not t or t[0].startswith('*'):continue
  if t[0].lower()=='.subckt':cur=t[1];subs[cur]=[t[2:],[]]
  elif t[0].lower()=='.ends':cur=None
  elif cur:subs[cur][1].append(t)
 out=[]
 def walk(name,prefix,pins):
  def node(n):return pins.get(n,prefix+n)
  for t in subs[name][1]:
   if t[0].startswith('X'):
    mi=next((i for i,x in enumerate(t) if x in subs),None)
    if mi is not None:walk(t[mi],prefix+t[0]+'/',dict(zip(subs[t[mi]][0],map(node,t[1:mi]))));continue
    out.append(('M',tuple(map(node,t[1:5])),tuple(t[5:])))
   elif t[0][0] in 'RC':out.append((t[0][0],tuple(map(node,t[1:3])),tuple(t[3:])))
 walk('eeg_adc_clk','',dict((x,x) for x in subs['eeg_adc_clk'][0]));return out,subs['eeg_adc_clk'][0]
a,ap=flatten(p/'cap.spice');b,bp=flatten(p/'rc.spice');base={n for typ,ns,v in a for n in ns};parent={}
def find(x):
 parent.setdefault(x,x)
 if parent[x]!=x:parent[x]=find(parent[x])
 return parent[x]
for typ,ns,v in b:
 if typ=='R':parent[find(ns[0])]=find(ns[1])
groups=collections.defaultdict(set)
for typ,ns,v in b:
 for n in ns:
  choices={n} if n in base else set()
  m=re.match(r'^(.*)\.[nt]\d+$',n)
  if m:choices|={x for x in [m[1],m[1]+'#'] if x in base}
  groups[find(n)]|=choices
unknown={x:list(v) for x,v in groups.items() if len(v)!=1}
def canon(n):
 s=groups[find(n)];return next(iter(s)) if len(s)==1 else 'UNRESOLVED:'+n
def value(v):
 m=re.fullmatch(r'([-+0-9.eE]+)([fpnum]?)',v);return float(m[1])*{'':1e15,'f':1,'p':1e3,'n':1e6,'u':1e9,'m':1e12}[m[2]]
def caps(rows,rc=False):
 z=collections.defaultdict(float)
 for typ,ns,v in rows:
  if typ=='C':
   x,y=(map(canon,ns) if rc else ns)
   if x!=y:z[tuple(sorted([x,y]))]+=value(v[0])
 return z
ca,cb=caps(a),caps(b,True);errs=sorted([(abs(ca[x]-cb[x]),list(x),ca[x],cb[x]) for x in set(ca)|set(cb)],reverse=True);ma=collections.Counter((ns,v) for typ,ns,v in a if typ=='M');mb=collections.Counter((tuple(map(canon,ns)),v) for typ,ns,v in b if typ=='M')
r={'ports_before':ap,'ports_after':bp,'ports_preserved':ap==bp,'counts_before':dict(collections.Counter(x[0] for x in a)),'counts_after':dict(collections.Counter(x[0] for x in b)),'ambiguous_or_missing_original_net_groups':unknown,'collapsed_device_topology_parameters_match':ma==mb,'max_cap_pair_error_fF':errs[0] if errs else None,'largest_cap_pair_errors':errs[:10],'scope':'Resistive subdivisions collapsed for bookkeeping; no independent spatial RC accuracy claim'};(p/'rc_preservation.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='ambiguous_or_missing_original_net_groups'},indent=2));print('unresolved groups',len(unknown))

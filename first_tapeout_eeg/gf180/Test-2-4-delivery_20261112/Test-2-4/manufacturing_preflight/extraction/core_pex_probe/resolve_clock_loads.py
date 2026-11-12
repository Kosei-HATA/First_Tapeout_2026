from pathlib import Path
import json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');source=Path('/work/Test-2-4/verification/eeg_core_reference.cdl');raw=source.read_text();lines=[]
for line in raw.splitlines():
 if line.startswith('+'):lines[-1]+=' '+line[1:]
 else:lines.append(line)
subs={};cur=None
for line in lines:
 t=line.split()
 if not t:continue
 if t[0].lower()=='.subckt':cur=t[1].upper();subs[cur]={'ports':[x.upper() for x in t[2:]],'lines':[]}
 elif t[0].lower()=='.ends':cur=None
 elif cur and not t[0].startswith('*'):subs[cur]['lines'].append((line,t))
loads=json.loads((p/'external_loads.json').read_text());wanted={d['schematic']:d for x in loads.values() for d in x['external_devices']};found={}
def walk(model,path,pins,chain):
 def net(n):return pins.get(n.upper(),path+n.upper())
 for line,t in subs[model]['lines']:
  typ=t[0][0].upper();name=path+t[0][1:].upper()
  if typ=='M' and name in wanted:
   found[name]={'source_subckt':model,'source_line':line,'hierarchy':chain,'D':net(t[1]),'G':net(t[2]),'S':net(t[3]),'B':net(t[4]),'model':t[5],'parameters':t[6:],'layout_L_W_um':{x:wanted[name]['params'][x] for x in ['L','W']},'lvs_device':wanted[name]['layout']}
  elif typ=='X' and any(n.startswith(name+'.') for n in wanted):
   pos=[x for x in t[1:] if '=' not in x];child=pos[-1].upper();assert child in subs;assert len(pos[:-1])==len(subs[child]['ports']);walk(child,name+'.',dict(zip(subs[child]['ports'],map(net,pos[:-1]))),chain+[{'instance':name,'model':child,'source_line':line}])
walk('EEG_CORE','',dict((x,x) for x in subs['EEG_CORE']['ports']),[]);assert set(found)==set(wanted),(set(wanted)-set(found))
r={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'note':'D/G/S/B are resolved from independent reference hierarchy; layout gate/bulk and L/W already cross-referenced in core LVS. No extraction netlist used as reference.','devices':found};(p/'external_load_terminals.json').write_text(json.dumps(r,indent=2));print(json.dumps({n:{x:d[x] for x in ['D','G','S','B']} for n,d in found.items()},indent=2))

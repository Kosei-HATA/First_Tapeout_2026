from pathlib import Path
import re,json,subprocess,time,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_q_terminal_stress_3p6';r.mkdir(exist_ok=True);src=p/'moscap_charge_equivalent/full_afe_q_diagnostic/tb.spice';base=src.read_text().replace('VDD VDD 0 PWL(0 0 100n 3.3)','VDD VDD 0 PWL(0 0 100n 3.6)');defs={}
def lines(text):
 out=[]
 for s in text.splitlines():
  s=s.strip().lower()
  if not s or s.startswith('*'):continue
  if s.startswith('+'):out[-1]+=' '+s[1:].strip()
  else:out.append(s)
 return out
for f in [p/'sim_work/gf180/tapeout/afe/eeg_afe.spice',p/'sim_work/gf180/tapeout/afe/eeg_afe_clk.spice',p/'moscap_charge_equivalent/bias_q_diagnostic.spice']:
 cur=None
 for s in lines(f.read_text()):
  tok=s.split()
  if tok[0]=='.subckt':
   cur=tok[1];pins=[]
   for t in tok[2:]:
    if '=' in t or t=='params:':break
    pins.append(t)
   defs[cur]={'pins':pins,'body':[],'source':str(f)}
  elif tok[0].startswith('.ends'):cur=None
  elif cur:defs[cur]['body'].append(s)
mos=[]
def walk(body,path,mapping):
 def node(n):return '0' if n=='0' else mapping.get(n,path+'.'+n if path else n)
 for s in body:
  tok=s.split()
  if not tok[0].startswith('x'):continue
  if len(tok)>5 and tok[5] in ['nfet_03v3','pfet_03v3']:
   mos.append({'instance':(path+'.' if path else '')+tok[0],'model':tok[5],'terminals':dict(zip(['d','g','s','b'],map(node,tok[1:5]))),'source_line':s});continue
  matches=[i for i,t in enumerate(tok) if i>0 and t in defs]
  if not matches:continue
  i=matches[0];sub=defs[tok[i]]
  if i-1!=len(sub['pins']):raise ValueError((s,sub['pins']))
  walk(sub['body'],(path+'.' if path else '')+tok[0],dict(zip(sub['pins'],map(node,tok[1:i]))))
walk(lines(base.split('.control')[0]),'',{})
target=set('rst cia ncia cib ncib cda ncda cdb ncdb ofph'.split());selected=[x for x in mos if target.intersection(x['terminals'].values())];nodes=sorted(set(n for x in selected for n in x['terminals'].values())-{'0'});(r/'connectivity.json').write_text(json.dumps({'flattened_mos_count':len(mos),'target_nodes':sorted(target),'selected_devices':selected,'saved_nodes':nodes},indent=2))
print('Devices',len(selected),'nodes',len(nodes),flush=True)
deck=re.sub(r'^wrdata wave.csv.*$','wrdata wave.csv '+' '.join('v('+n+')' for n in nodes),base,flags=re.M);(r/'tb.spice').write_text(deck);(r/'.spiceinit').write_bytes((src.parent/'.spiceinit').read_bytes());start=time.time()
try:q=subprocess.run([str(p/'ngspice48_isolated/install/bin/ngspice'),'-b','tb.spice'],cwd=r,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
(r/'run.log').write_text(log);s={'seconds':time.time()-start,'exitcode':rc,'diagnostics':[x for x in log.splitlines() if re.search('Timestep too small|Error:',x,re.I)],'completed':False}
if (r/'wave.csv').exists():
 a=np.atleast_2d(np.loadtxt(r/'wave.csv'));t=a[:,0];v={n:a[:,2*i+1] for i,n in enumerate(nodes)};v['0']=np.zeros(len(t));s.update(last_time_s=float(t[-1]),finite=bool(np.isfinite(a).all()),completed=bool(t[-1]>=31.25e-6*.999999),devices=[])
 for x in selected:
  row=dict(x);row['stress']={}
  for label,n1,n2 in [('vgs','g','s'),('vgd','g','d'),('vgb','g','b'),('vds','d','s'),('vdb','d','b'),('vsb','s','b')]:
   y=v[x['terminals'][n1]]-v[x['terminals'][n2]];ab=np.abs(y);i=int(np.argmax(ab));z={'min_V':float(y.min()),'max_V':float(y.max()),'max_abs_V':float(ab[i]),'peak_time_s':float(t[i])}
   durations={}
   for threshold in [3.3,3.63]:
    dur=0.;longest=0.;current=0.
    for k in range(len(t)-1):
     aa=ab[k]-threshold;bb=ab[k+1]-threshold;dt=t[k+1]-t[k]
     frac=1. if aa>0 and bb>0 else 0. if aa<=0 and bb<=0 else (aa/(aa-bb) if aa>0 else bb/(bb-aa));piece=dt*frac;dur+=piece
     if piece>0:current+=piece;longest=max(longest,current)
     if bb<=0:current=0.
    durations[str(threshold)]={'total_s':float(dur),'duty_fraction_of_record':float(dur/(t[-1]-t[0])),'longest_s':float(longest)}
   z['absolute_threshold_exposure']=durations;row['stress'][label]=z
  s['devices'].append(row)
 s['worst_gate_pair']=max(({'instance':x['instance'],'pair':k,**z} for x in s['devices'] for k,z in x['stress'].items() if k in ['vgs','vgd','vgb']),key=lambda x:x['max_abs_V'])
 s['worst_vds']=max(({'instance':x['instance'],**x['stress']['vds']} for x in s['devices']),key=lambda x:x['max_abs_V'])
(r/'summary.json').write_text(json.dumps(s,indent=2));print({k:v for k,v in s.items() if k!='devices'},flush=True)


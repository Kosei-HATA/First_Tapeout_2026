from pathlib import Path
import json,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_q_terminal_stress';s=json.loads((r/'summary.json').read_text());c=json.loads((r/'connectivity.json').read_text());a=np.loadtxt(r/'wave.csv');t=a[:,0];v={n:a[:,2*i+1] for i,n in enumerate(c['saved_nodes'])};v['0']=np.zeros(len(t))
def exposure(y,lim):
 intervals=[]
 for sign in [1,-1]:
  z=sign*y-lim;z0=z[:-1];z1=z[1:];mask=(z0>0)|(z1>0);idx=np.flatnonzero(mask);f=np.divide(z0,z0-z1,out=np.zeros_like(z0),where=z0!=z1);start=np.where(z0>0,t[:-1],t[:-1]+np.diff(t)*f);end=np.where(z1>0,t[1:],t[:-1]+np.diff(t)*f);intervals.extend(zip(start[idx],end[idx]))
 intervals.sort();merged=[]
 for x,y in intervals:
  if merged and x<=merged[-1][1]+1e-21:merged[-1][1]=max(y,merged[-1][1])
  else:merged.append([x,y])
 ds=[y-x for x,y in merged];return {'total_s':float(sum(ds)),'duty_fraction_of_record':float(sum(ds)/(t[-1]-t[0])),'longest_s':float(max(ds,default=0)),'interval_count':len(ds)}
for d in s['devices']:
 for pair,na,nb in [('vgs','g','s'),('vgd','g','d'),('vgb','g','b'),('vds','d','s'),('vdb','d','b'),('vsb','s','b')]:
  y=v[d['terminals'][na]]-v[d['terminals'][nb]];d['stress'][pair]['absolute_threshold_exposure']={str(x):exposure(y,x) for x in [3.3,3.63]}
s['direct_signal_groups']={}
for signal in ['rst','cia','cda']:
 dev=[d for d in s['devices'] if signal in d['terminals'].values()];gate=max(({'instance':d['instance'],'terminals':d['terminals'],'pair':pair,**z} for d in dev for pair,z in d['stress'].items() if pair in ['vgs','vgd','vgb']),key=lambda x:x['max_abs_V']);s['direct_signal_groups'][signal]={'device_count':len(dev),'worst_gate_pair':gate}
s['worst_gate_pair']=max(({'instance':d['instance'],'terminals':d['terminals'],'pair':pair,**z} for d in s['devices'] for pair,z in d['stress'].items() if pair in ['vgs','vgd','vgb']),key=lambda x:x['max_abs_V']);s['worst_vds']=max(({'instance':d['instance'],'terminals':d['terminals'],**d['stress']['vds']} for d in s['devices']),key=lambda x:x['max_abs_V']);s['exposure_method']='Piecewise-linear interpolation of signed terminal difference, evaluating positive and negative thresholds separately; startup-record fraction, not steady-state TDDB duty.'
s['source']='https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html';s['scope']='58 MOS wrappers directly connected to RST/CIA/NCIA/CIB/NCIB/CDA/NCDA/CDB/NCDB/OFPH. Not all MOS devices, intrinsic series-resistance nodes, PEX, PVT, steady-state or reliability signoff.'
(r/'summary.json').write_text(json.dumps(s,indent=2));print(json.dumps(s['direct_signal_groups'],indent=2))

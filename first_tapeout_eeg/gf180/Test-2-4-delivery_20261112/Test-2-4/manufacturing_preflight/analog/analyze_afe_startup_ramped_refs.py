from pathlib import Path
import json,ast,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_lvs_startup_controls';src=p/'afe_lvs_supply_3p6';c=json.loads((src/'connectivity.json').read_text());nodes=c['saved_nodes'];dev=c['selected_devices'];a=np.loadtxt(src/'wave.csv')
func=next(x for x in ast.parse((p/'finalize_afe_q_terminal_stress.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='exposure');exec(compile(ast.Module(body=[func],type_ignores=[]),'<exposure>','exec'))
def analyze(a,start,end):
 global t
 tt=a[:,0];mask=(tt>start)&(tt<end);edge=lambda x:np.array([x if i%2==0 else np.interp(x,tt,a[:,i]) for i in range(a.shape[1])]);b=np.vstack([edge(start),a[mask],edge(end)]);t=b[:,0];v={n:b[:,2*i+1] for i,n in enumerate(nodes)};v['0']=np.zeros(len(t));rows=[]
 for d in dev:
  for pair,na,nb in [('vgs','g','s'),('vgd','g','d'),('vgb','g','b'),('vds','d','s')]:
   y=v[d['terminals'][na]]-v[d['terminals'][nb]];idx=int(np.argmax(abs(y)));rows.append({'instance':d['instance'],'terminals':d['terminals'],'pair':pair,'max_abs_V':float(abs(y[idx])),'peak_time_s':float(t[idx]),'exposure_3p63':exposure(y,3.63)})
 gate=[x for x in rows if x['pair']!='vds'];over=[x for x in rows if x['max_abs_V']>3.63];return {'interval_s':[start,end],'worst_gate':max(gate,key=lambda x:x['max_abs_V']),'worst_vds':max((x for x in rows if x['pair']=='vds'),key=lambda x:x['max_abs_V']),'exceeding_pairs':over,'gate_pair_exceedance_count':sum(x['max_abs_V']>3.63 for x in gate),'gate_device_exceedance_count':len(set(x['instance'] for x in gate if x['max_abs_V']>3.63))}
bounds=[0,1e-6,7.8125e-6,15.625e-6,23.4375e-6,31.25e-6];s={'scope':'Current-LVS 3.6 V TT27 integral-Q diagnostic. Startup and later windows, not physical lifetime assessment.','baseline_phase_windows':[analyze(a,x,y) for x,y in zip(bounds[:-1],bounds[1:])],'startup_comparisons':{'baseline_1ns':analyze(a,0,1e-6)}}
for tag in ['tmax_025ns','regularized_1ns','ramped_refs_reset']:
 f=r/tag/'wave.csv'
 if f.exists():
  b=np.loadtxt(f)
  if b[-1,0]>=1e-6*.999999:s['startup_comparisons'][tag]=analyze(b,0,1e-6)
(r/'summary_with_ramp.json').write_text(json.dumps(s,indent=2));print(json.dumps({'phases':[{'interval':x['interval_s'],'gate_pairs':x['gate_pair_exceedance_count'],'worst_gate':x['worst_gate']} for x in s['baseline_phase_windows']],'startup':{k:v['worst_gate'] for k,v in s['startup_comparisons'].items()}},indent=2))


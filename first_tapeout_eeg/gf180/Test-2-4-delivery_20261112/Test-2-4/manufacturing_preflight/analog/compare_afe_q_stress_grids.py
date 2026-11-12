from pathlib import Path
import json,numpy as np,ast,csv
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_q_stress_convergence';base=p/'afe_q_terminal_stress_3p6';c=json.loads((base/'connectivity.json').read_text());nodes=c['saved_nodes'];devices=c['selected_devices'];end=8e-6
func=next(x for x in ast.parse((p/'finalize_afe_q_terminal_stress.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='exposure');exec(compile(ast.Module(body=[func],type_ignores=[]),'<exposure>','exec'))
allresults={}
for label,path in [('baseline_1ns',base),('quarter_025ns',r)]:
 a=np.loadtxt(path/'wave.csv');tt=a[:,0];mask=tt<end;b=a[mask];last=np.array([np.interp(end,tt,a[:,i]) for i in range(a.shape[1])]);last[::2]=end;a=np.vstack([b,last]);t=a[:,0];v={n:a[:,2*i+1] for i,n in enumerate(nodes)};v['0']=np.zeros(len(t));results=[]
 for d in devices:
  for pair,na,nb in [('vgs','g','s'),('vgd','g','d'),('vgb','g','b'),('vds','d','s')]:
   y=v[d['terminals'][na]]-v[d['terminals'][nb]];idx=int(np.argmax(np.abs(y)));results.append({'instance':d['instance'],'terminals':d['terminals'],'pair':pair,'max_abs_V':float(abs(y[idx])),'signed_peak_V':float(y[idx]),'peak_time_s':float(t[idx]),'exposure_3p63':exposure(y,3.63)})
 gate=max((x for x in results if x['pair']!='vds'),key=lambda x:x['max_abs_V']);idx=np.argmin(v['ofph']);allresults[label]={'source':str(path),'rows':len(a),'worst_gate':gate,'worst_vds':max((x for x in results if x['pair']=='vds'),key=lambda x:x['max_abs_V']),'gate_pairs_above_3p63':sum(x['max_abs_V']>3.63 for x in results if x['pair']!='vds'),'OFPH_min_context_V':{n:float(v[n][idx]) for n in ['ofph','gclk','vclk','vdd','xc.ofph1','xc.ofphi','xa.xoff.xop.nph','xa.xoff.xon.nph']},'all_pairs':results}
s={'common_interval_s':[0,end],'scope':'Same 3.6 V TT27 Q diagnostic and input stimulus, maximum timestep 1 ns versus 0.25 ns. Finite two-grid comparison, not extrapolated convergence or lifetime qualification.','results':allresults};(r/'common_interval_comparison.json').write_text(json.dumps(s,indent=2));print(json.dumps({k:{x:y for x,y in v.items() if x!='all_pairs'} for k,v in allresults.items()},indent=2))

from pathlib import Path
import json,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'moscap_charge_equivalent';s=json.loads((r/'summary.json').read_text());a=np.loadtxt(r/'full_afe_q_diagnostic/wave.csv');b=np.loadtxt(p/'afe_ramp_fourcycle/ngspice47plus/wave.csv');names=['outp','outn','vbn','vbcm','vcm','blp','bln','vdd','rst','cia','cda','src'];s['top']['voltage_ranges_V']={n:{'min':float(a[:,2*i+1].min()),'max':float(a[:,2*i+1].max()),'last':float(a[-1,2*i+1])} for i,n in enumerate(names)};rows=[]
for t in [0,.5e-6,1e-6,5e-6,7.8e-6]:
 rows.append({'time_s':t,'Q_minus_C_V':{n:float(np.interp(t,a[:,0],a[:,2*i+1])-np.interp(t,b[:,0],b[:,2*i+1])) for i,n in enumerate(names)}})
s['top']['common_time_comparison']=rows;s['top']['max_selected_preedge_bias_difference_V']=max(abs(x['Q_minus_C_V'][n]) for x in rows for n in ['vbn','vbcm','vcm','blp','bln']);s['top']['limitations']='Diagnostic integral-Q implementation only; four cycles not settled gain, no PEX/mismatch/noise validation; source currents not saved in this inherited deck.'
s['math_audit']='mathematical_equivalence.json';(r/'summary.json').write_text(json.dumps(s,indent=2));print(json.dumps(s['top'],indent=2))

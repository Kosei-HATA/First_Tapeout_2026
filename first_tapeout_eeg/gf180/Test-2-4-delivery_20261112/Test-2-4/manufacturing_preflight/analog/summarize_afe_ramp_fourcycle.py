from pathlib import Path
import numpy as np,json
r=Path('/work/Test-2-4/manufacturing_preflight/analog/afe_ramp_fourcycle');s=json.loads((r/'summary.json').read_text());a=np.loadtxt(r/'ngspice46/wave.csv');b=np.loadtxt(r/'ngspice47plus/wave.csv');names=['outp','outn','vbn','vbcm','vcm','blp','bln','vdd','rst','cia','cda','src'];rows=[]
for t in [0,.5e-6,1e-6,5e-6,7.8e-6]:
 v1={n:float(np.interp(t,a[:,0],a[:,2*i+1])) for i,n in enumerate(names)};v2={n:float(np.interp(t,b[:,0],b[:,2*i+1])) for i,n in enumerate(names)};rows.append({'time_s':t,'ngspice46_V':v1,'ngspice47plus_V':v2,'difference_V':{n:v2[n]-v1[n] for n in names}})
s['common_time_comparison']=rows;s['initial_max_absolute_node_difference_V']=max(abs(v) for v in rows[0]['difference_V'].values());s['pre_reset_release_7p8us_max_bias_difference_V']=max(abs(rows[-1]['difference_V'][n]) for n in ['vbn','vbcm','vcm','blp','bln']);s['interpretation']='Both versions fail during first reset deassertion, before the differential input step. No settled gain or startup success. Close initial and selected pre-edge voltages do not prove a correct steady-state operating point.'
(r/'summary.json').write_text(json.dumps(s,indent=2));print(s['initial_max_absolute_node_difference_V'],s['pre_reset_release_7p8us_max_bias_difference_V']);print(rows[-1])

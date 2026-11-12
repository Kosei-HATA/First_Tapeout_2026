from pathlib import Path
import numpy as np,json
p=Path('/work/Test-2-4/manufacturing_preflight/analog');T=1/1.024e6;TM=T/32;T0=2e-6;nf=72
status=json.loads((p/'dac_even_status.json').read_text());complete={x['tag'] for x in status['completed_subruns']};rows=[]
for c,t in [('ss',85),('ff',-20)]:
 for tag,ncell in [('one',1),('all',31)]:
  tags=[f'even_{tag}{k}_{c}{t}_v0_s0' for k in [0,1]]
  if not all(x in complete for x in tags):continue
  qs=[]
  for name in tags:
   x=np.loadtxt(p/f'dac_even/runs/{name}/tr.csv');time=x[:,0];i=x[:,1]-x[:,3];mask=(time>=T0+4*T+4*TM)&(time<=T0+(nf-2)*T+4*TM);qs.append(float(np.trapezoid(i[mask],time[mask])))
  v=(qs[0]-qs[1])/(32*ncell)*1e15;rows.append({'corner':c,'temperature_C':t,'pattern':tag,'integrated_charge_C':qs,'toggle_count_difference':32,'cells':ncell,'even_charge_fC_per_toggle':v,'limit_fC_per_toggle':.016,'within_limit':abs(v)<=.016})
(p/'dac_even_independent_partial.json').write_text(json.dumps({'scope':'Only complete waveform pairs; no claim for pending patterns or corners. Same documented integration interval and toggle normalization as supplied bench.','results':rows},indent=2));print(json.dumps(rows,indent=2))

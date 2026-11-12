from pathlib import Path
import subprocess,json,numpy as np
from expand_resistor_parallel import expand
p=Path('/work/Test-2-4/manufacturing_preflight/analog');o=p/'parallel_expansion_validation';o.mkdir(exist_ok=True);results=[]
for m in [1,2,4,8,16]:
 for temp in [27,85]:
  for length in [291.28,582.56]:
   pair=[]
   for mode in ['original','expanded']:
    tag=f'm{m}_t{temp}_l{length}_{mode}';d=o/tag;d.mkdir()
    instances=f'XR out 0 0 ppolyf_u_1k r_length={length}u r_width=1u m={m}'
    if mode=='expanded':instances,record=expand(instances);(d/'mapping.json').write_text(json.dumps(record,indent=2))
    deck=f"""* Analysis-only full-wrapper parallel expansion validation
.include {p}/models/design.ngspice
.lib {p}/models/sm141064.ngspice res_typical
.temp {temp}
ITEST 0 out DC 0 AC 1
{instances}
.control
set numdgt=15
dc ITEST -1u 1u 1u
wrdata dc.csv v(out)
ac lin 3 0.5 100
wrdata ac.csv real(v(out)) imag(v(out))
noise v(out) ITEST lin 11 0.5 100
setplot noise1
wrdata noise.csv onoise_spectrum
quit
.endc
.end
"""
    (d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\nset enable_noisy_r\n')
    r=subprocess.run(['/foss/tools/bin/ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=60);(d/'run.log').write_text(r.stdout+r.stderr)
    ac=np.atleast_2d(np.loadtxt(d/'ac.csv'));dc=np.atleast_2d(np.loadtxt(d/'dc.csv'));noise=np.atleast_2d(np.loadtxt(d/'noise.csv'));R=ac[0,1]
    pair.append((ac,dc,{'mode':mode,'R_ohm':float(R),'noise_PSD_ratio_to_4kTR':float(noise[0,1]**2/(4*1.380649e-23*(temp+273.15)*R)),'exitcode':r.returncode}))
   results.append({'m':m,'temperature_C':temp,'length_um':length,'AC_max_relative_difference':float(np.max(abs(pair[0][0][:,1]-pair[1][0][:,1]))/abs(pair[0][0][0,1])),'DC_max_voltage_difference_V':float(np.max(abs(pair[0][1]-pair[1][1]))),'results':[x[2] for x in pair]})
(o/'summary.json').write_text(json.dumps({'scope':'thermal-only explicit full-wrapper parallel equivalence, no local mismatch/flicker certification','pairs':results},indent=2))
print('pairs',len(results),'maxACrel',max(x['AC_max_relative_difference'] for x in results),'maxDC',max(x['DC_max_voltage_difference_V'] for x in results),'expandedPSD',[x['results'][1]['noise_PSD_ratio_to_4kTR'] for x in results])

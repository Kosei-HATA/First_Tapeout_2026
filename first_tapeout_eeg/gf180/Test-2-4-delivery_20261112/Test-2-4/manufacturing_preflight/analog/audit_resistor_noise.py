from pathlib import Path
import subprocess,os,json,time,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');out=p/'resistor_noise_sanity';out.mkdir(exist_ok=True)
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH']
cases=[('pdk_one',27,'XR out 0 0 ppolyf_u_1k r_length=291.28u r_width=1u'),('pdk_series',27,'XR1 out n 0 ppolyf_u_1k r_length=291.28u r_width=1u\nXR2 n 0 0 ppolyf_u_1k r_length=291.28u r_width=1u'),('pdk_parallel',27,'XR1 out 0 0 ppolyf_u_1k r_length=291.28u r_width=1u\nXR2 out 0 0 ppolyf_u_1k r_length=291.28u r_width=1u'),('pdk_hot',85,'XR out 0 0 ppolyf_u_1k r_length=291.28u r_width=1u'),('pdk_double_length',27,'XR out 0 0 ppolyf_u_1k r_length=582.56u r_width=1u'),('ideal_R',27,'R1 out 0 300k'),('ideal_R_noiseless',27,'R1 out 0 300k noisy=0'),('ideal_B',27,'B1 out 0 I=V(out)/300k')]
results=[]
for tag,temp,devices in cases:
 d=out/tag;d.mkdir()
 deck=f"""* independent resistor zero-bias thermal noise sanity
.include {p}/models/design.ngspice
.lib {p}/models/sm141064.ngspice res_typical
.temp {temp}
ITEST 0 out DC 0 AC 1
{devices}
.control
set noaskquit
set numdgt=15
ac lin 2 0.5 100
wrdata ac.csv real(v(out)) imag(v(out))
noise v(out) ITEST dec 10 0.5 100
setplot noise1
wrdata noise.csv onoise_spectrum inoise_spectrum
quit
.endc
.end
"""
 (d/'tb.spice').write_text(deck);start=time.time();r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=60)
 (d/'run.log').write_text(r.stdout+r.stderr)
 try:
  ac=np.atleast_2d(np.loadtxt(d/'ac.csv'));n=np.atleast_2d(np.loadtxt(d/'noise.csv'));R=float(ac[0,1]);expected=4*1.380649e-23*(temp+273.15)*R
  result={'case':tag,'seconds':time.time()-start,'exitcode':r.returncode,'R_ac_lowfreq_ohm':R,'frequency_Hz':float(n[0,0]),'output_noise_V_per_sqrtHz':float(n[0,1]),'expected_4kTR_V2_per_Hz':expected,'PSD_ratio':float(n[0,1]**2/expected)}
 except Exception as e:result={'case':tag,'error':repr(e),'exitcode':r.returncode}
 results.append(result);print(result,flush=True)
(out/'summary.json').write_text(json.dumps({'scope':'Zero DC bias thermal test; small-signal only, no flicker qualification','results':results},indent=2))


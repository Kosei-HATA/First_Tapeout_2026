from pathlib import Path
import subprocess,os,numpy as np,json
p=Path('/work/Test-2-4/manufacturing_preflight/analog');o=p/'adc_rin_noise_budget';o.mkdir(exist_ok=True)
rr=[]
for tag,explicit,flag in [('m16_thermal',False,True),('parallel16_thermal',True,True),('m16_unflagged',False,False)]:
 d=o/tag;d.mkdir()
 resistors='\n'.join(f'XR{s}{i} IN{s} S{s} 0 ppolyf_u_1k r_length=291.28u r_width=1u' for s in ['P','N'] for i in range(16)) if explicit else '\n'.join(f'XRIN{s} IN{s} S{s} 0 ppolyf_u_1k r_length=291.28u r_width=1u m=16' for s in ['P','N'])
 deck=f"""* Current design ADC RIN pair; thermal-only isolated budget
.include {p}/models/design.ngspice
.lib {p}/models/sm141064.ngspice res_typical
.temp 27
VCM CM 0 1.65
VSRC SRC 0 DC 0 AC 1
EP INP CM SRC 0 0.5
EN INN CM SRC 0 -0.5
{resistors}
RSP SP CM 1 noisy=0
RSN SN CM 1 noisy=0
.control
set numdgt=15
op
print v(inp) v(inn) v(sp) v(sn)
ac lin 501 0.5 100
let hr=real(v(sp)-v(sn))
let hi=imag(v(sp)-v(sn))
wrdata gain.csv hr hi
noise v(sp,sn) VSRC lin 501 0.5 100
setplot noise1
wrdata noise.csv onoise_spectrum inoise_spectrum
quit
.endc
.end
"""
 (d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\n'+('set enable_noisy_r\n' if flag else ''))
 r=subprocess.run(['/foss/tools/bin/ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=60);(d/'run.log').write_text(r.stdout+r.stderr)
 g=np.loadtxt(d/'gain.csv');n=np.loadtxt(d/'noise.csv');gain=np.hypot(g[:,1],g[:,3]);inp=n[:,1]/gain;R=1/gain[0]-1
 rr.append({'case':tag,'exitcode':r.returncode,'effective_R_per_leg_ohm':float(R),'gain_at_0p5Hz_V_per_V':float(gain[0]),'input_density_V_per_sqrtHz':float(inp[0]),'input_rms_0p5_100Hz_V':float(np.sqrt(np.trapezoid(inp**2,n[:,0]))),'noise_command_input_ref_max_relative_difference':float(np.max(abs(inp-n[:,3])/np.maximum(inp,1e-99))),'expected_thermal_rms_V':float(np.sqrt(8*1.380649e-23*300.15*R*99.5))})
s={'scope':'Isolated current ADC RIN resistor pair, VCM1.65V, zero differential DC, ideal low-noise signal source and ideal virtual-ground approximation via noiseless1ohm loads; thermal-only, not system/chopped/DEM noise','band_Hz':[.5,100],'results':rr,'electrode_target_rms_V':5.876768442749352e-9,'direct_target_comparison_valid':False}
(o/'summary.json').write_text(json.dumps(s,indent=2));print(json.dumps(s,indent=2))

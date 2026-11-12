from pathlib import Path
import subprocess,time,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'moscap_charge_equivalent';r.mkdir(exist_ok=True);binary=p/'ngspice48_isolated/install/bin/ngspice'
models='* Diagnostic exact integral of official C(V), not PDK qualification\n'
for kind,c1,c2,c3,c4 in [('nmos',.002003,.00198,6.25,-3.9375),('pmos',.001998,.00196,-6.25,-4.9375)]:
 models+=f'.subckt audit_q_{kind} 1 2 c_length=28.6u c_width=44u dtemp=0\nCQ 1 2 q=\'cap_{kind}_03v3_corner*c_length*c_width*({c1}*v(1,2)+({c2}/{c3})*ln(cosh({c3}*v(1,2)+({c4}))/cosh({c4})))\' dtemp=dtemp\n.ends\n'
(r/'q_models.spice').write_text(models)
header=f'.include {p}/models/design.ngspice\n.lib {p}/models/sm141064.ngspice typical\n.lib {p}/models/sm141064.ngspice moscap_typical\n.include {r}/q_models.spice\n'
deck='* nonlinear C versus exact integral Q\n'+header+f'.include {p}/moscap_saved_wave_replay/stimulus.inc\n'
for kind,sign in [('nmos',1),('pmos',-1)]:
 for impl,model in [('c','cap_'+kind+'_03v3'),('q','audit_q_'+kind)]:
  n=kind+'_'+impl;deck+=f'E{n} {n} 0 node 0 {sign}\nX{n} {n} 0 {model} c_length=28.6u c_width=44u m=1\n'
deck+='\n.temp 27\n.options method=gear reltol=1e-4 abstol=1e-12 vntol=1e-7\n.control\nset numdgt=15\ntran 1n 7.932482490343595u 0 1n\nwrdata wave.csv v(node) i(enmos_c) i(enmos_q) i(epmos_c) i(epmos_q)\nquit\n.endc\n.end\n'
def run(tag,deck):
 d=r/tag;d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\n');start=time.time()
 try:q=subprocess.run([str(binary),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log);z={'case':tag,'seconds':time.time()-start,'exitcode':rc,'diagnostics':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)]};a=None
 if (d/'wave.csv').exists():a=np.atleast_2d(np.loadtxt(d/'wave.csv'));z.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()))
 return z,a
z,a=run('unit_equivalence',deck);s={'unit':z};ok=False
if a is not None and z['last_time_s']>7.93e-6:
 metrics={}
 for kind,ic,iq in [('nmos',3,5),('pmos',7,9)]:
  c=a[:,ic];q=a[:,iq];t=a[:,0];rms=lambda x:np.sqrt(np.trapezoid(x*x,t)/(t[-1]-t[0]));qc=np.trapezoid(c,t);qq=np.trapezoid(q,t);metrics[kind]={'rms_current_difference_relative':float(rms(q-c)/rms(c)),'integrated_charge_C':float(qc),'q_integrated_charge_C':float(qq),'integrated_charge_relative_difference':float((qq-qc)/qc)}
 z['comparison']=metrics;ok=all(abs(x['integrated_charge_relative_difference'])<.01 and x['rms_current_difference_relative']<.01 for x in metrics.values())
s['unit_gate_for_top']=ok;(r/'summary.json').write_text(json.dumps(s,indent=2));print(s,flush=True)
if ok:
 bias=(p/'sim_work/gf180/tapeout/bias/eeg_bias.spice').read_text().replace('cap_nmos_03v3','audit_q_nmos').replace('cap_pmos_03v3','audit_q_pmos');(r/'bias_q_diagnostic.spice').write_text(bias)
 top=(p/'afe_ramp_fourcycle/ngspice47plus/tb.spice').read_text().replace(str(p/'sim_work/gf180/tapeout/bias/eeg_bias.spice'),str(r/'bias_q_diagnostic.spice'));top=top.replace('.temp 27',f'.include {r}/q_models.spice\n.temp 27')
 z,a=run('full_afe_q_diagnostic',top);s['top']=z
 if a is not None:z['completed']=bool(a[-1,0]>=31.25e-6*.999999);z['cycles']=float(a[-1,0]/7.8125e-6)
 (r/'summary.json').write_text(json.dumps(s,indent=2));print(s,flush=True)

from pathlib import Path
import subprocess,time,json,re,hashlib,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'moscap_saved_wave_replay';r.mkdir(exist_ok=True);a=np.loadtxt(p/'afe_reset_isolation/held/wave.csv');t=a[:,0];v=a[:,7];end=float(t[-1]);stop=end+100e-9;C=28.6e-6*44e-6*(.002003+.00198*np.tanh(6.25*v[-1]-3.9375))
points='VREPLAY node 0 PWL(\n'+'\n'.join('+ '+format(x,'.17g')+' '+format(y,'.17g') for x,y in zip(t,v))+'\n+ '+format(stop,'.17g')+' '+format(v[-1],'.17g')+')\n'
(r/'stimulus.inc').write_text(points)
header=f'.include {p}/models/design.ngspice\n.lib {p}/models/sm141064.ngspice typical\n.lib {p}/models/sm141064.ngspice moscap_typical\n.include {r}/stimulus.inc\n'
results=[]
for version,binary in [('46','/foss/tools/bin/ngspice'),('47plus',str(p/'ngspice48_isolated/install/bin/ngspice'))]:
 for kind in ['official','linear_diagnostic']:
  tag=version+'_'+kind;d=r/tag;d.mkdir(exist_ok=True);element='XC node 0 cap_nmos_03v3 c_length=28.6u c_width=44u m=1' if kind=='official' else f'CLIN node 0 {C:.17g}'
  deck='* saved converged voltage replay, not surrounding-circuit equivalence\n'+header+element+f'\n.temp 27\n.options method=gear reltol=1e-4 abstol=1e-12 vntol=1e-7\n.control\nset numdgt=15\ntran 1n {stop:.17g} 0 1n\nwrdata wave.csv v(node) i(vreplay)\nquit\n.endc\n.end\n';(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\n');start=time.time()
  try:q=subprocess.run([binary,'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
  except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
  (d/'run.log').write_text(log);z={'case':tag,'seconds':time.time()-start,'exitcode':rc,'diagnostics':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)],'completed':False}
  if (d/'wave.csv').exists():
   b=np.atleast_2d(np.loadtxt(d/'wave.csv'));expected=np.interp(b[:,0],t,v);z.update(last_time_s=float(b[-1,0]),completed=bool(b[-1,0]>=stop*.999999),finite=bool(np.isfinite(b).all()),max_voltage_replay_error_V=float(np.abs(b[:,1]-expected).max()),max_abs_source_current_A=float(np.abs(b[:,3]).max()),rows=len(b))
  results.append(z);s={'scope':'Replay of converged terminal voltage only; no original driving impedance or rejected solver state','source_last_time_s':end,'stop_time_s':stop,'extra_interval':'100 ns constant endpoint hold, not measured circuit trajectory','linear_C_F':float(C),'points':len(t),'min_source_dt_s':float(np.diff(t).min()),'stimulus_sha256':hashlib.sha256(points.encode()).hexdigest(),'results':results};(r/'summary.json').write_text(json.dumps(s,indent=2));print(z,flush=True)

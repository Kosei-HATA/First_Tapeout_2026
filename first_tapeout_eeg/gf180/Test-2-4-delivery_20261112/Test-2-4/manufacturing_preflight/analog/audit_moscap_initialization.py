from pathlib import Path
import subprocess,time,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');out=p/'moscap_initialization_audit';out.mkdir(exist_ok=True)
original=(p/'afe_current_top_pilot/tb.spice').read_text()
header=f'.include {p}/models/design.ngspice\n.lib {p}/models/sm141064.ngspice typical\n.lib {p}/models/sm141064.ngspice moscap_typical\n'
nodeset=original[original.index('.nodeset'):original.index('.control')]
bias=original[:original.index('RCLKP')]+nodeset
top=original[:original.index('.control')]
single=header+'VDRV drive 0 0.85\nRDRV drive gate 1k\nXC gate 0 cap_nmos_03v3 c_length=28.6u c_width=44u\n'
cases=[]
for method in ['gear','trap']:
 for init in ['op','uic','ramp']:
  cases.append(('single_'+method+'_'+init,single,method,init,'v(gate)',1e-6))
  cases.append(('bias_'+method+'_'+init,bias,method,init,'v(vbn) v(vcm)',2e-6))
for method in ['gear','trap']:
 cases.append(('top_'+method+'_op',top,method,'op','v(outp) v(vbn)',.5e-6))
results=[]
for tag,body,method,init,save,stop in cases:
 d=out/tag;d.mkdir()
 body=re.sub(r'^\.options.*$','',body,flags=re.M)
 if init=='ramp':
  body=body.replace('VDRV drive 0 0.85','VDRV drive 0 PWL(0 0 500n .85)').replace('VDD VDD 0 3.3','VDD VDD 0 PWL(0 0 1u 3.3)')
 deck='* original model isolation\n'+body+f'\n.options method={method} reltol=1e-4 abstol=1e-12 vntol=1e-7\n.control\nset numdgt=15\ntran 1n {stop} 0 1n '+('uic' if init=='uic' else '')+f'\nwrdata wave.csv {save}\nquit\n.endc\n.end\n'
 (d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\n')
 t=time.time()
 try:
  q=subprocess.run(['/foss/tools/bin/ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=30);log=q.stdout+q.stderr;(d/'run.log').write_text(log)
  bad=bool(re.search('aborted|Timestep too small|Error:',log,re.I));last=None
  if (d/'wave.csv').exists():last=float(np.atleast_2d(np.loadtxt(d/'wave.csv'))[-1,0])
  z={'tag':tag,'seconds':time.time()-t,'exitcode':q.returncode,'aborted':bad,'last_time_s':last,'requested_time_s':stop,'reached_stop':last is not None and last>=stop*.999,'diagnostic':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)]}
 except subprocess.TimeoutExpired:z={'tag':tag,'seconds':time.time()-t,'timeout_s':30}
 results.append(z);(out/'summary.json').write_text(json.dumps(results,indent=2));print(z,flush=True)

from pathlib import Path
import subprocess,os,json,time,signal
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');assert json.loads((p/'load_audit.json').read_text())['pass'];env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1');rows=[]
for name in ['schematic','cap','rc']:
 d=p/name;start=time.time();state={'variant':name,'status':'running'};(p/'status.json').write_text(json.dumps(rows+[state],indent=2))
 with (d/'run.log').open('w') as log:
  proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=proc.wait(timeout=300)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout_300s'
 state.update(status='finished',exitcode=rc,seconds=round(time.time()-start,2));rows.append(state);(p/'status.json').write_text(json.dumps(rows,indent=2));print(state,flush=True)

from pathlib import Path
import os,subprocess,json,time,signal
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');d=p/'sparse160';d.mkdir(exist_ok=True);s=(p/'rc/tb.spice').read_text();assert 'tran 0.01n 500n 0 0.05n' in s;(d/'tb.spice').write_text(s.replace('tran 0.01n 500n 0 0.05n','tran 0.01n 160n 0 0.05n'))
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1');start=time.time()
with (d/'run.log').open('w') as log:
 proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=proc.wait(timeout=300)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout_300s'
r={'variant':'sparse160','status':'finished','exitcode':rc,'seconds':round(time.time()-start,2),'only_change':'Original SPARSE full circuit, tstop160ns; all other stimulus and step parameters unchanged'};(p/'sparse160_status.json').write_text(json.dumps(r,indent=2));print(r)

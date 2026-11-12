from pathlib import Path
import os,subprocess,json,time,signal,re
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');d=p/'rc_klu';d.mkdir(exist_ok=True);s=(p/'rc/tb.spice').read_text();assert '.options sparse reltol=1e-4' in s;(d/'tb.spice').write_text(s.replace('.options sparse reltol=1e-4','.options klu reltol=1e-4'))
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1');start=time.time()
with (d/'run.log').open('w') as log:
 proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=proc.wait(timeout=300)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout_300s'
r={'variant':'rc_klu','status':'finished','exitcode':rc,'seconds':round(time.time()-start,2),'only_change':'.options sparse -> klu'}
rows=json.loads((p/'status.json').read_text());rows.append(r);(p/'status.json').write_text(json.dumps(rows,indent=2));print(r)

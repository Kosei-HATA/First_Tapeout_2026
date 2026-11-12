from pathlib import Path
import os,subprocess,json,time,signal
p=Path('/work/Test-2-4/manufacturing_preflight/analog');os.chdir(p)
while True:
 try:
  if len(json.loads((p/'clock_sensitivity.json').read_text())['cases'])==15:break
 except Exception:pass
 time.sleep(10)
env=os.environ.copy();env.update(PATH=str(p/'sim_bin')+':/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
results=[]
for corner,temp in [('typical',27),('ss',85),('ff',-20)]:
 name='dac_brk_'+corner;start=time.time();cmd=['python3','-u',str(p/'sim_work/gf180/tapeout/sim/dac1/dac1_check.py'),'--tests','brk','--corner',corner,'--temp',str(temp)]
 (p/'dac_break_status.json').write_text(json.dumps({'stage':'running','test':name,'start_epoch':start,'cmd':cmd,'completed':results},indent=2))
 with (p/(name+'.log')).open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
  try:rc=proc.wait(timeout=1800)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout_1800s'
 results.append({'test':name,'exitcode':rc,'seconds':round(time.time()-start,2),'log':name+'.log'})
 (p/'dac_break_results.json').write_text(json.dumps(results,indent=2))
(p/'dac_break_status.json').write_text(json.dumps({'stage':'finished','completed':results},indent=2))

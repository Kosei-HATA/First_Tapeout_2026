from pathlib import Path
import subprocess,time,json,os,signal
p=Path('/work/Test-2-4/functional'); root=p/'sim_work/gf180/tapeout/sim'
jobs=[('afe_actual_bias','afe/afe_bias_noise.py',['--cases','typical:27:2','ss:85:2','ff:-20:2'])]
for c,t in [('typical',27),('ss',85),('ff',-20)]:
 for mode in ['op','delay']:
  jobs.append((f'quantizer_{mode}_{c}','quantizer/qcmp_check.py',[mode,'--corner',c,'--temp',str(t)]))
results=[]
for name,script,args in jobs:
 start=time.time()
 with (p/(name+'.log')).open('w') as log:
  proc=subprocess.Popen(['python3','-u',str(root/script),*args],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try: rc=proc.wait(timeout=600)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout'
 results.append(dict(test=name,exitcode=rc,seconds=round(time.time()-start,1),log=name+'.log'))
 (p/'extended_analog_results.json').write_text(json.dumps(results,indent=2));print(results[-1],flush=True)

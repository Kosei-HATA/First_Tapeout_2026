from pathlib import Path
import os,subprocess,json,time
p=Path('/work/Test-2-4/functional');os.chdir(p)
e=os.environ.copy();e.update(PATH=str(p/'sim_bin')+':/foss/tools/bin:'+e['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
t=time.time()
with (p/'afe_clock.log').open('w') as log:r=subprocess.run(['python3','sim_work/gf180/tapeout/sim/afe/clk_check.py'],env=e,stdout=log,stderr=subprocess.STDOUT,timeout=600)
(p/'afe_clock.exitcode').write_text(str(r.returncode));(p/'afe_clock.status.json').write_text(json.dumps({'exitcode':r.returncode,'seconds':time.time()-t}))
subprocess.run(['python3','summarize_analog.py'],stdout=(p/'summarize_analog.log').open('w'))

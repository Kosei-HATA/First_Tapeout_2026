from pathlib import Path
import subprocess,os,json,time,signal,concurrent.futures
p=Path('/work/Test-2-4/functional');os.chdir(p)
env=os.environ.copy();env.update(LD_LIBRARY_PATH='/foss/tools/iverilog/lib:'+env.get('LD_LIBRARY_PATH',''),PATH=str(p/'sim_bin')+':/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHON='python3',PDK_ROOT='/foss/pdks',GL_TOP_NL=str(p/'netlists/eeg_digital_top.nl.v'),GL_ADC_NL=str(p/'netlists/eeg_adc_dig.nl.v'))
def job(name,cmd,limit):
 start=time.time()
 with (p/(name+'.log')).open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
  try:rc=proc.wait(timeout=limit)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM);proc.wait();rc='timeout'
 r={'name':name,'exitcode':rc,'seconds':round(time.time()-start,2)}
 (p/(name+'.status.json')).write_text(json.dumps(r,indent=2));return r
def analog():
 out=[]
 for n,c,l in [('analog_checks',['python3','run_analog_checks.py'],1600),('extended_analog',['python3','run_extended_analog.py'],1600),('adc_clock',['python3','sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py'],1200)]:out.append(job(n,c,l))
 (p/'adc_clock.exitcode').write_text(str(out[-1]['exitcode']))
 job('summarize_analog',['python3','summarize_analog.py'],60)
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 d=pool.submit(job,'digital_tests',['bash','rtl_tests/run_tests.sh','--gl'],3600);a=pool.submit(analog)
 results={'digital':d.result(),'analog':a.result()}
(p/'execution_summary.json').write_text(json.dumps(results,indent=2))

from pathlib import Path
import os,subprocess,json,time,shutil
p=Path('/work/Test-2-4/functional');os.chdir(p)
a=p/'initial_runtime_error';a.mkdir(exist_ok=True)
for n in ['digital_tests.log','digital_tests.status.json','execution_summary.json']:
 shutil.copy2(p/n,a/n)
shutil.copytree(p/'rtl_tests/build/logs',a/'digital_logs',dirs_exist_ok=True)
s=(p/'run_suite.py').read_text();s=s.replace("env=os.environ.copy();env.update(","env=os.environ.copy();env.update(LD_LIBRARY_PATH='/foss/tools/iverilog/lib:'+env.get('LD_LIBRARY_PATH',''),")
(p/'run_suite.py').write_text(s)
e=os.environ.copy();e.update(LD_LIBRARY_PATH='/foss/tools/iverilog/lib:'+e.get('LD_LIBRARY_PATH',''),PATH='/foss/tools/bin:'+e['PATH'],PYTHON='python3',PDK_ROOT='/foss/pdks',GL_TOP_NL=str(p/'netlists/eeg_digital_top.nl.v'),GL_ADC_NL=str(p/'netlists/eeg_adc_dig.nl.v'))
t=time.time()
with (p/'digital_tests.log').open('w') as log:r=subprocess.run(['bash','rtl_tests/run_tests.sh','--gl'],env=e,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
d={'name':'digital_tests','exitcode':r.returncode,'seconds':round(time.time()-t,2),'environment_fix':'LD_LIBRARY_PATH includes /foss/tools/iverilog/lib'}
(p/'digital_tests.status.json').write_text(json.dumps(d,indent=2))
s=json.loads((p/'execution_summary.json').read_text());s['digital']=d;(p/'execution_summary.json').write_text(json.dumps(s,indent=2))

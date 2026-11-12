from pathlib import Path
import os,json,time,importlib.util,types,traceback
p=Path('/work/Test-2-4/manufacturing_preflight/analog')
while json.loads((p/'dac_trace_status.json').read_text())['stage']!='finished':time.sleep(10)
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH'];os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
f=p/'sim_work/gf180/tapeout/sim/dac1/dac1_check_sequential.py';s=importlib.util.spec_from_file_location('dac',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);base=m.run;results=[];subruns=[]
def run(o,tag,*args,**kw):
 start=time.time();(p/'dac_even_status.json').write_text(json.dumps({'stage':'running','subrun':tag,'start_epoch':start,'completed_subruns':subruns,'completed_corners':results},indent=2));print('Starting '+tag,flush=True)
 x=base(o,tag,*args,**kw);subruns.append({'tag':tag,'seconds':round(time.time()-start,2),'last_time_s':float(x[-1,0]),'samples':len(x)});(p/'dac_even_subruns.json').write_text(json.dumps(subruns,indent=2));print(subruns[-1],flush=True);return x
m.run=run
try:
 for c,t in [('ss',85),('ff',-20)]:
  start=time.time();o=types.SimpleNamespace(corner=c,temp=t,voff=0,tol='A',mc=0);r=m.even(o);vals={k:float(v*1e15) for k,v in r.items()};results.append({'corner':c,'temperature_C':t,'tolerance':'A','even_charge_fC_per_toggle':vals,'limit_fC_per_toggle':0.016,'within_limit':all(abs(v)<=.016 for v in vals.values()),'seconds':round(time.time()-start,2)});(p/'dac_even_results.json').write_text(json.dumps(results,indent=2));print(results[-1],flush=True)
 (p/'dac_even_status.json').write_text(json.dumps({'stage':'finished','completed_corners':results,'completed_subruns':subruns},indent=2))
except Exception as e:
 (p/'dac_even_status.json').write_text(json.dumps({'stage':'failed','error':repr(e),'completed_corners':results,'completed_subruns':subruns},indent=2));traceback.print_exc();raise

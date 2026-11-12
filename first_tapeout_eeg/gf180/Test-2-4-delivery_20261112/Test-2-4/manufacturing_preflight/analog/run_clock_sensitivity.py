from pathlib import Path
import importlib.util,json,os,time,math,traceback
p=Path('/work/Test-2-4/manufacturing_preflight/analog')
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH'];os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
f=p/'sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py';s=importlib.util.spec_from_file_location('aclk',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[]
for vdd in [3.0,3.3,3.6]:
 m.VDD=vdd;m.HERE=str(p/'clock_sensitivity'/str(vdd))
 for corner,temp in [('typical',27),('ss',85),('ff',-20),('sf',27),('fs',27)]:
  start=time.time();row={'vdd':vdd,'corner':corner,'temperature_C':temp}
  try:
   _,_,values=m.run(corner,temp);row['measurements']=values; margins=[v for k,v in values.items() if k.startswith('margin')];row['minimum_margin_ns']=min(margins);row['finite']=all(math.isfinite(v) for v in values.values());row['positive_sequence_margins']=bool(row['finite'] and min(margins)>0)
  except Exception as e:row['error']=repr(e);traceback.print_exc()
  row['seconds']=round(time.time()-start,2);rows.append(row);print(json.dumps(row),flush=True)
  (p/'clock_sensitivity.json').write_text(json.dumps({'scope':'Clock/loaded-OTA timing sensitivity, fixed original ideal bias values and CM=1.65V. Schematic only, no PEX or full supply-tracking bias. 3.0/3.6V exploratory bounds from digital corner documentation, not confirmed full analog specification.','cases':rows},indent=2))

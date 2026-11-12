from pathlib import Path
import importlib.util,json,os,time,math
p=Path('/work/Test-2-4/manufacturing_preflight/analog');os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH'];os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
f=p/'sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py';s=importlib.util.spec_from_file_location('aclk',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);deck=m.deck
m.deck=lambda c,t:deck(c,t).replace('reltol=1e-4','reltol=1e-5').replace('tran 0.01n 500n 0 0.05n','tran 0.005n 500n 0 0.025n')
rows=[]
for vdd in [3.3,3.6]:
 m.VDD=vdd;m.HERE=str(p/'clock_convergence'/str(vdd));_,_,values=m.run('ff',-20);rows.append({'vdd':vdd,'corner':'ff','temperature_C':-20,'measurements':values,'minimum_margin_ns':min(v for k,v in values.items() if k.startswith('margin'))})
(p/'clock_convergence.json').write_text(json.dumps({'conditions':'reltol1e-5, output step5ps, maximum step25ps; original reltol1e-4/10ps/50ps. No circuit/model changes.','cases':rows},indent=2))

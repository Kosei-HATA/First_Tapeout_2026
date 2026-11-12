from pathlib import Path
import importlib.util,json,numpy as np,math,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');f=Path('/work/Test-2-4/functional/sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py');sp=importlib.util.spec_from_file_location('clock',f);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);rows=[]
for job in json.loads((p/'status.json').read_text()):
 name=job['variant'];d=p/name;row=dict(job);log=(d/'run.log').read_text();row['error_lines']=re.findall(r'^.*(?:Error:|aborted|stepping failed|Transient op).*$' ,log,re.M)
 if job.get('exitcode')!=0 or not (d/'out.csv').exists():rows.append(row);continue
 x=np.loadtxt(d/'out.csv');t=x[:,0];v={n:x[:,2*i+1] for i,n in enumerate(a.NAMES)};r={}
 for e,old,new,tag in [(a.E1,'a','b','A->B'),(a.E2,'b','a','B->A')]:
  t0=e-2e-9;co,no=v['ci'+old],v['nci'+old];cn,nn=v['ci'+new],v['nci'+new];do,dno=v['cd'+old],v['ncd'+old];dn,dnn=v['cd'+new],v['ncd'+new]
  r['dead '+tag]=(a.tg_on_start(t,cn,nn,t0)-a.tg_full_off(t,co,no,t0))*1e9
  r['overlap '+tag]=(a.cross(t,do,1.65,False,t0)-a.cross(t,dn,1.65,True,t0))*1e9
  r['margin1 '+tag]=(a.tg_off_start(t,co,no,t0)-a.tg_full_on(t,dn,dnn,t0))*1e9
  r['margin2 '+tag]=(a.tg_off_start(t,do,dno,t0)-a.tg_full_on(t,cn,nn,t0))*1e9
  r['delay '+tag]=(a.cross(t,dn,1.65,True,t0)-e)*1e9
 for n,rising in [('cia',True),('ncia',False),('cda',True),('ncda',False)]:
  r[n+' edge10_90']=(a.cross(t,v[n],2.97 if rising else .33,rising,a.E2-2e-9)-a.cross(t,v[n],.33 if rising else 2.97,rising,a.E2-2e-9))*1e9
 row['timing_ns']=r;row['finite']=bool(np.isfinite(x).all() and all(math.isfinite(z) for z in r.values()));row['positive_sequence_margins']=row['finite'] and all(z>0 for k,z in r.items() if k.startswith('margin'));row['supply_charge_per_edge_pC']=-np.trapezoid(v['idd'][t>50e-9],t[t>50e-9])/2*1e12
 nodes=json.loads((p/'comparison_inputs.json').read_text())['load_wave_nodes'];op=np.atleast_2d(np.loadtxt(d/'op.csv'));row['load_dc_V']={n:float(op[-1,2*i+1]) for i,n in enumerate(nodes)};w=np.loadtxt(d/'load_wave.csv');row['load_ranges_V']={n:[float(w[:,2*i+1].min()),float(w[:,2*i+1].max())] for i,n in enumerate(nodes)}
 rows.append(row)
base=next((r for r in rows if r['variant']=='schematic' and 'timing_ns' in r),None)
if base:
 for r in rows:
  if 'timing_ns' in r:r['delta_vs_schematic_ns']={k:v-base['timing_ns'][k] for k,v in r['timing_ns'].items()}
result={'scope':'Nominal typical27C/3.3V comparison; same real bias and schematic OTA 24MOS loads; isolated clock internal parasitics only.','cases':rows,'limits':['External TG diffusion and resistance parameters are schematic approximations.','ADC input pair held at common mode, not closed-loop signal trajectories.','Upper-level output routes, coupling and supply distribution excluded.','No minimum guardband specification or full-chip timing signoff.']};(p/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps([{k:v for k,v in r.items() if k not in ['load_ranges_V','load_dc_V']} for r in rows],indent=2))

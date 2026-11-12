from pathlib import Path
import os,json,time,subprocess,signal,concurrent.futures,hashlib,importlib.util,math,numpy as np,threading,re
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');out=p/'fixed_nominal_rc_pvt';out.mkdir(exist_ok=True);lock=threading.Lock();rows=[]
rc=p.parents[1]/'extraction/core_pex_probe/clock_probe/flat/rc.spice';rc_hash=hashlib.sha256(rc.read_bytes()).hexdigest();old='/work/Test-2-4/functional/sim_work/gf180/tapeout/adc/eeg_adc_clk.spice';nodes=json.loads((p/'comparison_inputs.json').read_text())['load_wave_nodes'];extra=' '.join(f'v({n})' for n in nodes)
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
def save():
 with lock:(out/'results.json').write_text(json.dumps({'scope':'Device PVT with fixed nominal clock RC. Not independent RC corners, whole-chip PEX, or manufacturing signoff.','rc_sha256':rc_hash,'max_workers':2,'per_case_timeout_s':600,'cases':rows},indent=2))
def measure(d,vdd):
 src='/work/Test-2-4/functional/sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py';sp=importlib.util.spec_from_file_location('clock_'+str(vdd),src);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);a.VDD=vdd
 z=np.loadtxt(d/'out.csv');t=z[:,0];v={n:z[:,2*i+1] for i,n in enumerate(a.NAMES)};r={}
 for e,oldphase,new,tag in [(a.E1,'a','b','A->B'),(a.E2,'b','a','B->A')]:
  t0=e-2e-9;co,no=v['ci'+oldphase],v['nci'+oldphase];cn,nn=v['ci'+new],v['nci'+new];do,dno=v['cd'+oldphase],v['ncd'+oldphase];dn,dnn=v['cd'+new],v['ncd'+new]
  r['dead '+tag]=(a.tg_on_start(t,cn,nn,t0)-a.tg_full_off(t,co,no,t0))*1e9;r['overlap '+tag]=(a.cross(t,do,vdd/2,False,t0)-a.cross(t,dn,vdd/2,True,t0))*1e9;r['margin1 '+tag]=(a.tg_off_start(t,co,no,t0)-a.tg_full_on(t,dn,dnn,t0))*1e9;r['margin2 '+tag]=(a.tg_off_start(t,do,dno,t0)-a.tg_full_on(t,cn,nn,t0))*1e9;r['delay '+tag]=(a.cross(t,dn,vdd/2,True,t0)-e)*1e9
 margins=[val for k,val in r.items() if k.startswith('margin')];finite=bool(np.isfinite(z).all() and all(math.isfinite(val) for val in r.values()));return {'timing_ns':r,'minimum_margin_ns':min(margins),'finite':finite,'positive_sequence_margins':bool(finite and min(margins)>0),'driver_charge_pC_per_edge':float(-np.trapezoid(v['idd'][t>50e-9],t[t>50e-9])/2*1e12)}
def job(case):
 v,c,temp=case;row={'vdd':v,'corner':c,'temperature_C':temp,'status':'running'};rows.append(row);save();start=time.time();d=out/f'{v}_{c}_{temp}';d.mkdir(exist_ok=True)
 try:
  s=(p.parent/'clock'/str(v)/'runs'/f'aclk_{c}_{temp}'/'tb.spice').read_text();assert old in s
  s=s.replace(old,str(rc)).replace('.options sparse reltol=1e-4','.options klu reltol=1e-4');s=s.replace('tran 0.01n','op\nwrdata op.csv '+extra+'\ntran 0.01n').replace('quit\n.endc','wrdata load_wave.csv '+extra+'\nquit\n.endc');(d/'tb.spice').write_text(s);row['deck_sha256']=hashlib.sha256(s.encode()).hexdigest()
  with (d/'run.log').open('w') as log:
   proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=proc.wait(timeout=600)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();code='timeout_600s'
  row['exitcode']=code;row['error_lines']=re.findall(r'^.*(?:Error:|aborted|stepping failed|Transient op).*$' ,(d/'run.log').read_text(),re.M)
  if code==0 and not row['error_lines']:row.update(measure(d,v))
 except Exception as e:row['error']=repr(e)
 row.update(status='finished',seconds=round(time.time()-start,2));save();print(json.dumps(row),flush=True)
nom=next(r for r in json.loads((p/'results.json').read_text())['cases'] if r['variant']=='rc_klu');assert nom['exitcode']==0 and nom['finite'];rows.append({'vdd':3.3,'corner':'typical','temperature_C':27,'status':'finished','exitcode':0,'reused_from':'../rc_klu','seconds':nom['seconds'],**measure(p/'rc_klu',3.3)});save()
cases=[(v,c,t) for v in [3.0,3.3,3.6] for c,t in [('typical',27),('ss',85),('ff',-20),('sf',27),('fs',27)] if (v,c,t)!=(3.3,'typical',27)]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(job,cases))
assert hashlib.sha256(rc.read_bytes()).hexdigest()==rc_hash
finished={'completed':len(rows),'all_positive':len(rows)==15 and all(r.get('positive_sequence_margins') for r in rows),'worst':min((r for r in rows if 'minimum_margin_ns' in r),key=lambda r:r['minimum_margin_ns']),'rc_unchanged':True};(out/'summary.json').write_text(json.dumps(finished,indent=2))


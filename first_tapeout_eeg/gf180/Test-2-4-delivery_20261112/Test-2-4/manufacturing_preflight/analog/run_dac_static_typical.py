from pathlib import Path
import os,json,time,re,importlib.util,types,subprocess,concurrent.futures,sys
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');out=p/'dac_static_typical'
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH']
log=(out/'multiplier_audit/expanded.log').read_text()
ml=[l for l in log.splitlines() if re.search(r':\s*m\.',l)]
values=[float(re.search(r'\bm=\s*([\d.eE+-]+)',l).group(1)) for l in ml]
assert len(ml)==659 and set(values)=={1.0}
(out/'multiplier_audit/result.json').write_text(json.dumps({'MOS_count':len(ml),'effective_m_values':sorted(set(values)),'scope':'PDK wrapper default m=1 warning; all expanded MOS m=1, no upstream DAC multiplicity above1. nf scaling retained separately.'},indent=2))
f=p/'sim_work/gf180/tapeout/sim/dac1/dac1_check.py';s=importlib.util.spec_from_file_location('dac',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def avg(t,y,a,b):
 mask=(t>a)&(t<b)
 return float(np.trapezoid(np.r_[np.interp(a,t,y),y[mask],np.interp(b,t,y)],np.r_[a,t[mask],b])/(b-a))
def run(k):
 d=out/('code_'+str(k).zfill(2))
 if (d/'result.json').exists():return json.loads((d/'result.json').read_text())
 d.mkdir(exist_ok=True);o=types.SimpleNamespace(corner='typical',temp=27,voff=0,tol='A');nf=12
 sels=[[int(i<k)]*nf for i in range(31)]
 deck=m.deck(o,sels,nf,0,'i(vop) i(von) i(vrp)').replace('set noaskquit','set noaskquit\nset numdgt=15')
 (d/'tb.spice').write_text(deck);start=time.time()
 try:
  r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=1200);(d/'run.log').write_text(r.stdout+r.stderr)
  x=np.loadtxt(d/'tr.csv');t=x[:,0];y=-x[:,1]+x[:,3]
  means=[avg(t,y,m.T0+j*m.T+4*m.TM,m.T0+(j+1)*m.T+4*m.TM) for j in [8,9,10]]
  plateau=[avg(t,y,m.T0+j*m.T+.5*m.T,m.T0+j*m.T+.9*m.T) for j in [8,9,10]]
  z={'code':k,'seconds':time.time()-start,'exitcode':r.returncode,'last_time_s':float(t[-1]),'samples':len(t),'J_A':float(np.mean(means[-2:])),'frame_8_9_10_means_A':means,'settling_last_frame_delta_A':means[-1]-means[-2],'plateau_means_A':plateau}
 except Exception as e:z={'code':k,'seconds':time.time()-start,'error':repr(e)}
 (d/'result.json').write_text(json.dumps(z,indent=2));print(json.dumps(z),flush=True);return z
codes=[0,15,16,31] if '--all' not in sys.argv else list(range(32))
res=[]
with concurrent.futures.ThreadPoolExecutor(2) as ex:
 for r in ex.map(run,codes):
  res.append(r);(out/'status.json').write_text(json.dumps({'stage':'running','requested':codes,'results':res},indent=2))
(out/'status.json').write_text(json.dumps({'stage':'finished','requested':codes,'results':res},indent=2))

from pathlib import Path
import os,json,time,importlib.util,types,subprocess,hashlib,concurrent.futures
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog')
out=p/'dac_ff_solver_pilot';out.mkdir(exist_ok=True)
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH']
f=p/'sim_work/gf180/tapeout/sim/dac1/dac1_check.py'
s=importlib.util.spec_from_file_location('dac',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
manifest=json.loads((p/'input_manifest.json').read_text())
nf=14
patterns=[([0]*4+[0,1]*32+[0]*4)[:nf],([0]*4+[0,0,1,1]*16+[0]*4)[:nf]]
settings=[('gear_base','A','0.5n'),('gear_half','A','0.25n'),('trap_base','B','0.5n')]
def integral(x):
 a=m.T0+4*m.T+4*m.TM;b=m.T0+12*m.T+4*m.TM
 t=x[:,0];y=x[:,1]-x[:,3];sel=(t>a)&(t<b)
 return float(np.trapezoid(np.r_[np.interp(a,t,y),y[sel],np.interp(b,t,y)],np.r_[a,t[sel],b]))
def run(arg):
 name,tol,step,k=arg;d=out/(name+'_p'+str(k));d.mkdir()
 o=types.SimpleNamespace(corner='ff',temp=-20,voff=0,tol=tol)
 sels=[patterns[k]]+[[1]*nf if i<15 else [0]*nf for i in range(1,31)]
 deck=m.deck(o,sels,nf,0,'i(vop) i(von) i(vrp)').replace('set noaskquit','set noaskquit\nset numdgt=15').replace('0 0.5n','0 '+step)
 (d/'tb.spice').write_text(deck)
 t=time.time()
 try:
  r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=900)
  (d/'run.log').write_text(r.stdout+r.stderr)
  x=np.loadtxt(d/'tr.csv')
  result=dict(setting=name,pattern=k,seconds=time.time()-t,exitcode=r.returncode,last_time_s=float(x[-1,0]),samples=len(x),charge_C=integral(x),deck_sha256=hashlib.sha256(deck.encode()).hexdigest())
 except Exception as e:result=dict(setting=name,pattern=k,seconds=time.time()-t,error=repr(e))
 (d/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 return result
jobs=[(name,tol,step,k) for name,tol,step in settings for k in [0,1]]
results=[]
(out/'status.json').write_text(json.dumps({'stage':'running','jobs':jobs}))
with concurrent.futures.ThreadPoolExecutor(2) as ex:
 for r in ex.map(run,jobs):
  results.append(r);(out/'status.json').write_text(json.dumps({'stage':'running','completed':results},indent=2))
comparison=[]
for name,_,_ in settings:
 rr=sorted([r for r in results if r['setting']==name],key=lambda r:r['pattern'])
 if all('charge_C' in r for r in rr):comparison.append({'setting':name,'even_fC_per_toggle':(rr[0]['charge_C']-rr[1]['charge_C'])/4*1e15})
old=[]
for k in [0,1]:
 x=np.loadtxt(p/'dac_even/runs'/('even_one'+str(k)+'_ff-20_v0_s0')/'tr.csv');old.append(integral(x))
comparison.append({'setting':'saved72frame_same_8frame_window','even_fC_per_toggle':(old[0]-old[1])/4*1e15})
summary={'scope':'14frame pilot only; first14 frames of original stimulus; interpolated frame4..12 window, toggle count difference4; not full72frame qualification','stage':'finished','results':results,'comparison':comparison}
(out/'status.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)

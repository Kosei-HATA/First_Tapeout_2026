from pathlib import Path
import subprocess,time,json,shutil,re,hashlib,numpy as np
root=Path(__file__).resolve().parent
p=root.parent
binary=root/'install/bin/ngspice'
out=root/'tests';out.mkdir(exist_ok=True)
prior={x['case']:x for x in json.loads((root/'test_progress.json').read_text())} if (root/'test_progress.json').exists() else {}
results=[]
def run(tag,deck,init,timeout=30):
 d=out/tag
 if tag in prior:
  results.append(prior[tag]);return d,prior[tag]
 d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_text(init)
 t=time.time()
 try:
  q=subprocess.run([str(binary),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=timeout);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:
  log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log)
 z={'case':tag,'seconds':time.time()-t,'exitcode':rc,'input_sha256':hashlib.sha256(deck.encode()).hexdigest(),'aborted':bool(re.search('aborted|Timestep too small|Error:',log,re.I))}
 if (d/'wave.csv').exists():z['last_time_s']=float(np.atleast_2d(np.loadtxt(d/'wave.csv'))[-1,0])
 results.append(z);(root/'test_progress.json').write_text(json.dumps(results,indent=2));print(z,flush=True)
 return d,z
for d in sorted((p/'moscap_initialization_audit').iterdir()):
 if d.is_dir() and (d/'tb.spice').exists():
  run('init_'+d.name,(d/'tb.spice').read_text(),(d/'.spiceinit').read_text())
noise=[]
for d in sorted((p/'adc_rin_noise_budget').iterdir()):
 if d.is_dir() and (d/'tb.spice').exists():
  nd,z=run('rin_'+d.name,(d/'tb.spice').read_text(),(d/'.spiceinit').read_text())
  if (nd/'noise.csv').exists():
   a=np.atleast_2d(np.loadtxt(nd/'noise.csv'));z['input_rms_V']=float(np.sqrt(np.trapezoid(a[:,3]**2,a[:,0])));z['density_V_sqrtHz']=float(a[0,3]);noise.append(z)
cv=[]
header=f'.include {p}/models/design.ngspice\n.lib {p}/models/sm141064.ngspice typical\n.lib {p}/models/sm141064.ngspice moscap_typical\n'
for kind in ['nmos','pmos']:
 for scale,m in [(1,1),(2,1),(1,2),(1,4),(1,8),(1,16)]:
  for mag in [0,.4,.85,1.65,3.3]:
   v=mag if kind=='nmos' else -mag
   deck='* official MOSCAP AC diagnostic\n'+header+f'VDRV gate 0 DC {v} AC 1\nXC gate 0 cap_{kind}_03v3 c_length={28.6*scale}u c_width=44u m={m}\n.control\nset numdgt=15\nop\nac lin 1 1000 1000\nlet ci=-imag(i(vdrv))/(2*PI*1000)\nwrdata cap.csv ci\nquit\n.endc\n.end\n'
   d,z=run(f'cv_{kind}_s{scale}_m{m}_v{v}',deck,'set ngbehavior=hsa\nset num_threads=1\n',10)
   z.update(kind=kind,length_scale=scale,m=m,voltage=v)
   if (d/'cap.csv').exists():z['ac_capacitance_F']=float(np.loadtxt(d/'cap.csv').reshape(-1)[1])
   cv.append(z)
(root/'comparison_summary.json').write_text(json.dumps({'scope':'Development build diagnostics only; no qualification of steady-state gain or physical ENOB','commit':(root/'commit.txt').read_text().strip(),'initialization':results[:16],'rin_noise':noise,'moscap_cv':cv},indent=2))




from pathlib import Path
import subprocess,time,json,re,hashlib,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_ramp_fourcycle';r.mkdir(exist_ok=True)
src=p/'moscap_initialization_audit/top_gear_ramp/tb.spice'
vectors=['v(outp)','v(outn)','v(vbn)','v(vbcm)','v(vcm)','v(blp)','v(bln)','v(vdd)','v(rst)','v(cia)','v(cda)','v(src)']
deck=src.read_text().replace('tran 1n 5e-07 0 1n','tran 1n 31.25u 0 1n').replace('wrdata wave.csv v(outp) v(vbn)','wrdata wave.csv '+' '.join(vectors))
results=[]
for tag,binary in [('ngspice46','/foss/tools/bin/ngspice'),('ngspice47plus',str(p/'ngspice48_isolated/install/bin/ngspice'))]:
 d=r/tag;d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src.parent/'.spiceinit').read_bytes());t=time.time()
 try:
  q=subprocess.run([binary,'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:
  log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log)
 z={'case':tag,'seconds':time.time()-t,'exitcode':rc,'input_sha256':hashlib.sha256(deck.encode()).hexdigest(),'requested_time_s':31.25e-6,'period_s':7.8125e-6,'aborted':bool(re.search('aborted|Timestep too small|Error:',log,re.I)),'diagnostics':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)]}
 if (d/'wave.csv').exists():
  a=np.atleast_2d(np.loadtxt(d/'wave.csv'));tt=a[:,0];z.update(last_time_s=float(tt[-1]),cycles=float(tt[-1]/7.8125e-6),finite=bool(np.isfinite(a).all()),rows=len(a),completed=bool(tt[-1]>=31.25e-6*.999),endpoints={v:float(a[-1,2*i+1]) for i,v in enumerate(vectors)},initial_values={v:float(a[0,2*i+1]) for i,v in enumerate(vectors)})
 else:
  times=re.findall(r'Reference value\s*:\s*([0-9.eE+-]+)',log);z['last_progress_time_s']=float(times[-1]) if times else None;z['completed']=False
 results.append(z);(r/'summary.json').write_text(json.dumps({'scope':'Identical 100 ns VDD ramp, ideal pre-established references and controls; startup speed only, not settled gain','results':results},indent=2));print(z,flush=True)

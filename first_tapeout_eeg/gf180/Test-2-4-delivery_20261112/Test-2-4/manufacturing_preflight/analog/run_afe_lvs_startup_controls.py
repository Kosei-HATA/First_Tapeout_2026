from pathlib import Path
import subprocess,json,time,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_lvs_startup_controls';r.mkdir(exist_ok=True);src=p/'afe_lvs_supply_3p6';base=(src/'tb.spice').read_text();q=p/'moscap_charge_equivalent/q_models.spice';regular=q.read_text().replace('.ends','RREG 1 2 1e15\n.ends');(r/'q_models_regularized.spice').write_text(regular);short=base.replace('tran 1n 31.25u 0 1n','tran 1n 1u 0 1n');cases=[('tmax_025ns',short.replace('tran 1n 1u 0 1n','tran 1n 1u 0 .25n')),('regularized_1ns',short.replace(str(q),str(r/'q_models_regularized.spice')))];s=[]
for tag,deck in cases:
 d=r/tag;d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src/'.spiceinit').read_bytes());start=time.time()
 try:
  v=subprocess.run([str(p/'ngspice48_isolated/install/bin/ngspice'),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=v.stdout+v.stderr;rc=v.returncode
 except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log);z={'case':tag,'seconds':time.time()-start,'exitcode':rc,'diagnostics':[x for x in log.splitlines() if re.search('Timestep too small|Error:',x,re.I)],'completed':False}
 if (d/'wave.csv').exists():
  a=np.loadtxt(d/'wave.csv');z.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=1e-6*.999999))
 s.append(z);(r/'run_summary.json').write_text(json.dumps(s,indent=2));print(z,flush=True)

from pathlib import Path
import subprocess,time,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_rtl_startup';d=r/'pilot';start=time.time()
try:q=subprocess.run([str(p/'ngspice48_isolated/install/bin/ngspice'),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
(d/'run.log').write_text(log);s={'seconds':time.time()-start,'exitcode':rc,'diagnostics':[l for l in log.splitlines() if re.search('Error:|Timestep too small',l,re.I)],'completed':False,'scope':'AFE-only current-LVS topology with RTL-derived controls; assumed board sequence and integral-Q model; not system or steady-state acceptance'}
if (d/'wave.csv').exists():
 a=np.loadtxt(d/'wave.csv');nodes=json.loads((r/'mapping_and_assumptions.json').read_text())['saved_nodes'];s.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=32e-6*.999999),endpoints={n:float(a[-1,2*i+1]) for i,n in enumerate(nodes) if n in ['outp','outn','vcm','vbn','vbcm','rtl_afe_rst','src']})
(r/'pilot_summary.json').write_text(json.dumps(s,indent=2));print(s)

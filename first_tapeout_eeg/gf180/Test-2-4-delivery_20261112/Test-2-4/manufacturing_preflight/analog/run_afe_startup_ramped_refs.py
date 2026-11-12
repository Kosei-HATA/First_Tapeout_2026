from pathlib import Path
import time,subprocess,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_lvs_startup_controls';d=r/'ramped_refs_reset';d.mkdir(exist_ok=True);src=r/'tmax_025ns';deck=(src/'tb.spice').read_text();changes=[('VRP VRP 0 1.9','VRP VRP 0 PWL(0 0 100n 1.9)'),('VRN VRN 0 1.4','VRN VRN 0 PWL(0 0 100n 1.4)'),('VRS AFE_RST 0 PWL(0 3.3 7.8125e-06 3.3 7.8135e-06 0)','VRS AFE_RST 0 PWL(0 0 100n 3.3 7.8125e-06 3.3 7.8135e-06 0)')]
for old,new in changes:
 assert deck.count(old)==1,old
 deck=deck.replace(old,new)
(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src/'.spiceinit').read_bytes());start=time.time()
try:q=subprocess.run([str(p/'ngspice48_isolated/install/bin/ngspice'),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
(d/'run.log').write_text(log);s={'case':'ramped_refs_reset','changes':changes,'seconds':time.time()-start,'exitcode':rc,'diagnostics':[l for l in log.splitlines() if re.search('Error:|Timestep too small',l,re.I)],'completed':False}
if (d/'wave.csv').exists():
 a=np.loadtxt(d/'wave.csv');s.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=1e-6*.999999))
(r/'ramp_run_summary.json').write_text(json.dumps(s,indent=2));print(s)

from pathlib import Path
import subprocess,time,json,re,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_ncda_candidates';r.mkdir(exist_ok=True);src=p/'afe_lvs_startup_controls/tmax_025ns';base=(src/'tb.spice').read_text();clk=p/'sim_work/gf180/tapeout/afe/eeg_afe_clk.spice';afe=p/'sim_work/gf180/tapeout/afe/eeg_afe.spice'
s=clk.read_text();old='XCDA3 NCDA CDAI VDD VSS eeg_clk_inv s=8';assert s.count(old)==1;(r/'clock_ncda_2x.spice').write_text(s.replace(old,old.replace('s=8','s=16')))
s=afe.read_text();start=s.index('.subckt eeg_afe_output_tg');end=s.index('.ends eeg_afe_output_tg',start);part=s[start:end];assert part.count('m=8')==2;(r/'afe_output_tg_half.spice').write_text(s[:start]+part.replace('m=8','m=4')+s[end:]);cases=[('ncda_driver_2x',base.replace(str(clk),str(r/'clock_ncda_2x.spice'))),('output_tg_half',base.replace(str(afe),str(r/'afe_output_tg_half.spice')))];results=[]
for tag,deck in cases:
 d=r/tag;d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src/'.spiceinit').read_bytes());start=time.time()
 try:q=subprocess.run([str(p/'ngspice48_isolated/install/bin/ngspice'),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log);z={'case':tag,'seconds':time.time()-start,'exitcode':rc,'diagnostics':[l for l in log.splitlines() if re.search('Error:|Timestep too small',l,re.I)],'completed':False}
 if (d/'wave.csv').exists():
  a=np.loadtxt(d/'wave.csv');z.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=1e-6*.999999))
 results.append(z);(r/'run_summary.json').write_text(json.dumps(results,indent=2));print(z,flush=True)

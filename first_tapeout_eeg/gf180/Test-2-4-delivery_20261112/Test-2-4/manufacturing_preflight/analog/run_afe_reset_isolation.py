from pathlib import Path
import subprocess,time,json,re,hashlib,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_reset_isolation';r.mkdir(exist_ok=True)
src=p/'afe_ramp_fourcycle/ngspice47plus/tb.spice';base=src.read_text();binary=p/'ngspice48_isolated/install/bin/ngspice'
vectors=['v(outp)','v(outn)','v(vbn)','v(vbcm)','v(vcm)','v(blp)','v(bln)','v(vdd)','v(rst)','v(afe_rst)','v(chop)','v(cia)','v(cda)','v(src)','v(vbn1)','v(vbcm1)','v(vnc1)','v(vpc1)','v(vbpc2)','v(vbnc2)','v(xb.gp)','v(xb.xcvbcm1_1.c_moscap_int1)','v(xb.xcvbcm1_1.c_moscap_int2)']
base=re.sub(r'^wrdata wave.csv.*$','wrdata wave.csv '+' '.join(vectors),base,flags=re.M)
cases=[('held','VRS AFE_RST 0 3.3'),('delayed_10us','VRS AFE_RST 0 PWL(0 3.3 10u 3.3 10.001u 0)'),('slew_100ns','VRS AFE_RST 0 PWL(0 3.3 7.8125u 3.3 7.9125u 0)')];results=[]
for tag,line in cases:
 d=r/tag;d.mkdir(exist_ok=True);deck=re.sub(r'^VRS.*$',line,base,flags=re.M);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src.parent/'.spiceinit').read_bytes());t=time.time()
 try:
  q=subprocess.run([str(binary),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log);z={'case':tag,'reset_definition':line,'seconds':time.time()-t,'exitcode':rc,'input_sha256':hashlib.sha256(deck.encode()).hexdigest(),'diagnostics':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)],'completed':False}
 if (d/'wave.csv').exists():
  a=np.atleast_2d(np.loadtxt(d/'wave.csv'));z.update(last_time_s=float(a[-1,0]),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=31.25e-6*.999),rows=len(a),vectors={v:{'min':float(a[:,2*i+1].min()),'max':float(a[:,2*i+1].max()),'last':float(a[-1,2*i+1])} for i,v in enumerate(vectors)})
  gp=a[:,2*vectors.index('v(xb.gp)')+1]-a[:,2*vectors.index('v(vdd)')+1];z['pmos_gp_minus_vdd_range_V']=[float(gp.min()),float(gp.max())]
 results.append(z);(r/'summary.json').write_text(json.dumps({'scope':'Reset stimulus changes only, unchanged solver and full original MOSCAP circuit','results':results},indent=2));print(z,flush=True)

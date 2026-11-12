from pathlib import Path
import subprocess,time,json,re,hashlib,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_numeric_controls';r.mkdir(exist_ok=True);src=p/'afe_ramp_fourcycle/ngspice47plus/tb.spice';base=src.read_text();binary=p/'ngspice48_isolated/install/bin/ngspice'
vectors=['v(outp)','v(outn)','v(vbn)','v(vbcm)','v(vcm)','v(blp)','v(bln)','v(vdd)','v(rst)','v(cia)','v(cda)','v(src)','i(vdd)','i(vrp)','i(vrn)','i(vit)']
base=re.sub(r'^wrdata wave.csv.*$','option\nwrdata wave.csv '+' '.join(vectors),base,flags=re.M)
cases=[('klu',base.replace('.options method=gear','.options klu method=gear')),('reltol_1e5',base.replace('reltol=1e-4','reltol=1e-5')),('tmax_025ns',base.replace('tran 1n 31.25u 0 1n','tran 1n 31.25u 0 .25n')),('trap',base.replace('method=gear','method=trap'))];results=[]
for tag,deck in cases:
 d=r/tag;d.mkdir(exist_ok=True);(d/'tb.spice').write_text(deck);(d/'.spiceinit').write_bytes((src.parent/'.spiceinit').read_bytes());start=time.time()
 try:q=subprocess.run([str(binary),'-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=300);log=q.stdout+q.stderr;rc=q.returncode
 except subprocess.TimeoutExpired as e:log=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');rc='timeout'
 (d/'run.log').write_text(log);z={'case':tag,'seconds':time.time()-start,'exitcode':rc,'input_sha256':hashlib.sha256(deck.encode()).hexdigest(),'diagnostics':[l for l in log.splitlines() if re.search('Timestep too small|trouble with|Error:',l,re.I)],'matrix_solver':re.findall(r'Matrix solver:\s*([^\n]+)',log),'completed':False}
 if (d/'wave.csv').exists():
  a=np.atleast_2d(np.loadtxt(d/'wave.csv'));z.update(last_time_s=float(a[-1,0]),cycles=float(a[-1,0]/7.8125e-6),finite=bool(np.isfinite(a).all()),completed=bool(a[-1,0]>=31.25e-6*.999999),rows=len(a),vectors={v:{'min':float(a[:,2*i+1].min()),'max':float(a[:,2*i+1].max()),'last':float(a[-1,2*i+1])} for i,v in enumerate(vectors)})
 results.append(z);(r/'summary.json').write_text(json.dumps({'scope':'Original four-cycle ramp stimulus; only one numerical setting per test; original nonlinear MOSCAP','results':results},indent=2));print(z,flush=True)

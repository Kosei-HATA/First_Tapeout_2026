from pathlib import Path
import re,os,subprocess,json,numpy as np,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/analog');o=p/'resistor_noise_instance_fix';o.mkdir(exist_ok=True)
src=(p/'models/sm141064.ngspice').read_text()
sub=re.search(r'^\.subckt ppolyf_u_1k .*?^\.ends ppolyf_u_1k',src,re.M|re.S).group(0)
sub=sub.replace('.subckt ppolyf_u_1k ','.subckt audit_ppolyf_u_1k ').replace('.ends ppolyf_u_1k','.ends audit_ppolyf_u_1k')
sub=re.sub(r'^(rb .*?)$',r'\1 noisy=1',sub,flags=re.M)
(o/'audit_model.spice').write_text('* Verification-only instance noise flag; not foundry-qualified replacement\n'+sub+'\n')
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH']
results=[]
for old in sorted((p/'resistor_noise_sanity').glob('pdk_*')):
 d=o/old.name;d.mkdir()
 deck=(old/'tb.spice').read_text().replace(' ppolyf_u_1k r_length',' audit_ppolyf_u_1k r_length').replace('.temp ',f'.include {o}/audit_model.spice\n.temp ')
 (d/'tb.spice').write_text(deck)
 r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=60);(d/'run.log').write_text(r.stdout+r.stderr)
 if r.returncode:print(r.stderr);continue
 ac=np.atleast_2d(np.loadtxt(d/'ac.csv'));n=np.atleast_2d(np.loadtxt(d/'noise.csv'));a0=np.atleast_2d(np.loadtxt(old/'ac.csv'))
 temp=85 if old.name=='pdk_hot' else 27
 R=ac[0,1];ratio=n[0,1]**2/(4*1.380649e-23*(temp+273.15)*R)
 results.append({'case':old.name,'R_ohm':float(R),'AC_max_abs_change':float(np.max(abs(ac-a0))),'noise_V_per_sqrtHz':float(n[0,1]),'PSD_ratio_to_4kTR':float(ratio)})
print(json.dumps(results,indent=2));(o/'summary.json').write_text(json.dumps({'scope':'Verification-only noisy=1 on copied body instance; thermal zero-bias only, not flicker/PDK signoff','source_model_sha256':hashlib.sha256(src.encode()).hexdigest(),'results':results},indent=2))

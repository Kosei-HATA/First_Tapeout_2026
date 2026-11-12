from pathlib import Path
import json,math,subprocess,time,numpy as np
r=Path(__file__).resolve().parent
s=json.loads((r/'comparison_summary.json').read_text())
for x in s['moscap_cv']:
 a,b,c,d=(.002003,.00198,6.25,-3.9375) if x['kind']=='nmos' else (.001998,.00196,-6.25,-4.9375)
 expected=28.6e-6*x['length_scale']*44e-6*x['m']*(a+b*math.tanh(c*x['voltage']+d))
 x['analytical_C_F']=expected
 if 'ac_capacitance_F' in x:x['relative_error']=x['ac_capacitance_F']/expected-1
 src=r/'tests'/x['case']; dst=r/'reference46_cv'/x['case'];dst.mkdir(parents=True,exist_ok=True)
 for f in ['tb.spice','.spiceinit']:(dst/f).write_bytes((src/f).read_bytes())
 q=subprocess.run(['/foss/tools/bin/ngspice','-b','tb.spice'],cwd=dst,capture_output=True,text=True,timeout=15)
 (dst/'run.log').write_text(q.stdout+q.stderr)
 if (dst/'cap.csv').exists():
  old=float(np.loadtxt(dst/'cap.csv').reshape(-1)[1]);x['reference46_C_F']=old;x['relative_change_from46']=x.get('ac_capacitance_F',float('nan'))/old-1
s['cv_max_abs_analytical_relative_error']=max(abs(x.get('relative_error',float('inf'))) for x in s['moscap_cv'])
s['cv_max_abs_change_from46']=max(abs(x.get('relative_change_from46',float('inf'))) for x in s['moscap_cv'])
base={x['tag']:x for x in json.loads((r.parent/'moscap_initialization_audit/summary.json').read_text())}
for x in s['initialization']:
 tag=x['case'].removeprefix('init_');old=base.get(tag)
 if old:x['reference46']=old
(r/'final_summary.json').write_text(json.dumps(s,indent=2))
print(json.dumps({k:v for k,v in s.items() if k not in ['moscap_cv','initialization']},indent=2))


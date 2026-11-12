from pathlib import Path
import subprocess,json,numpy as np
r=Path(__file__).resolve().parent; results=[]
for d in sorted((r.parent/'resistor_noise_official_flag').iterdir()):
 if not d.is_dir() or not (d/'tb.spice').exists():continue
 out=r/'thermal_regression'/d.name;out.mkdir(parents=True,exist_ok=True)
 for f in ['tb.spice','.spiceinit']:(out/f).write_bytes((d/f).read_bytes())
 q=subprocess.run([str(r/'install/bin/ngspice'),'-b','tb.spice'],cwd=out,capture_output=True,text=True,timeout=15);(out/'run.log').write_text(q.stdout+q.stderr)
 x={'case':d.name,'exitcode':q.returncode}
 for f in ['ac.csv','noise.csv']:
  a=np.loadtxt(out/f);b=np.loadtxt(d/f);x[f+'_max_abs_difference']=float(np.max(np.abs(a-b)));x[f+'_exactly_equal']=bool(np.array_equal(a,b))
 results.append(x)
(r/'thermal_regression_summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

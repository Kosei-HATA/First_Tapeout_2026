from pathlib import Path
import json,hashlib
p=Path(r'C:\projects\ft\test1x\Test-2-4\manufacturing_preflight\bias_validation\clock_pex_comparison\rc_corner_sensitivity');m=json.loads((p/'approved_inputs.json').read_text());r=json.loads((p/'results.json').read_text());s=json.loads((p/'summary.json').read_text());checks=[]
for x in m['corners']:
 f=Path(x['spice'].replace('/work/','C:/projects/ft/test1x/'));checks.append({'corner':x['name'],'unchanged':hashlib.sha256(f.read_bytes()).hexdigest()==x['sha256']})
assert all(x['unchanged'] for x in checks)
s.update(inputs_unchanged=checks,all_runs_exit0=all(x['exitcode']==0 for x in r['cases']),limits=['Fixed device3.6V/ff/-20C only; not all15x4 combinations.','Only internal clock RC, external schematic diffusion geometry and common-mode input.','LowR zero contact resistance is official model bound, not physical zero resistance.','Positive sequence margin only; no minimum product guardband specification, not full-chip signoff.'])
(p/'final_summary.json').write_text(json.dumps(s,indent=2))

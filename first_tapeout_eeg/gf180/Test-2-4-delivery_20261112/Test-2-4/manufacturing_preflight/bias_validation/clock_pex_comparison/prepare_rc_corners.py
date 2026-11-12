from pathlib import Path
import json,hashlib,collections
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');root=p.parents[1]/'extraction/core_pex_probe/clock_probe';data=json.loads((root/'rc_corners/summary.json').read_text());out=p/'rc_corner_sensitivity';out.mkdir(exist_ok=True)
def signature(f):return collections.Counter((t[5],tuple(sorted(t[6:]))) for t in (l.split() for l in f.read_text().splitlines()) if t and t[0].startswith('X'))
ref=signature(root/'flat/rc.spice');rows=[]
for c in ['hrhc','hrlc','lrhc','lrlc']:
 d=data[c];f=root/'rc_corners'/c/'rc.spice';sha=hashlib.sha256(f.read_bytes()).hexdigest();assert d['pass'] and d['rc_preservation_pass'] and d['independent_MOS_LVS_pass'] and sha==d['sha256']['rc.spice'];assert signature(f)==ref
 rows.append({'name':c,'spice':str(f),'sha256':sha,'audit_pass':True,'MOS_parameters_match_nominal':True,'source_audit':str(root/'rc_corners/summary.json'),'official_style':d['style']})
(out/'approved_inputs.json').write_text(json.dumps({'corners':rows,'nominal_MOS_count':sum(ref.values())},indent=2));print('4 audited corners approved, MOS parameter multisets identical')

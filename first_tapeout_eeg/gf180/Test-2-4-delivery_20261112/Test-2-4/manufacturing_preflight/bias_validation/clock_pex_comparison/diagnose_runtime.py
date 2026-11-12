from pathlib import Path
import json,re
p=Path(r'C:\projects\ft\test1x\Test-2-4\manufacturing_preflight\bias_validation\clock_pex_comparison');f=p.parents[1]/'extraction/core_pex_probe/clock_probe/flat/rc.spice';vals={'R':[],'C':[]}
for line in f.read_text().splitlines():
 t=line.split()
 if not t or t[0][0] not in vals:continue
 q=re.fullmatch(r'([\d.eE+-]+)([a-zA-Z]*)',t[3]);v=float(q[1])*{'':1,'f':1e-15,'p':1e-12,'n':1e-9,'u':1e-6,'m':1e-3,'k':1e3,'meg':1e6}[q[2].lower()];vals[t[0][0]].append(v)
r={k:{'count':len(a),'minimum_SI':min(a),'maximum_SI':max(a),'zeros':sum(v==0 for v in a),'negatives':sum(v<0 for v in a)} for k,a in vals.items()};r.update(solver='SPARSE1.3 pilot, KLU alternative same circuit',maxstep_s=5e-11,reltol=1e-4,pilot_time_s=300,achieved_time_s=2.67001e-7,projected_500ns_s=300*5e-7/2.67001e-7,diagnosis='No singular matrix/timestep-too-small failure. gmin stepping completed. Integration cap maxstep plus large sparse system likely dominant; minimum R/C alone cannot establish stiffness without topology.')
(p/'runtime_diagnostic.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

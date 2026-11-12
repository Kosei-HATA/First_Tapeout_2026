from pathlib import Path
import re,json,collections
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');root=p.parents[1]/'extraction/core_pex_probe/clock_probe/flat'
def num(v):
 m=re.fullmatch(r'([0-9.eE+-]+)([a-z]*)',v);return float(m[1])*{'':1,'u':1e-6,'p':1e-12,'n':1e-9,'f':1e-15}[m[2]]
res={}
for mode in ['cap','rc']:
 rows=[]
 for l in (root/(mode+'.spice')).read_text().splitlines():
  t=l.split()
  if not t or t[0][0].upper()!='X':continue
  par={k:num(v) for k,v in (x.lower().split('=') for x in t[6:])};rows.append({'name':t[0],'model':t[5],**par})
 res[mode]={'count':len(rows),'ranges_SI':{k:[min(r.get(k,1 if k in ['m','nf'] else 0) for r in rows),max(r.get(k,1 if k in ['m','nf'] else 0) for r in rows)] for k in ['w','l','ad','as','pd','ps','m','nf']},'rows':rows}
x={r['name']:r for r in res['cap']['rows']};y={r['name']:r for r in res['rc']['rows']};same=x==y
# Device width and gate length in SI; junction area/perimeter dimensions must be finite/nonnegative and plausible for each finger.
checks=[]
for r in res['rc']['rows']:
 ok=(.1e-6<=r['w']<=1000e-6 and .1e-6<=r['l']<=100e-6 and all(0<=r[k]<=1e-8 for k in ['ad','as']) and all(0<=r[k]<=.01 for k in ['pd','ps']))
 checks.append(ok)
for mode in res:res[mode].pop('rows')
res.update(parameter_identity=same,all_dimension_bounds_sane=all(checks),note='Ranges checked against emitted physical finger sizes. No unit scaling/conversion of extracted model parameters. Wrapper defaults nf=m=1. This is sanity, not foundry capacitance accuracy qualification.')
assert same and all(checks);(p/'mos_units_audit.json').write_text(json.dumps(res,indent=2));print(json.dumps(res,indent=2))

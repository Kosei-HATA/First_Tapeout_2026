from pathlib import Path
from collections import defaultdict
import json,re,math
p=Path(r'C:\projects\ft\test1x\Test-2-4\manufacturing_preflight\extraction');m=p/'io_asig_magic'
def val(s):
 q=re.fullmatch(r'([+\-0-9.eE]+)([a-zA-Z]*)',s);return float(q[1])*{'':1,'f':1e-15,'p':1e-12,'n':1e-9,'u':1e-6,'m':1e-3}[q[2].lower()]
def dims(file):
 groups=defaultdict(lambda:defaultdict(float));counts=defaultdict(float)
 for line in file.read_text().splitlines():
  t=line.split()
  if not t or t[0][0] not in 'DX':continue
  model=t[3];d={k:val(v) for k,v in (x.split('=',1) for x in t[4:] if '=' in x)};mult=d.get('m',1)
  if t[0][0]=='D':key=' '.join([model,*t[1:3]]);groups[key]['area_m2']+=mult*d['area'];groups[key]['perimeter_m']+=mult*d['pj']
  else:key=' '.join([model,*t[1:3],format(d['c_length'],'.12g')]);groups[key]['total_width_m']+=mult*d['c_width'];groups[key]['length_m']=d['c_length']
  counts[key]+=mult
 return dict(groups),dict(counts)
a,ac=dims(m/'actual_normalized.spice');b,bc=dims(m/'reference.spice');assert a.keys()==b.keys();checks=[]
for key in a:
 equal=all(math.isclose(a[key][k],b[key][k],rel_tol=1e-9,abs_tol=1e-24) for k in a[key]) and ac[key]==bc[key]
 checks.append({'group':key,'extracted':dict(a[key]),'reference':dict(b[key]),'extracted_multiplicity':ac[key],'reference_multiplicity':bc[key],'pass':equal})
assert all(x['pass'] for x in checks)
strict=(m/'strict_comparison.log').read_text();width=(m/'bad_width_comparison.log').read_text();pj=(m/'bad_pj_comparison.log').read_text()
r={'scope':'Single analog IO cell topology and primitive geometric parameters; not full ring, ESD behavior, parasitic RC or foundry signoff.','cell':'gf180mcu_fd_io__asig_5p0','topology_pass':'Final result: Circuits match uniquely.' in strict,'strict_property_pass':'Property errors were found.' not in strict,'independent_numeric_comparison_pass':all(x['pass'] for x in checks),'dimension_groups':checks,'negative_controls':{'moscap_width_10pct_detected':'Property errors were found.' in width and 'c_width circuit1' in width,'diode_perimeter_10pct_detected':'Property errors were found.' in pj and 'pj circuit1' in pj},'normalization_evidence':'io_asig_magic/normalization_evidence.json','model_basis':'Official Magic device subcircuit cap_nmos_06v0 declares l=c_length,w=c_width; official ngspice MOSCAP model uses c_length*c_width; official Netgen setup compares c_length/c_width with 1% tolerance. Primitive abstraction has no transistor interior in the model.','warning_resolution':'Netgen cap_nmos_06v0 placeholder is primitive abstraction. Negative width control plus independent numeric comparison establish geometric-parameter checks despite placeholder warning.','pdks_modified':False,'gds_modified':False}
assert all(r['negative_controls'].values()) and r['topology_pass'] and r['strict_property_pass']
(p/'io_strict_validation.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
old=json.loads((p/'io_lvs_assessment.json').read_text());old['later_validation']='io_strict_validation.json';old['later_scoped_topology_and_parameter_pass']=True;old['remaining_blockers']=['Full pad-ring/top independent reference CDL not assembled.','KLayout IO extraction incompatibility remains, but Magic/Netgen scoped alternative validated.','No ESD current/breakdown/mechanical or full-chip RC guarantee.'];(p/'io_lvs_assessment.json').write_text(json.dumps(old,indent=2))

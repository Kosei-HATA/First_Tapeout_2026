from pathlib import Path
import klayout.db as k,json,re
p=Path('/work/Test-2-4/verification/core_with_hints');db=k.LayoutVsSchematic();db.read(str(p/'eeg_core.lvsdb'));xref=db.xref();S=k.NetlistCrossReference;bad={S.Mismatch:'mismatch',S.NoMatch:'nomatch',S.Skipped:'skipped'}
def get(o,n):
 if o is None:return None
 x=getattr(o,n);return x() if callable(x) else x
r={'log_reports_match':'Congratulations! Netlists match.' in (p/'core_lvs.log').read_text(),'scope':'core only; delivered GDS with padring removed and labels restored','circuit_pairs':[],'bad_top_pin_pairs':[]}
for cp in xref.each_circuit_pair():
 a,b=cp.first(),cp.second();an=get(a,'name');bn=get(b,'name');row={'layout':an,'reference':bn,'status':bad.get(cp.status(),str(cp.status()))};r['circuit_pairs'].append(row)
 if str(an).lower()=='eeg_core' or str(bn).lower()=='eeg_core':
  for pp in xref.each_pin_pair(cp):
   if pp.status() in bad:r['bad_top_pin_pairs'].append({'layout':get(pp.first(),'name'),'reference':get(pp.second(),'name'),'status':bad[pp.status()]})
lt=next((c for c in db.netlist().each_circuit() if c.name.lower()=='eeg_core'),None)
rt=next((c for c in get(db,'reference').each_circuit() if c.name.lower()=='eeg_core'),None)
r['layout_top_pins']=[get(x,'name') for x in lt.each_pin()] if lt else []
r['reference_top_pins']=[get(x,'name') for x in rt.each_pin()] if rt else []
r['required_ports']=json.loads((p.parent/'core_lvs_preparation.json').read_text())['reference_ports']
r['missing_reference_ports']=sorted(set(r['required_ports'])-{str(x).upper() for x in r['reference_top_pins']})
r['core_lvs_pass']=r['log_reports_match'] and not r['bad_top_pin_pairs'] and not r['missing_reference_ports'] and bool(lt) and bool(rt)
(p/'core_lvs_summary.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

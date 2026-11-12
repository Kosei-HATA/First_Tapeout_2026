from pathlib import Path
import klayout.db as k,json,resource
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');l=k.LayoutVsSchematic();l.read('/work/Test-2-4/verification/core_with_hints/eeg_core.lvsdb');r={'layers':list(l.layer_names()),'circuits':[]}
for c in l.netlist().each_circuit():
 s=l.xref().other_circuit_for(c);r['circuits'].append({'layout':c.name,'schematic':s.name if s else None,'devices':sum(1 for _ in c.each_device()),'subcircuits':sum(1 for _ in c.each_subcircuit()),'nets':sum(1 for _ in c.each_net())})
r['maxrss_kb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;(p/'db_inventory.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))

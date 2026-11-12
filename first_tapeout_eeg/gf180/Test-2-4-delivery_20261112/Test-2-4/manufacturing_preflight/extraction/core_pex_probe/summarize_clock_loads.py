from pathlib import Path
import json,collections
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');r=json.loads((p/'mapping.json').read_text());outputs=['CIA','NCIA','CIB','NCIB','CDA','NCDA','CDB','NCDB'];out={}
for n in outputs:
 ds=[d for d in r['connected_devices'] if n in d['port_terminals'].values()];external=[d for d in ds if d['schematic'] and not d['schematic'].startswith('ADC.CLK1.')];out[n]={'all_connected_devices':len(ds),'external_devices':external,'external_gate_count':sum(d['port_terminals'].get('G')==n for d in external),'external_gate_W_um':sum(d['params'].get('W',0) for d in external if d['port_terminals'].get('G')==n),'all_external_are_gates':all(d['port_terminals'].get('G')==n for d in external)}
(p/'external_loads.json').write_text(json.dumps(out,indent=2));print(json.dumps({n:{k:v for k,v in x.items() if k!='external_devices'} for n,x in out.items()},indent=2))

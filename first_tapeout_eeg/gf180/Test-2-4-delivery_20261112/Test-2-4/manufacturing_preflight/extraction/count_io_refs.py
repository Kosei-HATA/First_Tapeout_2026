from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep');r=json.loads((p/'inventory.json').read_text());l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds')
for row in r:
 c=l.cell(row['cell']);row['direct_reference_count']=sum(max(1,i.inst().na)*max(1,i.inst().nb) for i in c.each_parent_inst())
(p/'inventory.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

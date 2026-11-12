from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');r=[]
for c in l.each_cell():
 if any(s in c.name.lower() for s in ['eeg_c2','cap_mim','eeg_c1','rdac']):r.append({'cell':c.name,'bbox':str(c.dbbox()),'parents':[l.cell(x).name for x in c.each_parent_cell()]})
(p/'candidate_cells.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))

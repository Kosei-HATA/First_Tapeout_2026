from pathlib import Path
import klayout.db as k,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep/gf180mcu_fd_io__bi_24t');l=k.Layout();l.read(str(p/'actual.gds'));c=l.cell('gf180mcu_fd_io__bi_24t');r=[]
for li in l.layer_indices():
 for s in c.shapes(li).each():
  if s.is_text():r.append({'layer':str(l.get_info(li)),'text':s.text.string,'x':s.text.x,'y':s.text.y})
print(json.dumps(r))

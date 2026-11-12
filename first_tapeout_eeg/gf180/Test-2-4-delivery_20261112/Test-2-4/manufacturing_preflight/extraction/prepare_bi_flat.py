from pathlib import Path
import klayout.db as k,re,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep/gf180mcu_fd_io__bi_24t');out=p/'flat_control';out.mkdir(exist_ok=True);l=k.Layout();l.read(str(p/'actual.gds'));c=l.cell('gf180mcu_fd_io__bi_24t');d=k.Layout();d.dbu=l.dbu;t=d.create_cell(c.name);ports=set(re.search(r'(?im)^\.subckt\s+\S+\s+([^\n]+)',(p/'reference.spice').read_text())[1].split());labels=[]
for li in l.layer_indices():
 info=l.get_info(li);reg=k.Region(c.begin_shapes_rec(li)).merged()
 if not reg.is_empty():t.shapes(d.layer(info)).insert(reg)
 it=c.begin_shapes_rec(li)
 while not it.at_end():
  sh=it.shape()
  if sh.is_text() and sh.text.string.rstrip('!') in ports:
   tx=sh.text.transformed(it.trans());t.shapes(d.layer(info)).insert(tx);labels.append({'text':tx.string,'layer':str(info),'x':tx.x,'y':tx.y})
  it.next()
d.write(str(out/'actual.gds'));(out/'labels.json').write_text(json.dumps(labels,indent=2));(out/'extract.tcl').write_text((p/'extract.tcl').read_text());print('retained terminal labels',len(labels))

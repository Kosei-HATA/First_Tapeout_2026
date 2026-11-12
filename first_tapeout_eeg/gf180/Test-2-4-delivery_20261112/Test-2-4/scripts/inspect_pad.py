import klayout.db as k
l=k.Layout();l.read('/work/Test2-3/gds/Test2-3.gds');c=l.cell('Bondpad_5LM')
print('CELL',c.name,c.dbbox())
for li in l.layer_indices():
 s=list(c.shapes(li).each()); r=k.Region(c.begin_shapes_rec(li));
 if s or not r.is_empty():
  print('LAYER',l.get_info(li),'direct',len(s),'recursive',r.count(),'box',r.bbox().to_dtype(l.dbu))
  for sh in s[:5]:print(str(sh)[:250])
for i in c.each_inst():print('INST',i.cell.name,i.dcplx_trans,i.dbbox())

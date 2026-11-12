from pathlib import Path
import klayout.db as k
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');out=p/'alternative';out.mkdir(exist_ok=True);l=k.Layout();l.read(str(p/'coupled_wires/input.gds'));c=l.top_cell()
for layer,labels in [(34,[(1000,'A'),(99000,'B')]),(36,[(1000,'C'),(99000,'D')])]:
 for x,name in labels:c.shapes(l.layer(layer,10)).insert(k.Text(name,k.Trans(x,500)))
l.write(str(out/'coupled_labeled.gds'))

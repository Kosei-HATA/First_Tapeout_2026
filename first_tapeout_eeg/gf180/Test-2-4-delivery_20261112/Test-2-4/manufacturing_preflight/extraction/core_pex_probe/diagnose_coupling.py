from pathlib import Path
import klayout.db as k,subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');f=p/'coupled_wires';f.mkdir(exist_ok=True);l=k.Layout();l.dbu=.001;c=l.create_cell('coupled_wires')
for num in [34,36]:c.shapes(l.layer(num,0)).insert(k.Box(0,0,100000,1000))
l.write(str(f/'input.gds'));s=(p/'wire/ports.tcl').read_text().replace('load wire','load coupled_wires');annot=''
for i,(x,label) in enumerate([(1,'C'),(99,'D')]):annot+=f'box values {x}um 0.5um {x}um 0.5um\nlabel {label} center metal2\nport make {i+3}\n'
s=s.replace('extresist threshold',annot+'extresist threshold');(f/'ports.tcl').write_text(s)
with (f/'ports.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','ports.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
print('coupled CAP',(f/'cap_ports.spice').read_text(),'RC',(f/'rc_ports.spice').read_text())
for variant in ['high_threshold','no_coupling']:
 f=p/variant;f.mkdir(exist_ok=True);(f/'input.gds').write_bytes((p/'mim_only/input.gds').read_bytes());s=(p/'mim_only/ports.tcl').read_text()
 if variant=='high_threshold':s=s.replace('extresist threshold 0','extresist threshold 100000')
 else:s=s.replace('extract do local','extract do local\nextract no coupling')
 (f/'ports.tcl').write_text(s)
 with (f/'ports.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','ports.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
 print(variant,'CAP',(f/'cap_ports.spice').read_text(),'RC',(f/'rc_ports.spice').read_text())

from pathlib import Path
import subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis')
ports={'wire':[(1,.5,'A','metal1'),(99,.5,'B','metal1')],'mim_only':[(.1,.1,'TOP','mimcap'),(-.5,-.5,'BOT','metal4')],'adc_flat':[(1.1,.5,'TOP','metal4'),(.5,3.5,'BOT','metal4')]}
for name,ps in ports.items():
 f=p/name;annot=''
 for i,(x,y,label,layer) in enumerate(ps):annot+=f'box values {x}um {y}um {x}um {y}um\nlabel {label} center {layer}\nport make {i+1}\n'
 s=(f/'hier.tcl').read_text().replace('select top cell','select top cell\n'+annot).replace('cap_hier.spice','cap_ports.spice').replace('rc_hier.spice','rc_ports.spice');(f/'ports.tcl').write_text(s)
 with (f/'ports.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','ports.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
 print(name,'cap',(f/'cap_ports.spice').read_text(),'RC',(f/'rc_ports.spice').read_text())

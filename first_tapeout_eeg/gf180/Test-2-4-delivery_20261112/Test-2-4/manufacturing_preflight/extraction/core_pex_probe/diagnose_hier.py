from pathlib import Path
import subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis')
for name in ['mim_only','adc_flat','wire']:
 f=p/name;s=(f/'extract.tcl').read_text().replace('ext2spice hierarchy off','ext2spice hierarchy on').replace('cap.spice','cap_hier.spice').replace('rc.spice','rc_hier.spice');(f/'hier.tcl').write_text(s)
 with (f/'hier.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','hier.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
 print(name,(f/'rc_hier.spice').read_text());print((f/(name+'.res.ext')).read_text()[:1500])

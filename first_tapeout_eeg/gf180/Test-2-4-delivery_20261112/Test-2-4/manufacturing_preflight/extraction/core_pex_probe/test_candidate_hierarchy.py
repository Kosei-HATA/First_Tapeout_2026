from pathlib import Path
import subprocess,shutil
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');d=p/'rc_diagnosis/magic_candidate/tests3/adc_hierarchy';d.mkdir(exist_ok=True);shutil.copy2(p/'rc_trial/adc_c2.gds',d/'input.gds');s=(p/'rc_trial/extract.tcl').read_text().split('ext2spice hierarchy')[0].replace('adc_c2.gds','input.gds').replace('crashbackups stop','scalegrid 1 10')+'quit -noprompt\n';(d/'extract.cmd').write_text(s)
with (d/'extract.log').open('w') as log:subprocess.run([str(d.parents[1]/'install/bin/magic'),'-dnull','-rcfile','/dev/null','-T','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech'],input=''.join(':'+x+'\n' for x in s.splitlines()),text=True,cwd=d,stdout=log,stderr=subprocess.STDOUT,timeout=90)
s=(d.parent/'adc_flat/convert.tcl').read_text().replace('adc_flat.ext','adc_c2.ext');(d/'convert.tcl').write_text(s)
with (d/'convert.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','convert.tcl'],cwd=d,stdout=log,stderr=subprocess.STDOUT)
print((d/'cap.spice').read_text());print((d/'rc.spice').read_text());print('KILLED',[(f.name,x) for f in d.glob('*.res.ext') for x in f.read_text().splitlines() if 'killnode' in x])

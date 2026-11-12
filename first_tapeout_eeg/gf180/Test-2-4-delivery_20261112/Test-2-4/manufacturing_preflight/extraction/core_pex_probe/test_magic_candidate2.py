from pathlib import Path
import subprocess,shutil,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');candidate=p/'magic_candidate';exe=candidate/'install/bin/magic';tech='/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech';out=candidate/'tests2';out.mkdir(exist_ok=True);status={}
for name in ['wire','coupled_wires','mim_only','adc_flat']:
 f=out/name;f.mkdir(exist_ok=True);shutil.copy2(p/name/'input.gds',f/'input.gds');s=(p/name/'ports.tcl').read_text();s=s.split('ext2spice hierarchy')[0]+'quit -noprompt\n';(f/'extract.cmd').write_text(s)
 with (f/'extract.log').open('w') as log:r=subprocess.run([str(exe),'-dnull','-rcfile','/dev/null','-T',tech],input=''.join(':'+line+'\n' for line in s.splitlines() if line.strip()),text=True,cwd=f,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 status[name]={'extract_returncode':r.returncode,'ext_count':len(list(f.glob('*.ext')))}
 # Conversion remains installed 8.3.664, explicitly a mixed-version diagnostic.
 cv='ext2spice hierarchy on\next2spice format ngspice\next2spice cthresh 0\next2spice merge none\next2spice subcircuit top on\next2spice global off\next2spice scale off\next2spice extresist off\next2spice -o cap.spice '+name+'.ext\next2spice extresist on\next2spice -o rc.spice '+name+'.ext\nquit -noprompt\n';(f/'convert.tcl').write_text(cv)
 with (f/'convert.log').open('w') as log:r=subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','convert.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
 status[name]['converter_returncode']=r.returncode;print(name,(f/'rc.spice').read_text() if (f/'rc.spice').exists() else (f/'extract.log').read_text()[-1800:])
(out/'status.json').write_text(json.dumps(status,indent=2))


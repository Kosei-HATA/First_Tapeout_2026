from pathlib import Path
import subprocess,shutil,json,os,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');candidate=p/'magic_candidate';exe=candidate/'install_tcl/bin/magic';out=candidate/'full_tcl';out.mkdir(exist_ok=True);status={};env=os.environ.copy();env['LD_LIBRARY_PATH']=str(candidate/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','')
for name in ['wire','coupled_wires','mim_only','adc_flat','inverter_link','adc_hierarchy']:
 d=out/name;d.mkdir(exist_ok=True)
 if name=='adc_hierarchy':
  shutil.copy2(p.parent/'rc_trial/adc_c2.gds',d/'input.gds');s=(p.parent/'rc_trial/extract.tcl').read_text().replace('adc_c2.gds','input.gds');top='adc_c2'
 else:shutil.copy2(p/name/'input.gds',d/'input.gds');s=(p/name/'ports.tcl').read_text();top=name
 s=s.split('ext2spice hierarchy')[0]
 s+='ext2spice hierarchy on\next2spice format ngspice\next2spice cthresh 0\next2spice merge none\next2spice subcircuit top on\next2spice global off\next2spice scale off\next2spice extresist off\next2spice -o cap.spice\next2spice extresist on\next2spice -o rc.spice\nquit -noprompt\n';(d/'run.tcl').write_text(s)
 with (d/'run.log').open('w') as log:r=subprocess.run([str(exe),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 status[name]={'returncode':r.returncode,'has_rc':(d/'rc.spice').exists(),'input_sha256':hashlib.sha256((d/'input.gds').read_bytes()).hexdigest(),'killnodes':[line for f in d.glob('*.res.ext') for line in f.read_text().splitlines() if line.startswith('killnode')]};print(name,status[name])
(out/'status.json').write_text(json.dumps(status,indent=2))

from pathlib import Path
import os,subprocess,shutil,json,re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');c=p/'rc_diagnosis/magic_candidate';root=c/'resistance_controls';env=os.environ.copy();env['LD_LIBRARY_PATH']=str(c/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','');out={}
for corner in ['hrhc','hrlc','lrhc','lrlc']:
 d=root/('via1_'+corner);d.mkdir(exist_ok=True);shutil.copy2(root/'via1/input.gds',d/'input.gds');s=(root/'via1/run.tcl').read_text().replace('extract all','extract style ngspice('+corner+')\nextract all');(d/'run.tcl').write_text(s)
 with (d/'run.log').open('w') as f:r=subprocess.run([str(c/'install_tcl/bin/magic'),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 raw=(d/'via1.ext').read_text();res=[x for x in (d/'rc.spice').read_text().splitlines() if re.match('^R[0-9]',x)];out[corner]={'style':next(x for x in raw.splitlines() if x.startswith('style')),'R':res,'returncode':r.returncode}
(root/'corner_results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

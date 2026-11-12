from pathlib import Path
import re,math,os,subprocess,json,shutil
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');c=p/'rc_diagnosis/magic_candidate';d=c/'sidewall_diagnostic/new_legacy_offset';d.mkdir(exist_ok=True);raw=Path('/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech').read_text();changes=[]
def change(m):
 v=math.trunc(float(m[2])/.05)*.05;changes.append([m[0],m[1]+str(v)]);return m[1]+str(v)
s=re.sub(r'(?m)^(\s*defaultsidewall\s+\S+\s+\S+\s+[-+0-9.eE]+\s+)([-+0-9.eE]+)',change,raw);(d/'gf180mcuD.tech').write_text(s);shutil.copy2(c/'full_tcl/adc_flat/input.gds',d/'input.gds');(d/'run.tcl').write_text('tech load '+str(d/'gf180mcuD.tech')+'\n'+(c/'full_tcl/adc_flat/run.tcl').read_text());env=os.environ.copy();env['LD_LIBRARY_PATH']=str(c/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','')
with (d/'run.log').open('w') as f:r=subprocess.run([str(c/'install_tcl/bin/magic'),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
(d/'changes.json').write_text(json.dumps(changes,indent=2));print((d/'cap.spice').read_text())

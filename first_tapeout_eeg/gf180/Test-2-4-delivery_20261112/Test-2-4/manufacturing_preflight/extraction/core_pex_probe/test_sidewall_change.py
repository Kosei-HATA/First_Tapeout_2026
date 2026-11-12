from pathlib import Path
import shutil,subprocess,os,re,json,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe'); c=p/'rc_diagnosis/magic_candidate'; out=c/'sidewall_diagnostic';out.mkdir(exist_ok=True)
tech=Path('/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech'); raw=tech.read_text(); changes=[]
def double(m):
 changes.append({'original':m[0],'modified':m[1]+str(float(m[2])*2)})
 return m[1]+str(float(m[2])*2)
s=re.sub(r'(?m)^(\s*defaultsidewall\s+\S+\s+\S+\s+)([-+0-9.eE]+)',double,raw)
(out/'gf180mcuD.tech').write_text(s)
shutil.copy2(c/'full_tcl/adc_flat/input.gds',out/'input.gds')
tcl=(c/'full_tcl/adc_flat/run.tcl').read_text();tcl='tech load '+str(out/'gf180mcuD.tech')+'\n'+tcl
(out/'run.tcl').write_text(tcl)
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(c/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','')
with (out/'run.log').open('w') as f:r=subprocess.run([str(c/'install_tcl/bin/magic'),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
report={'diagnostic_only':True,'returncode':r.returncode,'original_tech_sha256':hashlib.sha256(tech.read_bytes()).hexdigest(),'coefficient_changes':changes,'warning':'Not a qualified PDK correction. Tests whether new parser halving explains version difference.'}
(out/'diagnostic.json').write_text(json.dumps(report,indent=2));print(r.returncode);print((out/'run.log').read_text()[-3000:])

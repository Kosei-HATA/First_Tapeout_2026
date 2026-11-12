from pathlib import Path
import re,os,subprocess,json,shutil
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');c=p/'rc_diagnosis/magic_candidate';out=c/'sidewall_diagnostic';tech=Path('/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech');raw=tech.read_text(); results={}
for version in ['old','new']:
 for mode in ['original','zero','m4_only','m5_only']:
  d=out/(version+'_'+mode);d.mkdir(exist_ok=True);shutil.copy2(c/'full_tcl/adc_flat/input.gds',d/'input.gds')
  def change(m):
   keep=mode=='original' or (mode=='m4_only' and m[2]=='metal4') or (mode=='m5_only' and m[2]=='metal5')
   return m[1]+m[2]+m[3]+(m[4] if keep else '0')
  s=re.sub(r'(?m)^(\s*defaultsidewall\s+\S+\s+)(\S+)(\s+)([-+0-9.eE]+)',change,raw);(d/'gf180mcuD.tech').write_text(s)
  tcl='tech load '+str(d/'gf180mcuD.tech')+'\n'+(c/'full_tcl/adc_flat/run.tcl').read_text();(d/'run.tcl').write_text(tcl)
  env=os.environ.copy();env['LD_LIBRARY_PATH']=str(c/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','');exe=str(c/'install_tcl/bin/magic') if version=='new' else '/foss/tools/magic/bin/magic'
  with (d/'run.log').open('w') as f:r=subprocess.run([exe,'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
  caps=[x.split() for x in (d/'cap.spice').read_text().splitlines() if re.match(r'^C\d',x)];results[version+'_'+mode]={'rc':r.returncode,'caps':caps};print(version,mode,caps)
(out/'factor_sweep.json').write_text(json.dumps(results,indent=2))

from pathlib import Path
import re,json,subprocess,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe/rc_corners');report={};arrays={}
for corner in ['hrhc','hrlc','lrhc','lrlc']:
 d=p/corner;s=(d/'rc.spice').read_text();report[corner]={};arrays[corner]=[x for x in s.splitlines() if re.match(r'^R\d',x)]
 for name,txt in {'missing_R':re.sub(r'^R0 .*\n','',s,flags=re.M),'extra_C':s.replace('.ends','C999999 CHOP1 VSS 1f\n.ends')}.items():
  (d/(name+'.spice')).write_text(txt);r=subprocess.run(['python3',str(d/'validate.py'),name+'.spice',name+'.json'],capture_output=True,text=True);(d/(name+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0;v=json.loads((d/(name+'.json')).read_text());report[corner][name]={'detected':not v['pass'],'disconnected_groups':v['disconnected_groups'],'capacity_violations':v['cap_print_precision_violations'][:2]}
report['resistance_network_identical_with_C_corner_only_change']={'hrhc_hrlc':arrays['hrhc']==arrays['hrlc'],'lrhc_lrlc':arrays['lrhc']==arrays['lrlc']};(p/'negative_and_resistance_checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
manifest={str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() for x in p.rglob('*') if x.is_file() and x.name!='manifest.json'};(p/'manifest.json').write_text(json.dumps(manifest,indent=2))

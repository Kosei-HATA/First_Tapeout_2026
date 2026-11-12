from pathlib import Path
import json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep/gf180mcu_fd_io__bi_24t');geom=Path('/work/Test-2-4/baseline/pad_geometry.json');pads=[x for x in json.loads(geom.read_text())['pads'] if x['cell']=='gf180mcu_fd_io__bi_24t'];assert len(pads)==9 and all(x['nets']['DVSS']==x['nets']['VSS']=='VSS' for x in pads)
ref=(p/'reference.spice').read_text();lines=[]
for line in ref.splitlines():
 if line.lower().startswith('.subckt'):line=' '.join(x for x in line.split() if x!='DVSS')
 else:line=re.sub(r'\bDVSS\b','VSS',line)
 lines.append(line)
s='\n'.join(lines)+'\n';(p/'reference_common_ground.spice').write_text(s)
(p/'common_ground_evidence.json').write_text(json.dumps({'scope':'Conditional IO comparison for documented common-ground usage; not unconstrained standalone IO equivalence','source':str(geom),'sha256':hashlib.sha256(geom.read_bytes()).hexdigest(),'mapping':'DVSS -> VSS; remove duplicate external port','instances':[{'name':x['inst'],'DVSS':x['nets']['DVSS'],'VSS':x['nets']['VSS']} for x in pads],'reason':'All 9 independently recorded original pad instances connect DVSS and VSS to VSS. Magic extracts the common p-substrate connection.'},indent=2))

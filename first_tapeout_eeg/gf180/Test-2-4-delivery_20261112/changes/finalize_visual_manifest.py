"""Validate PNG readability and refresh artifact hashes after documented visual QA.
Run only after opening and inspecting the four current PNGs. This script is not a
substitute for visual review and will not set the visual-review assertions.
"""
from pathlib import Path
import hashlib,json,time
from PIL import Image
OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((OUT/'metadata.json').read_text())
qa=json.loads((OUT/'visual_qa.json').read_text())
assert qa['visual_review_completed'] is True
pngs=[]
for p in sorted(OUT.glob('*.png')):
 with Image.open(p) as im:
  im.verify()
 with Image.open(p) as im:
  pngs.append({'name':p.name,'pixels':list(im.size),'bytes':p.stat().st_size,'sha256':sha(p)})
assert len(pngs)==4
qa['png_files']=pngs
qa['manifest_updated_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
(OUT/'visual_qa.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False),encoding='utf-8')
meta['outputs']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ['metadata.json','SHA256SUMS.txt']]
meta['presentation_update']='Bridge PNG axis labels were adjusted using verified geometry_extract.json; no data change. Full renderer source has the same layout adjustment.'
meta['artifact_manifest_updated_utc']=qa['manifest_updated_utc']
(OUT/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
(OUT/'SHA256SUMS.txt').write_text('INPUT GDS FILES (relative to original test1x root)\n'+''.join(v['sha256']+'  '+v['relative_path']+'\n' for v in meta['input_files'].values())+'\nDELIVERY VISUALS (relative to this directory)\n'+''.join(sha(p)+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf-8')
print(json.dumps({'checks':meta['checks'],'pngs':pngs,'files':[p.name for p in sorted(OUT.iterdir()) if p.is_file()]},indent=2))

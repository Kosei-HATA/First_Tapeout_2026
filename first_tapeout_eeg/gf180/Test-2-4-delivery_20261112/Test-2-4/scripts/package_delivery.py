from pathlib import Path
import zipfile,hashlib,json,ast
p=Path(r'C:\projects\ft\test1x\Test-2-4'); out=p.parent/'Test-2-4_delivery_20261111.zip'
for f in (p/'scripts').glob('*.py'):ast.parse(f.read_text(encoding='utf-8-sig'))
files=[];excluded=[]
for f in p.rglob('*'):
 if not f.is_file():continue
 rel=f.relative_to(p);parts=rel.parts
 skip='__pycache__' in parts or 'rechecks' in parts or (parts[0]=='functional' and ('runs' in parts or 'build' in parts)) or (parts[0]=='verification' and f.suffix in ['.gds','.lvsdb'])
 if skip:excluded.append({'path':rel.as_posix(),'bytes':f.stat().st_size});continue
 files.append(f)
manifest={'delivery':'Test-2-4','note':'Includes delivered GDS, scripts, source copies, result summaries and logs. Large LVS database, intermediate GDS, generated simulation waveforms/build outputs remain in the local project. Existing GF180 project and PDK are required for rerun.','files':[{'path':f.relative_to(p).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in files],'excluded_local_files':excluded}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for f in files:z.write(f,'Test-2-4/'+f.relative_to(p).as_posix())
 z.writestr('Test-2-4/delivery_manifest.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
result={'path':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'files':len(files),'excluded_count':len(excluded),'zip_crc_verified':True}
(p/'verification/delivery_package.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

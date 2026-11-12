#!/usr/bin/env python3
"""Read-only integrity verification of the extracted delivery package."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
expected={item['path']:item for item in manifest['files']}
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='MANIFEST_SHA256.json'}
errors=[]
for name in sorted(set(expected)-actual):errors.append('Missing: '+name)
for name in sorted(actual-set(expected)):errors.append('Unexpected: '+name)
for name,item in expected.items():
 p=root/name
 if not p.is_file():continue
 if p.stat().st_size!=item['bytes']:errors.append('Size mismatch: '+name);continue
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 if h.hexdigest()!=item['sha256']:errors.append('SHA-256 mismatch: '+name)
print(json.dumps({'status':'PASS' if not errors else 'FAIL','checked_files':len(expected),'errors':errors,'scope':'File integrity only, not manufacturing signoff'},indent=2))
sys.exit(1 if errors else 0)

import json,pathlib,zipfile
root=pathlib.Path(__file__).resolve().parent
z=zipfile.ZipFile(root.parent.parent/'Test-2-4_preflight_evidence_20261111.zip')
bad=[];ok=0
for n in z.namelist():
    if not n.lower().endswith(('.md','.json')): continue
    b=z.read(n)
    try:
        t=b.decode('utf-8-sig')
        if '\ufffd' in t: bad.append({'path':n,'reason':'replacement character present'})
        else: ok+=1
    except UnicodeDecodeError:
        try:
            b.decode('cp932'); reason='CP932 decodes, not UTF8'
        except UnicodeDecodeError: reason='not UTF8 or CP932'
        bad.append({'path':n,'reason':reason})
print(json.dumps({'utf8_ok':ok,'issues':bad},ensure_ascii=False,indent=2))

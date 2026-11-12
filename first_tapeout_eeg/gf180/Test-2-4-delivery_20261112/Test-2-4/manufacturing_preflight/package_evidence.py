"""Package a compact evidence snapshot; never replaces design delivery or raw results."""
import argparse, datetime, hashlib, json, pathlib, zipfile, os
p=argparse.ArgumentParser();p.add_argument('--output', required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent
out=pathlib.Path(a.output).resolve()
if out.exists(): raise SystemExit('Refuse to overwrite existing snapshot')
source_excludes=('ngspice48_isolated/source/', 'ngspice48_isolated/build/', 'ngspice48_isolated/install/', 'ngspice48_isolated/deps/', 'magic_candidate/source/', 'magic_candidate/source_tcl/', 'magic_candidate/install_tcl/', 'magic_candidate/dependencies/', 'magic_candidate/deps/', 'magic_candidate/install/', '.git/', '__pycache__/')
keep=[];excluded=[]
def evidence_files():
    for current, dirs, files in os.walk(root):
        for name in list(dirs):
            rel=(pathlib.Path(current)/name).relative_to(root).as_posix()+'/'
            if any(x in rel for x in source_excludes):
                dirs.remove(name)
                excluded.append({'path':rel,'kind':'directory','reason':'Build dependency/source cache or metadata; commit references retained in logs'})
        for name in files:
            yield pathlib.Path(current)/name
for f in sorted(evidence_files()):
    if not f.is_file() or f.resolve()==out: continue
    rel=f.relative_to(root).as_posix(); size=f.stat().st_size
    reason=None
    if rel.startswith('delivery_report_20261112/') and f.name not in ('Test-2-4_verification_report_ja_20261112_final.pdf','Test-2-4_verification_report_ja_20261112_final.docx','report_qa_final.json'): reason='Superseded report draft or environment-specific document build helper; final report and QA included'
    elif any(x in rel for x in source_excludes): reason='Build dependency/source cache; commit references retained in logs'
    elif f.suffix.lower() in ('.lvsdb','.o','.a','.so','.raw','.zip'): reason='Large/binary source or derived artifact; retained locally'
    elif f.suffix.lower()=='.csv' and size>1000000: reason='Raw waveform retained locally; analysis, hashes, inputs and logs included'
    elif size>5000000: reason='Large evidence retained locally; excluded from compact snapshot'
    if reason:
        excluded.append({'path':rel,'bytes':size,'reason':reason})
    else:
        data=f.read_bytes()
        keep.append((rel,data,hashlib.sha256(data).hexdigest()))
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Compact evidence snapshot, not manufacturing signoff or standalone tool/PDK installation','design_delivery_gds_sha256':'7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755','included':[{'path':r,'bytes':len(d),'sha256':h} for r,d,h in keep],'excluded':excluded,'raw_results_location':'Test-2-4/manufacturing_preflight on MY-NOTE-2; source GDS remains in original delivered ZIP'}
with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for r,d,h in keep: z.writestr('manufacturing_preflight/'+r,d)
    z.writestr('SNAPSHOT_MANIFEST.json',json.dumps(manifest,indent=2,ensure_ascii=False))
with zipfile.ZipFile(out) as z:
    bad=z.testzip()
    if bad: raise RuntimeError('CRC failure: '+bad)
print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'included_files':len(keep),'excluded_files':len(excluded),'crc':'pass'},indent=2))








from pathlib import Path
import json,hashlib,datetime
import numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/analog');d=p/'dac_static_typical'
rows=[json.loads((d/('code_'+str(k).zfill(2))/'result.json').read_text()) for k in range(32)]
assert all(r.get('exitcode')==0 and r['last_time_s']>=13.71875e-6 for r in rows)
j=-np.array([r['J_A'] for r in rows]);lsb=(j[-1]-j[0])/31
dnl=np.diff(j)/lsb-1;inl=(j-j[0])/lsb-np.arange(32)
manifest=json.loads((p/'input_manifest.json').read_text());changed=[]
for item in manifest:
 f=p/item['path'].replace('\\','/')
 if hashlib.sha256(f.read_bytes()).hexdigest()!=item['sha256']:changed.append(item['path'])
summary={'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Schematic typical27C 3.3V, ideal output virtual ground and references, mismatch disabled. No PEX/noise/DWA. 5bit DAC static metrics do not qualify ADC16.5bit.','definitions':{'J':'i(VOP)-i(VON), positive slope by convention; sign opposite stored per-run J_A','average':'mean of complete frame9 and10 averages, each DAC update offset4TM; endpoint-interpolated integration','INL':'endpoint (J[k]-J[0])/LSB-k','DNL':'(J[k+1]-J[k])/LSB-1','settling':'frame10 minus frame9 mean, not system step-response settling'},'LSB_A':float(lsb),'range_A':[float(j[0]),float(j[-1])],'endpoint_offset_A':float((j[0]+j[-1])/2),'max_abs_INL_LSB':float(np.max(abs(inl))),'max_abs_DNL_LSB':float(np.max(abs(dnl))),'monotonic':bool(np.all(np.diff(j)>0)),'max_last_frame_delta_A':max(abs(r['settling_last_frame_delta_A']) for r in rows),'INL_LSB':inl.tolist(),'DNL_LSB':dnl.tolist(),'J_A':j.tolist(),'input_hash_checked':len(manifest),'input_hash_changed':changed,'performance_acceptance_spec_defined':False,'ENOB_qualified':False,'runs':rows}
(d/'summary.json').write_text(json.dumps(summary,indent=2))
with (d/'codes.csv').open('w') as f:
 f.write('code,J_A,INL_LSB,DNL_from_previous_LSB,settling_delta_A\n')
 for k in range(32):f.write(f'{k},{j[k]:.15g},{inl[k]:.15g},{dnl[k-1] if k else ""},{rows[k]["settling_last_frame_delta_A"]:.15g}\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['runs','INL_LSB','DNL_LSB','J_A']},indent=2))

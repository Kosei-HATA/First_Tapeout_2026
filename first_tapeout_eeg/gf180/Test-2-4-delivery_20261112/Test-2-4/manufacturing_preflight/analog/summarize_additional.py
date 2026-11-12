from pathlib import Path
import numpy as np,json,math,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/analog');rows=[]
T=1/1.024e6;TM=T/32;T0=2e-6
for corner,temp in [('typical',27),('ss',85),('ff',-20)]:
 f=p/f'dac_trace/runs/brk_{corner}{temp}/tr.csv';x=np.loadtxt(f);t=x[:,0];d=x[:,3];db=x[:,5];q=x[:,9];qb=x[:,11];m=t>T0+T
 overlap=(d[m]>.7)&(db[m]>.7)
 rows.append({'corner':corner,'temp':temp,'max_time_s':float(t[-1]),'samples':len(t),'both_D_DB_above_0p7_samples_after_first_frame':int(overlap.sum()),'max_simultaneous_min_D_DB_V':float(np.minimum(d[m],db[m]).max()),'wave_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'qualification':'Threshold-based nonoverlap observation for cell0 only; not device-current or all31-cell mismatch signoff.'})
a=json.loads((p/'clock_sensitivity.json').read_text());fine=json.loads((p/'clock_convergence.json').read_text());conv=[]
for f in fine['cases']:
 old=next(x for x in a['cases'] if x['vdd']==f['vdd'] and x['corner']=='ff');delta=f['minimum_margin_ns']-old['minimum_margin_ns'];conv.append({'vdd':f['vdd'],'baseline_margin_ns':old['minimum_margin_ns'],'fine_margin_ns':f['minimum_margin_ns'],'delta_ps':delta*1000})
manifest=json.loads((p/'input_manifest.json').read_text());changes=[]
for item in manifest:
 f=p/item['path'].replace('\\','/')
 if hashlib.sha256(f.read_bytes()).hexdigest()!=item['sha256']:changes.append(item['path'])
r={'clock_cases':len(a['cases']),'positive_clock_sequences_all':all(x['positive_sequence_margins'] for x in a['cases']),'minimum_clock_case':min(a['cases'],key=lambda x:x['minimum_margin_ns']),'clock_convergence':conv,'DAC_break_execution':json.loads((p/'dac_break_results.json').read_text()),'DAC_gate_nonoverlap':rows,'input_files_changed':changes,'ENOB_qualified':False,'scope':'Added schematic clock sensitivity and DAC break checks. Fixed bias/CM clock fixture; no extracted parasitics, full supply-tracking bias, device noise/mismatch or package effects.','next_steps':['Extracted-clock/load timing and bias tracking PVT','DAC even-charge/ref-charge corners and numerical convergence','Model-validated noise and mismatch budget','Continuous in-band chip-input-to-actual-decimator verification against16.5bit acceptance']}
(p/'analog_preflight_summary.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

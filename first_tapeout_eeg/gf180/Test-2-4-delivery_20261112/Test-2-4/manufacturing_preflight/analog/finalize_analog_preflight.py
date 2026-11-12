from pathlib import Path
import json,hashlib,datetime,shutil,subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/analog');stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
archive=p/'report_history'/tag;archive.mkdir(parents=True,exist_ok=False)
for name in ['analog_preflight_summary.json','README.md']:
 if (p/name).exists():shutil.copy2(p/name,archive/name)
subprocess.run(['python3',str(p/'summarize_additional.py')],check=True,stdout=subprocess.DEVNULL)
r=json.loads((p/'analog_preflight_summary.json').read_text());status=json.loads((p/'dac_even_status.json').read_text());results=json.loads((p/'dac_even_results.json').read_text());audit=json.loads((p/'dac_even_independent_partial.json').read_text())
assert status['stage']=='finished' and len(status['completed_subruns'])==8 and len(audit['results'])==4
for a in audit['results']:
 b=next(x for x in results if x['corner']==a['corner']);assert abs(a['even_charge_fC_per_toggle']-b['even_charge_fC_per_toggle'][a['pattern']])<1e-15
 assert a['within_limit']
waveforms=[]
for x in status['completed_subruns']:
 f=p/'dac_even/runs'/x['tag']/'tr.csv';assert f.exists()
 waveforms.append({'tag':x['tag'],'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size,'last_time_s':x['last_time_s'],'samples':x['samples']})
assert not r['input_files_changed']
gds=p.parents[1]/'gds/Test-2-4.gds';gds_hash=hashlib.sha256(gds.read_bytes()).hexdigest();assert gds_hash=='7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755'
r.update(report_updated_utc=stamp,report_state='Completed assigned additional clock sensitivity, DAC break/nonoverlap and SS/FF even-charge checks; overall manufacturing/ENOB qualification incomplete.',supersedes='Prior partial analog_preflight_summary.json, preserved in report_history/'+tag,DAC_even_charge_results=results,DAC_even_independent_audit=audit['results'],DAC_even_waveforms=waveforms,DAC_even_completed_subruns=8,DAC_even_all_measured_patterns_within_limit=True,simulation_inputs_hash_verified=True,GDS_unchanged_sha256=gds_hash)
r['next_steps']=['Extracted-clock/load timing and full bias tracking PVT','DAC even-charge numerical convergence across alternate solver settings and mismatch','Model-validated noise and mismatch budget','Continuous in-band chip-input-to-actual-decimator verification against16.5bit acceptance']
r['DAC_even_scope']='3.3V, ideal virtual-ground outputs and references, supplied tolerance A, nominal device geometry without mismatch and no extracted parasitics; SS85C and FF-20C, 72-frame patterns. Independent integration reuses documented window and toggle normalization. Does not qualify full DAC linearity, INL/DNL, noise, long-term settling or system ENOB.'
(p/'analog_preflight_summary.json').write_text(json.dumps(r,indent=2));audit.update(finalized_utc=stamp,scope='Final independent integration of all eight completed waveforms, four paired results. All compare identically with runner outputs.');(p/'dac_even_independent_final.json').write_text(json.dumps(audit,indent=2))
print(json.dumps({'updated_utc':stamp,'input_hashes_unchanged':not r['input_files_changed'],'input_file_count':len(json.loads((p/'input_manifest.json').read_text())),'GDS_unchanged':True,'completed_waveforms':len(waveforms),'all_even_charge_within_limit':True,'maximum_abs_fC_per_toggle':max(abs(x['even_charge_fC_per_toggle']) for x in audit['results']),'archive':str(archive)},indent=2))

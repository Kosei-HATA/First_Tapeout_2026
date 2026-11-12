from pathlib import Path
import json,hashlib,re,datetime
p=Path(r'C:\projects\ft\test1x\Test-2-4');v=p/'verification'
def j(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
build=j(v/'build.json');drc=j(v/'drc_summary.json');conn=j(v/'connectivity.json');lvs=j(v/'core_with_hints/core_lvs_summary.json');pad=j(v/'pad_eco_audit.json');func=j(p/'functional/functional_summary.json')
base=j(p.parent/'Test2-3/baseline/manifest.json')
inputs=base['inputs']+[{'path':str(p.parent/'Test2-3/gds/Test2-3.gds'),'sha256':build['input_sha256']}]
for x in inputs:x['unchanged']=sha(Path(x['path']))==x['sha256']
log=(v/'full_drc.log').read_text();old=(p.parent/'Test2-3/verification/full_drc.log').read_text();decks=set(re.findall(r'Completed deck\s*:\s*(\S+)',log));baseline=set(re.findall(r'Completed deck\s*:\s*(\S+)',old))
r={'name':'Test-2-4','completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'gds_sha256':sha(p/'gds/Test-2-4.gds'),'input_files':inputs,'full_drc_pass':drc['pass'],'drc_marker_count':drc['total_items'],'completed_decks':len(decks),'missing_baseline_decks':sorted(baseline-decks),'extra_decks':sorted(decks-baseline),'rules_waived':False,'core_lvs_pass':lvs['core_lvs_pass'],'probe_connectivity_pass':conn['pass'],'probe_count':conn['point_count'],'net_count':conn['group_count'],'pad_audit':pad,'digital_pass_count':int(func['digital_summary'][-1][0]),'digital_fail_count':int(func['digital_summary'][-1][1]),'analog_process_success_count':sum(x['exitcode']==0 for x in func['analog_execution_results']),'adc_clock_minimum_margin_ns':func['adc_clock_minimum_margin_ns'],'functional_report':'functional/functional_summary.json','release_status':'Public DRC clean candidate; NOT foundry/assembly or full-chip analog performance signoff. Custom non-CUP bondpad metal requires approval.','unverified':func['unverified']+['full pad-ring device LVS','assembly/bonding mechanical qualification','ESD robustness','CUP applicability and manufacturer approval','specified analog accuracy and timing guardbands']}
assert all(x['unchanged'] for x in inputs)
assert r['gds_sha256']==build['output_sha256']==conn['input_sha256']
assert r['full_drc_pass'] and r['drc_marker_count']==0 and len(decks)==177 and not r['missing_baseline_decks']
assert r['core_lvs_pass'] and r['probe_connectivity_pass'] and r['digital_pass_count']==15 and r['digital_fail_count']==0
assert pad['checks']['all_other_geometry_hierarchy_and_properties_unchanged']
(v/'final_summary.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
(p/'baseline/manifest.json').write_text(json.dumps({'name':'Test-2-4','inputs':inputs,'gds_sha256':r['gds_sha256'],'originals_modified':False},indent=2),encoding='utf-8')
print(json.dumps(r,indent=2))

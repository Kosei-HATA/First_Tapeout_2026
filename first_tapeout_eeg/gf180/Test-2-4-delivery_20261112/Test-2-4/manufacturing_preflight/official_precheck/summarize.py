from pathlib import Path
import json,hashlib,datetime
p=Path(__file__).resolve().parent;run=p/'runs/verify_test24_20261111'
def j(f):return json.loads(f.read_text(encoding='utf-8-sig'))
metrics={};steps=[]
for d in sorted(run.iterdir()):
 f=d/'state_out.json'
 if d.is_dir() and f.exists():metrics.update(j(f).get('metrics',{}));steps.append(d.name)
mlog=run/'12-magic-drc/magic-drc.log';mtext=mlog.read_text(errors='replace') if mlog.exists() else ''
clog=p/'official_precheck.log';ctext=clog.read_text(encoding='utf-8-sig',errors='replace') if clog.exists() else ''
cs=j(p/'container_state.json');config=j(run/'resolved.json');keys=['klayout__density_error__count','klayout__zero_area_polygons__count','klayout__antenna_error__count','klayout__drc_error__count','magic__drc_error__count']
done='DRC Checking DONE' in mtext;success='Precheck successfully completed' in ctext
input=Path(r'C:\projects\ft\test1x\Test-2-4\gds\Test-2-4.gds');digest=hashlib.sha256(input.read_bytes()).hexdigest();same=digest=='7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755'
strict=done and success and cs.get('Status')=='exited' and cs.get('ExitCode')==0 and all(metrics.get(key)==0 for key in keys) and same
cob=j(p/'cob_mask_state.json');cobpass=cob.get('ExitCode')==0 and cob.get('Status')=='exited' and 'Success: Pad mask matches!' in (p/'cob_mask.log').read_text(encoding='utf-8-sig')
r={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'strict_pass':strict,'flow_success_message':success,'container_state':cs,'magic_completed':done,'magic_duplicate_instance_warnings':mtext.count('placed on top of itself'),'metrics':metrics,'completed_steps':steps,'required_zero_metrics':keys,'input_sha256':digest,'input_unchanged':same,'resolved_options':{k:config.get(k) for k in ['PDK','WS_ID','WS_SLOT','WS_COB','KLAYOUT_DRC_OPTIONS','ERROR_ON_MAGIC_DRC']},'cob_mask_geometry_pass':cobpass,'cob_qualification':'Separate geometric mask inclusion only; does not choose or qualify CoB bonding.','scope':'Pinned official local manufacturing precheck. Its KLayout DRC excludes CUP; the prior full-public 177-deck run includes CUP and is separately archived. Not foundry acceptance or electrical/performance signoff.','derived_output':'Test-2-4_prechecked.gds contains flow ID/dummy normalization; source delivery GDS is untouched.'}
(p/'official_summary.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))

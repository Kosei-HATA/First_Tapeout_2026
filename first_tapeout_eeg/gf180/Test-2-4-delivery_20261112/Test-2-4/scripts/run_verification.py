from pathlib import Path
import subprocess,time,json,sys
import klayout.rdb as rdb
p=Path('/work/Test-2-4');v=p/'verification';status=json.loads((v/'jobs.json').read_text()) if (v/'jobs.json').exists() else {}
status.pop('workflow',None)
def run(name,cmd):
 if status.get(name,{}).get('exitcode')==0:return
 start=time.time();status[name]={'status':'running','start_epoch':start,'cmd':cmd};save()
 with (v/(name+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 status[name].update(status='finished',exitcode=r.returncode,seconds=round(time.time()-start,2));save()
 if r.returncode:raise RuntimeError(name+' process failed')
def save():(v/'jobs.json').write_text(json.dumps(status,indent=2))
try:
 run('connectivity',['python3',str(p/'scripts/check_connectivity.py')])
 run('prepare_core',['python3',str(v/'prepare_core_lvs.py')])
 run('restore_hints',['python3',str(v/'restore_lvs_hints.py')])
 run('core_lvs',['bash',str(v/'core_with_hints/run.sh')])
 run('summarize_core',['python3',str(v/'summarize_core_lvs.py')])
 run('full_drc',['/foss/tools/klayout/klayout','-b','-r','/foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc','-rd','input=/work/Test-2-4/gds/Test-2-4.gds','-rd','report=/work/Test-2-4/verification/full_drc.lyrdb','-rd','topcell=chip_top','-rd','variant=D','-rd','run_mode=deep','-rd','workers=2','-rd','threads=2','-rd','decks=all'])
 db=rdb.ReportDatabase();db.load(str(v/'full_drc.lyrdb')); cats=[]
 for c in db.each_category():
  if c.num_items():cats.append({'name':c.name(),'count':c.num_items()})
 result={'total_items':db.num_items(),'categories':cats,'pass':db.num_items()==0,'note':'No waiver. Compare inherited CUP markers separately; a zero process exit is not DRC pass.'};(v/'drc_summary.json').write_text(json.dumps(result,indent=2))
 status['workflow']={'status':'finished'};save()
except Exception as e:
 status['workflow']={'status':'failed','error':str(e)};save();raise

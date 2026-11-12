from pathlib import Path
import re,json,subprocess,time
p=Path('/work/Test-2-4/functional');root=p/'sim_work/gf180/tapeout/sim';changed=[]
pattern=r'os\.path\.expanduser\("~/.ciel/ciel/gf180mcu/versions/"\s*"f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice"\)'
for f in root.rglob('*.py'):
 s=f.read_text();new,n=re.subn(pattern,'"/work/Test-2-4/functional/models"',s)
 if n:f.write_text(new);changed.append(str(f.relative_to(root)))
(p/'analog_environment.json').write_text(json.dumps({'model_revision':'f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7','model_source':'existing local PDK staging copy; copied into container /work/Test-2-4/functional/models','path_only_changes':changed,'scope':'Schematic-level supplied testbenches; includes supplied linear MOSCAP approximation; not extracted-chip validation.'},indent=2))
jobs=[('bias_op','bias/bias_check.py',['op']),('bias_start','bias/bias_check.py',['start']),('reference','ref/ref_check.py',[]),('testmux_tt','test/testmux_check.py',[]),('testmux_ss','test/testmux_check.py',['--corner','ss','--temp','85']),('testmux_ff','test/testmux_check.py',['--corner','ff','--temp','-20'])]
results=[]
for name,script,args in jobs:
 t=time.time()
 try:
  with (p/(name+'.log')).open('w') as f:r=subprocess.run(['python3',str(root/script),*args],stdout=f,stderr=subprocess.STDOUT,timeout=240)
  rc=r.returncode
 except subprocess.TimeoutExpired:rc='timeout'
 results.append({'test':name,'exitcode':rc,'seconds':round(time.time()-t,1),'log':name+'.log'})
 print(results[-1],flush=True);(p/'analog_results.json').write_text(json.dumps(results,indent=2))

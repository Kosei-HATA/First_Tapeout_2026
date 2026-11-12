from pathlib import Path
import ast,os,json,time,subprocess,signal,concurrent.futures,hashlib,threading,re
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');out=p/'full_rc_pvt_matrix'
tree=ast.parse((p/'run_fixed_rc_pvt.py').read_text(encoding='utf-8-sig'));exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)) or isinstance(n,ast.FunctionDef) and n.name=='measure'],type_ignores=[]),'<measure>','exec'))
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
old='/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe/flat/rc.spice'
prior=json.loads((p/'fixed_nominal_rc_pvt/results.json').read_text())
corners=[{'name':'nominal','spice':old,'sha256':prior['rc_sha256']}]+json.loads((p/'rc_corner_sensitivity/approved_inputs.json').read_text())['corners']
for c in corners:assert sha(c['spice'])==c['sha256']
oldclock='/work/Test-2-4/functional/sim_work/gf180/tapeout/adc/eeg_adc_clk.spice'
extra=' '.join('v('+n+')' for n in json.loads((p/'comparison_inputs.json').read_text())['load_wave_nodes'])
bases={};rows=[];reuse=[];manifest={}
for r in prior['cases']:
 v,c,t=r['vdd'],r['corner'],r['temperature_C'];key=(v,c,t)
 d=p/'rc_klu' if key==(3.3,'typical',27) else p/'fixed_nominal_rc_pvt'/f'{v}_{c}_{t}'
 s=(d/'tb.spice').read_text()
 expected=(p.parent/'clock'/str(v)/'runs'/f'aclk_{c}_{t}'/'tb.spice').read_text().replace(oldclock,old).replace('.options sparse reltol=1e-4','.options klu reltol=1e-4').replace('tran 0.01n','op\nwrdata op.csv '+extra+'\ntran 0.01n').replace('quit\n.endc','wrdata load_wave.csv '+extra+'\nquit\n.endc')
 assert s==expected,(key,'deck mismatch')
 if 'deck_sha256' in r:assert sha(d/'tb.spice')==r['deck_sha256']
 m=measure(d,v);assert m=={k:r[k] for k in m},(key,'measurement mismatch')
 assert r['exitcode']==0 and r['positive_sequence_margins']
 bases[key]=s;row={**r,'rc_corner':'nominal','reused_from':str(d),'deck_sha256':sha(d/'tb.spice')};rows.append(row);reuse.append(str(d))
for r in json.loads((p/'rc_corner_sensitivity/results.json').read_text())['cases']:
 if r['rc_corner']=='nominal':continue
 c=next(c for c in corners if c['name']==r['rc_corner']);d=p/'rc_corner_sensitivity'/c['name']
 assert (d/'tb.spice').read_text()==bases[(3.6,'ff',-20)].replace(old,c['spice'])
 assert r['spice_sha256']==c['sha256'];m=measure(d,3.6);assert m=={k:r[k] for k in m}
 rows.append({**r,'reused_from':str(d),'deck_sha256':sha(d/'tb.spice')});reuse.append(str(d))
assert len(rows)==19
# Snapshot all recursively included inputs, plus simulator, wrapper and measurement source.
def collect(path):
 path=Path(path).resolve()
 if str(path) in manifest:return
 manifest[str(path)]=sha(path)
 if path.suffix not in ('.spice','.ngspice'):return
 for line in path.read_text(errors='replace').splitlines():
  z=re.match(r'^\s*\.(?:include|lib)\s+["\x27]?([^\s"\x27]+)',line,re.I)
  if z:
   q=Path(z[1]);q=q if q.is_absolute() else path.parent/q
   if q.is_file():collect(q)
for d in reuse:
 collect(Path(d)/'tb.spice')
 for n in ('out.csv','run.log'):manifest[str(Path(d)/n)]=sha(Path(d)/n)
for c in corners:collect(c['spice'])
for f in ['/foss/tools/bin/ngspice','/work/Test-2-4/functional/sim_bin/ngspice','/work/Test-2-4/functional/sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py']:collect(f)
(out/'input_manifest.json').write_text(json.dumps(manifest,indent=2))
(out/'reuse_audit.json').write_text(json.dumps({'reused':19,'deck_regeneration_exact':True,'measurements_recomputed_exact':True,'corners':corners,'sources':reuse},indent=2))
lock=threading.Lock();start_all=time.time()
def save():
 with lock:
  done=[r for r in rows if r['status']=='finished'];good=[r for r in done if 'minimum_margin_ns'in r]
  summary={'completed':len(done),'total':75,'reused':19,'new_completed':len(done)-19,'running':sum(r['status']=='running' for r in rows),'elapsed_s':round(time.time()-start_all,1),'failures':[r for r in done if not r.get('positive_sequence_margins') or r.get('exitcode')!=0],'worst':min(good,key=lambda r:r['minimum_margin_ns'])}
  (out/'summary.tmp').write_text(json.dumps(summary,indent=2));os.replace(out/'summary.tmp',out/'summary.json')
  (out/'results.tmp').write_text(json.dumps({'max_workers':4,'timeout_s':600,'scope':'15 selected device/supply/temperature combinations x 5 official clock RC corners; schematic external loads, not full-chip signoff.','cases':rows},indent=2));os.replace(out/'results.tmp',out/'results.json')
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
def job(case):
 key,c=case;v,dev,t=key;d=out/f"{v}_{dev}_{t}_{c['name']}";d.mkdir()
 s=bases[key].replace(old,c['spice']);(d/'tb.spice').write_text(s)
 row={'vdd':v,'corner':dev,'temperature_C':t,'rc_corner':c['name'],'status':'running','deck_sha256':sha(d/'tb.spice'),'spice_sha256':c['sha256']};rows.append(row);save();start=time.time()
 try:
  assert sha(c['spice'])==c['sha256']
  with (d/'run.log').open('w') as log:
   proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=proc.wait(timeout=600)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();code='timeout_600s'
  row['exitcode']=code;row['error_lines']=re.findall(r'^.*(?:Error:|aborted|stepping failed|Transient op).*$' ,(d/'run.log').read_text(),re.M)
  if code==0 and not row['error_lines']:row.update(measure(d,v))
 except Exception as e:row['error']=repr(e)
 row.update(status='finished',seconds=round(time.time()-start,2));save();print(json.dumps(row),flush=True)
save()
cases=[(key,c) for key in bases for c in corners[1:] if key!=(3.6,'ff',-20)]
assert len(cases)==56
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(job,cases))
changed=[f for f,h in manifest.items() if sha(f)!=h]
(out/'input_preservation.json').write_text(json.dumps({'unchanged':not changed,'changed':changed},indent=2))
save()

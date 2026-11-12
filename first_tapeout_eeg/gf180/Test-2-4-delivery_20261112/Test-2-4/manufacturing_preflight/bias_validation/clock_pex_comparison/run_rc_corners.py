from pathlib import Path
import ast,os,json,time,subprocess,signal,concurrent.futures,hashlib,threading,re
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');out=p/'rc_corner_sensitivity';out.mkdir(exist_ok=True)
# Import only the already used measurement function and imports, never rerun PVT.
tree=ast.parse((p/'run_fixed_rc_pvt.py').read_text(encoding='utf-8-sig'));selected=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)) or isinstance(n,ast.FunctionDef) and n.name=='measure'];exec(compile(ast.Module(body=selected,type_ignores=[]),'<measurement>','exec'))
m=json.loads((out/'approved_inputs.json').read_text());assert len(m['corners'])==4 and all(x['audit_pass'] for x in m['corners'])
old='/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe/flat/rc.spice';base=(p/'fixed_nominal_rc_pvt/3.6_ff_-20/tb.spice').read_text();assert old in base
nom=next(r for r in json.loads((p/'fixed_nominal_rc_pvt/results.json').read_text())['cases'] if (r['vdd'],r['corner'],r['temperature_C'])==(3.6,'ff',-20));rows=[{'rc_corner':'nominal','reused_from':'../fixed_nominal_rc_pvt/3.6_ff_-20',**nom}];lock=threading.Lock()
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
def save():
 with lock:(out/'results.json').write_text(json.dumps({'scope':'Official RC corner sensitivity at fixed3.6V/ff/-20C, same real-bias schematic OTA load. Not full-chip signoff.','cases':rows},indent=2))
def job(c):
 d=out/c['name'];d.mkdir(exist_ok=True);path=Path(c['spice']);assert hashlib.sha256(path.read_bytes()).hexdigest()==c['sha256'];s=base.replace(old,str(path));(d/'tb.spice').write_text(s)
 row={'rc_corner':c['name'],'vdd':3.6,'corner':'ff','temperature_C':-20,'status':'running','spice_sha256':c['sha256']};rows.append(row);save();start=time.time()
 try:
  with (d/'run.log').open('w') as log:
   proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:code=proc.wait(timeout=600)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();code='timeout_600s'
  row['exitcode']=code;row['error_lines']=re.findall(r'^.*(?:Error:|aborted|stepping failed|Transient op).*$' ,(d/'run.log').read_text(),re.M)
  if code==0 and not row['error_lines']:row.update(measure(d,3.6))
 except Exception as e:row['error']=repr(e)
 row.update(status='finished',seconds=round(time.time()-start,2));save();print(json.dumps(row),flush=True)
save()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(job,m['corners']))
for row in rows:
 if 'minimum_margin_ns' in row:row['delta_minimum_vs_nominal_ns']=row['minimum_margin_ns']-nom['minimum_margin_ns']
save();(out/'summary.json').write_text(json.dumps({'completed':len(rows),'all_positive':len(rows)==5 and all(r.get('positive_sequence_margins') for r in rows),'worst':min((r for r in rows if 'minimum_margin_ns' in r),key=lambda r:r['minimum_margin_ns'])},indent=2))

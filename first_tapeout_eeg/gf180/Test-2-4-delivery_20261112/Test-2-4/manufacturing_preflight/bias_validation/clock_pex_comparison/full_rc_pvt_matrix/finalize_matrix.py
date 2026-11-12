from pathlib import Path
import ast,json,hashlib,re,csv,time,os,subprocess,signal,concurrent.futures
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');out=p/'full_rc_pvt_matrix'
tree=ast.parse((p/'run_fixed_rc_pvt.py').read_text(encoding='utf-8-sig'));exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom)) or isinstance(n,ast.FunctionDef) and n.name=='measure'],type_ignores=[]),'<measure>','exec'))
while not (out/'input_preservation.json').exists():time.sleep(15)
assert json.loads((out/'input_preservation.json').read_text())['unchanged']
data=json.loads((out/'results.json').read_text());rows=data['cases'];assert len(rows)==75
for r in rows:
 d=Path(r['reused_from']) if 'reused_from' in r else out/f"{r['vdd']}_{r['corner']}_{r['temperature_C']}_{r['rc_corner']}"
 assert r['exitcode']==0
 log=(d/'run.log').read_text()
 if r.get('error_lines'):
  assert all(x=='Warning: Dynamic gmin stepping failed' for x in r['error_lines'])
  assert log.count('True gmin stepping completed')>=log.count('Dynamic gmin stepping failed')
  r['recovered_convergence_warnings']=r['error_lines']
  r['fatal_error_lines']=[];r.update(measure(d,r['vdd']))
 z=np.loadtxt(d/'out.csv');assert abs(z[-1,0]-500e-9)<1e-15 and np.isfinite(z).all()
 assert r['finite'] and r['positive_sequence_margins']
 r['verified_end_time_s']=float(z[-1,0])
data['all_75_positive']=True;(out/'audited_results.json').write_text(json.dumps(data,indent=2))
cols=['vdd','corner','temperature_C','rc_corner','minimum_margin_ns','seconds']
with (out/'minimum_margins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r[k] for k in cols} for r in rows)
(out/'minimum_margins.json').write_text(json.dumps([{k:r[k] for k in cols} for r in rows],indent=2))
worst=min(rows,key=lambda r:r['minimum_margin_ns']);(out/'final_summary.json').write_text(json.dumps({'total':75,'reused':19,'additional':56,'all_positive':True,'timeouts':0,'recovered_warning_cases':[r for r in rows if r.get('recovered_convergence_warnings')],'worst':worst,'original_inputs_unchanged':True},indent=2))
try:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 dev=[(v,c,t) for v in [3.0,3.3,3.6] for c,t in [('typical',27),('ss',85),('ff',-20),('sf',27),('fs',27)]]
 rc=['nominal','hrhc','hrlc','lrhc','lrlc'];a=np.array([[next(r['minimum_margin_ns'] for r in rows if (r['vdd'],r['corner'],r['temperature_C'],r['rc_corner'])==(*k,c)) for c in rc] for k in dev])
 fig,ax=plt.subplots(figsize=(10,11));im=ax.imshow(a,cmap='YlGn',vmin=0,aspect='auto')
 ax.set_xticks(range(5),rc);ax.set_yticks(range(15),[f'{v:.1f} V | {c.upper()} | {t} C' for v,c,t in dev])
 for i in range(15):
  for j in range(5):ax.text(j,i,f'{a[i,j]:.4f}',ha='center',va='center',color='black' if a[i,j]<.65 else 'white')
 ax.set_title('ADC internal clock: minimum sequence margin (ns)\n15 selected device / supply / temperature cases x 5 RC corners')
 fig.colorbar(im,ax=ax,label='Minimum margin (ns)')
 fig.text(.08,.035,'Internal clock PEX only; external loads use schematic approximations.\nProduct guardband undefined. Positive ordering is not full-chip signoff.',fontsize=10)
 fig.subplots_adjust(left=.25,bottom=.10,top=.91,right=.90);fig.savefig(out/'margin_heatmap.png',dpi=150);plt.close(fig)
except ImportError as e:(out/'plot_unavailable.txt').write_text(str(e))
# Two one-factor controls preserve circuit and stimulus.
d=Path(worst['reused_from']) if 'reused_from' in worst else out/f"{worst['vdd']}_{worst['corner']}_{worst['temperature_C']}_{worst['rc_corner']}"
base=(d/'tb.spice').read_text();controls=out/'convergence_controls';controls.mkdir(exist_ok=True)
env=os.environ.copy();env.update(PATH='/work/Test-2-4/functional/sim_bin:/foss/tools/bin:'+env['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
def run(spec):
 name,old,new=spec;dest=controls/name;dest.mkdir();assert base.count(old)==1;s=base.replace(old,new);(dest/'tb.spice').write_text(s);start=time.time();r={'name':name,'changed_from':old,'changed_to':new}
 with (dest/'run.log').open('w') as log:
  proc=subprocess.Popen(['ngspice','-b','tb.spice'],cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=proc.wait(timeout=600)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait();code='timeout_600s'
 r['exitcode']=code;r['seconds']=time.time()-start
 if code==0:
  r.update(measure(dest,worst['vdd']));r['delta_minimum_margin_ns']=r['minimum_margin_ns']-worst['minimum_margin_ns'];r['maximum_timing_delta_ns']=max(abs(r['timing_ns'][k]-worst['timing_ns'][k]) for k in r['timing_ns'])
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:ctrl=list(ex.map(run,[('half_maxstep','500n 0 0.05n','500n 0 0.025n'),('tight_reltol','reltol=1e-4','reltol=1e-5')]))
(controls/'results.json').write_text(json.dumps({'baseline':worst,'controls':ctrl,'diagnostic_timing_tolerance_ns':0.005,'all_within_5ps':all(r.get('maximum_timing_delta_ns',float('inf'))<=.005 for r in ctrl)},indent=2))
print('AUDIT_AND_CONTROLS_COMPLETE',flush=True)

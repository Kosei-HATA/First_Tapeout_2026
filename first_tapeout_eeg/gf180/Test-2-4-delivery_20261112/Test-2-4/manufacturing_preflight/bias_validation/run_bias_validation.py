from pathlib import Path
import importlib.util,os,re,json,subprocess,time,hashlib,math,numpy as np
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation'); f=Path('/work/Test-2-4/functional');p.mkdir(exist_ok=True)
os.environ.update(PATH=str(f/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
def module(n,path):
 s=importlib.util.spec_from_file_location(n,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=module('bias',f/'sim_work/gf180/tapeout/sim/bias/bias_check.py');a=module('clock',f/'sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py')
inputs=[Path(b.BIAS),Path('/work/gf180/tapeout/bias/eeg_bias.spice'),Path(a.CLK),Path(a.OTAS),Path(b.MOSLIN)]
(p/'input_manifest.json').write_text(json.dumps({'files':[{ 'path':str(x),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in inputs],'bias_copy_matches_project':inputs[0].read_bytes()==inputs[1].read_bytes()},indent=2))
N=['vbn','vbcm','bln','blp','vbn1','vbcm1','vnc1','vpc1','vbpc2','vbnc2','vcm'];rows=[]
cases=[(v,c,t) for v in [3.0,3.3,3.6] for c,t in [('typical',27),('ss',85),('ff',-20),('sf',27),('fs',27)]]
def run(d,deck,bias):
 d.mkdir(parents=True,exist_ok=True);(d/'tb.spice').write_text(deck);(d/'bias.spice').write_text(bias)
 r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=120);log=r.stdout+r.stderr;(d/'run.log').write_text(log)
 if r.returncode or re.search('stepping failed|Transient op|aborted|Error:',log):raise RuntimeError('simulation failed: '+str(d))
 return log
for v,c,t in cases:
 st=time.time();row={'vdd':v,'corner':c,'temperature_C':t,'startup':[]};d=p/'runs'/f'{v}_{c}_{t}'
 try:
  deck,bias=b.build(2,c,t);deck=deck.replace('VDD VDD 0 3.3',f'VDD VDD 0 {v}')
  for name,node in [('VIB1','IB1'),('VBP0','BP0'),('VBN0','BN0')]:deck=re.sub(rf'^{name} .*$',f'E{name} {node} 0 VDD 0 1',deck,flags=re.M)
  deck=re.sub(r'\.control[\s\S]*?\.endc','.control\nset noaskquit\nop\nprint '+' '.join(f'v({x})' for x in N)+' i(vmbln) i(vmblp) i(vmiq)\nquit\n.endc',deck)
  log=run(d/'op',deck,bias);op={k:float(val) for k,val in re.findall(r'^(\S+) = ([-0-9.e+]+)',log,re.M)};row['dc']=op
  for ramp in [1,10,100]:
   stop=ramp+100;tran=deck.replace(f'VDD VDD 0 {v}',f'VDD VDD 0 PWL(0 0 {ramp}u {v})')
   tran=re.sub(r'\.control[\s\S]*?\.endc','.control\nset noaskquit\ntran 50n '+str(stop)+'u 0 50n\nwrdata wave.csv '+' '.join(f'v({x})' for x in N)+' i(vmbln) i(vmblp) i(vmiq)\nquit\n.endc',tran)
   rd=d/f'ramp_{ramp}us';run(rd,tran,bias);x=np.loadtxt(rd/'wave.csv');names=[f'v({n})' for n in N]+['i(vmbln)','i(vmblp)','i(vmiq)'];last={n:float(x[-1,2*i+1]) for i,n in enumerate(names)}
   errs={n:abs(last[n]-op[n])/max(abs(op[n]),1e-9) for n in names};row['startup'].append({'ramp_us':ramp,'settle_after_ramp_us':100,'final':last,'max_relative_dc_error':max(errs.values()),'within_2percent_dc_screen':max(errs.values())<=.02,'finite':bool(np.isfinite(x).all())})
 except Exception as e:row['error']=repr(e)
 row['seconds']=round(time.time()-st,2);rows.append(row);(p/'bias_results.json').write_text(json.dumps(rows,indent=2));print(row['vdd'],c,row.get('error','done'),flush=True)
# Real bias circuit replaces four ideal ADC bias sources, original mirror loads retained.
orig=a.deck;clock=[]
for v,c,t in cases:
 a.VDD=v;a.HERE=str(p/'clock'/str(v));st=time.time();row={'vdd':v,'corner':c,'temperature_C':t}
 def actual(corner,temp):
  s=orig(corner,temp);bd,bt=b.build(2,corner,temp)
  block=bd[bd.index('VIB1 '):bd.index('.control')]
  for name,node in [('VIB1','IB1'),('VBP0','BP0'),('VBN0','BN0')]:block=re.sub(rf'^{name} .*$',f'E{name} {node} 0 VDD 0 1',block,flags=re.M)
  for name in ['VBN1','VNC1','VPC1','VBCM1','VCM']:s=re.sub(rf'^{name} .*\n','',s,flags=re.M)
  s=re.sub(r'\bCM\b','VCM',s)
  rc={'ss':'res_ss','ff':'res_ff'}.get(corner,'res_typical');cc={'ss':'ss','ff':'ff'}.get(corner,'typical')
  s=s.replace('.control',f'.lib {b.PDK}/sm141064.ngspice {rc}\n.param moscap_corner={b.MOSF[cc]}\n.include {b.MOSLIN}\n.include {b.BIAS}\n'+block+'\n.control')
  return s
 a.deck=actual
 try:
  _,_,val=a.run(c,t);m=[z for k,z in val.items() if k.startswith('margin')];row.update(measurements=val,minimum_margin_ns=min(m),finite=all(math.isfinite(z) for z in val.values()),positive_sequence_margins=all(math.isfinite(z) and z>0 for z in m))
 except Exception as e:row['error']=repr(e)
 row['seconds']=round(time.time()-st,2);clock.append(row);(p/'actual_bias_clock.json').write_text(json.dumps(clock,indent=2));print('clock',v,c,row.get('error','done'),flush=True)
(p/'finished.json').write_text(json.dumps({'bias_cases':len(rows),'clock_cases':len(clock)},indent=2))

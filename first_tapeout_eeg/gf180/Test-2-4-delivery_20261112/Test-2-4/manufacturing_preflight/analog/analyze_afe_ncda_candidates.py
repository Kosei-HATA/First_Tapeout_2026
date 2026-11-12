from pathlib import Path
import numpy as np,json,ast
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_ncda_candidates';c=json.loads((p/'afe_lvs_supply_3p6/connectivity.json').read_text());nodes=c['saved_nodes'];dev=c['selected_devices']
for file,name in [('finalize_afe_q_terminal_stress.py','exposure'),('analyze_afe_lvs_startup_controls.py','analyze')]:
 f=next(x for x in ast.parse((p/file).read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name);exec(compile(ast.Module(body=[f],type_ignores=[]),'<analysis>','exec'))
s={}
for tag,d in [('baseline',p/'afe_lvs_startup_controls/tmax_025ns'),('ncda_driver_2x',r/'ncda_driver_2x'),('output_tg_half',r/'output_tg_half')]:
 a=np.loadtxt(d/'wave.csv');z=analyze(a,0,1e-6);v={n:a[:,2*i+1] for i,n in enumerate(nodes)};i=int(np.argmin(v['ncda']));z['NCDA_min_context']={'time_s':float(a[i,0]),'volts':{n:float(v[n][i]) for n in ['ncda','xc.cdai','vclk','vdd','xa.opi','xa.oni','outp','outn']}};z['end_voltages']={n:float(v[n][-1]) for n in ['ncda','xc.cdai','vclk','xa.opi','xa.oni','outp','outn']};z['peak_driver_gate_pairs']=[x for x in z['exceeding_pairs'] if x['instance'].startswith('xc.xcda3')];s[tag]=z
(r/'summary.json').write_text(json.dumps({'scope':'Two diagnostic sizing/load candidates; same current-LVS TT27 3.6 V startup, 0-1 us, 0.25 ns, original unregularized Q; no layout changes','cases':s},indent=2));print(json.dumps({k:{x:y for x,y in v.items() if x in ['worst_gate','worst_vds','gate_pair_exceedance_count','NCDA_min_context']} for k,v in s.items()},indent=2))

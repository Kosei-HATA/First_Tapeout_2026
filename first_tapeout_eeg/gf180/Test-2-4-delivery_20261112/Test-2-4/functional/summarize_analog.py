from pathlib import Path
import re,json
p=Path('/work/Test-2-4/functional')
def read(n):
 f=p/n;return f.read_text(errors='replace') if f.exists() else ''
def dat(n):return json.loads(read(n)) if read(n) else []
r={'scope':'Schematic-level supplied benches; 3.3V nominal supply; corrected hsa model selection. Not full-chip PEX/noise/ENOB signoff.','execution_results':dat('analog_results.json')+dat('extended_analog_results.json')+dat('dac_results.json'),'quantizer_delay':{},'clock_checks':{},'dac_even':dat('dac1_even_result.json')}
for c in ['typical','ss','ff']:
 t=read('quantizer_delay_'+c+'.log');times=[float(x) for x in re.findall(r'\(ok\), ([0-9.]+) ns',t)]
 r['quantizer_delay'][c]={'correct_decisions':t.count('(ok)'),'wrong_decisions':t.count('WRONG'),'timing_measurements':len(times),'no_transition_cases':t.count('no change'),'max_measured_ns':max(times) if times else None,'expected_decisions':8,'observed_decisions_pass':t.count('(ok)')==8 and 'WRONG' not in t,'all_delays_measured_and_under_61ns':len(times)==8 and max(times)<61}
for label,file in [('ADC','adc_clock'),('AFE','afe_clock')]:
 t=read(file+'.log');v={}
 for line in t.splitlines():
  if line.startswith('| '):
   cells=[x.strip() for x in line.strip('|').split('|')]
   try:v[cells[0]]=[float(x) for x in cells[1:]]
   except ValueError:pass
 r['clock_checks'][label]={'exitcode':read(file+'.exitcode').strip(),'values':v}
minimums=[x for key,vals in r['clock_checks']['ADC']['values'].items() if key.startswith('margin') for x in vals]
r['adc_clock_minimum_margin_ns']=min(minimums) if minimums else None
r['primary_log_failures']={}
for x in r['execution_results']:
 t=read(x['log']);matches=re.findall(r'^.*(?:Traceback|operating point failed|WRONG|fatal error).*$' ,t,re.M)
 if matches:r['primary_log_failures'][x['log']]=matches
r['dac_even_output']=read('dac1_even_typical.log')
m=re.search(r'one cell ([+-]?[0-9.]+) fC, all cells ([+-]?[0-9.]+) fC',r['dac_even_output'])
if m:
 values={k:float(v) for k,v in zip(['one_cell_fC','all_cells_fC'],m.groups())}
 r['dac_even_criterion']={**values,'absolute_limit_fC':0.016,'pass':r['dac_even'].get('exitcode')==0 and r['dac_even'].get('complete_output') is True and all(abs(v)<=0.016 for v in values.values()),'scope':'typical 27C, voff 0, supplied tolerance A; values rounded as printed by bench'}
(p/'analog_summary.json').write_text(json.dumps(r,indent=2));print(json.dumps({a:b for a,b in r.items() if a not in ['clock_checks','execution_results']},indent=2))

from pathlib import Path
import re,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');root=p/'magic_candidate/tests3'
def parse(s):
 out={'C':[],'R':[],'ports':[]}
 for line in s.splitlines():
  t=line.split()
  if not t:continue
  if t[0]=='.subckt':out['ports']+=t[2:]
  if t[0][0] in ['C','R']:
   m=re.fullmatch(r'([0-9.eE+-]+)([fpnum]?)',t[3]);v=float(m[1])*{'':1,'f':1e-15,'p':1e-12,'n':1e-9,'u':1e-6,'m':1e-3}[m[2]];out[t[0][0]].append((t[1],t[2],v))
 return out
def check(cap,rc,wire=False):
 a=parse(cap);b=parse(rc)
 def sums(x):return [sum(v for n,m,v in x['C'] if any(y.startswith('w_') or y=='VSUBS' for y in [n,m])),sum(v for n,m,v in x['C'] if not any(y.startswith('w_') or y=='VSUBS' for y in [n,m]))]
 ac=sums(a);bc=sums(b);r={'ground_before_fF':ac[0]*1e15,'ground_after_fF':bc[0]*1e15,'coupling_before_fF':ac[1]*1e15,'coupling_after_fF':bc[1]*1e15,'cap_conserved':all(abs(v-w)<1e-18 for v,w in zip(ac,bc)),'R_count':len(b['R'])}
 if wire:
  pairs={frozenset([n,m]):v for n,m,v in b['R']};r['wire_R_valid']=all(pair in pairs and abs(pairs[pair]/8.82-1)<.001 for pair in [frozenset(['A','B']),frozenset(['C','D'])]);r['all_four_ports']=all(x in b['ports'] for x in ['A','B','C','D'])
 r['pass']=r['cap_conserved'] and r['R_count']>0 and r.get('wire_R_valid',True) and r.get('all_four_ports',True);return r
report={'scope':'8.3.697 non-Tcl extractor plus installed 8.3.664 converter; limited mixed-version validation, not full-flow qualification','positive':{},'negative':{}}
for n in ['wire','coupled_wires','mim_only','adc_flat','adc_hierarchy']:
 d=root/n;report['positive'][n]=check((d/'cap.spice').read_text(),(d/'rc.spice').read_text(),n=='coupled_wires')
d=root/'coupled_wires';c=(d/'cap.spice').read_text();s=(d/'rc.spice').read_text();neg=root/'negative';neg.mkdir(exist_ok=True)
cases={'duplicate_coupling':s.replace('.ends','C999 B D 5.9027f\n.ends'),'lost_resistor':re.sub(r'^R0.*\n','',s,flags=re.M),'wrong_resistance':s.replace('8.8205','9.70255'),'lost_port':s.replace('.subckt coupled_wires A B C D','.subckt coupled_wires A B C')}
for name,content in cases.items():
 (neg/(name+'.spice')).write_text(content);report['negative'][name]=check(c,content,True)
report['old_version_coupled_wires']=check((p/'coupled_wires/cap_ports.spice').read_text(),(p/'coupled_wires/rc_ports.spice').read_text(),True)
report['all_negative_controls_detected']=all(not x['pass'] for x in report['negative'].values());report['uncovered']=['Actual killnode/reconnected coupling case not exercised','Complete Tcl 8.3.697 conversion not tested','Spatial RC accuracy/contact mesh convergence','ADC coupling changed about 0.1325 fF across versions and needs independent validation']
(root/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

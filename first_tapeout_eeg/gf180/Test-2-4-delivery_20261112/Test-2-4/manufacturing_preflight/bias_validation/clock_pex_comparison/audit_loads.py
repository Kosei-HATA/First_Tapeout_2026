from pathlib import Path
import json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');ext=p.parents[1]/'extraction/core_pex_probe/clock_probe'
src=Path('/work/Test-2-4/functional/sim_work/gf180/tapeout/adc/eeg_adc_otas.spice');sub={};cur=None
for l in src.read_text().splitlines():
 t=l.split()
 if not t or t[0].startswith('*'):continue
 if t[0].lower()=='.subckt':cur=t[1].upper();sub[cur]={'pins':[x.upper() for x in t[2:]],'lines':[]}
 elif t[0].lower()=='.ends':cur=None
 elif cur:sub[cur]['lines'].append(t)
leaf={}
def walk(model,path,nodes):
 s=sub[model];mapping=dict(zip(s['pins'],nodes))
 def net(n):return mapping.get(n.upper(),path+'.'+n.upper())
 for t in s['lines']:
  if not t[0].upper().startswith('X'):continue
  end=next((i for i,x in enumerate(t) if '=' in x),len(t));m=t[end-1];name=path+'.'+t[0][1:].upper()
  if m.upper() in sub:walk(m.upper(),name,[net(n) for n in t[1:end-1]])
  elif m in ['nfet_03v3','pfet_03v3']:
   leaf[name]={'model':m,**dict(zip('DGSB',[net(n) for n in t[1:5]])),'parameters':dict(x.lower().split('=') for x in t[end:])}
pins=sub['GF180_INSIDE_CASCODE_OTA']['pins'];nodes=['ADC.I1P','ADC.I1N','ADC.O1P','ADC.O1N','VCM','VBN1','VNC1','VPC1','VBCM1']+['ADC.'+n for n in ['CIA','NCIA','CIB','NCIB','CDA','NCDA','CDB','NCDB']]+['AVDD','AVSS'];walk('GF180_INSIDE_CASCODE_OTA','ADC.OTA1',nodes)
ref=json.loads((ext/'external_load_terminals.json').read_text());rows=[]
for name,r in ref['devices'].items():
 s=leaf[name];same=all(r[k]==s[k] for k in ['D','G','S','B','model']);w=float(s['parameters']['w'].rstrip('u'))*float(s['parameters'].get('m','1'));l=float(s['parameters']['l'].rstrip('u'));same=same and abs(w-r['layout_L_W_um']['W'])<1e-8 and abs(l-r['layout_L_W_um']['L'])<1e-8
 rows.append({'name':name,'same_terminals_model_W_L':same,'schematic':s,'layout_W_L_um':r['layout_L_W_um']})
assert len(rows)==24 and all(r['same_terminals_model_W_L'] for r in rows)
(p/'load_audit.json').write_text(json.dumps({'pass':True,'count':24,'devices':rows,'binding_notes':['ADC.I1P/I1N both bound to VCM in this nominal common-mode benchmark. This is not complete closed-loop ADC trajectory.','Internal OTA nodes remain dynamic with transistor models and real bias.','External TG AD/AS/PD/PS/NRD/NRS remain source schematic assumptions and are not taken from extracted load devices.']},indent=2));print('24 load terminal/model/width/length matches')


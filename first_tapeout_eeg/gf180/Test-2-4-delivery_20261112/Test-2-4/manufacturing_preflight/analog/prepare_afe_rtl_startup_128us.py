from pathlib import Path
import csv,json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_rtl_startup';rows=list(csv.DictReader((r/'rtl/controls.csv').open()));
for row in rows:
 for k,v in row.items():row[k]=float(v) if k=='time_ns' else int(v)
assert all(x['cpf']==8 and x['ibias']==2 and x['bp']==1 and x['bn']==1 and x['ofm']==0 and x['ofs']==0 and x['ofen']==0 and x['chop_en']==1 for x in rows)
release=next(x['time_ns']*1e-9 for x in rows if x['afe_rst']==0);step=release+7.8125e-6
sigs={'CHOP':('chop',None),'CHOP_OUT':('chop_out',None),'BLANK':('blank',None),'AFE_RST':('afe_rst',None),'CHOP_EN':('chop_en',None),'OFS':('ofs',None)}
for prefix,col,width in [('CPF','cpf',4),('IB','ibias',2),('BP','bp',2),('BN','bn',2),('OFM','ofm',10),('OFEN','ofen',4)]:
 for bit in range(width):sigs[prefix+str(bit)]=(col,bit)
pwl='* RTL-derived logical levels with assumed 0.5 ns analog slew and 1 us DVDD ramp\n'
for name,(col,bit) in sigs.items():
 value=lambda row:row[col] if bit is None else (row[col]>>bit)&1
 prev=value(rows[0]);points=[(0.,0.),(1e-6,3.3*prev)]
 for row in rows[1:]:
  nxt=value(row)
  if nxt!=prev:
   t=row['time_ns']*1e-9;assert t>1e-6;points.extend([(t,3.3*prev),(t+.5e-9,3.3*nxt)]);prev=nxt
 points.append((128e-6,3.3*prev));pwl+=f'VRTL_{name} RTL_{name} 0 PWL(\n'+'\n'.join(f'+ {t:.15g} {v:.15g}' for t,v in points)+')\n'
(r/'controls.inc').write_text(pwl)
def merge(text):
 out=[]
 for line in text.splitlines():
  if line.startswith('+'):out[-1]+=' '+line[1:]
  else:out.append(line)
 return out
source=p/'afe_lvs_supply_3p3/tb.spice';lines=merge(source.read_text());afe=merge((p/'sim_work/gf180/tapeout/afe/eeg_afe.spice').read_text());bias=merge((p/'moscap_charge_equivalent/bias_q_diagnostic.spice').read_text());pins=lambda ls,name:next(x.split()[2:] for x in ls if x.lower().startswith('.subckt '+name+' '));ap=pins(afe,'eeg_afe');bp=pins(bias,'eeg_bias');mapping={};out=[]
for line in lines:
 tok=line.split();name=tok[0].upper() if tok else ''
 if name in ['VCH','ECO','VBL','VRS']:continue
 if name=='VDD':line='VDD VDD 0 PWL(0 0 1u 3.3)'
 if name=='VRP':line='VRP VRP 0 PWL(0 0 1u 1.9)'
 if name=='VRN':line='VRN VRN 0 PWL(0 0 1u 1.4)'
 if name=='VS':line=f'VS SRC 0 PWL(0 0 {step:.15g} 0 {step+1e-9:.15g} 100u)'
 if name=='XA':
  nets=tok[1:-1];assert len(nets)==len(ap)
  for i,pin in enumerate(ap):
   if pin in sigs:nets[i]='RTL_'+pin
  mapping['XA']=dict(zip(ap,nets));line='XA '+' '.join(nets)+' eeg_afe'
 if name=='XB':
  nets=tok[1:-1];assert len(nets)==len(bp)
  for i,pin in enumerate(bp):
   if pin in sigs:nets[i]='RTL_'+pin
  mapping['XB']=dict(zip(bp,nets));line='XB '+' '.join(nets)+' eeg_bias'
 if name=='XC':line='XC RTL_CHOP RTL_CHOP_OUT RTL_BLANK RTL_CHOP_EN RTL_AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RST VCLK 0 eeg_afe_clk'
 if line.startswith('.control'):out.append(f'.include {r}/controls.inc')
 if line.startswith('tran '):line='tran 1n 32u 0 1n'
 if line.startswith('wrdata '):
  old=json.loads((p/'afe_lvs_supply_3p3/connectivity.json').read_text())['saved_nodes'];nodes=sorted(set(old+['vcm','vbn','vbcm','blp','bln','src','rtl_afe_rst','rtl_chop','rtl_chop_out','rtl_blank']));line='wrdata wave.csv '+' '.join(f'v({n})' for n in nodes)
 out.append(line)
(r/'pilot').mkdir(exist_ok=True);(r/'pilot/tb.spice').write_text('\n'.join(out)+'\n');(r/'pilot/.spiceinit').write_bytes((p/'afe_lvs_supply_3p3/.spiceinit').read_bytes())
meta={'assumptions':{'AVDD_DVDD_V':3.3,'ramp_s':1e-6,'references_V':[1.9,1.4],'MCLK_start_s':2e-6,'RESET_N_release_s':3e-6,'SPI_Hz':2e6,'CONTROL_write':'0x20 0x02 0x64; only AFE_RST bit4 cleared from reset0x74','analog_logic_slew_s':.5e-9,'AFE_reset_observed_release_s':release,'input_differential_step_s':step,'input_differential_step_V':100e-6,'electrode_common_mode':'Internally generated VCM; no independent external electrode model','VIT_V':1},'mapping':mapping,'saved_nodes':nodes,'connected_RTL':['CHOP','CHOP_OUT','CHOP_BLANK','AFE_RST','CHOP_EN','CPF_TRIM','AFE_IBIAS','BTRIM_P','BTRIM_N','OFM','OFS','OFEN'],'unused_RTL':['ADC_RST_N observed only','TH_CAPTURE','DAC_LOAD','DWA_EN','CMP_STROBE','DAC_CLK','CHOP1','TEST_CFG','RAW outputs','MISO and FIFO outputs'],'fixed_or_omitted':['CODE=16 for RTL input; no ADC/DWA analog loop','No pad/board or finite substrate/package model','No system decimation/ENOB test'],'sources':[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(Path('/work/gf180/tapeout/rtl').glob('*.sv'))]}
(r/'mapping_and_assumptions.json').write_text(json.dumps(meta,indent=2));criteria={'purpose':'Engineering diagnostic convergence, not specification or ENOB acceptance','minimum_after_last_control_or_signal_step_s':8*7.8125e-6,'two_successive_windows_cycles_each':4,'per_cycle_mean_change_V':{'OUTP_minus_OUTN':1e-6,'VCM':1e-4},'cycle_rms_change':'<= max(1 uV,0.1% of prior cycle RMS) for differential output','require_all':'Every adjacent cycle comparison across both four-cycle windows; no clipping/nonfinite or omitted outlier','steady_gain':'Not measured from initial step ratio; requires settled matched positive/negative input or sinusoidal transfer later','pilot_is_steady_test':False}
(r/'steady_criteria.json').write_text(json.dumps(criteria,indent=2));print(json.dumps({'release_s':release,'step_s':step,'cpf_mapping':{k:v for k,v in mapping['XA'].items() if k.startswith('CPF')},'saved_nodes':len(nodes)},indent=2))

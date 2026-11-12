from pathlib import Path
import json,numpy as np
r=Path('/work/Test-2-4/manufacturing_preflight/analog/afe_reset_isolation');s=json.loads((r/'summary.json').read_text());names=['outp','outn','vbn','vbcm','vcm','blp','bln','vdd','rst','afe_rst','chop','cia','cda','src','vbn1','vbcm1','vnc1','vpc1','vbpc2','vbnc2','xb.gp','xb.xcvbcm1_1.c_moscap_int1','xb.xcvbcm1_1.c_moscap_int2']
for z in s['results']:
 a=np.loadtxt(r/z['case']/'wave.csv');cols={n:a[:,2*i+1] for i,n in enumerate(names)}
 nodes=['vbn','vbcm','vbn1','vbcm1','vnc1','vpc1','vbpc2','vbnc2'];z['nmoscap_terminal_voltage_range_V']=[min(float(cols[n].min()) for n in nodes),max(float(cols[n].max()) for n in nodes)];cap=28.6e-6*44e-6*(.002003+.00198*np.tanh(6.25*cols['vbcm1']-3.9375));z['target_moscap_C_range_F']=[float(cap.min()),float(cap.max())]
 z['target_internal_voltage_error_max_V']=float(np.max(np.abs(cols['xb.xcvbcm1_1.c_moscap_int1']-cols['vbcm1'])));z['target_internal_voltage_error_last_V']=float(cols['xb.xcvbcm1_1.c_moscap_int1'][-1]-cols['vbcm1'][-1]);z['target_internal_ground_max_V']=float(np.max(np.abs(cols['xb.xcvbcm1_1.c_moscap_int2'])))
 print(z['case'],z['nmoscap_terminal_voltage_range_V'],z['target_moscap_C_range_F'],z['target_internal_voltage_error_max_V'])
a=np.loadtxt(r/'held/wave.csv');b=np.loadtxt(r/'delayed_10us/wave.csv');s['held_vs_delayed_saved_waves_exactly_equal']=bool(np.array_equal(a,b));s['model_limitations_source']='https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_6.html';s['model_limitations_note']='Official model limitations/restrictions section says To be added. Voltage nominality is not proof of characterized model validity.'
s['conclusion']='Reset release is not the sole trigger. Held/delayed reset fails at the next BLANK transition; slower reset reaches the next CHOP transition. Finite saved terminals and smooth positive C(V) do not identify the internal solver root cause.'
(r/'summary.json').write_text(json.dumps(s,indent=2))

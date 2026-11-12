from pathlib import Path
import json,numpy as np,importlib.util
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');f=Path('/work/Test-2-4/functional/sim_work/gf180/tapeout/sim/adc_loop/aclk_check.py');s=importlib.util.spec_from_file_location('a',f);a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
assert json.loads((p/'sparse160_status.json').read_text())['exitcode']==0
x=np.loadtxt(p/'sparse160/out.csv');y=np.loadtxt(p/'rc_klu/out.csv');grid=np.linspace(0,160e-9,32001);err={}
for i,n in enumerate(a.NAMES[:-1]):
 diff=np.interp(grid,x[:,0],x[:,2*i+1])-np.interp(grid,y[:,0],y[:,2*i+1]);err[n]={'max_abs_V':float(abs(diff).max()),'rms_V':float(np.sqrt(np.mean(diff**2))),'stable_max_abs_V':float(abs(diff[(grid<90e-9)|(grid>120e-9)]).max())}
def measure(z):
 t=z[:,0];v={n:z[:,2*i+1] for i,n in enumerate(a.NAMES)};t0=a.E1-2e-9;co,no=v['cia'],v['ncia'];cn,nn=v['cib'],v['ncib'];do,dno=v['cda'],v['ncda'];dn,dnn=v['cdb'],v['ncdb']
 return {'dead':(a.tg_on_start(t,cn,nn,t0)-a.tg_full_off(t,co,no,t0))*1e9,'overlap':(a.cross(t,do,1.65,False,t0)-a.cross(t,dn,1.65,True,t0))*1e9,'margin1':(a.tg_off_start(t,co,no,t0)-a.tg_full_on(t,dn,dnn,t0))*1e9,'margin2':(a.tg_off_start(t,do,dno,t0)-a.tg_full_on(t,cn,nn,t0))*1e9,'delay':(a.cross(t,dn,1.65,True,t0)-a.E1)*1e9}
u,w=measure(x),measure(y);delta={k:u[k]-w[k] for k in u};mx=max(v['max_abs_V'] for v in err.values());stable=max(v['stable_max_abs_V'] for v in err.values());r={'interval_ns':[0,160],'interpolation_grid_ps':5,'sparse_tstop_ns':160,'klu_tstop_ns':500,'same_RC_circuit':True,'sparse_A_to_B_timing_ns':u,'klu_A_to_B_timing_ns':w,'delta_sparse_minus_klu_ns':delta,'voltage_error':err,'diagnostic_tolerances':{'timing_ns':.05,'max_voltage_V':.05,'stable_voltage_V':.001},'diagnostic_pass':max(abs(v) for v in delta.values())<=.05 and mx<=.05 and stable<=.001,'note':'Engineering solver-agreement screen, not silicon tolerance. Adaptive time points and different stop times may alter interpolation; comparison covers first transition only, not B->A at300ns.'}
(p/'solver_comparison.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

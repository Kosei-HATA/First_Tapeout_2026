from pathlib import Path
import json,numpy as np
r=Path('/work/Test-2-4/manufacturing_preflight/analog/moscap_charge_equivalent');rows=[]
logcosh=lambda x:np.logaddexp(x,-x)-np.log(2.)
for name,c1,c2,c3,c4 in [('nmos',.002003,.00198,6.25,-3.9375),('pmos',.001998,.00196,-6.25,-4.9375)]:
 for L in [14.3e-6,28.6e-6,57.2e-6]:
  for W in [22e-6,44e-6]:
   for m in [1,2,4,8,16]:
    for corner in [.9,1,1.1]:
     v=np.linspace(-3.3,3.3,1321);scale=L*W*m*corner
     Q=lambda v:scale*(c1*v+c2/c3*(logcosh(c3*v+c4)-logcosh(c4)))
     C=scale*(c1+c2*np.tanh(c3*v+c4));h=1e-5;D=(Q(v-2*h)-8*Q(v-h)+8*Q(v+h)-Q(v+2*h))/(12*h)
     rows.append({'kind':name,'L_m':L,'W_m':W,'m':m,'corner':corner,'max_relative_derivative_error':float(np.max(np.abs(D-C)/C)),'Q_at_zero_C':float(Q(0))})
a=np.loadtxt(r/'unit_equivalence/wave.csv');t=a[:,0];charges={}
for kind,c,q in [('nmos',3,5),('pmos',7,9)]:
 integral=lambda y:np.r_[0,np.cumsum((y[1:]+y[:-1])*.5*np.diff(t))]
 qc=integral(a[:,c]);qq=integral(a[:,q]);charges[kind]={'max_cumulative_charge_difference_C':float(np.max(np.abs(qc-qq))),'max_reference_charge_C':float(np.max(np.abs(qc))),'relative_to_max_reference_charge':float(np.max(np.abs(qc-qq))/np.max(np.abs(qc)))}
 np.savetxt(r/(kind+'_cumulative_charge.csv'),np.c_[t,qc,qq,qq-qc],header='time_s C_form_charge_C Q_form_charge_C difference_C')
s={'scope':'Independent mathematical derivative check, not new SPICE runs or foundry qualification','voltage_interval_V':[-3.3,3.3],'voltage_points':1321,'cases':rows,'max_relative_derivative_error':max(x['max_relative_derivative_error'] for x in rows),'cumulative_charge':charges,'definition_evidence':'Pinned ngspice inpcom.c capacitance formulation: internal measured capacitor current times C(V). This implements differential C, not Q/V. Q-form uses the charge formulation branch.','Q_units':'Coulombs: geometry[m^2] times coefficient[F/m^2] times voltage[V]. Q(0)=0 by subtracting logcosh(c4).','stable_evaluation':'Independent audit uses logaddexp. SPICE ln(cosh()) argument magnitude <=25.5625 over the tested interval, far below overflow. This does not authorize extrapolation to arbitrary voltages.'}
(r/'mathematical_equivalence.json').write_text(json.dumps(s,indent=2));print(s['max_relative_derivative_error'],charges)

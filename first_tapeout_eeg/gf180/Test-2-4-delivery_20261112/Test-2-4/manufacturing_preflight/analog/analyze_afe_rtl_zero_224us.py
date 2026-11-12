from pathlib import Path
import json,numpy as np,sys
p=Path('/work/Test-2-4/manufacturing_preflight/analog');r=p/'afe_rtl_zero_224us';mode=sys.argv[1] if len(sys.argv)>1 else 'pilot';a=np.loadtxt(r/mode/'wave.csv');meta=json.loads((r/'mapping_and_assumptions.json').read_text());nodes=meta['saved_nodes'];t=a[:,0];v={n:a[:,2*i+1] for i,n in enumerate(nodes)};vd=v['outp']-v['outn'];T=7.8125e-6;anchor=3.068117e-6
mean=lambda tt,yy:float(np.trapezoid(yy,tt)/(tt[-1]-tt[0]))
def window(lo,hi):
 mask=(t>lo)&(t<hi);tt=np.r_[lo,t[mask],hi];out={}
 for n,y in [('differential',vd),('vcm',v['vcm'])]:
  yy=np.r_[np.interp(lo,t,y),y[mask],np.interp(hi,t,y)];out[n+'_mean_V']=mean(tt,yy);out[n+'_rms_V']=np.sqrt(mean(tt,yy*yy))
 return {'start_s':lo,'end_s':hi,**out}
cycles=[window(anchor+k*T,anchor+(k+1)*T) for k in range(100) if anchor+(k+1)*T<=t[-1]+1e-15];s={'mode':mode,'last_time_s':float(t[-1]),'finite':bool(np.isfinite(a).all()),'cycles':cycles,'voltage_ranges_V':{n:{'min':float(y.min()),'max':float(y.max()),'last':float(y[-1])} for n,y in v.items()},'steady_criteria_met':False,'steady_evaluation_available':False}
criteria=json.loads((r/'steady_criteria.json').read_text());start=criteria['earliest_phase_aligned_evaluation_start_s'];end=criteria['earliest_phase_aligned_evaluation_end_s']
if t[-1]>=end:
 win=[window(start+k*T,start+(k+1)*T) for k in range(8)];checks=[]
 for prev,cur in zip(win[:-1],win[1:]):
  dm=abs(cur['differential_mean_V']-prev['differential_mean_V']);cm=abs(cur['vcm_mean_V']-prev['vcm_mean_V']);dr=abs(cur['differential_rms_V']-prev['differential_rms_V']);limit=max(1e-6,.001*abs(prev['differential_rms_V']));checks.append({'differential_mean_change_V':dm,'vcm_mean_change_V':cm,'rms_change_V':dr,'rms_limit_V':limit,'pass':bool(dm<=1e-6 and cm<=1e-4 and dr<=limit)})
 s.update(steady_evaluation_available=True,evaluation_cycles=win,adjacent_checks=checks,steady_criteria_met=bool(s['finite'] and all(x['pass'] for x in checks)))
c=json.loads((p/'afe_lvs_supply_3p3/connectivity.json').read_text());v['0']=np.zeros(len(t));pairs=[]
for d in c['selected_devices']:
 for pair,n1,n2 in [('vgs','g','s'),('vgd','g','d'),('vgb','g','b'),('vds','d','s')]:
  y=v[d['terminals'][n1]]-v[d['terminals'][n2]];i=int(np.argmax(abs(y)));pairs.append({'instance':d['instance'],'pair':pair,'max_abs_V':float(abs(y[i])),'peak_time_s':float(t[i])})
s['worst_gate_pair']=max((x for x in pairs if x['pair']!='vds'),key=lambda x:x['max_abs_V']);s['worst_vds']=max((x for x in pairs if x['pair']=='vds'),key=lambda x:x['max_abs_V']);s['scope']='Engineering periodicity test only. AFE-only, assumed external sequence, ideal common substrate, Q diagnostic, no full ADC loop or ENOB validation.'
(r/(mode+'_analysis.json')).write_text(json.dumps(s,indent=2));print(json.dumps({k:v for k,v in s.items() if k not in ['voltage_ranges_V','cycles']},indent=2))

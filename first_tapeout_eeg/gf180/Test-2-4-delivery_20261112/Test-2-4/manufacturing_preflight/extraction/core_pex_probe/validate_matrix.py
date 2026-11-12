from pathlib import Path
import json,numpy as np,re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis');d=p/'magic_candidate/tests3';r={}
def matrix(path):
 s=path.read_text();M=np.zeros((2,2));mapping={'A':0,'B':0,'C':1,'D':1}
 for line in s.splitlines():
  t=line.split()
  if not t or not t[0].startswith('C'):continue
  v=float(t[3][:-1]) * {'f':1,'p':1000}[t[3][-1]];a=mapping.get(t[1]);b=mapping.get(t[2])
  if a is not None:M[a,a]+=v
  if b is not None:M[b,b]+=v
  if a is not None and b is not None:M[a,b]-=v;M[b,a]-=v
 return M
base=matrix(d/'coupled_wires/cap.spice')
for name,path in [('candidate',d/'coupled_wires/rc.spice'),('old',p/'coupled_wires/rc_ports.spice'),('duplicate_negative',d/'negative/duplicate_coupling.spice')]:
 m=matrix(path);r[name]={'matrix_fF':m.tolist(),'max_error_fF':float(np.max(abs(m-base))),'common_mode_energy_fJ':float(.5*np.ones(2)@m@np.ones(2)),'differential_energy_fJ':float(.5*np.array([1,-1])@m@np.array([1,-1])),'positive_semidefinite':bool(np.linalg.eigvalsh(m).min()>=0),'matches_reference':bool(np.max(abs(m-base))<1e-6)}
r['reference_matrix_fF']=base.tolist();r['meaning']='Lumped low-frequency matrix after collapsing each independently verified wire resistor path. Energy=0.5 V^T C V, units fJ for volts/fF. Does not establish distributed high-frequency coupling position.'
(d/'cap_matrix_check.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))

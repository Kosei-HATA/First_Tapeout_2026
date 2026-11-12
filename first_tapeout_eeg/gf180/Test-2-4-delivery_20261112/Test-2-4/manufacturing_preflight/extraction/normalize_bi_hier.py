from pathlib import Path
import re,json,hashlib,collections
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep/gf180mcu_fd_io__bi_24t')
def val(s):
 m=re.fullmatch(r'([+\-0-9.eE]+)([a-zA-Z]*)',s);return float(m[1])*{'':1,'f':1e-15,'p':1e-12,'n':1e-9,'u':1e-6,'m':1e-3}[m[2].lower()]
raw=[]
for f in p.glob('*.ext'):
 lines=f.read_text().splitlines();scale=float(next(x for x in lines if x.startswith('scale ')).split()[3])*1e-8
 for line in lines:
  if not line.startswith('device '):continue
  t=line.split();params=dict(re.findall(r'\b([alp w]+)=([0-9.]+)',line))
  if t[1] in ['ndiode','pdiode']:
   a=float(re.search(r'\ba=([0-9.]+)',line)[1])*scale**2;per=float(re.search(r'\bp=([0-9.]+)',line)[1])*scale
   raw.append({'model':t[2],'area_m2':a,'perimeter_m':per,'ext_file':f.name,'linear_scale_m':scale,'raw_line':line})
changes=[];out=[]
for line in (p/'actual_hier.spice').read_text().splitlines():
 if line.startswith('D'):
  t=line.split();pars=dict(x.split('=',1) for x in t[4:] if '=' in x);area=val(pars['area']);pj=val(pars['pj']);matches=[x for x in raw if x['model']==t[3] and abs(x['area_m2']/area-1)<1e-9]
  assert matches
  expected={round(x['perimeter_m'],14) for x in matches};assert len(expected)==1
  target=expected.pop();assert abs(pj/target-1)<1e-8
  new=re.sub(r'\bpj=\S+',f'pj={target:.12e}',line);changes.append({'device':t[0],'old_pj':pars['pj'],'new_pj_m':target,'factor':1,'derived_from':matches[0]['ext_file']});line=new
 out.append(line)
(p/'actual_hier_normalized.spice').write_text('\n'.join(out)+'\n')

(p/'hier_normalization.json').write_text(json.dumps({'raw':raw,'changes':changes},indent=2))


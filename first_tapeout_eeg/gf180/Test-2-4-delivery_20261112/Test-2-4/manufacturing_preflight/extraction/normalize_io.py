from pathlib import Path
import re,json,hashlib,collections
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_asig_magic')
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
for line in (p/'actual.spice').read_text().splitlines():
 if line.startswith('D'):
  t=line.split();pars=dict(x.split('=',1) for x in t[4:] if '=' in x);area=val(pars['area']);pj=val(pars['pj']);matches=[x for x in raw if x['model']==t[3] and abs(x['area_m2']/area-1)<1e-9]
  assert matches
  expected={round(x['perimeter_m'],14) for x in matches};assert len(expected)==1
  target=expected.pop();assert abs(pj*1e6/target-1)<1e-8
  new=re.sub(r'\bpj=\S+',f'pj={target:.12e}',line);changes.append({'device':t[0],'old_pj':pars['pj'],'new_pj_m':target,'factor':1e6,'derived_from':matches[0]['ext_file']});line=new
 out.append(line)
(p/'actual_normalized.spice').write_text('\n'.join(out)+'\n')
setup=Path('/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl').read_text()
assert setup.count('delete par1 pj')==2
setup=setup.replace('delete par1 pj','delete par1')
setup=setup.replace('tolerance {area 0.02}','tolerance {area 0.02} {pj 0.02}')
setup=setup.replace('merge {area add_critical}','merge {area add_critical}\n\tproperty "-circuit1 $dev" merge {pj add_critical}',1)
# The second device block is circuit2.
pos=setup.find('merge {area add_critical}',setup.find('merge {area add_critical}')+1)
setup=setup[:pos]+setup[pos:].replace('merge {area add_critical}','merge {area add_critical}\n\tproperty "-circuit2 $dev" merge {pj add_critical}',1)
(p/'strict_setup.tcl').write_text(setup)
ref=(p/'reference.spice').read_text();(p/'reference_bad_width.spice').write_text(ref.replace('c_width=15e-6','c_width=16.5e-6'))
(p/'reference_bad_pj.spice').write_text(ref.replace('pj=106e-6','pj=116.6e-6'))
r={'scope':'Local output normalization, not original GDS or PDK change','ext_length_unit':'scale lscale is centimicrons; SI multiplier lscale*1e-8','normalization_basis':'Physical perimeter derived from raw .ext p values and per-file scale. Each emitted diode area independently matched raw .ext area before accepting mapping.','raw_diodes':raw,'changes':changes,'strict_setup':'Copied official setup, preserve PJ instead of deleting it, add 2% PJ tolerance and additive parallel perimeter. No parameter exclusions added.','official_setup_sha256':hashlib.sha256(Path('/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl').read_bytes()).hexdigest()}
(p/'normalization_evidence.json').write_text(json.dumps(r,indent=2));print('normalized',len(changes),'diodes')

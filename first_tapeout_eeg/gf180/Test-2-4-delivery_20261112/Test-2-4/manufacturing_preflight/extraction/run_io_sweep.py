from pathlib import Path
import subprocess,json,time,re,shutil,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/io_sweep');parent=p.parent;status={};setup=parent/'io_asig_magic/strict_setup.tcl'
def save():(p/'jobs.json').write_text(json.dumps(status,indent=2))
def run(cmd,cwd,log):
 t=time.time()
 with (cwd/log).open('w') as f:r=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
 return {'returncode':r.returncode,'seconds':round(time.time()-t,2)}
def value(s):
 m=re.fullmatch(r'([+\-0-9.eE]+)([a-zA-Z]*)',s);return float(m[1])*{'':1,'f':1e-15,'p':1e-12,'n':1e-9,'u':1e-6,'m':1e-3}[m[2].lower()]
for row in json.loads((p/'inventory.json').read_text()):
 name=row['cell'];out=p/name
 if not (out/'actual.gds').exists():continue
 status[name]={'state':'running','input_sha256':hashlib.sha256((out/'actual.gds').read_bytes()).hexdigest()};save()
 tcl=f'''drc off
crashbackups stop
gds read actual.gds
load {name}
select top cell
extract do local
extract all
ext2spice lvs
ext2spice hierarchy off
ext2spice global off
ext2spice scale off
ext2spice subcircuit top on
ext2spice -o actual.spice
quit -noprompt
''';(out/'extract.tcl').write_text(tcl)
 status[name]['magic']=run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','extract.tcl'],out,'magic.log');save()
 try:
  raw=[]
  for f in out.glob('*.ext'):
   lines=f.read_text().splitlines();scale=float(next(x for x in lines if x.startswith('scale ')).split()[3])*1e-8
   for line in lines:
    t=line.split()
    if len(t)>2 and t[0]=='device' and t[1] in ['ndiode','pdiode']:
     raw.append({'model':t[2],'area_m2':float(re.search(r'\ba=([0-9.]+)',line)[1])*scale**2,'perimeter_m':float(re.search(r'\bp=([0-9.]+)',line)[1])*scale,'source':f.name,'raw_line':line})
  changes=[];lines=[]
  for line in (out/'actual.spice').read_text().splitlines():
   if line.startswith('D'):
    t=line.split();d=dict(x.split('=',1) for x in t[4:] if '=' in x);area=value(d['area']);pj=value(d['pj']);matches=[x for x in raw if x['model']==t[3] and abs(x['area_m2']/area-1)<1e-8]
    vals={round(x['perimeter_m'],14) for x in matches};assert len(vals)==1,(t[0],matches)
    target=vals.pop();assert abs(pj*1e6/target-1)<1e-8
    changes.append({'instance':t[0],'old_pj':d['pj'],'new_pj_m':target,'source':matches[0]['source']});line=re.sub(r'\bpj=\S+',f'pj={target:.12e}',line)
   lines.append(line)
  (out/'actual_normalized.spice').write_text('\n'.join(lines)+'\n');(out/'normalization.json').write_text(json.dumps({'raw_diodes':raw,'changes':changes},indent=2))
  status[name]['netgen']=run(['/foss/tools/netgen/bin/netgen','-batch','lvs','actual_normalized.spice '+name,'reference.spice '+name,str(setup),'comparison.log'],out,'netgen.log')
  comp=(out/'comparison.log').read_text();status[name]['topology_match']='Final result: Circuits match uniquely.' in comp;status[name]['property_errors']='Property errors were found.' in comp
  ref=(out/'reference.spice').read_text();match=re.search(r'\b(c_width|r_width|w)=(\S+)',ref)
  if match:
   bad=ref[:match.start(2)]+f'{value(match[2])*1.1:.12e}'+ref[match.end(2):];(out/'reference_negative.spice').write_text(bad)
   status[name]['negative']=run(['/foss/tools/netgen/bin/netgen','-batch','lvs','actual_normalized.spice '+name,'reference_negative.spice '+name,str(setup),'negative_comparison.log'],out,'negative_netgen.log')
   n=(out/'negative_comparison.log').read_text();status[name]['negative_parameter']=match[1];status[name]['negative_detected']='Property errors were found.' in n or 'do not match' in n.lower()
  else:status[name]['negative_detected']=None
  status[name]['state']='finished'
 except Exception as e:status[name]['state']='blocked';status[name]['error']=str(e)
 save();print(name,status[name],flush=True)

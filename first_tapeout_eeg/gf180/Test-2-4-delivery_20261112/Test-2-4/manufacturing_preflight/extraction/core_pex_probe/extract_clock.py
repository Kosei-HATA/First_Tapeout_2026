from pathlib import Path
import json,re,klayout.db as k,subprocess,os,time
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');base=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis/magic_candidate');geo=json.loads((p/'geometry_precheck.json').read_text());raw=Path('/work/Test-2-4/verification/eeg_core_reference.cdl').read_text();subs={m[1].lower():m[0] for m in re.finditer(r'(?ims)^\.subckt\s+(\S+)[^\n]*\n.*?^\.ends[^\n]*',raw)};todo=['eeg_adc_clk'];selected={}
while todo:
 n=todo.pop()
 if n in selected:continue
 s=subs[n];selected[n]=s
 for line in s.splitlines():
  a=line.split()
  if a and a[0].lower().startswith('x'):
   for token in a[1:]:
    if token.lower() in subs and token.lower() not in selected:todo.append(token.lower())
(p/'reference.cdl').write_text('* Independent closure from verified eeg_core_reference.cdl\n'+'\n\n'.join(selected.values())+'\n');l=k.Layout();l.read(str(p/'eeg_adc_clk.gds'));cell=l.cell('eeg_adc_clk')
for pin in geo['pin_geometry']:cell.shapes(l.layer(42,10)).insert(k.Text(pin['name'],round(pin['x']/l.dbu),round(pin['y']/l.dbu)))
l.write(str(p/'labeled.gds'));print('reference_subckts',len(selected),'gds_bytes',(p/'labeled.gds').stat().st_size,flush=True)
t='drc off\ncrashbackups stop\ngds read labeled.gds\nload eeg_adc_clk\nselect top cell\n'
for i,pin in enumerate(geo['pin_geometry'],1):t+=f"box values {pin['x']}um {pin['y']}um {pin['x']}um {pin['y']}um\nlabel {pin['name']} center metal3\nport make {i}\n"
t+='extract style ngspice()\n'+(base/'full_tcl/wire/run.tcl').read_text().split('extresist threshold')[1].replace(' 0\nextresist minres','extresist threshold 0\nextresist minres',1)
(p/'run.tcl').write_text(t);env=os.environ.copy();env['LD_LIBRARY_PATH']=str(base/'deps/lib')+':'+env.get('LD_LIBRARY_PATH','');start=time.time()
with (p/'magic.log').open('w') as f:r=subprocess.run([str(base/'install_tcl/bin/magic'),'-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','run.tcl'],cwd=p,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
(p/'extraction_status.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start,'style':'ngspice()','reference_subckts':list(selected)},indent=2));print('extract complete',r.returncode,time.time()-start)

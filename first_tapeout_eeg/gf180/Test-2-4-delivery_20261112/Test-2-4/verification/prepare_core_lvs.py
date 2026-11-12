import sys,types,re,json,hashlib,gzip
from pathlib import Path
import pya
root=Path('/work/gf180/tapeout/layout');out=Path('/work/Test-2-4/verification');out.mkdir(exist_ok=True)
sys.dont_write_bytecode=True;sys.path.insert(0,str(root))
f=root/'gf180lay.py';txt=f.read_text();txt=txt.replace('PDK = "/Users/noah/Codings/ws_gf180/gf180mcu-project-template/gf180mcu/gf180mcuD"','PDK = "/foss/pdks/gf180mcuD"');txt=txt.replace('import cells  # noqa: E402  (GF180 pcell library; registers "gf180mcu")','# Pcell registration not needed for annotation/netlist conversion.')
g=types.ModuleType('gf180lay');g.__file__=str(f);sys.modules['gf180lay']=g;exec(compile(txt,str(f),'exec'),g.__dict__)
import chip_lay as chip
l=pya.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');top=l.cell('chip_top');a=g.Cell(l,top)
adc=types.SimpleNamespace(src=l,srctop=l.cell('adc_top'),trans=pya.DCplxTrans(1,0,False,*chip.ADC_O))
# Use actual delivered layout; do not regenerate placement/routing.
l.cell('padring').prune_cell();top.name='eeg_core'
for c in l.each_cell():
 for key in g.L:
  if key.endswith('_label'):
   idx=l.find_layer(*g.L[key])
   if idx is not None:
    for s in list(c.shapes(idx).each()):
     if s.is_text():c.shapes(idx).erase(s)
chip.core_labels(a,{'pads':chip.pads(),'adc':adc})
ren=dict(chip.TIES)
labels=[]
for idx in l.layer_indices():
 for s in top.shapes(idx).each():
  if s.is_text():
   t=s.text;t.string=ren.get(t.string,t.string);s.text=t
   labels.append({'name':t.string,'layer':str(l.get_info(idx)),'x_um':t.x*l.dbu,'y_um':t.y*l.dbu})
l.write(str(out/'eeg_core_from_delivered.gds'))
cdl=g.to_cdl(chip.NETLISTS,'eeg_core');head,body=cdl.split('.subckt eeg_core ',1);line,rest=body.split('\n',1);ports=[]
for n in line.split():
 n=ren.get(n,n)
 if n not in ports:ports.append(n)
body,tail=rest.split('.ends eeg_core',1)
for n,z in ren.items():body=re.sub(rf'(?<=\s){re.escape(n)}(?=\s|$)',z,body,flags=re.M)
cdl=head+'.subckt eeg_core '+' '.join(ports)+'\n'+body+'.ends eeg_core'+tail
(out/'eeg_core_reference.cdl').write_text(cdl)
sourcehash=hashlib.sha256(gzip.decompress(Path('/work/gf180/tapeout/chip/gds/chip_top_fill_r6_20261026.gds.gz').read_bytes())).hexdigest()
r={'baseline_input_sha256':sourcehash,'matches_delivered_input':sourcehash=='1343e9cc55cb2020f6213937c4622f2a126db6381ae66615719398aa6a027529','scope':'Core-only LVS on delivered GDS after removing padring; fill retained; no layout regeneration. Does not prove pad ring LVS.','transformations':['remove padring and unused children','remove text labels on label layers; keep polygon geometry','add core boundary labels using supplied core_labels','rename AVSS_CLK and DVSS to AVSS per supplied substrate convention'],'ties':chip.TIES,'top_labels':labels,'reference_ports':ports,'source_netlists':[{'path':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in chip.NETLISTS],'adc_match_hints':'No deep ADC hints added; delivered GDS has stripped block labels.'}
(out/'core_lvs_preparation.json').write_text(json.dumps(r,indent=2));print(json.dumps({'matches_input':r['matches_delivered_input'],'labels':len(labels),'ports':ports,'sources':len(chip.NETLISTS)},indent=2))

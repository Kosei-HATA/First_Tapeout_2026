from pathlib import Path
import klayout.db as k,json,hashlib
p=Path('/work/Test-2-4/verification');out=p/'core_with_hints';out.mkdir(exist_ok=True)
l=k.Layout();l.read(str(p/'eeg_core_from_delivered.gds'));top=l.cell('eeg_core');adc=l.cell('adc_top')
name='gf180_inside_cascode_ota';src=Path('/work/gf180/tapeout/layout/gds')/(name+'.gds');s=k.Layout();s.read(str(src));st=s.cell(name);dest=l.cell(name)
assert st and dest
differences={}
for info in s.layer_infos():
 si=st.begin_shapes_rec(s.layer(info));si.shape_flags=k.Shapes.SAll & ~k.Shapes.STexts;a=k.Region(si);idx=l.find_layer(info)
 b=k.Region()
 if idx is not None:
  di=dest.begin_shapes_rec(idx);di.shape_flags=k.Shapes.SAll & ~k.Shapes.STexts;b=k.Region(di)
 delta=a^b
 if not delta.is_empty():differences[str(info)]=delta.area()*l.dbu*l.dbu
assert not differences,differences
ats=[i.cplx_trans for i in top.each_inst() if i.cell_index==adc.cell_index()]
ots=[i.cplx_trans for i in adc.each_inst() if i.cell_index==dest.cell_index()]
assert len(ats)==len(ots)==1
t=ats[0]*ots[0];wanted={'CIP','CIN','OTA.CORE.D1P','OTA.CORE.D1N','OTA.CORE.P1P','OTA.CORE.P1N'};labels=[]
for idx in s.layer_indices():
 info=s.get_info(idx)
 if info.datatype!=10:continue
 for sh in st.shapes(idx).each():
  if sh.is_text() and sh.text.string in wanted:
   text=sh.text.transformed(t);text.string='ADC.OTA1.'+text.string;top.shapes(l.layer(info)).insert(text)
   labels.append(dict(name=text.string,layer=str(info),x_um=text.x*l.dbu,y_um=text.y*l.dbu))
assert {x['name'].removeprefix('ADC.OTA1.') for x in labels}==wanted,labels
l.write(str(out/'eeg_core_from_delivered.gds'))
r=dict(reason='Restore six internal net-name hints explicitly used by supplied adc_lay.py and chip_lay.py; delivered file has stripped these labels.',geometry_xor_um2=differences,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),labels=labels,changes='text labels only; no topology or device changes; no forced net matches')
(out/'hints.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
script=(p/'run_core_lvs.sh').read_text().replace('cd /work/Test-2-4/verification','cd /work/Test-2-4/verification/core_with_hints').replace('-r core_lvs.lvs','-r ../core_lvs.lvs')
for f in ['eeg_core_from_delivered.gds','eeg_core.lvsdb','eeg_core_extracted.cir']:
 script=script.replace('/verification/'+f,'/verification/core_with_hints/'+f)
(out/'run.sh').write_text(script)

from pathlib import Path
import klayout.db as k,subprocess,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');out=p/'rc_diagnosis';out.mkdir(exist_ok=True)
l=k.Layout();l.read(str(p/'adc_c2.gds'))
for name,source in [('mim_only','cap_mim$5$3'),('adc_flat','adc_c2')]:
 d=k.Layout();d.dbu=l.dbu;c=d.create_cell(name);src=l.cell(source)
 for li in l.layer_indices():c.shapes(d.layer(l.get_info(li))).insert(k.Region(src.begin_shapes_rec(li)).merged())
 f=out/name;f.mkdir(exist_ok=True);d.write(str(f/'input.gds'))
d=k.Layout();d.dbu=.001;c=d.create_cell('wire');li=d.layer(34,0);c.shapes(li).insert(k.Box(0,0,100000,1000));f=out/'wire';f.mkdir(exist_ok=True);d.write(str(f/'input.gds'))
for name in ['mim_only','adc_flat','wire']:
 f=out/name
 tcl=f'''drc off
crashbackups stop
gds read input.gds
load {name}
select top cell
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
ext2spice hierarchy off
ext2spice format ngspice
ext2spice cthresh 0
ext2spice merge none
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice extresist off
ext2spice -o cap.spice
ext2spice extresist on
ext2spice -o rc.spice
quit -noprompt
'''
 (f/'extract.tcl').write_text(tcl)
 with (f/'magic.log').open('w') as log:subprocess.run(['/foss/tools/magic/bin/magic','-dnull','-noconsole','-rcfile','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc','extract.tcl'],cwd=f,stdout=log,stderr=subprocess.STDOUT)
 print(name,'CAP', (f/'cap.spice').read_text(),'RC',(f/'rc.spice').read_text())

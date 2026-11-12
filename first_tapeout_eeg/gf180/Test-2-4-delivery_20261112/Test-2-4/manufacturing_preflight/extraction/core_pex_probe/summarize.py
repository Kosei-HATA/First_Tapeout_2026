from pathlib import Path
import json,re,hashlib
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');mapping=json.loads((p/'mapping_evidence.json').read_text());r={}
r['scope']='Isolated adc_c2 cell from actual Test-2-4, not in-context whole-block PEX';r['mapping']=mapping
r['schematic_dimension_um']=98.83;r['extracted_dimension_um']=98.82999
for key,dim in [('schematic',98.83e-6),('extracted',98.82999e-6)]:r[key+'_physical_cap_F']=1.99e-3*dim**2+2.383e-10*4*dim
r['dimension_relative_cap_error']=(r['extracted_physical_cap_F']/r['schematic_physical_cap_F']-1)
r['klayout_lvs_cap_F']=19.5347378e-12;r['lvs_C_usage']='Device recognition value is 2 fF/um2 times area, not the simulation model (1.99 fF/um2 plus 0.2383 fF/um perimeter). Do not add this LVS C to the physical model.'
r['raw_parasitics_fF']={'TOP_BOT':17.52885,'TOP_SUB':90.27211,'BOT_SUB':13.6077};r['dominant_device_double_count_check']='One physical MIM X device only; no additional 19.53 pF lumped capacitor. Intentional duplicate X negative control doubles AC capacitance. Residual parasitic/fringe attribution still requires validation.'
r['rc_trial']={'completed':True,'resistor_ohm':0.193943,'ground_cap_without_R_fF':90.27211+13.6077,'ground_cap_with_R_fF':85.7325+13.80997+5.11888+13.09857+10.50128,'usable_for_performance':False,'reason':'Capacitance sum differs when ext2spice extresist is enabled, and substrate anchor naming changes; no convergence/conservation qualification.'}
r['simulation_readiness']={'device_only':True,'raw_capacitance_debug_only':True,'qualified_post_layout_RC':False}
base='''* Qualified for isolated nominal device-model unit/multiplicity check only.
* TOP/BOT map via existing core LVS: C2P ADC.I2P/O2N, C2N ADC.I2N/O2P.
* Include sm141064.ngspice mimcap_typical (loads native cap_mim_new).
.subckt adc_c2_device TOP BOT
X0 TOP BOT cap_mim_2f0_m4m5_noshield c_width=98.82999u c_length=98.82999u
.ends adc_c2_device
''';(p/'adc_c2_device_validated.spice').write_text(base)
raw=(p/'adc_c2_flat.spice').read_text().replace('.subckt adc_c2','.subckt adc_c2_cap_debug TOP BOT SUB').replace('m4_200_80#','TOP').replace('m4_200_21366#','BOT').replace('VSUBS','SUB');(p/'adc_c2_cap_unvalidated.spice').write_text('* DEBUG ONLY: MIM shielding/fringe and in-context substrate attribution are not qualified.\n'+raw)
sources=['/work/Test-2-4/gds/Test-2-4.gds','/work/gf180/tapeout/adc/eeg_adc.spice','/work/gf180/tapeout/layout/adc_lay.py','/foss/pdks/gf180mcuD/libs.tech/magic/gf180mcuD.tech','/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice','/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064_mim.spice']
r['source_sha256']={s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources};(p/'summary.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['mapping','source_sha256']},indent=2))

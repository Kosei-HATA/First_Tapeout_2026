from pathlib import Path
import json,hashlib,re
p=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison');base=p.parent/'clock/3.3/runs/aclk_typical_27/tb.spice';ext=p.parents[1]/'extraction/core_pex_probe/clock_probe'
assert json.loads((ext/'flat/rc_preservation.json').read_text())['pass']
text=base.read_text();old='/work/Test-2-4/functional/sim_work/gf180/tapeout/adc/eeg_adc_clk.spice'
nodes=['vcm','vbn1','vnc1','vpc1','vbcm1','xota1.cip','xota1.cin']+[f'xota1.xota.xcore.{n}' for n in ['d1p','d1n','n1p','n1n','p1p','p1n','p2p','p2n']]
extra=' '.join(f'v({n})' for n in nodes)
text=text.replace('tran 0.01n','op\nwrdata op.csv '+extra+'\ntran 0.01n').replace('quit\n.endc','wrdata load_wave.csv '+extra+'\nquit\n.endc')
manifest=[]
for name,path in [('schematic',Path(old)),('cap',ext/'flat/cap.spice'),('rc',ext/'flat/rc.spice')]:
 d=p/name;d.mkdir(exist_ok=True);s=text.replace(old,str(path));(d/'tb.spice').write_text(s)
 manifest.append({'variant':name,'clock_file':str(path),'clock_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'deck_sha256':hashlib.sha256(s.encode()).hexdigest()})
(p/'comparison_inputs.json').write_text(json.dumps({'cases':manifest,'load_wave_nodes':nodes,'differences':'Only clock .include path differs among variants. Added output probes identical.','external_load_model':'Unmodified real-bias plus schematic OTA TGs, 24 gate-connected MOS instances. External diffusion geometry is schematic approximation, not extracted.','double_counting':'Schematic clock .include replaced, not appended. PEX parasitics included once inside chosen clock definition. External OTA unchanged.'},indent=2))
print('prepared only; awaiting final external terminal mapping')

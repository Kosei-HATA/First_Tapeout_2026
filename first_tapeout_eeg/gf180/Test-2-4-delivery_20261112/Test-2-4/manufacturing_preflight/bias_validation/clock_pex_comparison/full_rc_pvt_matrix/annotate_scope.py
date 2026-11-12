from pathlib import Path
import json,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path('/work/Test-2-4/manufacturing_preflight/bias_validation/clock_pex_comparison/full_rc_pvt_matrix');bias=out.parents[1];clock=out.parent
scope={'MOSCAP_model':'Linear constant-C approximation in functional/sim_work/gf180/tapeout/sim/moscap_lin.spice, not official voltage-dependent MOSCAP.','affected_tests':'All 45 bias startup cases; actual-bias 15 schematic-clock cases; nominal/cap/RC comparisons; 75 clock device/RC cases and numerical controls.','limitation':'Circuit source matching and clock extraction audit do not validate nonlinear MOSCAP behavior, full-chip startup, accuracy, or manufacturing signoff.','formula':'NMOS: factor*L*W*3.983e-3 F/m2; PMOS: factor*L*W*3.958e-3 F/m2; factor typical=1, ff=.9, ss=1.1.'}
decks=list((bias/'runs').glob('*/ramp_*/tb.spice'));assert len(decks)==45
assert all('moscap_lin.spice' in f.read_text() and not any(line.startswith('.lib ') and line.split()[-1].startswith('moscap') for line in f.read_text().splitlines()) for f in decks)
(out/'moscap_scope_audit.json').write_text(json.dumps({'startup_decks_checked':45,'all_linear_MOSCAP':True,'model_scope':scope,'deck_hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in decks}},indent=2))
files=[bias/'summary.json']+list(clock.rglob('summary.json'))+list(clock.rglob('final_summary.json'))
for f in files:
 obj=json.loads(f.read_text(encoding='utf-8-sig'));obj['model_scope']=scope;f.write_text(json.dumps(obj,indent=2))
for f in [bias/'README.md',clock/'README.md']:
 with f.open('a') as s:s.write('\n\n## MOSCAPモデルの適用範囲（追補）\n45件の起動試験、実bias付き15/75条件クロック試験はmoscap_lin.spiceの線形定数C近似です。公式MOSCAPの電圧依存モデルによる動作成立を示しません。回路ソースや配線の一致とモデルの一致は別です。元デッキ・波形・数値結果は変更していません。\n')
rows=json.loads((out/'audited_results.json').read_text())['cases']
dev=[(v,c,t) for v in [3.0,3.3,3.6] for c,t in [('typical',27),('ss',85),('ff',-20),('sf',27),('fs',27)]]
rc=['nominal','hrhc','hrlc','lrhc','lrlc'];a=np.array([[next(r['minimum_margin_ns'] for r in rows if (r['vdd'],r['corner'],r['temperature_C'],r['rc_corner'])==(*k,c)) for c in rc] for k in dev])
fig,ax=plt.subplots(figsize=(10,11));im=ax.imshow(a,cmap='YlGn',vmin=0,aspect='auto')
ax.set_xticks(range(5),rc);ax.set_yticks(range(15),[f'{v:.1f} V | {c.upper()} | {t} C' for v,c,t in dev])
for i in range(15):
 for j in range(5):ax.text(j,i,f'{a[i,j]:.4f}',ha='center',va='center',color='black' if a[i,j]<.65 else 'white')
ax.set_title('ADC internal clock: minimum sequence margin (ns)\n15 selected device / supply / temperature cases x 5 RC corners')
fig.colorbar(im,ax=ax,label='Minimum margin (ns)')
fig.text(.06,.02,'Internal clock PEX only; schematic external loads; LINEAR MOSCAP approximation.\nOfficial nonlinear MOSCAP startup is NOT validated.\nProduct guardband undefined. Positive ordering is not full-chip signoff.',fontsize=10)
fig.subplots_adjust(left=.25,bottom=.12,top=.91,right=.90);fig.savefig(out/'margin_heatmap.png',dpi=150)

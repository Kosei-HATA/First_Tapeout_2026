from pathlib import Path
import re,subprocess,json
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');s=(p/'flat/cap.spice').read_text();s=re.sub(r'^C\d+[^\n]*\n','',s,flags=re.M);s=re.sub(r'^X(\d+)(.*\b[ np]fet_03v3\b.*)$',r'M\1\2',s,flags=re.M)
# Explicit model wrappers and primitive M have the same four D,G,S,B terminals here.
lines=[]
for line in s.splitlines():
 t=line.split()
 if t and t[0].startswith('X') and t[5] in ['nfet_03v3','pfet_03v3']:line='M'+line[1:]
 lines.append(line)
(p/'flat/mos_only.cir').write_text('\n'.join(lines)+'\n')
cmd=['/foss/tools/netgen/bin/netgen','-batch','lvs',str(p/'flat/mos_only.cir')+' eeg_adc_clk',str(p/'reference.cdl')+' eeg_adc_clk','/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl',str(p/'flat/netgen_comparison.log')]
r=subprocess.run(cmd,cwd=p,capture_output=True,text=True);(p/'flat/netgen_run.log').write_text(r.stdout+r.stderr);print(r.returncode);print((p/'flat/netgen_comparison.log').read_text()[-2400:])

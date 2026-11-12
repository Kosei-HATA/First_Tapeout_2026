from pathlib import Path
import shutil,json,hashlib
p=Path('/work/Test-2-4/functional'); old=Path('/work/verification_20261029/source_followup')
ignore=shutil.ignore_patterns('runs*','build','__pycache__','*.pyc')
for name in ['rtl_tests','sim_work','sim_bin']:
 shutil.copytree(old/name,p/name,ignore=ignore,dirs_exist_ok=True)
shutil.copytree('/tmp/source_ngspice',p/'models',dirs_exist_ok=True)
for name in ['run_analog_checks.py','run_extended_analog.py','summarize_analog.py']:
 s=(old/name).read_text().replace(str(old),str(p)).replace('/tmp/source_ngspice',str(p/'models'))
 (p/name).write_text(s)
for f in (p/'sim_work').rglob('*.py'):
 s=f.read_text();n=s.replace('/tmp/source_ngspice',str(p/'models'))
 if n!=s:f.write_text(n)
(p/'sim_bin/ngspice').chmod(0o755)
(p/'netlists').mkdir(exist_ok=True)
for n in ['eeg_digital_top.nl.v','eeg_adc_dig.nl.v']:
 shutil.copy2(Path('/work/gf180/tapeout/layout/gds')/n,p/'netlists'/n)
manifest={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for root in ['rtl_tests','sim_work','models','netlists'] for f in (p/root).rglob('*') if f.is_file()}
(p/'input_hashes.json').write_text(json.dumps(manifest,indent=2))
print(len(manifest),'input files')

# Run inside the existing iic-osic-tools container. Never overwrite delivered results.
from pathlib import Path
import datetime,shutil,subprocess,hashlib
p=Path('/work/Test-2-4')
assert hashlib.sha256((p/'gds/Test-2-4.gds').read_bytes()).hexdigest()=='7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755'
r=p/'rechecks'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');r.mkdir(parents=True,exist_ok=False)
for name in ['gds','baseline']:shutil.copytree(p/name,r/name)
for name in ['scripts','verification']:(r/name).mkdir()
for name in ['check_connectivity.py','run_verification.py']:
 (r/'scripts'/name).write_text((p/'scripts'/name).read_text(encoding='utf-8-sig').replace(str(p),str(r)))
for name in ['prepare_core_lvs.py','restore_lvs_hints.py','run_core_lvs.sh','core_lvs.lvs','summarize_core_lvs.py']:
 (r/'verification'/name).write_text((p/'verification'/name).read_text(encoding='utf-8-sig').replace(str(p),str(r)))
print('Fresh results directory: '+str(r),flush=True)
raise SystemExit(subprocess.call(['python3',str(r/'scripts/run_verification.py')]))

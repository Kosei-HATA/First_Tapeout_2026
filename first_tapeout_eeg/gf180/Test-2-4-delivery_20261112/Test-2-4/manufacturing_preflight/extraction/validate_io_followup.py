from pathlib import Path
import json,re,subprocess
p=Path('/work/Test-2-4/manufacturing_preflight/extraction'); setup=p/'io_asig_magic/strict_setup.tcl'; results={}
def run(d,actual,ref,label):
 with (d/(label+'_netgen.log')).open('w') as f: subprocess.run(['/foss/tools/netgen/bin/netgen','-batch','lvs',actual+' '+d.name,ref+' '+d.name,str(setup),label+'_comparison.log'],cwd=d,stdout=f,stderr=subprocess.STDOUT)
 s=(d/(label+'_comparison.log')).read_text();return {'unique_match':'Final result: Circuits match uniquely.' in s,'property_errors':'Property errors were found.' in s,'mismatch':'do not match' in s.lower()}
d=p/'io_sweep/gf180mcu_fd_io__bi_24t';ref=(d/'reference_common_ground.spice').read_text()
for param in ['d_sab','s_sab','r_width','r_length','w','l','pj']:
 m=re.search(r'\b'+param+r'=(\S+)',ref)
 if not m:continue
 def val(s):
  a=re.fullmatch(r'([+\-0-9.eE]+)([a-zA-Z]*)',s);return float(a[1])*{'':1,'u':1e-6,'n':1e-9,'p':1e-12,'m':1e-3}[a[2]]
 bad=ref[:m.start(1)]+str(val(m[1])*1.1)+ref[m.end(1):];file='hier_negative_'+param+'.spice';(d/file).write_text(bad)
 results[param]=run(d,'actual_hier_normalized.spice',file,'hier_negative_'+param)
(d/'hier_negative_summary.json').write_text(json.dumps(results,indent=2));print('bi negatives',results)
s=(p/'prepare_bi_common_ground.py').read_text().replace('gf180mcu_fd_io__bi_24t','gf180mcu_fd_io__cor').replace('len(pads)==9','len(pads)==4').replace('All 9','All 4');exec(compile(s,'cor_common_ground','exec'),{})
d=p/'io_sweep/gf180mcu_fd_io__cor';r=run(d,'actual_normalized.spice','reference_common_ground.spice','common_ground');(d/'common_ground_summary.json').write_text(json.dumps(r,indent=2));print('cor',r)


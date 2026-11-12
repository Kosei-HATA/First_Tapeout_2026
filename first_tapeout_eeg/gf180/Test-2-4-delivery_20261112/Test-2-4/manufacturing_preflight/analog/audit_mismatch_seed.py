from pathlib import Path
import os,re,json,subprocess,time
p=Path('/work/Test-2-4/manufacturing_preflight/analog');out=p/'mismatch_seed_audit';out.mkdir(exist_ok=True)
os.environ['PATH']=str(p/'sim_bin')+':/foss/tools/bin:'+os.environ['PATH']
src=(p/'dac_static_typical/code_15/tb.spice').read_text();src=src[:src.index('.control')]+'.control\nlisting e\nquit\n.endc\n.end\n'
cases=[('off_s1',0,0,1),('local_s1a',0,1,1),('local_s1b',0,1,1),('local_s2',0,1,2),('global_s1a',1,0,1),('global_s1b',1,0,1),('global_s2',1,0,2)]
results=[]
for tag,g,l,seed in cases:
 d=out/tag;d.mkdir()
 deck=src.replace('.param sw_stat_mismatch=0',f'.param sw_stat_global={g} sw_stat_mismatch={l}').replace('seed=1',f'seed={seed}')
 (d/'tb.spice').write_text(deck);t=time.time();r=subprocess.run(['ngspice','-b','tb.spice'],cwd=d,capture_output=True,text=True,timeout=60)
 (d/'expanded.log').write_text(r.stdout+r.stderr)
 lines=r.stdout.splitlines()
 mos=[x.split(':',1)[1].strip() for x in lines if re.search(r':\s*m\.',x)]
 res=[x.split(':',1)[1].strip() for x in lines if re.search(r':\s*r\.',x)]
 def vals(lines,key):
  return [float(re.search(r'\b'+key+r'=\s*([\d.eE+-]+)',x).group(1)) for x in lines if re.search(r'\b'+key+r'=\s*([\d.eE+-]+)',x)]
 data={'tag':tag,'seconds':time.time()-t,'returncode':r.returncode,'MOS_count':len(mos),'resistor_count':len(res),'delvto':vals(mos,'delvto'),'mulu0':vals(mos,'mulu0'),'resistor_lines':res}
 (d/'parameters.json').write_text(json.dumps(data,indent=2));results.append(data)
 print(tag,len(mos),len(res),data['seconds'],res[:1],flush=True)
(out/'all_parameters.json').write_text(json.dumps(results,indent=2))

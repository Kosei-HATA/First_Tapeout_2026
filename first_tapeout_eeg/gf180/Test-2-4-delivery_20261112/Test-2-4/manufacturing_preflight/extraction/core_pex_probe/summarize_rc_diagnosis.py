from pathlib import Path
import json,shlex,collections,re
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');out=p/'rc_diagnosis';r={};alias={'m4_200_80#':'TOP','m4_200_21366#':'BOT','cap_mim$5$3_0/m4_0_0#':'TOP','cap_mim$5$3_0/m4_n120_n120#':'BOT'};rows=[];sums=collections.defaultdict(float)
for line in (p/'rc_trial/adc_c2.ext').read_text().splitlines():
 if not line.startswith('cap '):continue
 t=shlex.split(line);a,b,v=t[1],t[2],float(t[3])/1000;kind='same_final_net' if alias[a]==alias[b] else 'different_final_nets';sums[kind]+=v
 root=a if '/' not in a else b;sums['incident_'+alias[root]]+=v;rows.append({'raw_a':a,'raw_b':b,'final_a':alias[a],'final_b':alias[b],'fF':v,'kind':kind})
r['original_parent_cap_records']={'sums_fF':dict(sums),'rows':rows};r['original_added_ground_fF']={'child_res_nodes':.731272+5.11888,'parent_TOP_res_node':8.55896,'parent_BOT_res_node':9.97228,'total':.731272+5.11888+8.55896+9.97228}
def value(s):
 m=re.fullmatch(r'([0-9.eE+-]+)([a-zA-Z]*)',s);return float(m[1])*{'':1e15,'f':1,'p':1000,'n':1e6,'u':1e9}[m[2]]
def parse(f):
 rows=[];rs=[]
 for line in f.read_text().splitlines():
  t=line.split()
  if t and t[0].startswith('C'):rows.append({'name':t[0],'nodes':t[1:3],'fF':value(t[3]),'ground':any(n.startswith('w_') for n in t[1:3])})
  if t and t[0].startswith('R'):rs.append({'nodes':t[1:3],'ohm':float(t[3])})
 return {'capacitors':rows,'resistors':rs,'ground_sum_fF':sum(x['fF'] for x in rows if x['ground']),'coupling_sum_fF':sum(x['fF'] for x in rows if not x['ground'])}
r['controls']={}
for n in ['wire','coupled_wires','mim_only','adc_flat','high_threshold','no_coupling']:
 c=parse(out/n/'cap_ports.spice');rc=parse(out/n/'rc_ports.spice');r['controls'][n]={'cap':c,'rc':rc,'ground_delta_fF':rc['ground_sum_fF']-c['ground_sum_fF']}
r['finding']='Current Magic RC output retains coupling capacitors and additionally adds .res.ext rnode capacitance to ground. On coupled metal wires each resistively extracted net receives one full coupling value as added ground capacitance. On MIM only the bottom terminal is resistively split, adding one coupling value. In original hierarchy, parent-level raw coupling includes same-final-net entries which also contribute before alias cancellation.'
r['qualification']='FAIL: reproduces without MIM or hierarchy; no supported option found that preserves distributed R and qualified coupling/ground capacitance simultaneously. No manual subtraction accepted.'
(out/'diagnosis.json').write_text(json.dumps(r,indent=2));print(json.dumps({'original_parent_sums':sums,'original_added':r['original_added_ground_fF'],'control_ground_deltas':{n:x['ground_delta_fF'] for n,x in r['controls'].items()}},indent=2))

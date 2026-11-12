from pathlib import Path
import klayout.db as k,json,resource
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe');e=json.loads((p/'cell_evidence.json').read_text());l=k.LayoutVsSchematic();l.read('/work/Test-2-4/verification/core_with_hints/eeg_core.lvsdb');r={'probes':[],'devices':[]};wanted=set()
for place in e['placements_in_core']:
 tx,ty=[v*.001 for v in place['matrix'][3:]]
 for name,x,y,layers in [('m4_200_80#',1.002,.402,['l20','l25']),('m4_200_21366#',1.002,106.832,['l20','l25']),('mim_top_center',50,53,['l67']),('mim_bottom_center',50,53,['l66','l25','l20'])]:
  hits=[]
  for layer in layers:
   n=l.probe_net(l.layer_by_name(layer),k.DPoint(tx+x,ty+y))
   if n:
    s=l.xref().other_net_for(n);hits.append({'layer':layer,'layout_net':n.expanded_name(),'schematic_net':s.expanded_name() if s else None});wanted.add(n.expanded_name())
  r['probes'].append({'placement':place['path'],'node':name,'core_point_um':[tx+x,ty+y],'hits':hits})
for c in l.netlist().each_circuit():
 for d in c.each_device():
  dc=d.device_class()
  if 'cap_mim' not in dc.name:continue
  nets={t.name:d.net_for_terminal(t.id()).expanded_name() for t in dc.terminal_definitions()}
  if any(d.net_for_terminal(t.id()).expanded_name() in wanted for t in dc.terminal_definitions()):
   sd=l.xref().other_device_for(d);r['devices'].append({'layout_name':d.expanded_name(),'class':dc.name,'nets':nets,'params':{x.name:d.parameter(x.id()) for x in dc.parameter_definitions()},'schematic_name':sd.expanded_name() if sd else None})
r['maxrss_kb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;(p/'mapping_evidence.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))


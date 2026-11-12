from pathlib import Path
import klayout.db as k,json,hashlib,resource,time
p=Path('/work/Test-2-4/manufacturing_preflight/extraction/core_pex_probe/clock_probe');l=k.Layout();src=Path('/work/Test-2-4/gds/Test-2-4.gds');l.read(str(src));cell=l.cell('eeg_adc_clk');d=k.Layout();d.dbu=l.dbu;t=d.create_cell(cell.name);t.copy_tree(cell);d.write(str(p/'eeg_adc_clk.gds'));places=[]
def walk(c,tr,path):
 if c.name==cell.name:places.append((tr,path));return
 for i,inst in enumerate(c.each_inst()):
  for sub in inst.cell_inst.each_cplx_trans():walk(inst.cell,tr*sub,path+'/'+inst.cell.name+'['+str(i)+']')
walk(l.cell('chip_top'),k.ICplxTrans(),'chip_top')
width=145.8;ytop=83.5;gx0=.24;ports=['CHOP1','CIA','NCIA','CIB','NCIB','CDA','NCDA','CDB','NCDB'];step=(width-8.8)/len(ports);pts=[(n,gx0+round((4.4+step*(i+.5)-gx0)/.8)*.8,ytop-.3) for i,n in enumerate(ports)]+[('VDD',width-1.6,2),('VSS',1.6,2)]
# Confirm every proposed pin point intersects actual M3 geometry before DB lookup.
reg=k.Region(cell.begin_shapes_rec(l.layer(42,0)));geometry=[]
for n,x,y in pts:geometry.append({'name':n,'x':x,'y':y,'on_metal3':not (reg & k.Region(k.Box(round(x/l.dbu)-1,round(y/l.dbu)-1,round(x/l.dbu)+1,round(y/l.dbu)+1))).is_empty()})
r={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'pin_geometry':geometry,'placements':[{'path':path,'transform':str(tr)} for tr,path in places],'probes':[],'connected_devices':[]};(p/'geometry_precheck.json').write_text(json.dumps(r,indent=2));print('geometry',geometry,flush=True)
assert all(x['on_metal3'] for x in geometry)
db=k.LayoutVsSchematic();start=time.time();db.read('/work/Test-2-4/verification/core_with_hints/eeg_core.lvsdb');print('DB loaded',time.time()-start,flush=True);wanted={}
for tr,path in places:
 for n,x,y in pts:
  pos=tr*k.Point(round(x/l.dbu),round(y/l.dbu));point=k.DPoint(pos.x*l.dbu,pos.y*l.dbu);hits=[]
  for layer in db.layer_names():
   net=db.probe_net(db.layer_by_name(layer),point)
   if net:
    sn=db.xref().other_net_for(net)
    if sn:hits.append({'layer':layer,'layout':net.expanded_name(),'schematic':sn.expanded_name()});wanted[net.expanded_name()]=n
  r['probes'].append({'port':n,'point_um':[point.x,point.y],'hits':hits})
for circuit in db.netlist().each_circuit():
 for dev in circuit.each_device():
  hits={t.name:wanted[dev.net_for_terminal(t.id()).expanded_name()] for t in dev.device_class().terminal_definitions() if dev.net_for_terminal(t.id()) and dev.net_for_terminal(t.id()).expanded_name() in wanted}
  if hits:
   sd=db.xref().other_device_for(dev);r['connected_devices'].append({'layout':dev.expanded_name(),'schematic':sd.expanded_name() if sd else None,'class':dev.device_class().name,'port_terminals':hits,'params':{x.name:dev.parameter(x.id()) for x in dev.device_class().parameter_definitions()}})
r['elapsed_seconds']=time.time()-start;r['maxrss_kb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;(p/'mapping.json').write_text(json.dumps(r,indent=2));print('probes',r['probes']);print('devices',len(r['connected_devices']),'rss',r['maxrss_kb'])

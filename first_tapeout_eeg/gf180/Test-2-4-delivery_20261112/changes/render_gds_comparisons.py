"""Render verified GDS ECO comparisons. No input GDS is written.
Run inside existing gf180-audit-20261029 container:
  MPLBACKEND=Agg python3 /work/Test-2-4/delivery_visuals_20261112/render_gds_comparisons.py
Requires installed klayout, numpy, matplotlib. Outputs are restricted to this directory.
"""
from pathlib import Path
from functools import lru_cache
import hashlib, json, csv, platform, gc, time
import klayout.db as k
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Rectangle, Circle, Patch
from matplotlib.path import Path as MPath
from matplotlib.lines import Line2D
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
GDS = {
 'original':(ROOT/'chip_top_fill_r6_20261026.gds','1343e9cc55cb2020f6213937c4622f2a126db6381ae66615719398aa6a027529'),
 'Test2-3':(ROOT/'Test2-3/gds/Test2-3.gds','1ec7bd329d5ee1ba7cf3ac39ab22a698fb91847c486b6ede2aa6c3fb2003277c'),
 'Test-2-4':(ROOT/'Test-2-4/gds/Test-2-4.gds','7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755')}

def sha(p):
 with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def log(s): print(s,flush=True)

files={}; layouts={}
for name,(path,expected) in GDS.items():
 actual=sha(path); assert actual==expected, (name,actual)
 files[name]={'relative_path':str(path.relative_to(ROOT)), 'bytes':path.stat().st_size, 'sha256':actual}
 l=k.Layout();l.read(str(path));assert l.dbu==0.001;layouts[name]=l
 log('Loaded and verified '+name)
u=layouts['Test-2-4'].dbu
A,B,C=(layouts[x] for x in ['original','Test2-3','Test-2-4'])
at,bt,ct=(x.cell('chip_top') for x in [A,B,C])

def reg(layout,cell,layer):
 i=layout.find_layer(layer,0)
 return k.Region(cell.begin_shapes_rec(i)).merged() if i is not None else k.Region()

def box(t): return k.Region(k.DBox(*t).to_itype(u))
def area(r): return round(r.area()*u*u,8)
def bbox(r):
 b=r.bbox().to_dtype(u)
 return [b.left,b.bottom,b.right,b.top]
def polyjson(p):
 return {'hull':[[round(q.x*u,6),round(q.y*u,6)] for q in p.each_point_hull()], 'holes':[[[round(q.x*u,6),round(q.y*u,6)] for q in p.each_point_hole(i)] for i in range(p.holes())]}
def coords(r): return [polyjson(p) for p in r.each()]

bridge_boxes=[(3519,596.86,3523,606.86),(3519,655.14,3523,665.14),(3519,2006.86,3523,2016.86),(3519,2065.14,3523,2075.14)]
m5old=reg(A,at,81);m5mid=reg(B,bt,81);m5new=reg(C,ct,81)
bridge_added=m5mid-m5old;bridge_removed=m5old-m5mid
expected=k.Region()
for x1,y1,x2,y2 in bridge_boxes:expected+=box((3520,y1,3522,y2))
assert (expected^bridge_added).is_empty();assert bridge_removed.is_empty()
assert (m5mid^m5new).is_empty()
log('M5 verified: exact 80 um2 addition; unchanged from Test2-3 to Test-2-4')

# Expand only hierarchy branches that contain the altered pad cell.
pad=C.cell('Bondpad_5LM'); pad_index=pad.cell_index()
@lru_cache(None)
def contains_pad(ci):
 if ci==pad_index:return True
 return any(contains_pad(inst.cell_index) for inst in C.cell(ci).each_inst())
transforms=[]
def walk(ci,tr,path):
 if ci==pad_index:
  transforms.append((tr,path));return
 for n,inst in enumerate(C.cell(ci).each_inst()):
  if not contains_pad(inst.cell_index):continue
  for j,t in enumerate(inst.cell_inst.each_cplx_trans()):
   walk(inst.cell_index,tr*t,path+[{'cell':C.cell(inst.cell_index).name,'instance_index':n,'array_element':j}])
walk(ct.cell_index(),k.ICplxTrans(),[])
assert len(transforms)==72,len(transforms)
pad_positions=[]
for i,(tr,path) in enumerate(transforms):
 p=tr*pad.bbox();d=p.to_dtype(u)
 pad_positions.append({'id':i+1,'transform_dbu':str(tr),'bbox_um':[d.left,d.bottom,d.right,d.top],'hierarchy':path})

pad_regions={};pad_stats=[];top_deltas={}
for name,layer in [('M2',36),('M3',42),('M4',46)]:
 old=reg(B,B.cell('Bondpad_5LM'),layer);new=reg(C,pad,layer)
 original=reg(A,A.cell('Bondpad_5LM'),layer)
 assert (original^old).is_empty()
 added=new-old;removed=old-new
 assert removed.is_empty(); assert (added^(box((3.34,1.27,62,62.205))-old)).is_empty()
 expected_top=k.Region()
 for tr,_ in transforms:expected_top+=added.transformed(tr)
 expected_top.merge()
 log('Checking full-chip '+name+' physical difference')
 old_top=reg(B,bt,layer);new_top=reg(C,ct,layer)
 topadd=new_top-old_top;topremove=old_top-new_top
 assert topremove.is_empty(); assert (topadd^expected_top).is_empty(),(name,area(topadd),area(expected_top))
 stats={'name':name,'gds_layer':f'{layer}/0','local_before_area_um2':area(old),'local_after_area_um2':area(new),'local_added_area_um2':area(added),'local_removed_area_um2':area(removed),'local_added_bbox_um':bbox(added),'added_polygon_count_local':added.count(),'top_added_area_um2':area(topadd),'top_removed_area_um2':area(topremove),'instance_count':len(transforms),'full_chip_delta_matches_transformed_local_delta':True,'original_equals_Test2_3_local':True}
 pad_stats.append(stats);pad_regions[name]=(old,new,added);top_deltas[name]=topadd
 del old_top,new_top,topremove;gc.collect()
 log(json.dumps(stats))

# Preserve complete extracted geometry for differences, and exact plotted windows.
geometry={'dbu_um':u,'bridge_added_chip_coordinates':coords(bridge_added),'pad_local':{},'pad_instances':pad_positions}
for name,(old,new,added) in pad_regions.items():
 geometry['pad_local'][name]={'before':coords(old),'after':coords(new),'added':coords(added)}
geometry['bridges']=[]
for i,r in enumerate(bridge_boxes):
 center=(r[1]+r[3])/2;roi=(3509,center-10,3533,center+10);clip=box(roi)
 geometry['bridges'].append({'id':f'B{i+1}','inserted_box_um':r,'plotted_window_um':roi,'before':coords(m5old&clip),'after':coords(m5mid&clip),'added':coords(bridge_added&clip)})
(OUT/'geometry_extract.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')

# Plot exact polygon hulls and holes (compound paths with preserved winding).
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,'figure.facecolor':'#f5f7fa','axes.facecolor':'#ffffff','axes.edgecolor':'#a0adbc','axes.labelcolor':'#34445a','text.color':'#17273b','grid.color':'#e4e9ef','grid.linewidth':0.5,'savefig.facecolor':'#f5f7fa'})
OLD='#7892ac';ADD='#00a891';PAD='#b265d6';REM='#df3853';INK='#17273b';PALE='#dce4ec'

def draw(ax,r,color,edge=None,alpha=1,linewidth=0.5):
 if r.is_empty():return
 verts=[];codes=[]
 for p in r.each():
  loops=[list(p.each_point_hull())]+[list(p.each_point_hole(i)) for i in range(p.holes())]
  for points in loops:
   if not points:continue
   xy=[(q.x*u,q.y*u) for q in points]
   verts.extend(xy+[xy[0]]);codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(xy)-1)+[MPath.CLOSEPOLY])
 ax.add_patch(PathPatch(MPath(verts,codes),facecolor=color,edgecolor=(edge if edge is not None else 'none'),alpha=alpha,lw=linewidth,rasterized=False))

def axes_setup(ax,limits,label=True):
 ax.set_xlim(limits[0],limits[2]);ax.set_ylim(limits[1],limits[3]);ax.set_aspect('equal');ax.set_axisbelow(True)
 ax.grid(True,alpha=.7)
 if label:ax.set_xlabel('x (um)');ax.set_ylabel('y (um)')
 ax.ticklabel_format(style='plain',useOffset=False)

def scale(ax,length,limits):
 x=limits[0]+.06*(limits[2]-limits[0]);y=limits[1]+.07*(limits[3]-limits[1])
 ax.plot([x,x+length],[y,y],color=INK,lw=2.5,zorder=12)
 ax.text(x+length/2,y+.025*(limits[3]-limits[1]),f'{length:g} um',ha='center',va='bottom',fontsize=9,color=INK,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none','pad':1},zorder=13)

def title(fig,heading,sub):
 fig.suptitle(heading,x=.045,y=.975,ha='left',fontsize=20,fontweight='bold')
 fig.text(.045,.942,sub,fontsize=11,color='#47586c',ha='left')
def foot(fig,text):fig.text(.045,.018,text,fontsize=9,color='#47586c',ha='left')
def save(fig,name):
 p=OUT/name;fig.savefig(p,dpi=220,bbox_inches=None);plt.close(fig);log('Wrote '+name)

# 01. Real full-chip M5 context with all changed pad instances and bridge positions.
fig=plt.figure(figsize=(16,10));gs=fig.add_gridspec(1,2,width_ratios=[4.5,1.5],left=.055,right=.98,bottom=.09,top=.89,wspace=.08)
ax=fig.add_subplot(gs[0,0]);info=fig.add_subplot(gs[0,1]);info.axis('off')
draw(ax,m5new,'#d5dde6',edge=None)
# PAD openings, extracted from GDS, distinguish physical pad footprints.
opening=k.Region()
for tr,_ in transforms:opening+=reg(C,pad,37).transformed(tr)
draw(ax,opening,'#e4d6f0',edge='#a778c3',linewidth=.3)
for name in ['M2','M3','M4']:draw(ax,top_deltas[name],PAD,edge=None,alpha=.8)
draw(ax,bridge_added,ADD)
for item in pad_positions:
 x1,y1,x2,y2=item['bbox_um'];ax.add_patch(Rectangle((x1,y1),x2-x1,y2-y1,fill=False,ec=PAD,lw=1.1))
for i,r in enumerate(bridge_boxes):
 x,y=(r[0]+r[2])/2,(r[1]+r[3])/2
 ax.add_patch(Circle((x,y),30,fill=False,ec=ADD,lw=1.8,zorder=9))
 dx=120 if i%2 else -135;dy=25 if i%2 else -40
 ax.annotate(f'B{i+1}',(x,y),xytext=(x+dx,y+dy),color=ADD,fontweight='bold',fontsize=10,arrowprops={'arrowstyle':'-','color':ADD,'lw':1},ha='center')
axes_setup(ax,(-30,-30,3962,2561));scale(ax,500,(-30,-30,3962,2561))
ax.set_title('chip_top: 3932 x 2531 um | global coordinates',loc='left',fontsize=12,pad=12)
info.text(0,1,'TWO SEPARATE CHANGES',fontsize=12,fontweight='bold',va='top')
info.text(0,.91,'A  DVDD bridges',fontsize=15,fontweight='bold',color=ADD)
info.text(0,.86,'Original -> Test2-3\nRetained unchanged in Test-2-4\n\nMetal5, GDS 81/0\n4 inserted boxes: 4 x 10 um\nNew union area: 80 um2\n2 um isolation gap bridged locally\n\nB1/B2: y ~ 602 / 660 um\nB3/B4: y ~ 2012 / 2070 um',fontsize=11,va='top',linespacing=1.5)
info.text(0,.48,'B  Bondpad notch fill',fontsize=15,fontweight='bold',color=PAD)
info.text(0,.43,'Test2-3 -> Test-2-4\nBondpad_5LM: 72 placements\n\nM2 (36/0): +561.6000 um2 / pad\nM3 (42/0): +555.1416 um2 / pad\nM4 (46/0): +555.1416 um2 / pad\n\nAdded metal only; no removal.\nVias, PAD openings and M5\nare unchanged by the pad ECO.',fontsize=11,va='top',linespacing=1.5)
info.text(0,.035,'Legend',fontweight='bold',fontsize=11)
info.legend(handles=[Patch(fc='#d5dde6',label='Existing M5 context'),Patch(fc='none',ec=PAD,label='Pad ECO locations (72)'),Line2D([],[],marker='o',mfc='none',mec=ADD,color='none',label='Bridge locator (not to scale)')],loc='upper left',bbox_to_anchor=(-.05,.02),frameon=False,fontsize=9)
title(fig,'Test-2-4 | Where the GDS changed','Exact GDS geometry, separated by revision. Full-chip overview is a locator; use the following close-ups for dimensional review.')
foot(fig,'Units: micrometres (um). M5 and PAD context only, not every chip layer. Pad outlines / bridge circles are location guides. No fabrication or bonding signoff implied.')
save(fig,'01_change_locations.png')

# 02. Four DVDD bridge windows, all exact original/test2-3/difference geometry.
fig,axs=plt.subplots(4,3,figsize=(14,15));fig.subplots_adjust(left=.07,right=.97,bottom=.12,top=.89,wspace=.30,hspace=.40)
for i,r in enumerate(bridge_boxes):
 cy=(r[1]+r[3])/2;roi=(3509,cy-10,3533,cy+10);cl=box(roi);old=m5old&cl;new=m5mid&cl;added=bridge_added&cl
 for j,ax in enumerate(axs[i]):
  if j==0:draw(ax,old,OLD)
  elif j==1:
   draw(ax,new,OLD);draw(ax,added,ADD)
   ax.add_patch(Rectangle((r[0],r[1]),4,10,fill=False,ec='#eaa63b',ls='--',lw=1.3))
  else:draw(ax,old,PALE,edge='#aab8c6',linewidth=.3);draw(ax,added,ADD)
  axes_setup(ax,roi);ax.set_title(['BEFORE | Original','AFTER | Test2-3 = Test-2-4','DIFFERENCE | Added only'][j],loc='left',fontsize=11)
  if i<3:ax.set_xlabel('')
  if j==0:ax.text(.01,1.18,f'B{i+1}: y = {r[1]:.2f} to {r[3]:.2f} um',transform=ax.transAxes,fontweight='bold',fontsize=11)
  if j==2:
   ax.annotate('+20 um2\n2 x 10 um',(3521,cy),xytext=(3527,cy+5),fontsize=9,fontweight='bold',color='#007f70',ha='center',arrowprops={'arrowstyle':'->','color':'#007f70','lw':1})
  if i==3:scale(ax,5,roi)
title(fig,'A | Four local DVDD bridges on Metal5','Original -> Test2-3; no subsequent M5 change in Test-2-4. GDS layer 81/0. Global coordinates; equal x/y scale.')
fig.legend(handles=[Patch(fc=OLD,label='Existing / unchanged metal'),Patch(fc=ADD,label='New metal in former 2 um gap'),Patch(fc='none',ec='#eaa63b',ls='--',label='Inserted 4 x 10 um box (1 um overlap each side)')],loc='lower center',bbox_to_anchor=(.5,.037),ncol=3,frameon=False,fontsize=10)
foot(fig,'Boolean union difference = 4 x 20 = 80 um2; removed metal = 0. The full 2 um slot was NOT filled, only these four local bridges.')
save(fig,'02_dvdd_bridges_before_after_diff.png')

# 03. Complete pad cell: each modified layer independently, local coordinates.
fig,axs=plt.subplots(3,3,figsize=(14,14));fig.subplots_adjust(left=.06,right=.98,bottom=.13,top=.89,wspace=.27,hspace=.30)
roi=(-3,-2,68,68)
for row,stats in enumerate(pad_stats):
 name=stats['name'];old,new,added=pad_regions[name]
 for j,ax in enumerate(axs[row]):
  if j==0:draw(ax,old,OLD)
  elif j==1:draw(ax,new,OLD);draw(ax,added,ADD)
  else:draw(ax,old,PALE,edge=None);draw(ax,added,ADD)
  axes_setup(ax,roi);ax.set_title([f'{name} ({stats["gds_layer"]}) | BEFORE Test2-3',f'{name} | AFTER Test-2-4',f'{name} | +{area(added):.4f} um2'][j],loc='left',fontsize=11)
  # Exact fixed crop reused in detail image; guide is not geometry.
  ax.add_patch(Rectangle((4,10),10,10,fill=False,ec='#d48622',ls='--',lw=1.1))
  if row==2:scale(ax,10,roi)
title(fig,'B | Bondpad_5LM metal additions','Test2-3 -> Test-2-4. Cell-local coordinates, all 72 placements. Original pad geometry equals the Test2-3 BEFORE geometry.')
fig.legend(handles=[Patch(fc=OLD,label='Existing / unchanged metal'),Patch(fc=ADD,label='Added metal'),Patch(fc=PALE,label='Before context in difference view'),Patch(fc='none',ec='#d48622',ls='--',label='10 x 10 um detail window')],loc='lower center',bbox_to_anchor=(.5,.04),ncol=2,frameon=False,fontsize=10)
foot(fig,'Metal union additions only. No deletion on M2/M3/M4. The other cell layers, vias, PAD openings and Metal5 are not changed by this pad ECO.')
save(fig,'03_pad_layers_before_after_diff.png')

# 04. High-magnification view of actual notch geometry for each changed pad layer.
fig,axs=plt.subplots(3,3,figsize=(14,13.5));fig.subplots_adjust(left=.065,right=.98,bottom=.13,top=.89,wspace=.26,hspace=.34)
roi=(4,10,14,20);clip=box(roi)
for row,stats in enumerate(pad_stats):
 name=stats['name'];old,new,added=pad_regions[name];old=old&clip;new=new&clip;added=added&clip
 for j,ax in enumerate(axs[row]):
  if j==0:draw(ax,old,OLD)
  elif j==1:draw(ax,new,OLD);draw(ax,added,ADD)
  else:draw(ax,old,PALE,edge=None);draw(ax,added,ADD)
  axes_setup(ax,roi);ax.set_xticks(np.arange(4,15,2));ax.set_yticks(np.arange(10,21,2))
  ax.set_title([f'{name} ({stats["gds_layer"]}) | BEFORE',f'{name} | AFTER',f'{name} | DIFFERENCE'][j],loc='left',fontsize=11)
  if row==2:scale(ax,2,roi)
title(fig,'B | Pad notch detail at 10 x 10 um','Test2-3 -> Test-2-4. Identical cell-local crop on M2 / M3 / M4; no drawing simplification or geometry exaggeration.')
fig.legend(handles=[Patch(fc=OLD,label='Existing / unchanged metal'),Patch(fc=ADD,label='Added metal'),Patch(fc=PALE,label='Before context in difference view')],loc='lower center',bbox_to_anchor=(.5,.04),ncol=3,frameon=False,fontsize=10)
foot(fig,'Window: x = 4 to 14 um, y = 10 to 20 um in Bondpad_5LM. This is a detailed crop, not the entire added area of a pad.')
save(fig,'04_pad_notch_detail.png')

# Independent all-cell scope checks; these edits affect RAM only, never a GDS file.
bridge_shape_container=bt.shapes(B.find_layer(81,0))
for r in bridge_boxes:
 target=k.DBox(*r).to_itype(u)
 matches=[s for s in bridge_shape_container.each() if s.is_box() and s.box==target]
 assert len(matches)==1
 bridge_shape_container.erase(matches[0])
bridge_scope_ok=k.LayoutDiff().compare(A,B,k.LayoutDiff.BoxesAsPolygons,0)
assert bridge_scope_ok
for r in bridge_boxes:bridge_shape_container.insert(k.DBox(*r).to_itype(u))
for layer in [36,42,46]:
 src=B.cell('Bondpad_5LM').shapes(B.find_layer(layer,0));dst=pad.shapes(C.find_layer(layer,0))
 dst.clear()
 for shape in src.each():dst.insert(shape)
pad_scope_ok=k.LayoutDiff().compare(B,C,k.LayoutDiff.BoxesAsPolygons,0)
assert pad_scope_ok
log('Scope checks PASS: only 4 bridge boxes in original -> Test2-3; only declared pad layers in Test2-3 -> Test-2-4')
metadata={'title':'Exact GDS ECO comparison images','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'method':'KLayout Region Boolean geometry and matplotlib paths; input GDS read only; no generative image synthesis','versions':{'python':platform.python_version(),'klayout':k.__version__,'matplotlib':matplotlib.__version__},'input_files':files,'units':'um; areas um^2','dbu_um':u,'top_cell':'chip_top','top_bbox_um':bbox(k.Region(ct.bbox())),'pad_cell':'Bondpad_5LM','pad_instance_count':len(transforms),'bridge_change':{'from':'original','to':'Test2-3','layer':'81/0','inserted_boxes_um':bridge_boxes,'actual_added_polygons_um':coords(bridge_added),'added_area_um2':area(bridge_added),'removed_area_um2':area(bridge_removed),'unchanged_Test2_3_to_Test_2_4':True},'pad_change':{'from':'Test2-3','to':'Test-2-4','layers':pad_stats},'checks':{'all_three_hashes_match_expected':True,'non_bridge_geometry_hierarchy_and_properties_unchanged':bridge_scope_ok,'non_pad_geometry_hierarchy_and_properties_unchanged':pad_scope_ok,'M5_exact_expected_union':True,'M5_unchanged_in_pad_ECO':True,'pad_additions_match_full_chip_geometry':True,'no_metal_removal_on_changed_layers':True},'limitations':['Visualization and change verification are not fabrication or mechanical bonding approval.','Overview shows M5 and pad context, not every GDS layer.','Inserted bridge rectangle area (40 um2 each) includes overlaps; actual new union area is 20 um2 each.','Pad additions are shown in local coordinates; expanded pad instances are separately enumerated.']}
for name,(p,_) in GDS.items():assert sha(p)==files[name]['sha256']
metadata['checks']['input_hashes_unchanged_after_rendering']=True
metadata['outputs']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.suffix in ['.png','.py','.json'] and p.name!='metadata.json']
(OUT/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
with (OUT/'changed_areas.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f);w.writerow(['change','layer_datatype','local_added_um2','placements','top_added_um2','top_removed_um2'])
 w.writerow(['DVDD bridges','81/0',20,4,area(bridge_added),0])
 for s in pad_stats:w.writerow(['Bondpad_5LM',s['gds_layer'],s['local_added_area_um2'],72,s['top_added_area_um2'],s['top_removed_area_um2']])
(OUT/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+v['relative_path']+'\n' for v in files.values())+'\n'+''.join(sha(p)+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf-8')
log('SUCCESS: PNGs, exact geometry, metadata, coordinate/area CSV and hashes saved; all input hashes preserved.')



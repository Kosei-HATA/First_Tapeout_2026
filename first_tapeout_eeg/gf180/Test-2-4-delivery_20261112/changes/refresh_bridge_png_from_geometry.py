"""Refresh only the bridge PNG from already verified geometry_extract.json.
This avoids re-reading the 675 MB of GDS for a presentation-only change.
The full renderer produces the same plot and rechecks GDS geometry.
"""
from pathlib import Path
import json
import klayout.db as k
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Rectangle, Circle, Patch
from matplotlib.path import Path as MPath
from matplotlib.lines import Line2D
import numpy as np
OUT=Path(__file__).resolve().parent
u=.001
raw=json.loads((OUT/'geometry_extract.json').read_text())
def region(items):
 r=k.Region()
 for item in items:
  p=k.Polygon([k.DPoint(*x).to_itype(u) for x in item['hull']])
  for hole in item['holes']:p.insert_hole([k.DPoint(*x).to_itype(u) for x in hole])
  r.insert(p)
 return r
m5old=k.Region();m5mid=k.Region();bridge_added=k.Region()
bridge_boxes=[]
for b in raw['bridges']:
 bridge_boxes.append(b['inserted_box_um'])
 m5old+=region(b['before']);m5mid+=region(b['after']);bridge_added+=region(b['added'])
def box(t):return k.Region(k.DBox(*t).to_itype(u))
def log(s):print(s,flush=True)
code=(OUT/'render_gds_comparisons.py').read_text(encoding='utf-8-sig')
exec(code[code.index('# Plot exact'):code.index('# 01.')])
exec(code[code.index('# 02.'):code.index('# 03.')])

#!/usr/bin/env python3
"""Connectivity self-check for the integrated wrapper GDS.

    scripts/klayout/.venv/bin/python scripts/klayout/check_wrapper_nets.py

Flattens GDSII/user_analog_project_wrapper.gds, union-finds all metal
(m1..m5 + vias; via3 over capm excluded — MIM plates falsely merge
m3<->m4), and verifies the wrapper integration net map:

  1. every macro top-level pin (matched by name AND mirrored position)
     shares its net with the intended wrapper pad/stub label;
  2. no net carries two different RELEVANT names (macro top pins,
     wrapper labels, template power labels) — block-internal labels
     (A/B/EN/Y/INP/...) are hierarchy noise and ignored;
  3. known res_generic_m3 links (invisible to metal tracing) are
     whitelisted: vssa1<->io_clamp_low[0..2]/io_clamp_high[1..2],
     io_analog[4]<->io_clamp_high[0].

Labels map to nets through polygons of their OWN layer family
(m4L text -> m4 metal, ...), never a random layer in the stack.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import kdb

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GDS = os.path.join(PROJECT, "GDSII", "user_analog_project_wrapper.gds")
PX, PY = 2078.0, 890.0    # gen_wrapper.py's mirrored macro placement

# macro top-pin labels, macro-local (name, x, y, label-layer)
MACRO_PINS_LOCAL = [
    ("ELP", -762.0, 41.0, 71), ("ELN", -762.0, -79.0, 71),
    ("S8", -560.0, -38.0, 71), ("S16", -556.0, -39.2, 71),
    ("S32", -552.0, -40.4, 71), ("S64", -569.5, -50.0, 71),
    ("PHII", -290.0, 18.0, 71), ("NPHII", -292.0, 19.0, 71),
    ("PHIBI", -295.0, 20.0, 71), ("NPHIBI", -300.0, 21.0, 71),
    ("PHIM", 365.5, 80.0, 71), ("NPHIM", 362.0, 81.0, 71),
    ("PHIBM", 358.5, 82.0, 71), ("NPHIBM", 355.65, 83.0, 71),
    ("CLK16", -692.0, 1622.15, 71), ("NCLK16", -688.8, 1620.05, 71),
    ("BIT", -425.0, 730.65, 71), ("NBIT", -575.0, 1494.79, 71),
    ("VP", -440.0, 718.25, 71), ("VN", -415.0, 718.25, 71),
    ("VDD18", 0.0, 1771.95, 72), ("VCM_REF", 465.0, 1777.95, 72),
    ("VSS", 540.0, 1783.95, 72)]
# wrapper labels added by gen_wrapper.py (name, x, y, label-layer)
WRAPPER_LABELS = [
    ("io_analog[0]", 2918.0, 3402.4, 70), ("io_analog[1]", 2845.5, 3517.75, 70),
    ("io_analog[2]", 2339.5, 3517.75, 70), ("io_analog[3]", 2079.5, 3517.75, 70),
    ("io_analog[4]", 1790.0, 3070.0, 72),
    ("io_in[5]", 2918.5, 240.76, 70), ("io_in[6]", 2918.5, 464.05, 70),
    ("io_in[7]", 2918.5, 1364.16, 70), ("io_in[8]", 2918.5, 1586.27, 70),
    ("io_in[9]", 2918.5, 1812.38, 70), ("io_in[10]", 2918.5, 2044.49, 70),
    ("io_in[11]", 2918.5, 2266.6, 70), ("io_in[12]", 2918.5, 2488.71, 70),
    ("io_in[13]", 2918.5, 2935.82, 70),
    ("io_in[14]", 2.0, 2540.20, 70), ("io_in[15]", 2.0, 2324.09, 70),
    ("io_in[16]", 2.0, 2107.98, 70), ("io_in[17]", 2.0, 1891.87, 70),
    ("io_in[18]", 2.0, 1675.76, 70),
    ("io_out[19]", 2.0, 1453.74, 70), ("io_out[20]", 2.0, 1238.63, 70),
    ("io_clamp_low[0]", 1627.0, 3515.0, 70),
    ("io_clamp_high[0]", 1639.5, 3515.0, 70),
    ("io_clamp_low[1]", 1118.5, 3510.0, 70),
    ("io_clamp_high[1]", 1131.0, 3510.0, 70),
    ("io_clamp_low[2]", 860.0, 3510.0, 70),
    ("io_clamp_high[2]", 872.5, 3510.0, 70)]
# template power labels surviving from the padframe
TEMPLATE_POWER = [("VDDA1", 2860.85, 2763.76, 70),
                  ("VSSA1", 2565.38, 3352.92, 70),
                  ("VCCD1", 2880.93, 3210.73, 70)]

PAIRS = [("VDD18", "VDDA1"), ("VSS", "VSSA1"),
         ("ELP", "io_analog[0]"), ("ELN", "io_analog[1]"),
         ("VCM_REF", "io_analog[2]"), ("VP", "io_analog[3]"),
         ("VN", "io_analog[4]"),
         ("PHII", "io_in[5]"), ("NPHII", "io_in[6]"), ("PHIBI", "io_in[7]"),
         ("NPHIBI", "io_in[8]"), ("PHIM", "io_in[9]"), ("NPHIM", "io_in[10]"),
         ("PHIBM", "io_in[11]"), ("NPHIBM", "io_in[12]"), ("CLK16", "io_in[13]"),
         ("NCLK16", "io_in[14]"), ("S8", "io_in[15]"), ("S16", "io_in[16]"),
         ("S32", "io_in[17]"), ("S64", "io_in[18]"),
         ("BIT", "io_out[19]"), ("NBIT", "io_out[20]")]
# name groups allowed to share one net (expected merges; the
# res_generic_m3 clamp resistors are invisible to metal tracing)
ALLOWED_GROUPS = [{a, b} for a, b in PAIRS] + [
    {"VSS", "VSSA1", "io_clamp_low[0]", "io_clamp_low[1]", "io_clamp_low[2]",
     "io_clamp_high[1]", "io_clamp_high[2]"},
    {"VN", "io_analog[4]", "io_clamp_high[0]"}]

METAL = [(68, 20), (68, 44), (69, 20), (69, 44), (70, 20), (70, 44),
         (71, 20), (71, 44), (72, 20)]
DRAW_OF_LABEL = {68: (68, 20), 69: (69, 20), 70: (70, 20), 71: (71, 20),
                 72: (72, 20)}

ly = kdb.Layout()
ly.read(GDS)
top = ly.cell("user_analog_project_wrapper")
top.flatten(True)

regions = {}
for spec in METAL:
    regions[spec] = kdb.Region(top.shapes(ly.layer(*spec))).merged()
capm = kdb.Region(top.shapes(ly.layer(89, 44))).merged()
regions[(70, 44)] = regions[(70, 44)] - capm   # MIM via3 fields are not wires

polys = []
for spec, r in regions.items():
    for p in r.each():
        polys.append((spec, p))
parent = list(range(len(polys)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb


CELL = 100000
grid = defaultdict(list)
for i, (spec, p) in enumerate(polys):
    bb = p.bbox()
    for gx in range(bb.left // CELL, bb.right // CELL + 1):
        for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
            grid[(gx, gy)].append(i)
CONSEC = [((68, 20), (68, 44)), ((68, 44), (69, 20)), ((69, 20), (69, 44)),
          ((69, 44), (70, 20)), ((70, 20), (70, 44)), ((70, 44), (71, 20)),
          ((71, 20), (71, 44)), ((71, 44), (72, 20))]
for sa, sb in CONSEC:
    for i, (spec, p) in enumerate(polys):
        if spec != sa:
            continue
        bb = p.bbox()
        seen = set()
        for gx in range(bb.left // CELL, bb.right // CELL + 1):
            for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
                for j in grid.get((gx, gy), ()):
                    if j in seen or polys[j][0] != sb:
                        continue
                    seen.add(j)
                    if not (kdb.Region(polys[i][1]).sized(1) &
                            kdb.Region(polys[j][1]).sized(1)).is_empty():
                        union(i, j)


def net_at(x, y, label_layer):
    """Union root of the DRAWING-layer polygon at (x, y) um."""
    pt = kdb.Point(int(round(x * 1000)), int(round(y * 1000)))
    spec = DRAW_OF_LABEL[label_layer]
    for i, (pspec, p) in enumerate(polys):
        if pspec == spec and p.bbox().contains(pt) and p.inside(pt):
            return find(i)
    return None


relevant = [(name, PX - x, PY + y, lf) for name, x, y, lf in MACRO_PINS_LOCAL]
relevant += WRAPPER_LABELS + TEMPLATE_POWER

net_names = defaultdict(list)
fails = 0
for name, x, y, lf in relevant:
    root = net_at(x, y, lf)
    if root is None:
        print(f"*** LABEL ON NO METAL: {name} at ({x},{y})")
        fails += 1
    else:
        net_names[root].append((name, x, y))

for a, b in PAIRS:
    ma = next(v for v in MACRO_PINS_LOCAL if v[0] == a)
    lb = next(v for v in WRAPPER_LABELS + TEMPLATE_POWER if v[0] == b)
    ra = net_at(PX - ma[1], PY + ma[2], ma[3])
    rb = net_at(lb[1], lb[2], lb[3])
    if ra is None or rb is None or ra != rb:
        print(f"*** NOT CONNECTED: {a} <-> {b}")
        fails += 1

for root, occs in sorted(net_names.items()):
    names = sorted({n for n, _, _ in occs})
    print(f"net#{root}: {names}")
    if len(names) <= 1:
        continue
    if not any(all(n in g for n in names) for g in ALLOWED_GROUPS):
        print(f"  *** SHORT: net carries {names}")
        fails += 1

print("NETS OK" if fails == 0 else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)

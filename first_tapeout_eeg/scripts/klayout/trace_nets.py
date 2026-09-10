#!/usr/bin/env python3
"""Union-find net tracer for the full2 GDS (debugging LVS shorts).

Usage: trace_nets.py <gds> <topcell> probe x,y [x,y ...]
       trace_nets.py <gds> <topcell> dump x0 y0 x1 y1   # nets in window

Connectivity: m1/via/m2/via2/m3/via3/m4 (flattened).  via3 shapes that
overlap capm are EXCLUDED (MIM plates would falsely merge m3<->m4).
"""
import sys
from collections import defaultdict
import klayout.db as kdb

GDS, TOP = sys.argv[1], sys.argv[2]
MODE = sys.argv[3]

ly = kdb.Layout()
ly.read(GDS)
top = ly.cell(TOP)
top.flatten(True)
dbu = ly.dbu

SPECS = {"m1": (68, 20), "via1": (68, 44), "m2": (69, 20), "via2": (69, 44),
         "m3": (70, 20), "via3": (70, 44), "m4": (71, 20)}

regions = {}
for name, spec in SPECS.items():
    r = kdb.Region(top.begin_shapes_rec(ly.layer(*spec)))
    r.merge()
    regions[name] = r
capm = kdb.Region(top.begin_shapes_rec(ly.layer(89, 44))).merged()
regions["via3"] = regions["via3"] - capm   # MIM via3 fields are not wires

polys = []   # (layer_name, kdb.Polygon)
for name, r in regions.items():
    for p in r.each():
        polys.append((name, p))
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

# spatial hash
CELL = int(50 / dbu)
grid = defaultdict(list)
for i, (n, p) in enumerate(polys):
    bb = p.bbox()
    for gx in range(bb.left // CELL, bb.right // CELL + 1):
        for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
            grid[(n, gx, gy)].append(i)

CONNECT = (("m1", "via1"), ("via1", "m2"), ("m2", "via2"), ("via2", "m3"),
           ("m3", "via3"), ("via3", "m4"))
for a, b in CONNECT:
    for i, (na, pa) in enumerate(polys):
        if na != a:
            continue
        bb = pa.bbox()
        seen = set()
        for gx in range(bb.left // CELL, bb.right // CELL + 1):
            for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
                for j in grid.get((b, gx, gy), ()):
                    if j in seen:
                        continue
                    seen.add(j)
                    qb = polys[j][1].bbox()
                    if bb.overlaps(qb) and not (kdb.Region(pa) & kdb.Region(polys[j][1])).is_empty():
                        union(i, j)

def net_at(x, y):
    pt = kdb.Point(int(x / dbu), int(y / dbu))
    for i, (n, p) in enumerate(polys):
        if p.bbox().contains(pt) and p.inside(pt):
            root = find(i)
            members = [(nn, pp.bbox()) for k, (nn, pp) in enumerate(polys)
                       if find(k) == root]
            return root, members
    return None, []

if MODE == "probe":
    pts = [tuple(map(float, a.split(","))) for a in sys.argv[4:]]
    roots = {}
    for x, y in pts:
        root, members = net_at(x, y)
        if root is None:
            print(f"({x},{y}): no metal")
            continue
        roots.setdefault(root, []).append((x, y))
        tb = kdb.Box()
        for n, b in members:
            tb += b
        print(f"({x},{y}): net#{root} layers={sorted(set(n for n,_ in members))} "
              f"shapes={len(members)} bbox=({tb.left*dbu:.1f},{tb.bottom*dbu:.1f},"
              f"{tb.right*dbu:.1f},{tb.top*dbu:.1f})")
    rl = list(roots)
    for i in range(len(rl)):
        for j in range(i + 1, len(rl)):
            print(f"{roots[rl[i]]} vs {roots[rl[j]]}: "
                  f"{'*** SAME NET ***' if rl[i] == rl[j] else 'different'}")
elif MODE == "dump":
    x0, y0, x1, y1 = map(float, sys.argv[4:8])
    box = kdb.Box(int(x0 / dbu), int(y0 / dbu), int(x1 / dbu), int(y1 / dbu))
    seen = defaultdict(set)
    for i, (n, p) in enumerate(polys):
        if p.bbox().overlaps(box):
            seen[find(i)].add(n)
    for r, layers in seen.items():
        members = [(n, p.bbox()) for k, (n, p) in enumerate(polys) if find(k) == r]
        tb = kdb.Box()
        for n, b in members:
            tb += b
        print(f"net#{r}: layers={sorted(layers)} shapes={len(members)} "
              f"bbox=({tb.left*dbu:.1f},{tb.bottom*dbu:.1f},{tb.right*dbu:.1f},{tb.top*dbu:.1f})")

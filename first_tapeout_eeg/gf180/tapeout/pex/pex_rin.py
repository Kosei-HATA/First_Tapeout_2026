#!/usr/bin/env python3
"""Wiring resistance of the electrode signal path (tracker D6), from the chip core layout
(the LVS database of eeg_core, gf180/tapeout/layout/runs/chip_top/eeg_core.lvsdb) with
the KLayout R extractor (klayout.pex), per side, in three sections in series:

  E  ELP / ELN: from the core's pad connections (two pads per electrode, tied) through
     the Metal5/Metal4 straps, the input chopper's spines, its Metal4 straps and
     Metal3/Metal2 lanes, to the Metal1 pillars on the finger sources/drains;
  W  AFE.WP / WN: from those pillars through the chopper's lanes and Metal5 stripes, the
     Cin bottom-plate bus and spines, to the Metal4 bottom plates of the 32 Cin units;
  T  AFE.INP / INN: from the 32 Cin top plates (their Metal5) through the top-plate bus,
     the core's INP / INN stub and its gate wiring (Metal4..Metal1, contacts, poly) to
     the channels of the input-pair fingers.

The thermal noise of a resistive network in the signal path is that of one resistor
R_eff = P / I^2 = sum_k R_k (I_k / I)^2 (the power it dissipates for a current I over
I^2), with the current split of the terminations (by reciprocity, for T: the weights
with which the amplifier senses its gates). E and W: each chopper finger carries the
same current within its kind, NMOS : PMOS by the on-conductance of one finger at
mid-rail (W 10 um, L 0.28 um: 3.06 mS and 0.657 mS, typical; 70 % of the current in the
NMOS fingers); each pillar carries one finger's current in either chopper phase (the
commutator ring EP -CIA- WP -CIB- EN -CIA- WN -CIB- EP shares each S/D region between a
phase-A and a phase-B finger); each Cin unit takes the same current (60 kohm at 128 kHz
against ohms of metal). T: each input-pair finger by its gm (typical operating point:
NMOS pair 142 mS over 1024 fingers of 20 um, PMOS pair 184 mS over 2048, per side).
E and W add to the source resistance and T to the amplifier's input like the TG
on-resistance: each is in series with the signal, input-referred one to one.

Conductors: --algo square (SquareCounting, the default) or tess (Tesselation, a finite-
element mesh of triangles of at most 4 um2). On wires and narrow buses they agree (AFE.INP:
71.6 ohm against 70.3 / 71.1 ohm with 4 / 1 um2 triangles); on wide sheets fed from a point
SquareCounting misses the spreading (a Metal3 sheet of 860 x 420 um from a corner to 8 feet:
0.059 against 0.13 ohm), so layouts with planes are measured with tess.

Sheet and via resistances: magic's gf180mcuD tech, variant () and the high corner
(hrhc): Metal1-4 90 (104) mohm/sq, Metal5 40 (49) mohm/sq, via1-4 4.5 (15) ohm per
0.26 um cut, poly 7.3 (15) ohm/sq, poly contact 8 (15) ohm per 0.22 um cut.

--afe measures on the AFE block alone (gf180/tapeout/layout/runs/afe_top/afe_top.lvsdb,
AFE coordinates), for checking a new AFE layout before the chip is assembled: E then starts
where the chip's pad straps meet the chopper's spines (the y bands of AFE_STRAP, as the chip
of 10/23 places them) instead of at the core's pad connections, so it leaves out the straps
themselves (0.04 / 0.05 ohm).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/pex_rin.py [--corner typ|high] [--nets ELP AFE.WP ...] [--afe]
       [--algo square|tess]
"""
import argparse
import os
import time
from collections import defaultdict

import numpy as np
import klayout.db as kdb
import klayout.pex as kpex
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
LVSDB = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "chip_top", "eeg_core.lvsdb")
LVSDB_AFE = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "afe_top", "afe_top.lvsdb")
AFE_ORIGIN = (482.0, 542.0)    # the AFE's place in the core (um)
# where the pad straps meet the chopper's spines, AFE coordinates (um): ELP's straps overlap
# the EP spine (x 2..14), ELN's cross under it on Metal4 to the EN spine (x 16..28)
AFE_STRAP = {"ELP": [(2.0, 772.34, 14.0, 815.66), (2.0, 913.34, 14.0, 956.66)],
             "ELN": [(16.0, 490.34, 28.0, 533.66), (16.0, 631.34, 28.0, 674.66)]}
# LVS layers (gf180mcu.lvs): conductors (Metal4 / Metal5 inside the MIM marker are l25 /
# l26) and cuts (l8 contact, here only the poly contacts of the gate net)
COND = {"po": ["l12"], "m1": ["l13"], "m2": ["l15"], "m3": ["l17"], "m4": ["l20", "l25"], "m5": ["l23", "l26"]}
VIAS = {"co": ("l8", "po", "m1"), "v1": ("l14", "m1", "m2"), "v2": ("l16", "m2", "m3"), "v3": ("l19", "m3", "m4"),
        "v4": ("l22", "m4", "m5")}
NWELL = "l6"
SHEET = {"typ": {"po": 7.3, "m1": 0.090, "m2": 0.090, "m3": 0.090, "m4": 0.090, "m5": 0.040, "co": 8.0, "via": 4.5},
         "high": {"po": 15.0, "m1": 0.104, "m2": 0.104, "m3": 0.104, "m4": 0.104, "m5": 0.049, "co": 15.0, "via": 15.0}}
CUT = {"co": 0.22 * 0.22, "via": 0.26 * 0.26}
G_N, G_P = 3.063e-3, 0.657e-3        # S per TG finger (ngspice, typical, 1 mV across at 1.65 V)
GM_N, GM_P = 0.1422 / 1024, 0.1841 / 2048   # S per input-pair finger (typical operating point)
K_BOLTZ, TEMP = 1.380649e-23, 300.0
BW = 99.5
SECTION = {"ELP": "E", "ELN": "E", "AFE.WP": "W", "AFE.WN": "W", "AFE.INP": "T", "AFE.INN": "T"}
SIDE = {"ELP": "P", "AFE.WP": "P", "AFE.INP": "P", "ELN": "N", "AFE.WN": "N", "AFE.INN": "N"}


def net_geometry(lvs, net):
    """{layer key: Region} of one layout net (merged)."""
    geo = {}
    for k, ls in COND.items():
        r = kdb.Region()
        for l in ls:
            r += lvs.shapes_of_net(net, lvs.layer_by_name(l), True)
        geo[k] = r.merged()
    for k, (l, _, _) in VIAS.items():
        geo[k] = lvs.shapes_of_net(net, lvs.layer_by_name(l), True).merged()
    return geo


def network(geo, ports, corner, tess=()):
    """R network of the geometry; ports: [(layer key, Polygon)]. Returns (node count,
    [(a, b, R, key)] with key the conductor or cut of the element, {port index: node},
    {node: location (um)}). tess: the conductors meshed with the Tesselation algorithm
    (the others by SquareCounting)."""
    sh = SHEET[corner]
    keys = list(COND) + list(VIAS)
    lid = {k: i for i, k in enumerate(keys)}
    tech = kpex.RExtractorTech()
    for k in COND:
        c = kpex.RExtractorTechConductor()
        c.layer, c.resistance = lid[k], sh[k]
        if k in tess:
            c.algorithm = kpex.RExtractorTechConductor.Tesselation
            c.triangulation_max_area = 4.0
        else:
            c.algorithm = kpex.RExtractorTechConductor.SquareCounting
        tech.add_conductor(c)
    for k, (_, lo, hi) in VIAS.items():
        v = kpex.RExtractorTechVia()
        v.cut_layer, v.bottom_conductor, v.top_conductor = lid[k], lid[lo], lid[hi]
        v.resistance = (sh["co"] * CUT["co"]) if k == "co" else (sh["via"] * CUT["via"])
        v.merge_distance = 0.2
        tech.add_via(v)
    pp, seq, cnt = {}, {}, {}
    for g, (k, poly) in enumerate(ports):
        li = lid[k]
        pp.setdefault(li, []).append(poly)
        seq[(li, cnt.get(li, 0))] = g
        cnt[li] = cnt.get(li, 0) + 1
    net = kpex.RNetExtractor(0.001).extract(tech, {lid[k]: r for k, r in geo.items() if not r.is_empty()}, {}, pp)
    nodes, lay, loc, port_node = {}, {}, {}, {}
    for n in net.each_node():
        i = len(nodes)
        nodes[n.object_id()] = i
        lay[i] = keys[n.layer()] if n.layer() < len(keys) else "?"
        b = n.location()
        loc[i] = ((b.left + b.right) / 2, (b.bottom + b.top) / 2)
        if n.type() == kpex.RNodeType.PolygonPort:
            port_node[seq[(n.layer(), n.port_index())]] = i
    els = []
    for e in net.each_element():
        a, b = nodes[e.a().object_id()], nodes[e.b().object_id()]
        k = lay[a] if lay[a] == lay[b] else "-".join(sorted((lay[a], lay[b])))
        els.append((a, b, e.resistance(), k))
    return len(nodes), els, port_node, loc


def cond(r):
    """Conductance of an element, sign kept: the Tesselation algorithm (a finite-element
    mesh) gives negative couplings for obtuse triangles, which belong to the solution."""
    return 1.0 / r if abs(r) > 1e-12 else 1e12


def solve(n, els, inj, ties=()):
    """Node voltages for current injections {node: A} (sum 0) with ideal shorts `ties`;
    returns (power = sum I V, voltage per node)."""
    rep = list(range(n))
    for grp in ties:
        for x in grp[1:]:
            rep[x] = grp[0]
    uniq = sorted(set(rep))
    m = {u: i for i, u in enumerate(uniq)}
    rows, cols, vals = [], [], []
    for a, b, r, _ in els:
        a, b = m[rep[a]], m[rep[b]]
        if a == b:
            continue
        g = cond(r)
        rows += [a, b, a, b]
        cols += [a, b, b, a]
        vals += [g, g, -g, -g]
    N = len(uniq)
    G = coo_matrix((vals, (rows, cols)), shape=(N, N)).tocsr()
    I = np.zeros(N)
    for node, cur in inj.items():
        I[m[rep[node]]] += cur
    ref = m[rep[min(inj, key=lambda k: inj[k])]]
    keep = np.array([i for i in range(N) if i != ref])
    V = np.zeros(N)
    V[keep] = spsolve(G[keep][:, keep], I[keep])
    return float(I @ V), np.array([V[m[rep[i]]] for i in range(n)])


def pillars(geo, wells):
    """Metal1 pillars on the chopper fingers' S/D regions: [(polygon, is PMOS)]."""
    out = []
    for p in geo["m1"].each():
        b = p.bbox()
        if b.height() > 5000 and b.width() < 2000:  # 10 um fingers, sub-um pillars (dbu 1 nm)
            out.append((p, not (kdb.Region(p) & wells).is_empty()))
    return out


def gate_channels(geo):
    """Input-pair fingers of the gate net (poly 20.96 um tall: 1.5 um NMOS, 0.36 um PMOS):
    [(convex port inside the poly over the channel, is NMOS)]."""
    out = []
    for p in geo["po"].each():
        b = p.bbox()
        if 20000 < b.height() < 22000 and b.width() <= 1600:
            out.append((kdb.Polygon(kdb.Box(b.left, b.bottom + 600, b.right, b.top - 600)), b.width() > 1000))
    return out


def block_of(x, y, origin=AFE_ORIGIN):
    """Region of a point (um; core coordinates, or AFE ones with origin (0, 0)): AFE parts
    by the placement of afe_lay.py (input chopper x 2..190, core band y 422..1025)."""
    xa, ya = x - origin[0], y - origin[1]
    if xa < 0:
        return "pad straps"
    if xa < 192.0 and 422.0 <= ya <= 1025.0:
        return "input chopper"
    if 422.0 <= ya <= 1025.0:
        return "core band"
    return "Cin arrays and buses"


def section(lvs, xref, sc, wells, name, corner, afe=False, algo="square"):
    """R_eff of one net (one section of one side), with the power split by element kind
    and by region. afe: the AFE block's lvsdb (net names without the AFE. prefix)."""
    net = xref.other_net_for(sc.net_by_name(name.replace("AFE.", "") if afe else name))
    geo = net_geometry(lvs, net)
    sec = SECTION[name]
    src, snk = [], []
    if sec in ("E", "W"):
        for p, pm in pillars(geo, wells):
            src.append(("m1", p, G_P if pm else G_N))
    if sec == "E" and afe:
        for x1, y1, x2, y2 in AFE_STRAP[name]:
            snk.append(("m5", kdb.Polygon(kdb.Box(int(x1 * 1000), int(y1 * 1000), int(x2 * 1000), int(y2 * 1000))), 1.0))
    elif sec == "E":
        edge = kdb.Region(kdb.Box(0, 0, 380000, 3000000))   # the core's west edge: pad connections
        for p in (geo["m5"] & edge).merged().each():
            snk.append(("m5", kdb.Polygon(p.bbox()), 1.0))
    elif sec == "W":
        for p in lvs.shapes_of_net(net, lvs.layer_by_name("l25"), True).merged().each():
            if p.area() > 9.0e9:                            # Cin bottom plates (~9940 um2)
                snk.append(("m4", kdb.Polygon(p.bbox()), 1.0))
    else:
        for p in lvs.shapes_of_net(net, lvs.layer_by_name("l26"), True).merged().each():
            if p.area() > 9.0e9:                            # Metal5 over the Cin top plates
                src.append(("m5", kdb.Polygon(p.bbox()), 1.0))
        for p, isn in gate_channels(geo):
            snk.append(("po", p, GM_N if isn else GM_P))
    ports = [(k, p) for k, p, _ in src + snk]
    t = time.time()
    # tess: mesh every conductor; KLayout's triangulation stops on some shapes (an internal
    # error), then only the plane layers, then Metal5 only, then none
    tries = [tuple(COND), ("m3", "m4", "m5"), ("m5",), ()] if algo == "tess" else [()]
    for tess in tries:
        try:
            n, els, pn, loc = network(geo, ports, corner, tess)
            break
        except RuntimeError:
            continue
    used = "+".join(tess) if tess else "square"
    inj = defaultdict(float)
    ws, wk = sum(w for _, _, w in src), sum(w for _, _, w in snk)
    for i, (_, _, w) in enumerate(src):
        inj[pn[i]] += w / ws
    for j, (_, _, w) in enumerate(snk):
        inj[pn[len(src) + j]] -= w / wk
    ties = [[pn[len(src) + j] for j in range(len(snk))]] if sec == "E" else ()
    p, V = solve(n, els, dict(inj), ties)
    kind, region = defaultdict(float), defaultdict(float)
    for a, b, r, k in els:
        q = (V[a] - V[b]) ** 2 * cond(r)
        kind[k] += q
        region[block_of(*loc[a], origin=(0.0, 0.0) if afe else AFE_ORIGIN)] += q
    return dict(name=name, reff=p, nsrc=len(src), nsnk=len(snk), nodes=n, els=len(els), t=time.time() - t,
                kind=dict(kind), region=dict(region), used=used)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", choices=sorted(SHEET), default="typ")
    ap.add_argument("--nets", nargs="+", default=list(SECTION))
    ap.add_argument("--afe", action="store_true", help="the AFE block's lvsdb (E from the strap landings)")
    ap.add_argument("--algo", choices=["square", "tess"], default="square", help="conductor algorithm")
    a = ap.parse_args()
    t = time.time()
    lvs = kdb.LayoutVsSchematic()
    lvsdb = LVSDB_AFE if a.afe else LVSDB
    lvs.read(lvsdb)
    xref = lvs.xref()
    sc = next(lvs.reference.each_circuit_top_down())
    wells = kdb.Region(lvs.internal_top_cell().begin_shapes_rec(lvs.layer_of(lvs.layer_by_name(NWELL))))
    print(f"read {os.path.relpath(lvsdb, REPO)} in {time.time() - t:.0f} s; corner {a.corner}, {a.algo}")
    res = {}
    for name in a.nets:
        r = section(lvs, xref, sc, wells, name, a.corner, a.afe, a.algo)
        res[name] = r
        print(f"{name} ({SECTION[name]}): {r['nsrc']} sources, {r['nsnk']} sinks, {r['nodes']} nodes, "
              f"{r['els']} resistors ({r['t']:.0f} s, tess on {r['used']}): R_eff {r['reff'] * 1e3:.0f} mohm", flush=True)
        print("    by kind (mohm): " + ", ".join(f"{k} {v * 1e3:.0f}" for k, v in
                                               sorted(r["kind"].items(), key=lambda kv: -kv[1]) if v * 1e3 >= 1))
        print("    by region (mohm): " + ", ".join(f"{k} {v * 1e3:.0f}" for k, v in
                                                 sorted(r["region"].items(), key=lambda kv: -kv[1])))
    tot = 0.0
    for side in ("P", "N"):
        parts = {SECTION[n]: res[n]["reff"] for n in res if SIDE[n] == side}
        s = sum(parts.values())
        tot += s
        print(f"side {side}: {s * 1e3:.0f} mohm (" + ", ".join(f"{k} {v * 1e3:.0f}" for k, v in sorted(parts.items()))
              + ")")
    vn = np.sqrt(4 * K_BOLTZ * TEMP * tot * BW)
    print(f"both sides {tot * 1e3:.0f} mohm: {vn * 1e9:.2f} nVrms over 0.5-100 Hz, electrode-referred ({a.corner})")


if __name__ == "__main__":
    main()

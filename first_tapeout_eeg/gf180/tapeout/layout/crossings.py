#!/usr/bin/env python3
"""Crossings between sensitive nets and switching nets, from a KLayout LVS database (r12,
11/13). For every victim net V and aggressor net D: where a shape of V and a shape of D
overlap on two different metals, the part with no conductor of any net on a metal between
them (unshielded), its plate capacitance with the Magic tech's area coefficients, and where
it is; and same-metal edges of V and D closer than --side um (parallel run length).

The LVS database's layers are anonymous: each is matched to a GDS metal by comparing the
shapes in a window of the top cell.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/crossings.py <lvsdb> <gds>
         --victims I1P,I1N,O1P,O1N --aggressors 'SEL1_.*,DAC_CLK,MCLK' [--side 1.0]
         [--shift dx dy] [--top N]
(--shift: add to the printed coordinates, e.g. the block's origin on the die)
"""
import argparse
import collections
import re
import time
import klayout.db as kdb

GDS_METALS = {"metal1": (34, 0), "metal2": (36, 0), "metal3": (42, 0), "metal4": (46, 0), "metal5": (81, 0)}
ORDER = ["metal1", "metal2", "metal3", "metal4", "metal5"]
# Magic gf180mcuD.tech defaultoverlap between metals (aF/um^2; the 5-metal stack, the PEX's)
AREA_CAP = {("metal1", "metal2"): 59.027, ("metal1", "metal3"): 20.238, ("metal1", "metal4"): 12.212,
            ("metal1", "metal5"): 8.142, ("metal2", "metal3"): 59.027, ("metal2", "metal4"): 20.238,
            ("metal2", "metal5"): 11.067, ("metal3", "metal4"): 59.027, ("metal3", "metal5"): 17.276,
            ("metal4", "metal5"): 39.351}


def match_layers(lvs, gds):
    """{metal name: lvsdb layer index}: the lvsdb layer whose shapes in a window equal the GDS metal's."""
    ly = kdb.Layout()
    ly.read(gds)
    top = ly.top_cell()
    bb = top.bbox()
    out = {}
    for fx, fy in ((0.5, 0.5), (0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75), (0.1, 0.5), (0.9, 0.5)):
        cx, cy = int(bb.left + fx * bb.width()), int(bb.bottom + fy * bb.height())
        w = kdb.Box(cx - 40000, cy - 40000, cx + 40000, cy + 40000)
        want = {}
        for m, (l, d) in GDS_METALS.items():
            li = ly.find_layer(l, d)
            if m not in out and li is not None:
                g = (kdb.Region(top.begin_shapes_rec_touching(li, w)) & kdb.Region(w)).merged()
                if not g.is_empty():
                    want[m] = g
        if not want:
            continue
        for i in lvs.layer_indexes():
            if i in out.values():
                continue
            r = (lvs.layer_by_index(i) & kdb.Region(w)).merged()
            if r.is_empty():
                continue
            for m, g in want.items():
                if m not in out and (r ^ g).area() < 1e-3 * g.area():
                    out[m] = i
                    break
        if len(out) == len(GDS_METALS):
            break
    missing = [m for m in ORDER if m not in out]
    if missing:
        raise RuntimeError(f"no lvsdb layer matches {missing}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lvsdb")
    ap.add_argument("gds")
    ap.add_argument("--victims", required=True)
    ap.add_argument("--aggressors", required=True, help="comma-separated regexes on schematic net names")
    ap.add_argument("--side", type=float, default=1.0)
    ap.add_argument("--shift", type=float, nargs=2, default=(0.0, 0.0))
    ap.add_argument("--top", type=int, default=6, help="locations printed per victim / aggressor group")
    a = ap.parse_args()
    t0 = time.time()
    lvs = kdb.LayoutVsSchematic()
    lvs.read(a.lvsdb)
    L = match_layers(lvs, a.gds)
    dbu = lvs.internal_layout().dbu
    regs = {m: lvs.layer_by_index(i) for m, i in L.items()}
    xref = lvs.xref()
    sch = lvs.reference
    top = [c for c in sch.each_circuit_top_down()][0]
    print(f"{a.lvsdb}: top {top.name}, layers {L}, read in {time.time() - t0:.0f} s")
    names = {n.name: n for n in top.each_net() if n.name}
    pats = [re.compile(p + "$") for p in a.aggressors.split(",")]
    aggs = sorted(n for n in names if any(p.match(n) for p in pats))
    vics = a.victims.split(",")

    def shapes(name):
        net = xref.other_net_for(names[name])
        if net is None:
            return None
        return {m: lvs.shapes_of_net(net, r, True).merged() for m, r in regs.items()}

    allm = {m: r.merged() for m, r in regs.items()}
    V = {v: shapes(v) for v in vics}
    for v in [v for v, sh in V.items() if sh is None]:
        print(f"({v}: no layout net)")
        del V[v]
    vics = list(V)
    group = lambda n: next(p.pattern[:-1] for p in pats if p.match(n))
    res = collections.defaultdict(lambda: collections.defaultdict(float))
    locs = collections.defaultdict(list)
    side = collections.defaultdict(float)
    sx, sy = a.shift
    for d in aggs:
        D = shapes(d)
        if D is None:
            print(f"({d}: no layout net)")
            continue
        for v in vics:
            for i, lv in enumerate(ORDER):
                for j, la in enumerate(ORDER):
                    if i == j or V[v][lv].is_empty() or D[la].is_empty():
                        continue
                    ov = V[v][lv] & D[la]
                    if ov.is_empty():
                        continue
                    lo, hi = sorted((i, j))
                    between = kdb.Region()
                    for k in range(lo + 1, hi):
                        between += allm[ORDER[k]]
                    un = ov - between if hi - lo > 1 else ov
                    key = (v, group(d))
                    pair = tuple(sorted((lv, la), key=ORDER.index))
                    res[key][(lv, la, "all")] += ov.area() * dbu * dbu
                    res[key][(lv, la, "open")] += un.area() * dbu * dbu
                    for p in un.each():
                        b = p.bbox().to_dtype(dbu)
                        locs[key].append((p.area() * dbu * dbu * AREA_CAP[pair], d, lv, la, b))
            for m in ORDER:
                if V[v][m].is_empty() or D[m].is_empty():
                    continue
                ep = V[v][m].separation_check(D[m], int(round(a.side / dbu)))
                side[(v, group(d), m)] += sum(e.first.length() for e in ep.each()) * dbu
    print(f"done in {time.time() - t0:.0f} s; areas in um^2, C in fF (plate only)")
    for (v, gname), r in sorted(res.items()):
        tot = 0.0
        parts = []
        for (lv, la, kind), ar in sorted(r.items()):
            if kind != "open" or ar <= 0:
                continue
            c = ar * AREA_CAP[tuple(sorted((lv, la), key=ORDER.index))] * 1e-3
            tot += c
            parts.append(f"{v}:{lv[-1]}/{gname}:{la[-1]} {ar:.2f} (all {r[(lv, la, 'all')]:.2f}) {c:.3f} fF")
        print(f"{v} x {gname}: unshielded plate C {tot:.3f} fF  |  " + "; ".join(parts))
        for c, d, lv, la, b in sorted(locs[(v, gname)], key=lambda x: -x[0])[:a.top]:
            print(f"    {d:>10s} {v}:{lv} under/over {la}: {c * 1e-3:.4f} fF at x {b.left + sx:.2f}..{b.right + sx:.2f}"
                  f" y {b.bottom + sy:.2f}..{b.top + sy:.2f}")
    for (v, gname, m), ln in sorted(side.items()):
        if ln > 0:
            print(f"side {m}: {v} x {gname}: {ln:.1f} um of edges within {a.side} um")


if __name__ == "__main__":
    main()

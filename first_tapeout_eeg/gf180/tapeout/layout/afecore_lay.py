#!/usr/bin/env python3
"""Layout of eeg_afe_core (gf180/tapeout/afe/eeg_afe.spice, tracker E3): the AFE's
current-reuse input stage with regulated cascodes, shaped for the AFE's core band
(about 790 x 600 um between the two Cin arrays).

Two columns of guarded multi-strip cells (analog.multi_strip_cell), each device split
into strips of about the column width. The pairs, tails and cascodes use W 20 um fingers
(half the fingers of the netlist's W 10 um m; LVS combines them; about 10 % less area
than W 10 um strips), the boosters W 10 um:
  column N (west), bottom to top: NMOS boosters (XGNCPB / XGNCNB L4, XGPCPL / XGPCNL L8,
    XBLND), tail XNT (L1, 768 fingers), input pair XN_P / XN_N (L1.5, 2048 + 2048, A B B A
    by finger pairs, every other strip B A A B), cascodes XNC_P / XNC_N (L1, interleaved)
  column P (east), bottom to top: PMOS boosters (XGNCPL / XGNCNL L8, XGPCPB / XGPCNB L2,
    XBLPD), tail XPT (L2, 2048), input pair XP_P / XP_N (L0.28, 4096 + 4096), cascodes
    XPC_P / XPC_N (L1)
The branch current (9.6 mA per side, 19.2 mA in the tails) runs on Metal3 lanes over
each column (blocks.lanes; 12 lanes of 1.2 um per branch net, 24 for SN, SP, VDD, VSS;
0.67 mA per um of Metal3). The output nodes leave the cascodes of both columns at the
top into a band above all cells: one trunk per net (OUTP Metal2, OUTN Metal3, 11 um) to
the east edge as the OUTP / OUTN ports, under a Metal4 shield over the band and the whole
cascode cells (VSS on the N column's side, VDD on the P column's; the router reaches the
cascodes' gate bars from below), since the AFE's INP Metal5 runs over the cascodes to the
top edge (tracker D6). The N boosters share strips, so that column N stays low enough for
the band. VSS and VDD come in from above through Metal4 bar segments over the supply
lanes of the two tails (via3 on the lanes), for the AFE's Metal5 supply rails.

The input-pair gates INP / INN are hand-drawn (their wiring resistance is in series with
the signal, input-referred one to one; tracker D6, documentation/gf180_pex_20261023.md):
  - straps: vertical Metal4 straps over each pair, INP and INN side by side, cut at the
    supply lanes (so that INN can pass the tail between them); Metal5 on the straps where
    the AFE's supply rails leave it free (above RAIL_TOP);
  - taps: on every strip, Metal2 pads below the INP gate bar and above the INN bar, via2
    to Metal3 islands between the lanes, via3 to the strap of the net;
  - INP: Metal5 from the straps up over the cascodes to the top edge (the AFE joins it to
    the Cin_P top-plate bus along the core's width);
  - INN: Metal4 straps on through the tails between the supply segments, via4 below the
    tails onto Metal5 that runs down over the boosters to the bottom edge (joined to the
    Cin_N bus the same way).
Ports: INP (Metal5, top edge), INN (Metal5, bottom edge), VBN, VBP, BLP, BLN on the east
edge. The other gates and the boosters' nets: route.Router.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/afecore_lay.py [--drc] [--lvs]
"""
import argparse
import math
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import fets as f
import route
from ota_lay import pair_seq, dev_seq

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
SW = 2.4
TN, TP = 300.0, 400.0                 # target strip lengths of the two columns (um)
WF = 20.0                             # finger width of the pairs, tails and cascodes
HEIGHT = 588.36                       # the core's height (the AFE's core band between the Cin arrays)
TRUNK_W = 11.0                        # output trunks over the cascodes: OUTP Metal2, OUTN Metal3
SHIELD_OPEN = 1.0                     # cascode cells: shield from this far above their bottom
PWR_W, N_PWR = 6.0, 5                 # rows of Metal4 supply segments over each tail
RAIL_GROW = {"VSS": 0.0, "VDD": 10.0}  # the AFE's Metal5 rails: supply rows grown by this (afe_lay)
AVDD_RAIL_X0 = 304.0                  # the AFE's AVDD rails start here (core x, between the columns)
STRAP_W = 11.0                        # target width of the INP / INN straps
STRAP_GAP = 0.6                       # Metal4 / Metal5 between straps (MT.2b 0.6)
SEG_KEEP = 0.35                       # Metal4 between a supply segment and an INN strap (M4.2b 0.3)
LANE_KEEP = 0.28                      # Metal3 island to a lane (M3.2a)
WIDE_KEEP = 0.31                      # wide Metal3 (over 10 um both ways) to a lane (M3.2b 0.3)
INP_PAD, INN_PAD = 4.0, 3.4           # tap pads (Metal2): below the INP gate bar, above the INN bar
ROUTER_X = {"N": 5.0, "P": 9.0}       # router access left free on the east of each tail (VBN, VBP)
EDGE_BAR = 4.0                        # Metal5 bars joining the INP strips (top edge), INN (bottom)
STUB_X = 26.0                         # the AFE's offdac_p INP stub lands on the INP bar west of here


def split(total, per):
    """total units in strips of at most per units, as evenly as possible"""
    n = max(1, math.ceil(total / per))
    base, extra = divmod(total, n)
    return [base + 1 if k < extra else base for k in range(n)]


def pair_strips(da, ga, db, gb, s, fingers, l, target, straps, w=10.0):
    """fingers: count at W 10 um (the netlist's m); drawn with w um fingers"""
    fingers = int(round(fingers * 10.0 / w))
    per = max(1, int((target - 2.0) / (8 * (l + f.SD_IN))))
    return [dict(w=w, l=l, seq=pair_seq(da, ga, db, gb, s, n4, start_b=(k % 2 == 1)),
                 gates={ga: ("t", 0), gb: ("t", 1)}, order=[s, da, db], straps=straps)
            for k, n4 in enumerate(split(fingers // 8, per))]


def dev_strips(d, gt, s, fingers, l, target, straps=None, order=None, w=10.0):
    """fingers: count at W 10 um; drawn with w um fingers"""
    fingers = int(round(fingers * 10.0 / w))
    per = max(2, int((target - 2.0) / (l + f.SD_IN)) // 2 * 2)
    return [dict(w=w, l=l, seq=dev_seq(d, gt, s, n), order=order or [s, d], straps=straps)
            for n in split(fingers, per)]


def interleave(a, b):
    out = []
    for k in range(len(a)):
        out += [a[k], b[k]] if k % 2 == 0 else [b[k], a[k]]
    return out


def cells(b):
    C = {}
    C["npair"] = an.multi_strip_cell(b, "afec_npair", "n", pair_strips(
        "DNP", "INP", "DNN", "INN", "SN", 4096, 1.5, TN, {"SN": 4, "DNP": 4, "DNN": 4}, WF), bulk="VSS")
    C["ntail"] = an.multi_strip_cell(b, "afec_ntail", "n", dev_strips(
        "SN", "VBN", "VSS", 768, 1.0, TN, {"VSS": 6, "SN": 6}, w=WF), bulk="VSS")
    C["ncas"] = an.multi_strip_cell(b, "afec_ncas", "n", interleave(
        dev_strips("OUTN", "GNCP", "DNP", 512, 1.0, TN, {"DNP": 6, "OUTN": 6}, ["DNP", "OUTN"], WF),
        dev_strips("OUTP", "GNCN", "DNN", 512, 1.0, TN, {"DNN": 6, "OUTP": 6}, ["DNN", "OUTP"], WF)), bulk="VSS")
    # NMOS boosters in four strips over the column's width (the column's top keeps a band
    # free for the output trunks): XGNCPB / XGNCNB on their common VSS like a pair (32 + 32
    # fingers, L4), then XGPCPL / XGPCNL / XBLND, all gated by BLN on VSS (40 + 40 + 8 fingers,
    # L8), by two-finger units sharing a drain, A B B A with the diode's units mid-strip
    nb = [dict(w=10.0, l=4.0, seq=pair_seq("GNCP", "DNP", "GNCN", "DNN", "VSS", 8),
               gates={"DNP": ("t", 0), "DNN": ("t", 1)}, order=["VSS", "GNCP", "GNCN"])]
    u = ["GPCP", "GPCN", "GPCN", "GPCP"] * 10
    for us in (u[0:6] + ["BLN"] * 2 + u[6:13], u[13:19] + ["BLN"] * 2 + u[19:26], u[26:40]):
        seq = ["VSS"]
        for d in us:
            seq += ["BLN", d, "BLN", "VSS"]
        nb.append(dict(w=10.0, l=8.0, seq=seq, order=["VSS", "GPCP", "GPCN"] + ["BLN"] * ("BLN" in us)))
    C["nboost"] = an.multi_strip_cell(b, "afec_nboost", "n", nb, bulk="VSS")
    C["ppair"] = an.multi_strip_cell(b, "afec_ppair", "p", pair_strips(
        "DPP", "INP", "DPN", "INN", "SP", 8192, 0.28, TP, {"SP": 4, "DPP": 4, "DPN": 4}, WF), bulk="VDD")
    C["ptail"] = an.multi_strip_cell(b, "afec_ptail", "p", dev_strips(
        "SP", "VBP", "VDD", 2048, 2.0, TP, {"VDD": 6, "SP": 6}, w=WF), bulk="VDD")
    C["pcas"] = an.multi_strip_cell(b, "afec_pcas", "p", interleave(
        dev_strips("OUTN", "GPCP", "DPP", 1024, 1.0, TP, {"DPP": 6, "OUTN": 6}, ["DPP", "OUTN"], WF),
        dev_strips("OUTP", "GPCN", "DPN", 1024, 1.0, TP, {"DPN": 6, "OUTP": 6}, ["DPN", "OUTP"], WF)), bulk="VDD")
    pb = []
    for d, gt, n, l in (("GNCP", "BLP", 64, 8.0), ("GNCN", "BLP", 64, 8.0), ("GPCP", "DPP", 128, 2.0),
                        ("GPCN", "DPN", 128, 2.0), ("BLP", "BLP", 8, 8.0)):
        pb += dev_strips(d, gt, "VDD", n, l, TP, order=["VDD", d])
    C["pboost"] = an.multi_strip_cell(b, "afec_pboost", "p", pb, bulk="VDD")
    return C


def minus(lo, hi, cuts):
    """The parts of [lo, hi] outside the intervals cuts."""
    out, x = [], lo
    for a, b in sorted(cuts):
        if b <= x or a >= hi:
            continue
        if a > x:
            out.append((x, a))
        x = max(x, b)
    if x < hi:
        out.append((x, hi))
    return out


def mslot_openings(plate, vias):
    """1 x 2 um openings (a Region) in a Metal4 plate wherever 30 x 30 um of it stay without
    a via (vias: grown by 0.2 um), as the deck's MSLOT4.1 sees it: 20 um apart over each
    such part, none on a via."""
    k = 15000
    opening = lambda r: r.sized(0, -k, 2).sized(-k, 0, 2).sized(0, k, 2).sized(k, 0, 2)
    holes = g.pya.Region()
    for _ in range(5):
        bad = opening(opening(plate - holes) - vias)
        if bad.is_empty():
            return holes
        for poly in bad.each():
            for t in poly.decompose_trapezoids():
                bb = t.bbox()
                nx, ny = max(1, round(bb.width() / 20000)), max(1, round(bb.height() / 20000))
                for i in range(nx):
                    for j in range(ny):
                        cx = bb.left + int((i + 0.5) * bb.width() / nx)
                        cy = bb.bottom + int((j + 0.5) * bb.height() / ny)
                        holes.insert(g.pya.Box(cx - 1000, cy - 500, cx + 1000, cy + 500))
        holes = holes.not_interacting(vias)
    raise RuntimeError("MSLOT4.1 openings did not converge")


def strap_plan(x_lo, x_hi, supply_x, sites):
    """INP / INN straps over a pair between x_lo and x_hi: the cells between the supply
    lanes (left edges supply_x, SEG_KEEP kept around each), each split into straps of about
    STRAP_W, the nets alternating west to east. Returns [[net, x1, x2, cell, tap sites]],
    the sites being the parts of the free Metal3 intervals `sites` inside the strap
    (at least two vias wide); straps without a site are left out."""
    cells = minus(x_lo, x_hi, [(x - SEG_KEEP, x + 1.2 + SEG_KEEP) for x in supply_x])
    out = []
    for c1, c2 in cells:
        w = c2 - c1
        if w < 4.0:
            continue
        k = max(1, round((w + STRAP_GAP) / (STRAP_W + STRAP_GAP)))
        sw = (w - (k - 1) * STRAP_GAP) / k
        for j in range(k):
            x1 = c1 + j * (sw + STRAP_GAP)
            x2 = x1 + sw
            st = [(max(a, x1), min(b, x2)) for a, b in sites if min(b, x2) - max(a, x1) >= 0.9]
            if st:
                out.append([None, x1, x2, (c1, c2), st])
    for k, s in enumerate(out):
        s[0] = ("INP", "INN")[k % 2]
    return out


def tile(x1, x2, avoid=(), w_max=28.0, gap=1.0):
    """Metal5 strips under 30 um (MSLOT5.1) over x1..x2, gap um apart, with the gaps
    placed outside the intervals `avoid` (straps of the strips' net that must not bridge
    two strips). Returns [(a, b)]."""
    out, a = [], x1
    while x2 - a > w_max:
        b, moved = a + w_max, True
        while moved:                           # a gap that would cut a strap goes west of it
            moved = False
            for p, q in avoid:
                if p < b + gap and q > b:
                    b, moved = p - gap, True
        if b - a < 4.0:
            raise ValueError(f"no room for a strip gap after x {a:.1f}")
        out.append((a, b))
        a = b + gap
    out.append((a, x2))
    return out


def gate_network(b, pd, lanes, supply, rows, rail_bot, rail_mid, rail_top, height):
    """Draw the INP / INN wiring (module doc). supply: {column: supply lane x list} (VSS
    over the N tail, VDD over the P tail), rows: {column: y of the supply rows}; Metal5
    stays below rail_bot (the AVSS rails cross the whole core), and above rail_mid (top of
    the AVSS rails) in the N column, above rail_top (AVDD rails) in the P column. Returns
    (fixed shapes [(layer, box, net)] for the router, via3 boxes, {column: INN pieces
    (x1, x2) through the tail}, {net: label point})."""
    fixed, vias3, pieces = [], [], {}
    inp_x, tops = [], {}
    y_tb = rail_bot - 7.24                         # INN Metal4 down to here, via4 above it
    for side, pk, tk in (("N", "NPAIR", "NTAIL"), ("P", "PPAIR", "PTAIL")):
        p, t = pd[pk], pd[tk]
        x_lo, x_hi = p.x + 0.4, p.x + p.cell.width - 0.4
        y_lo, top = p.y, p.y + p.cell.height
        tops[side] = top
        occupied = [(s[1] - LANE_KEEP, s[3] + LANE_KEEP) for segs in lanes.values() for s in segs
                    if s[1] < x_hi and s[3] > x_lo and s[2] < top and s[4] > y_lo]
        plan = strap_plan(x_lo, x_hi, supply[side], minus(x_lo, x_hi, occupied))
        # taps on every strip: Metal2 pad, via2, Metal3 island, via3 onto the strap
        for net, x1, x2, cell, sites in plan:
            for _, px1, py1, px2, py2 in p.pins[net]:
                ya, yb_ = (py2 - INP_PAD, py2) if net == "INP" else (py1, py1 + INN_PAD)
                for sa, sb in sites:
                    sa, sb = max(sa, px1), min(sb, px2)
                    if sb - sa < 0.9:
                        continue
                    b.vias_fit("via2", sa, ya, sb, yb_)
                    b.vias_fit("via3", sa, ya, sb, yb_)
                    vias3.append((sa, ya, sb, yb_))
                    fixed.append(("metal3", (sa, ya, sb, yb_), net))
        # straps: Metal4 over the pair, Metal5 on them (in the P column above rail_top, where
        # the AFE's AVDD rails cross; INP on to the top edge), via4 rows between the two
        for net, x1, x2, cell, sites in plan:
            m5y1 = max(rail_top if x2 > AVDD_RAIL_X0 - 0.6 else rail_mid, y_lo + 1.0)
            if net == "INP":
                m4 = (x1, y_lo + 1.0, x2, top + 1.0)
                m5 = (x1, m5y1, x2, height)
                inp_x.append((x1, x2))
            else:
                m4 = (x1, y_lo, x2, max(top + 0.5, max(q[2] for q in p.pins["INN"]) + INN_PAD))
                m5 = (x1, m5y1, x2, top)
            b.box("metal4", *m4)
            b.box("metal5", *m5)
            fixed.append(("metal4", m4, net))
            y = m5y1 + 0.5
            while y + 2.0 < min(m4[3], m5[3]) - 0.5:
                b.vias_fit("via4", x1, y, x2, y + 2.0)
                y += 11.5
        # INN through the tail: every strap cell, in pieces under 30 um cut in the gaps
        # between straps, from y_tb up to the pair (the INN straps go on from there); the
        # pieces are linked across the supply lanes where no supply row is (Metal4), and Metal3
        # strips in the free lane places under them add to it (via3 rows); the router keeps
        # the tail's east end (the tail's gate pins)
        t_hi = t.x + t.cell.width - ROUTER_X[side]
        groups = {}
        for s in plan:
            groups.setdefault(s[3], []).append(s)
        pcs = []
        for _, ss in sorted(groups.items()):
            run = []
            for s in ss + [None]:
                if s is not None and (not run or s[2] - run[0][1] <= 28.0):
                    run.append(s)
                    continue
                if min(run[-1][2], t_hi) - run[0][1] >= 2.0:
                    pcs.append((run[0][1], min(run[-1][2], t_hi)))
                run = [s] if s is not None else []
        for a, c in pcs:
            b.box("metal4", a, y_tb, c, y_lo + 0.5)
            fixed.append(("metal4", (a, y_tb, c, y_lo + 0.5), "INN"))
        sr = sorted(rows[side])
        spans = [(y_tb, sr[0] - SEG_KEEP)] + [(sr[k] + PWR_W + SEG_KEEP, sr[k + 1] - SEG_KEEP)
                                             for k in range(len(sr) - 1)] + [(sr[-1] + PWR_W + SEG_KEEP, y_lo + 0.5)]
        for (a1, c1), (a2, c2) in zip(pcs, pcs[1:]):
            if a2 - c1 < 3.0:                           # a supply lane or a strap gap between them
                for y1, y2 in spans:
                    if y2 - y1 >= 2.0:
                        ym = (y1 + y2) / 2
                        lk = (c1, max(y1, ym - 5.0), a2, min(y2, ym + 5.0))
                        b.box("metal4", *lk)
                        fixed.append(("metal4", lk, "INN"))
        tail_lanes = [(s[1] - WIDE_KEEP, s[3] + WIDE_KEEP) for segs in lanes.values() for s in segs
                      if s[1] < t_hi and s[3] > t.x and s[2] < y_lo and s[4] > t.y]
        free3 = minus(t.x + 0.4, t_hi, tail_lanes)
        for a, c in pcs:
            for fa, fc in free3:
                x1, x2 = max(a, fa), min(c, fc)
                if x2 - x1 < 0.9:
                    continue
                m3 = (x1, t.y, x2, y_lo - 0.6)
                b.box("metal3", *m3)
                fixed.append(("metal3", m3, "INN"))
                y = t.y + 0.5
                while y + 2.0 < y_lo - 1.0:
                    b.vias_fit("via3", x1, y, x2, y + 2.0)
                    vias3.append((x1, y, x2, y + 2.0))
                    y += 10.0
        pieces[side] = pcs
    # INN Metal5 over the boosters, from the bottom edge up to the via4 rows on the pieces,
    # the strips joined by a bar along the edge (the AFE joins the bar to the Cin_N bus)
    allp = pieces["N"] + pieces["P"]
    bot = tile(min(a for a, _ in allp), max(c for _, c in allp))
    for a, c in bot:
        b.box("metal5", a, 0.0, c, rail_bot)
    b.box("metal5", bot[0][0], 0.0, bot[-1][1], EDGE_BAR)
    for pa, pc in allp:
        for a, c in bot:
            if min(c, pc) - max(a, pa) >= 0.9:
                b.vias_fit("via4", max(a, pa), y_tb, min(c, pc), rail_bot - 0.24)
    # INP Metal5 over the cascodes, from above the pairs to the top edge; the strips join
    # the INP straps (gaps never cut one) and keep clear of the INN straps' tops
    x_mid = (pd["NPAIR"].x + pd["NPAIR"].cell.width + pd["PPAIR"].x) / 2
    top_strips = tile(pd["NPAIR"].x + 0.4, pd["PPAIR"].x + pd["PPAIR"].cell.width - 0.4, avoid=inp_x)
    for a, c in top_strips:
        y1 = (tops["N"] if a < x_mid else tops["P"]) + 1.0
        if a < x_mid < c:
            y1 = max(tops.values()) + 1.0
        b.box("metal5", a, y1, c, height)
    b.box("metal5", top_strips[0][0], height - EDGE_BAR, top_strips[-1][1], height)
    lbl = {"INP": ((top_strips[len(top_strips) // 2][0] + top_strips[len(top_strips) // 2][1]) / 2, height - 0.5),
           "INN": ((bot[len(bot) // 2][0] + bot[len(bot) // 2][1]) / 2, 0.5)}
    return fixed, vias3, pieces, lbl


def spread(x1, x2, plan, w=1.2):
    """Lane left edges for {net: count} spread evenly over x1..x2, nets interleaved."""
    order = []
    for r in range(max(plan.values())):
        for n, k in plan.items():
            if r < k:
                order.append(n)
    step = (x2 - x1) / len(order)
    if step < w + 0.4:
        raise ValueError(f"lanes too dense: {len(order)} in {x2 - x1:.1f} um")
    out = {}
    for i, n in enumerate(order):
        out.setdefault(n, []).append(round((x1 + (i + 0.5) * step - w / 2) / 0.005) * 0.005)
    return out


def build():
    name = "eeg_afe_core"
    b = g.Block(name)
    C = cells(b)
    nets, placed = {}, []

    def place(key, x, y):
        cell = C[key]
        b.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, key.upper())
        for pn, segs in p.pins.items():
            nets.setdefault(pn, []).extend(segs)
        placed.append(p)
        return p

    x0 = round((SW + 2.4) / lg.PITCH) * lg.PITCH
    yb = 4.0                                        # margin under the boosters (INN Metal5 to the edge)
    col = {"N": ["nboost", "ntail", "npair", "ncas"], "P": ["pboost", "ptail", "ppair", "pcas"]}
    xs = {"N": x0}
    xs["P"] = round((x0 + max(C[k].width for k in col["N"]) + 8.0) / lg.PITCH) * lg.PITCH
    tops = {}
    for side, keys in col.items():
        y = yb
        for key in keys:
            place(key, xs[side], y)
            y += C[key].height + 3.0
        tops[side] = y - 3.0
    pd = {p.name: p for p in placed}
    height = HEIGHT
    width = xs["P"] + max(C[k].width for k in col["P"]) + 4.0 + 6.0

    def common(*keys, free=5.0):
        ps = [pd[k.upper()] for k in keys]
        return max(p.x for p in ps) + 2.2 + free, min(p.x + p.cell.width for p in ps) - 2.2

    # ---- lanes over the tail, pair and cascodes of each column
    lanes, lx_side = {}, {}
    for side, plan in (("N", {"SN": 24, "DNP": 12, "DNN": 12, "OUTN": 12, "OUTP": 12, "VSS": 24}),
                       ("P", {"SP": 24, "DPP": 12, "DPN": 12, "OUTN": 12, "OUTP": 12, "VDD": 24})):
        keys = col[side][1:]
        lx = lx_side[side] = spread(*common(*keys), plan)
        bars = bl.lanes(b, [pd[k.upper()] for k in keys], lx)
        for n, segs in bars.items():
            lanes.setdefault(n, []).extend(segs)
    # ---- output trunks in a band over both columns' cascodes, shielded from the AFE's INP
    # Metal5 (over the cascodes to the top edge) by Metal4 (below): OUTP on Metal2, OUTN on
    # Metal3 above it, the OUT lanes run up into them (tracker D6: Metal4 trunks under the
    # INP Metal5 gave 0.6 pF INP-OUT and HD2 -70 dBc)
    vias3, band = [], []
    y_band = max(tops.values()) + 1.0
    yt = {"OUTP": (y_band, y_band + TRUNK_W), "OUTN": (y_band + TRUNK_W + 1.5, y_band + 2 * TRUNK_W + 1.5)}
    ports_out = {}
    for n, lay in (("OUTP", "metal2"), ("OUTN", "metal3")):
        y1, y2 = yt[n]
        xw = min(s[1] for s in lanes[n])
        b.box(lay, xw, y1, width, y2)
        band.append((lay, (xw, y1, width, y2), n))
        ports_out[n] = (lay, xw, y1, width, y2)
        for xl in sorted({s[1] for s in lanes[n]}):
            ss = [s for s in lanes[n] if s[1] == xl]
            xr, top_ = ss[0][3], max(s[4] for s in ss)
            ext = (xl, top_ - 0.5, xr, y2 if n == "OUTP" else y1 + 0.5)
            b.box("metal3", *ext)
            lanes[n].append(("metal3",) + ext)
            if n == "OUTP":
                b.vias_fit("via2", xl, y1, xr, y2)
    # the shield: a plate over the band up to the top edge, and one over each column's
    # cascode cell, the whole cell wide, from SHIELD_OPEN above its bottom up to the band (the
    # cells' own OUT straps and drains are Metal2 and Metal1). The N column's plate and the
    # band west of the P column are on VSS, the P column's plate and the band over it on VDD:
    # the columns' supply lanes run up under them to the OUTP trunk's top (via3), which also
    # breaks up the plates for MSLOT4.1 (1 x 2 um openings where no via does). The router
    # reaches the cascodes' gate bars from below on Metal3 between the lanes. West of STUB_X
    # the core's top EDGE_BAR + 0.4 um stay free of Metal4 (the AFE lands offdac_p's INP stub
    # there, on the INP bar). (Tracker D6: an opening along each P cascode gate bar, the cell
    # ends and the 4 um between the OUTN trunk and the top edge left 17 fF INP-OUTN.)
    um = lambda v: int(round(v * 1000))
    rect = lambda *bx: g.pya.Region(g.pya.Box(*[um(v) for v in bx]))
    y_low = yt["OUTN"][1] + 0.5
    assert y_low <= height - EDGE_BAR - 0.4, "the output trunks do not fit under the top edge"
    split, x_w, y_top = pd["PCAS"].x - 3.0, pd["NCAS"].x - 0.5, height - 0.4
    shield = {"VSS": rect(x_w, y_band - 0.6, split - 0.3, y_top) - rect(x_w, y_low, STUB_X, y_top),
              "VDD": rect(split + 0.3, y_band - 0.6, width - 1.0, y_top)}
    for side, key, net in (("N", "NCAS", "VSS"), ("P", "PCAS", "VDD")):
        p = pd[key]
        shield[net] += rect(p.x - 0.5, p.y + SHIELD_OPEN, p.x + p.cell.width + 0.5, y_band - 0.6)
        for xl in lx_side[side][net]:
            ss = [sg for sg in lanes[net] if sg[1] == xl]
            xr = ss[0][3]
            ext = (xl, max(sg[4] for sg in ss) - 0.5, xr, y_band + TRUNK_W)
            b.box("metal3", *ext)
            lanes[net].append(("metal3",) + ext)
            b.vias_fit("via3", xl, p.y + SHIELD_OPEN + 0.3, xr, y_band + TRUNK_W)
            vias3.append((xl, p.y + SHIELD_OPEN + 0.3, xr, y_band + TRUNK_W))
    vreg = g.pya.Region([g.pya.Box(*[um(v) for v in bx]) for bx in vias3]).sized(um(0.2))
    for net, plate in shield.items():
        plate.merge()
        b.cell.shapes(b.li("metal4")).insert(plate - mslot_openings(plate, vreg))
        for poly in plate.each():                   # (router: 0.3 um to wide Metal4, M4.2b)
            for t in poly.decompose_trapezoids():
                x1, y1, x2, y2 = [v / 1000 for v in (t.bbox().left, t.bbox().bottom, t.bbox().right, t.bbox().top)]
                band.append(("metal4", (x1 - 0.05, y1 - 0.05, x2 + 0.05, y2 + 0.05), net))
    # ---- supply rows over the tails; the AFE's Metal5 rails cover them (afe_lay.wiring)
    rows = {}
    for net, key in (("VSS", "ntail"), ("VDD", "ptail")):
        p = pd[key.upper()]
        nb_ = max(1, min(N_PWR, int((p.cell.height - 4.0) / (PWR_W + 2.0))))
        rows[net] = [p.y + 2.0 + k * (p.cell.height - 4.0 - PWR_W) / max(1, nb_ - 1) for k in range(nb_)]
    rail_bot = rows["VSS"][0] - 0.6                      # Metal5 keeps 0.6 um from the rails (MT.2b)
    rail_mid = rows["VSS"][-1] + PWR_W + RAIL_GROW["VSS"] + 0.6
    rail_top = rows["VDD"][-1] + PWR_W + RAIL_GROW["VDD"] + 0.6
    # ---- INP / INN gate network
    fixed, gvias3, pieces, lbl = gate_network(
        b, pd, lanes, {"N": lx_side["N"]["VSS"], "P": lx_side["P"]["VDD"]}, {"N": rows["VSS"], "P": rows["VDD"]},
        rail_bot, rail_mid, rail_top, height)
    vias3 += gvias3
    # ---- supply segments (Metal4) on the tails' supply lanes, between the INN pieces
    pwr = {}
    for net, key, side in (("VSS", "ntail", "N"), ("VDD", "ptail", "P")):
        p = pd[key.upper()]
        segs = [s for s in lanes[net] if s[2] <= p.y + p.cell.height and s[4] >= p.y]
        x1, x2 = min(s[1] for s in segs), max(s[3] for s in segs)
        cuts = [(a - SEG_KEEP, c + SEG_KEEP) for a, c in pieces[side]]
        for y1 in rows[net]:
            for a, c in minus(x1, x2, cuts):
                on = [s for s in segs if a - 1e-6 <= s[1] and s[3] <= c + 1e-6 and s[2] <= y1 and y1 + PWR_W <= s[4]]
                if not on:
                    continue
                b.box("metal4", a, y1, c, y1 + PWR_W)
                for s in on:
                    b.vias("via3", s[1], y1, s[3], y1 + PWR_W)
                    vias3.append((s[1], y1, s[3], y1 + PWR_W))
                pwr.setdefault(net, []).append(("metal4", a, y1, c, y1 + PWR_W))
    # the lanes replace the Metal2 strap pins of their nets in the column cells; the straps
    # of the cells already join all lanes of a net (and the trunks and supply segments their
    # lanes), so the router only joins the boosters' pins of a lane net to its nearest lane;
    # the gates INP / INN are not routed
    for n in lanes:
        keep = [sg for sg in nets.get(n, []) if not any(sg in p.pins.get(n, []) for p in placed
                                                         if p.name not in ("NBOOST", "PBOOST"))]
        if not keep:
            nets.pop(n, None)
            continue
        xc = sum(s[1] + s[3] for s in keep) / (2 * len(keep))
        nets[n] = keep + [min(lanes[n], key=lambda s: abs(s[1] - xc))]
    for n in ("OUTP", "OUTN"):                 # the trunks join all lanes of their net
        nets.pop(n, None)
    # the P cascodes' gate bars (GPCN's two between GPCP's two) are reached from below, on
    # Metal3 between the lanes under the shield: each net on its own half of its bars, or
    # GPCP's pin reserves (route.Router) close the column GPCN starts in
    pc = pd["PCAS"]
    xm = pc.x + pc.cell.width / 2
    for n, east in (("GPCP", True), ("GPCN", False)):
        nets[n] = [s if s not in pc.pins[n] else (s[0], max(s[1], xm + 2.0), s[2], s[3], s[4]) if east
                   else (s[0], s[1], s[2], min(s[3], xm - 2.0), s[4]) for s in nets[n]]
    for n in ("INP", "INN"):
        nets.pop(n)
    # ---- ports
    gx0 = 0.24
    pp = {}
    for n, (x, y) in lbl.items():
        b.label("metal5", n, x, y)
    for k, n in enumerate(["VBN", "VBP", "BLP", "BLN"]):
        y = -1.5 + round((yb + 20.0 + k * 6.0 + 1.5) / route.P) * route.P
        b.box("metal4", width - 3.0, y - 0.19, width, y + 0.19)
        b.label("metal4", n, width - 1.5, y)
        pp[n] = ("metal4", width - 3.0, y - 0.19, width, y + 0.19)
    for n, pin in pp.items():
        nets.setdefault(n, []).append(pin)
    for n in ("OUTP", "OUTN"):
        lay, _, y1, _, y2 = ports_out[n]
        b.label(lay, n, width - 1.5, (y1 + y2) / 2)
    for n in ("VSS", "VDD"):
        s = pwr[n][0]
        b.label("metal4", n, (s[1] + s[3]) / 2, (s[2] + s[4]) / 2)
    r = route.Router(gx0, -1.5, width, height + 0.5, px=lg.PITCH)
    for bx in vias3:
        r.via_keepout(*bx)
    for n, segs in list(lanes.items()) + list(pwr.items()):
        for s in segs:
            r.obstacle(*s, n)
    for lay, box, n in band:
        if lay != "metal2":
            r.obstacle(lay, *box, n)
    for lay, box, n in fixed:
        r.obstacle(lay, *box, n)
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(b)
    return b, name, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "eeg_afe_core")
    os.makedirs(runs, exist_ok=True)
    b, name, (w, h) = build()
    print(f"{name}: {w:.1f} x {h:.1f} um")
    bl.check(b, name, [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

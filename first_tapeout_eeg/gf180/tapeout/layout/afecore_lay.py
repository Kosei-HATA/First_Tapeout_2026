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
top on Metal4 trunks (three of 5 um per net) that reach the east edge as the OUTP /
OUTN ports. VSS and VDD come in from above on Metal4 bars over the two tails (via3 on
their lanes), for the AFE's Metal5 supply straps. Ports: INP on the top edge, INN on the
bottom edge (towards the Cin buses), VBN, VBP, BLP, BLN on the east edge. The gates and
the boosters' nets: route.Router.

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
TRUNK_W, N_TRUNK = 5.0, 3             # output trunks per net (Metal4)
PWR_W, N_PWR = 6.0, 5                 # Metal4 supply bars over each tail


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
    nb = []
    for d, gt, n, l in (("GNCP", "DNP", 32, 4.0), ("GNCN", "DNN", 32, 4.0), ("GPCP", "BLN", 40, 8.0),
                        ("GPCN", "BLN", 40, 8.0), ("BLN", "BLN", 8, 8.0)):
        nb += dev_strips(d, gt, "VSS", n, l, TN, order=["VSS", d])
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
    yb = 4.0                                        # room for the INN port's stub
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
    height = max(tops.values()) + 6.0
    width = xs["P"] + max(C[k].width for k in col["P"]) + 4.0 + 6.0

    def common(*keys, free=5.0):
        ps = [pd[k.upper()] for k in keys]
        return max(p.x for p in ps) + 2.2 + free, min(p.x + p.cell.width for p in ps) - 2.2

    # ---- lanes over the tail, pair and cascodes of each column
    lanes = {}
    for side, plan in (("N", {"SN": 24, "DNP": 12, "DNN": 12, "OUTN": 12, "OUTP": 12, "VSS": 24}),
                       ("P", {"SP": 24, "DPP": 12, "DPN": 12, "OUTN": 12, "OUTP": 12, "VDD": 24})):
        keys = col[side][1:]
        lx = spread(*common(*keys), plan)
        bars = bl.lanes(b, [pd[k.upper()] for k in keys], lx)
        for n, segs in bars.items():
            lanes.setdefault(n, []).extend(segs)
    # ---- output trunks (Metal4) over the cascodes of both columns, to the east edge
    vias3 = []
    y_cas = max(pd["NCAS"].y, pd["PCAS"].y)
    yt0 = y_cas + 4.0
    ports_out = {}
    for k in range(N_TRUNK):
        for j, n in enumerate(("OUTP", "OUTN")):
            y1 = yt0 + (2 * k + j) * (TRUNK_W + 2.0)
            segs = lanes[n]
            b.box("metal4", min(s[1] for s in segs), y1, width, y1 + TRUNK_W)
            for s in segs:
                if s[2] <= y1 and y1 + TRUNK_W <= s[4]:
                    b.vias("via3", s[1], y1, s[3], y1 + TRUNK_W)
                    vias3.append((s[1], y1, s[3], y1 + TRUNK_W))
            ports_out.setdefault(n, []).append(("metal4", min(s[1] for s in segs), y1, width, y1 + TRUNK_W))
    top_cas = min(pd["NCAS"].y + C["ncas"].height, pd["PCAS"].y + C["pcas"].height)
    assert yt0 + 2 * N_TRUNK * (TRUNK_W + 2.0) < top_cas, "trunks do not fit over the cascodes"
    # ---- supply bars (Metal4) over the tails, via3 on their lanes
    pwr = {}
    for net, key in (("VSS", "ntail"), ("VDD", "ptail")):
        p = pd[key.upper()]
        segs = [s for s in lanes[net] if s[2] <= p.y + p.cell.height and s[4] >= p.y]
        x1, x2 = min(s[1] for s in segs), max(s[3] for s in segs)
        nb_ = max(1, min(N_PWR, int((p.cell.height - 4.0) / (PWR_W + 2.0))))
        for k in range(nb_):
            y1 = p.y + 2.0 + k * (p.cell.height - 4.0 - PWR_W) / max(1, nb_ - 1)
            b.box("metal4", x1, y1, x2, y1 + PWR_W)
            for s in segs:
                if s[2] <= y1 and y1 + PWR_W <= s[4]:
                    b.vias("via3", s[1], y1, s[3], y1 + PWR_W)
                    vias3.append((s[1], y1, s[3], y1 + PWR_W))
            pwr.setdefault(net, []).append(("metal4", x1, y1, x2, y1 + PWR_W))
    # the lanes replace the Metal2 strap pins of their nets in the column cells
    for n in lanes:
        keep = [sg for sg in nets.get(n, []) if not any(sg in p.pins.get(n, []) for p in placed
                                                         if p.name not in ("NBOOST", "PBOOST"))]
        nets[n] = keep + lanes[n]
    for n in ("OUTP", "OUTN"):
        nets[n] = nets[n] + ports_out[n]
    for n in ("VSS", "VDD"):
        nets[n] = nets[n] + pwr[n]
    # ---- ports
    gx0 = 0.24
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    pp = bl.ports_top(b, ["INP"], [snap(width / 2)], height)
    pp.update(bl.ports_bottom(b, ["INN"], [snap(width / 2)], 0.0))
    for k, n in enumerate(["VBN", "VBP", "BLP", "BLN"]):
        y = -1.5 + round((yb + 20.0 + k * 6.0 + 1.5) / route.P) * route.P
        b.box("metal4", width - 3.0, y - 0.19, width, y + 0.19)
        b.label("metal4", n, width - 1.5, y)
        pp[n] = ("metal4", width - 3.0, y - 0.19, width, y + 0.19)
    for n, pin in pp.items():
        nets.setdefault(n, []).append(pin)
    for n in ("OUTP", "OUTN"):
        s = ports_out[n][0]
        b.label("metal4", n, width - 1.5, (s[2] + s[4]) / 2)
    for n in ("VSS", "VDD"):
        s = pwr[n][0]
        b.label("metal4", n, (s[1] + s[3]) / 2, (s[2] + s[4]) / 2)
    r = route.Router(gx0, -1.5, width, height + 0.5, px=lg.PITCH)
    for bx in vias3:
        r.via_keepout(*bx)
    for n, segs in list(lanes.items()) + list(pwr.items()) + list(ports_out.items()):
        for s in segs:
            r.obstacle(*s, n)
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

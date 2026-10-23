#!/usr/bin/env python3
"""Layout of the AFE input chopper (the four eeg_afe_input_tg of eeg_afe_amp,
gf180/tapeout/afe/eeg_afe.spice; LVS wrapper lvs/afe_tgin.spice), tracker E3.

All four TGs in one strip pattern, the commutator ring
    EP -CIA- WP -CIB- EN -CIA- WN -CIB- EP ...
(fingers EP-WP on CIA = XIP_A, WP-EN on CIB = XIN_B, EN-WN on CIA = XIN_A, WN-EP on CIB =
XIP_B), so every S/D region is shared and every strip carries all four signal nets.
W 10 um fingers, L 0.28: NMOS 2048 fingers (12 strips), PMOS 4096 (two cells of 12
strips, below and above the NMOS cell: the block is symmetric about its middle).

The signal current of the electrodes flows through these nets, so their wiring is wide:
  - Metal3 lanes per net over all strips (WP / WN lanes in pairs, EP / EN singles);
  - WP: Metal5 stripes over the WP lane pairs, from the bottom of the block up and out of
    its top edge (they meet the Cin_P bottom-plate bus there); WN: the same downwards,
    the two combs interleaved; via3 + via4 stacks from the lanes at regular rows;
  - EP / EN: Metal4 straps across the block at the other rows, via3 on their lanes, from
    two Metal5 spines on the west edge (EP outermost) that the pad straps feed.
Gates: Metal3 lanes (CIA / CIB over the NMOS cell, NCIA / NCIB over both PMOS cells) with
via2 on every strip's gate pin, out of the bottom edge for the clock driver eeg_afe_clk.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/afetg_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import analog as an
import blocks as bl

HERE = os.path.dirname(os.path.abspath(__file__))
NETLISTS = [os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice"), os.path.join(HERE, "lvs", "afe_tgin.spice")]
NAME = "afe_tgin"
L = 0.28
PERIODS_N, PERIODS_P = 512, 1024        # four fingers per period
STRIPS = 12                              # per cell
SPINE_W = 12.0                           # EP / EN spines (Metal5)
LANE_W = 1.2
PERIOD_X = 12.0                          # lane pattern [WP WP EP EN WN WN EP EN] every 12 um
ROW_P = 22.0                             # pitch of the via-stack / strap rows


def ring_seq(ga, gb, periods):
    seq = ["EP"]
    for _ in range(periods):
        seq += [ga, "WP", gb, "EN", ga, "WN", gb, "EP"]
    return seq


def strips(ga, gb, periods):
    base, extra = divmod(periods, STRIPS)
    out = []
    for k in range(STRIPS):
        n = base + (1 if k < extra else 0)
        out.append(dict(w=10.0, l=L, seq=ring_seq(ga, gb, n), gates={ga: ("t", 0), gb: ("t", 1)},
                        order=["EP", "WP", "EN", "WN"], straps={"EP": 3, "WP": 3, "EN": 3, "WN": 3}))
    return out


def build():
    b = g.Block(NAME)
    pl = an.multi_strip_cell(b, "afetg_p0", "p", strips("NCIA", "NCIB", PERIODS_P // 2), bulk="VDD")
    nc = an.multi_strip_cell(b, "afetg_n", "n", strips("CIA", "CIB", PERIODS_N), bulk="VSS")
    pu = an.multi_strip_cell(b, "afetg_p1", "p", strips("NCIA", "NCIB", PERIODS_P // 2), bulk="VDD")
    x0 = 2 * SPINE_W + 4.0
    placed = []
    y = 0.0
    for cell, nm in ((pl, "PL"), (nc, "N"), (pu, "PU")):
        b.place(cell.cell, x0, y)
        placed.append(bl.Placed(cell, x0, y, False, nm))
        y += cell.height + 3.0
    height = y - 3.0
    wcell = max(c.width for c in (pl, nc, pu))
    width = x0 + wcell + 2.0
    # ---- lanes: [WP WP EP EN WN WN EP EN] every PERIOD_X, inside the rings
    xa, xb = x0 + 2.0, x0 + wcell - 2.0 - LANE_W
    order = ["WP", "WP", "EP", "EN", "WN", "WN", "EP", "EN"]
    step = PERIOD_X / len(order)
    lanes_x = {}
    x = xa
    while x + PERIOD_X <= xb + step:
        for k, n in enumerate(order):
            lanes_x.setdefault(n, []).append(round((x + k * step) / 0.005) * 0.005)
        x += PERIOD_X
    lanes = bl.lanes(b, placed, lanes_x, w=LANE_W)
    y_lo = min(s[2] for segs in lanes.values() for s in segs)
    y_hi = max(s[4] for segs in lanes.values() for s in segs)
    # ---- rows: via stacks (WP / WN) at even rows, EP / EN straps at odd rows
    rows = []
    yr = y_lo + 4.0
    while yr + 3.0 < y_hi:
        rows.append(yr)
        yr += ROW_P / 2
    pins = {}
    # WP / WN stripes over the lane pairs (Metal5), via stacks on even rows
    pairs = {n: [(lanes_x[n][k], lanes_x[n][k + 1] + LANE_W) for k in range(0, len(lanes_x[n]), 2)]
             for n in ("WP", "WN")}
    for n, (s1, s2) in (("WP", (y_lo, height + 3.0)), ("WN", (-3.0, y_hi))):
        for x1, x2 in pairs[n]:
            b.box("metal5", x1, s1, x2, s2)
            for k, yr in enumerate(rows):
                if k % 2 == 0:
                    for xl in (x1, x2 - LANE_W):
                        b.vias("via3", xl, yr, xl + LANE_W, yr + 2.0)
                    b.vias("via4", x1, yr, x2, yr + 2.0)
        pins[n] = [("metal5", x1, s2 - 1.0, x2, s2) if n == "WP" else ("metal5", x1, s1, x2, s1 + 1.0)
                   for x1, x2 in pairs[n]]
    # EP / EN: spines on the west edge, Metal4 straps on odd rows (EP on rows 1, 5, ...,
    # EN on rows 3, 7, ...)
    spine = {"EP": (0.0, SPINE_W), "EN": (SPINE_W + 2.0, 2 * SPINE_W + 2.0)}
    for n, (sx1, sx2) in spine.items():
        b.box("metal5", sx1, y_lo, sx2, y_hi)
        pins[n] = [("metal5", sx1, y_lo, sx2, y_hi)]
    for k, yr in enumerate(rows):
        if k % 2 == 0:
            continue
        n = "EP" if (k // 2) % 2 == 0 else "EN"
        sx1, sx2 = spine[n]
        b.box("metal4", sx1, yr, xb + LANE_W, yr + 2.0)
        b.vias("via4", sx1, yr, sx2, yr + 2.0)
        for xl in lanes_x[n]:
            b.vias("via3", xl, yr, xl + LANE_W, yr + 2.0)
    # ---- gate lanes: CIA / CIB over the NMOS cell, NCIA / NCIB over both PMOS cells,
    # west of the S/D lanes (inside the rings), out of the top edge
    gate_x = {"CIA": x0 + wcell + 3.0, "CIB": x0 + wcell + 6.0, "NCIA": x0 + wcell + 9.0, "NCIB": x0 + wcell + 12.0}
    width = x0 + wcell + 16.0
    for n, xg in gate_x.items():
        segs = [s for p in placed for s in p.pins.get(n, []) if s[0] == "metal2"]
        ylo, yhi = -3.0, max(s[4] for s in segs)
        b.box("metal3", xg, ylo, xg + 1.2, yhi)
        for _, x1, y1, x2, y2 in segs:
            b.box("metal2", x2 - 1.0, y1, xg + 1.2, y2)
            b.vias("via2", xg, y1, xg + 1.2, y2)
        pins[n] = [("metal3", xg, ylo, xg + 1.2, ylo + 1.5)]
    # ---- bulk: the rings' bottom Metal2 (VDD for the PMOS cells, VSS for the NMOS); the
    # two PMOS rings joined by a Metal3 bar east of the gate lanes
    xv = x0 + wcell + 15.0
    width = xv + 3.0
    vdd = [s for p in placed for s in p.pins.get("VDD", [])]
    b.box("metal3", xv, min(s[2] for s in vdd), xv + 2.0, max(s[4] for s in vdd))
    for _, x1, y1, x2, y2 in vdd:
        b.box("metal2", x2 - 1.0, y1, xv + 2.0, y2)
        b.vias("via2", xv, y1, xv + 2.0, y2)
    pins["VDD"] = [("metal3", xv, min(s[2] for s in vdd), xv + 2.0, max(s[4] for s in vdd))]
    pins["VSS"] = [s for p in placed for s in p.pins.get("VSS", [])]
    for n, segs in pins.items():
        lay, x1, y1, x2, y2 = segs[0]
        b.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return b, (width, height), pins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", NAME)
    os.makedirs(runs, exist_ok=True)
    b, (w, h), _ = build()
    print(f"{NAME}: {w:.1f} x {h:.1f} um")
    bl.check(b, NAME, NETLISTS, runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Layout of eeg_quantizer (gf180/tapeout/adc/eeg_quantizer.spice, tracker E4): the
5-bit flash quantizer of the ADC.

Comparator unit (unit_cell below), one per threshold, 19.2 x 135.9 um, bottom to top:
  - seven Metal4 bus rows: DVSS, CLK, DVDD, VBQ, INN, INP, AVDD
  - preamp pair A on INP/INN (Nwell on SA), its gate bars facing the bus rows: INP / INN
    rise on two hand-drawn Metal3 lines side by side, between AVDD lines, straight from
    their bus rows to the bars; the router may not come near them (D6: the routed risers
    ran beside the preamp output VOP and the latch node OB, documentation/
    gf180_pex_20261023.md)
  - preamp tails (Nwell on AVDD), pair B on RP/RN (Nwell on SB): the pairs have bulk =
    source, so each sits in its own well
  - the latch (latch() below): the StrongARM and the two inverters on its outputs, mirror-
    symmetric about the unit column x = XA under OA <-> OB, X <-> Y, VOP <-> VON, every wire
    on OA / OB / X / Y drawn by hand, DVSS shields on both sides; the routers keep out of it
    and of the strip east of it, where the strobe comes in (D6: the routed latch wires gave
    OA 1.3..2.6 fF more than OB, a common threshold shift of +1.3..2.4 mV,
    documentation/gf180_adc_d6_fix_20261023.md)
  - the NOR SR latch, the output inverter (TH) and the dummy inverter (DVDD/DVSS)
  - ports VOP, RP, RN, VON (hand-drawn risers in the west strip of the unit, between two DVSS
    lines) and TH on the top edge
So the strobe, the latch and its outputs stay in the upper part of the unit, away from
the inputs.
Array: 16 + 15 units in two rows. Below them: the 62 preamp loads (300 kohm,
297.98 x 1 um) in one resistor row with all west ends on AVSS, the ladder (320 units of
2 x 2 um in a serpentine, taps T0..T30), the VBQ bias (NMOS mirror from IQ, PMOS diode,
2 pF MIM) and the strobe buffer. Routing: route.Router, except the inputs, the strobe and
TH; it keeps out of the units (only their port stubs are reached, from the channels).
TH (hand-drawn): from each unit's port stub one Metal4 row in the channel beside its row of
units, east past the pair to a column of its own, on that to its east-edge stub; the units'
other ports cross the TH rows on hand-drawn Metal3, the router takes them from there.
Inputs (hand-drawn, D6): the INN/INP bus rows of both rows of units are fed at their east
end by one Metal3 pair (INN, INP side by side between AVSS lines) that runs from row 0
through the gap between the loads and the ladder up to row 1, and from it a Metal4 pair
(between AVSS lines) east to the INP / INN ports. Everything that switches crosses the
pairs at right angles, so it couples to INP and INN alike; the router keeps one more
track clear on both sides. The other buses are fed at the east end as well, their rows
running on east under the pair's lower ends: the static ones (DVSS, DVDD, VBQ, AVDD) to
their pins just past it, the strobe (CLK, under DVDD and VBQ) further, to a hand-drawn
riser east of the strobe buffer that joins both rows (DVSS lines on both sides, the router
off that strip on Metal3).
Block ports, all on the east edge (Metal4 stubs; the ADC assembly feeds them from the
east): INP / INN above the bias, the other analog / clock / supply ports beside the
middle zone, TH0..15 beside row 0 and TH16..30 beside row 1 (east of the comparators
the rows leave room for their wires).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/quant_lay.py [--drc] [--lvs]
"""
import argparse
import os
from types import SimpleNamespace
import gf180lay as g
import fets as f
import logic as lg
import analog as an
import blocks as bl
import route
from dac2_lay import Combo

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_quantizer.spice")
BUSES = ["DVSS", "CLK", "DVDD", "VBQ", "INN", "INP", "AVDD"]
N = 31
SW = 2.4
P = lg.PITCH         # router column pitch (blocks and units)
UNIT_W, UNIT_H = 24 * P, 135.9
# the latch (cell coordinates: mirror axis at x = 0) and its place in the unit
XA = 9.84            # the axis in the unit (a router column)
G3 = 1.66            # gap between the two islands of a cross pair: their outer columns line
                     # up with the end columns of the input strip (x -/+1.82)
XR = 4.18            # outer edge of both rings (PMOS: COMP 2.01 + 0.5 + GAP + NW_ENC + ring)
XS = 4.0             # DVSS shields (Metal3) over the ring sides
XX = 2.3             # X / Y risers (Metal3)
XO = 1.02            # OA / OB risers (Metal3), over the inner drains of the cross pairs
XK = 1.80            # gate links (Metal2) between the NMOS and the PMOS cross pair
XB = 4.6             # half width of the region kept free of other wiring
# the unit: risers to the top-edge ports (west strip), TH port, supply risers, SR latch row
# (between DVSS lines: VOP and VON each beside a DVSS line and a tap, not beside each other)
WEST = {"VOP": 1.84, "RP": 2.64, "RN": 3.44, "VON": 4.24}
X_DVSS = (1.04, 5.04)
X_TH, X_DVDD, X_LOG = 14.64, 15.44, 6.4


class Latch:
    def __init__(self, cell, top, pins, clk):
        self.cell, self.top, self.pins, self.clk = cell, top, pins, clk


def latch(b, inv):
    """The StrongARM latch and the inverters on its outputs (eeg_qcmp XM0..XM6, XS1..XS4,
    XIA, XIB), mirror-symmetric about x = 0 under OA <-> OB, X <-> Y, VOP <-> VON,
    SETQ <-> RSTQ (OA side west); the NMOS ring's bottom edge at y = 0. Bottom to top:
      - NMOS (DVSS ring): the input strip [X VOP TL CLK DVSS CLK TL VON Y] (the tail's two
        fingers in the middle; VOP / VON gate bars below, CLK above) and the cross pair as
        two islands [X OB OA] | [OB OA Y], gate bars on top
      - PMOS (DVDD ring, Nwell): the cross pair [DVDD OB OA] | [OB OA DVDD], gate bars at the
        bottom, facing the NMOS pair's; the OA / OB precharge [OA CLK DVDD CLK OB]; the X / Y
        precharge [X CLK DVDD] | [DVDD CLK Y], its CLK bars on the one below (shared poly)
      - the two inverters upside down (inputs at the bottom, next to the PMOS ring), the one
        on OB mirrored
    Wires, all in mirror pairs: OA / OB on Metal3 at -/+XO from the NMOS pair's inner drains
    to the inverter inputs, over the PMOS pair's drains (the OA / OB precharge joined to
    those in Metal1); X / Y on Metal3 at -/+XX from the input strip to the X / Y precharge
    (the cross pair's outer columns joined to the input strip in Metal1); the NMOS and PMOS
    gates of each side joined by a Metal2 link at -/+XK, and each link to the other side's
    riser by a Metal2 jog in the 2 um between the rings: the only place where the halves
    differ (the OB jog 0.5 um above the NMOS ring, the OA jog 0.5 um below the PMOS ring).
    TL: a Metal2 strap across the input strip. CLK: Metal4 lines across the latch at the
    two CLK bars (the unit feeds them from the east). DVSS shields (Metal3) at -/+XS over
    the ring sides, on the NMOS ring and the inverters' VSS rail. Returns a Latch: pins
    (cell coordinates) VOP / VON (via points on the input gate bars), SETQ / RSTQ (Metal3
    exits above the inverters), DVDD (via point on the VDD rail at the unit's DVDD riser);
    the CLK line heights; the top."""
    c = b.new_cell("qcmp_latch")
    PE, PP = f.PO_EXT, f.PO_PAD
    bar = PE + PP / 2 + f.M1_COL / 2           # COMP edge to the far edge of a gate bar
    RW, GP = an.RING_W, an.GAP
    swap = {"OA": "OB", "OB": "OA", "X": "Y", "Y": "X"}

    def mbox(lay, x1, y1, x2, y2):             # a box and its mirror image about x = 0
        c.box(lay, x1, y1, x2, y2)
        c.box(lay, -x2, y1, -x1, y2)

    def mvia(v, x, y):
        f.via(c, v, x, y)
        f.via(c, v, -x, y)

    def mstack(lo, hi, x, y):
        f.via_stack(c, lo, hi, x, y)
        f.via_stack(c, lo, hi, -x, y)

    def col(geo, net):                         # (x, y1, y2) of the first S/D column of net
        _, x, y1, y2 = geo.cols_of(net)[0]
        return x, y1, y2

    def island(kind, w, seq, x0, y0, gates):   # an island west of the axis and its mirror image
        sl = f.Strip(kind, w, 0.28, seq)
        sr = f.Strip(kind, w, 0.28, [swap.get(n, n) for n in reversed(seq)])
        return (f.draw_strip(c, sl, x0, y0, gates=gates, well=False),
                f.draw_strip(c, sr, -x0 - sl.length, y0, gates={swap.get(n, n): v for n, v in gates.items()},
                             well=False))

    # ---- NMOS
    s_in = f.Strip("n", 4.0, [0.5, 0.28, 0.28, 0.5], ["X", "VOP", "TL", "CLK", "DVSS", "CLK", "TL", "VON", "Y"])
    xe = s_in.length / 2                       # 2.01: also the outer end of the islands
    assert abs(xe - G3 / 2 - 2 * f.SD_END - 0.28) < 1e-9
    y0 = RW + GP + bar                         # input strip (gate bars below)
    gi = f.draw_strip(c, s_in, -xe, y0, gates={"VOP": ("b", 0), "VON": ("b", 0), "CLK": ("t", 0)}, well=False)
    y3 = y0 + 4.0 + 1.4                        # cross pair: its poly 0.44 above the CLK pads
    gl3, gr3 = island("n", 4.0, ["X", "OB", "OA"], -xe, y3, {"OB": ("t", 0)})
    hn = y3 + 4.0 + bar + GP + RW              # NMOS ring top edge
    f.ring(c, "p", -XR, 0.0, XR, hn, w=RW, well=False)
    for ya in (y0, y3):                        # dummy poly at the outer ends, the cross pair's inner ends
        mbox("poly2", -xe - 0.52, ya - PE, -xe - 0.24, ya + 4.0 + PE)
    mbox("poly2", -G3 / 2 + 0.24, y3 - PE, -G3 / 2 + 0.52, y3 + 4.0 + PE)
    assert abs(col(gl3, "OA")[0] + XO) < 1e-9 and abs(col(gl3, "X")[0] - col(gi, "X")[0]) < 1e-9
    x, y1, _ = col(gi, "DVSS")                 # DVSS: the middle column down into the ring
    c.box("metal1", x - 0.19, 0.0, x + 0.19, y1 + 0.2)
    f.strap(c, gi, "TL", y0 + 2.0, x1=-0.99, x2=0.99)
    x, _, y2 = col(gi, "X")                    # X / Y: input strip -> cross pair (Metal1)
    mbox("metal1", x - 0.19, y2 - 0.2, x + 0.19, col(gl3, "X")[1] + 0.2)
    yx0 = y0 + 2.0                             # X / Y risers: from the input strip ...
    mvia("via1", x, yx0)
    mbox("metal2", -XX - 0.19, yx0 - 0.19, x + 0.19, yx0 + 0.19)
    mvia("via2", XX, yx0)
    yo3 = y3 + 2.0                             # OA / OB risers: from the NMOS pair's inner drains
    mstack("metal1", "metal3", XO, yo3)
    pins = {}
    for n in ("VOP", "VON"):                   # the input gates: Metal2 over the bars (vias below)
        x1, y1, x2, y2 = gi.bars[n]
        c.box("metal2", x1, y1, x2, y2)
        f.via(c, "via1", (x1 + x2) / 2, (y1 + y2) / 2)
        pins[n] = ((x1 + x2) / 2, (y1 + y2) / 2)
    x1, yn1, x2, yn2 = gl3.bars["OB"]          # the NMOS pair's gate pins, out to the links
    mbox("metal2", -XK - 0.19, yn1, x2, yn2)
    mvia("via1", (x1 + x2) / 2, (yn1 + yn2) / 2)

    # ---- PMOS
    yp = hn + 2.0
    mp = GP + f.NW_ENC
    y1p = yp + RW + mp + bar                   # cross pair (gate bars below)
    gl1, gr1 = island("p", 4.0, ["DVDD", "OB", "OA"], -xe, y1p, {"OB": ("b", 0)})
    y2p = y1p + 4.0 + 2 * PE + 0.3             # OA / OB precharge: poly 0.3 above the pair's
    s2 = f.Strip("p", 2.0, 0.28, ["OA", "CLK", "DVDD", "CLK", "OB"])
    g2 = f.draw_strip(c, s2, -s2.length / 2, y2p, gates={"CLK": ("t", 0)}, well=False)
    y3p = y2p + 2.0 + 2 * PE + PP              # X / Y precharge: its CLK pads on the ones below
    gl5, gr5 = island("p", 2.0, ["X", "CLK", "DVDD"], -xe, y3p, {"CLK": ("b", 0)})
    hp = y3p + 2.0 + PE + mp + RW              # PMOS ring top edge
    f.ring(c, "n", -XR, yp, XR, hp, w=RW, well=False)
    c.box("nwell", -XR - 0.22, yp - 0.22, XR + 0.22, hp + 0.22)
    for ya, h in ((y1p, 4.0), (y3p, 2.0)):
        mbox("poly2", -xe - 0.52, ya - PE, -xe - 0.24, ya + h + PE)
    mbox("poly2", -G3 / 2 + 0.24, y1p - PE, -G3 / 2 + 0.52, y1p + 4.0 + PE)
    x1, yq1, x2, yq2 = gl1.bars["OB"]          # the PMOS pair's gate pins and the links
    mbox("metal2", -XK - 0.19, yq1, x2, yq2)
    mvia("via1", (x1 + x2) / 2, (yq1 + yq2) / 2)
    mbox("metal2", -XK - 0.19, yn1, -XK + 0.19, yq2)
    mstack("metal1", "metal3", XO, y1p + 2.0)  # OA / OB risers on the PMOS pair's drains
    x, _, y2 = col(gl1, "OA")                  # ... and the precharge joined to those (Metal1)
    xq, y1, _ = col(g2, "OA")
    mbox("metal1", x - 0.19, y2 - 0.3, xq + 0.19, y1 + 0.3)
    x, y1, _ = col(g2, "DVDD")                 # DVDD: the precharge's middle column down into the ring,
    c.box("metal1", x - 0.19, yp, x + 0.19, y1 + 0.2)
    x, _, y2 = col(gl1, "DVDD")                # the pair's outer columns up and over to the ring sides,
    ys = y2p + 1.0
    mbox("metal1", x - 0.19, y2 - 0.2, x + 0.19, ys + 0.25)
    mvia("via1", x, ys)
    mvia("via1", XR - RW / 2, ys)
    mbox("metal2", -XR + 0.02, ys - 0.19, x + 0.19, ys + 0.19)
    x, _, y2 = col(gl5, "DVDD")                # the X / Y precharge's inner columns up into the ring
    mbox("metal1", x - 0.19, y2 - 0.2, x + 0.19, hp)
    yx1 = y3p + 1.0                            # X / Y risers: ... to the X / Y precharge
    x, _, _ = col(gl5, "X")
    mvia("via1", x, yx1)
    mbox("metal2", -XX - 0.19, yx1 - 0.19, x + 0.19, yx1 + 0.19)
    mvia("via2", XX, yx1)
    mbox("metal3", -XX - 0.19, yx0 - 0.19, -XX + 0.19, yx1 + 0.19)
    x1, y1, _, y2 = gl5.bars["CLK"]            # the precharges' CLK bars as one
    c.box("metal1", x1, y1, -x1, y2)
    clk = [(gi.bars["CLK"][1] + gi.bars["CLK"][3]) / 2, (y1 + y2) / 2]
    for y in clk:                              # CLK lines across the latch
        f.via_stack(c, "metal1", "metal4", 0.0, y)
        c.box("metal4", -XS - 0.19, y - 0.19, XS + 0.19, y + 0.19)

    # ---- the jogs between the rings (OB above the NMOS ring, OA below the PMOS ring)
    for x1, x2, xv, y in ((-XK - 0.19, XO + 0.19, XO, hn + 0.5), (-XO - 0.19, XK + 0.19, -XO, yp - 0.5)):
        c.box("metal2", x1, y - 0.19, x2, y + 0.19)
        f.via(c, "via2", xv, y)

    # ---- the inverters (upside down; the one on OB mirrored)
    yi = hp + 0.6
    top = yi + lg.H
    c.place(inv.cell, -inv.width, top, rot=0, mirror=True)
    c.place(inv.cell, inv.width, top, rot=2)
    _, ax1, ay1, ax2, ay2 = inv.pins["A"][0]
    xa, ya = -inv.width + (ax1 + ax2) / 2, top - (ay1 + ay2) / 2            # the input on OA
    mbox("metal3", xa - 0.19, ya - 0.19, -XO + 0.19, ya + 0.19)
    mvia("via2", xa, ya)
    mbox("metal3", -XO - 0.19, yo3 - 0.19, -XO + 0.19, ya + 0.19)           # OA / OB risers
    _, tx1, ty1, tx2, ty2 = inv.pins["Y"][0]
    xt, yt = -2 * P, top - (ty1 + ty2) / 2     # SETQ / RSTQ exits on router columns
    assert -inv.width + tx1 + 0.19 <= xt <= -inv.width + tx2 - 0.19
    mvia("via2", xt, yt)
    mbox("metal3", xt - 0.19, yt - 0.19, xt + 0.19, top + 1.5)
    pins["SETQ"] = ("metal3", xt - 0.19, yt - 0.19, xt + 0.19, top + 1.5)
    pins["RSTQ"] = ("metal3", -xt - 0.19, yt - 0.19, -xt + 0.19, top + 1.5)
    c.box("metal1", -inv.width, hp - 0.2, inv.width, yi + 0.3)             # PMOS ring -> VDD rail
    c.box("nwell", -inv.width - 0.2, hp, inv.width + 0.2, yi + 0.3)
    c.box("nplus", -inv.width - 0.16, hp, inv.width + 0.16, yi)            # one implant over both taps (NP.2)
    xd = X_DVDD - XA                           # the VDD rail out to the unit's DVDD riser (east)
    mbox("metal2", inv.width, yi, XB, yi + 0.6)
    c.box("metal2", XB, yi, xd + 0.19, yi + 0.6)
    f.via(c, "via2", xd, yi + 0.3)
    pins["DVDD"] = (xd, yi + 0.3)
    c.box("metal2", -XS - 0.19, top - 0.6, XS + 0.19, top)                 # VSS rail -> shields
    mvia("via2", XS, top - 0.3)
    mbox("metal3", XS - 0.19, -1.5, XS + 0.19, top)                       # DVSS shields
    for y in (1.5, (y0 + y3) / 2 + 2.0, hn - 1.5):
        mstack("metal1", "metal3", XR - RW / 2, y)                         # NMOS ring -> shields
    return Latch(c, top, pins, clk)


def unit_cell(b, name, parts, lat, logic, gap=2.0, margin=0.8, bus_w=1.0, bus_gap=0.8):
    """The comparator unit (see the module doc), UNIT_W x UNIT_H. parts: the preamp
    [(cell, {cell pin: net}, x)] bottom to top, parts[0] the pair with its INP / INN gate
    bars at the bottom, parts[-1] the pair on RP / RN; lat: latch(); logic: the SR latch row.
    Drawn by hand:
      - INP / INN rise from their bus rows to the bars on two neighbouring router columns,
        an AVDD line on the column beside each; the router keeps off the next column on both
        sides and off the space between the bus rows and the bars;
      - CLK rises from its bus row on the last router columns but one (DVSS lines on both
        sides, the router off the next column) and enters the latch on its two Metal4 lines
        from the east: a routed CLK riser beside one of the preamp outputs gave every
        comparator the same offset (3 fF more CLK coupling on VON than on VOP);
      - the latch's inputs: VOP / VON on Metal3 straight up from the RP / RN pair's straps to
        the input gates, each crossing the other's strap;
      - the risers to the ports (WEST, between two DVSS lines): VOP / VON from both pairs'
        straps, RP / RN with Metal4 jogs to their gate pins that cross VOP and VON alike;
      - DVSS: those lines, the latch's shields (the east one down to the bus row) up to the
        SR row's VSS rail; DVDD: a riser from the bus row to the latch's and the SR row's VDD
        rails.
    route.Router does the rest of the preamp (SA, SB, VBQ, AVDD) and the SR row, outside the
    latch, the strip east of it and the west strip.
    Returns a blocks.Unit (pins: bus rows and port stubs)."""
    c = b.new_cell(name)
    nets, fixed = {}, []
    y = 0.6
    bus_y = {}
    width, height = UNIT_W, UNIT_H

    def wire(lay, x1, y1, x2, y2, net):        # a hand-drawn Metal3 / Metal4 wire
        c.box(lay, x1, y1, x2, y2)
        fixed.append((lay, (x1, y1, x2, y2), net))

    def via(v, x, y, net, pads=True):
        if pads:
            f.via(c, v, x, y)
            for lay in g.METALS[g.VIAS.index(v):g.VIAS.index(v) + 2]:
                if lay in ("metal3", "metal4"):
                    fixed.append((lay, (x - 0.19, y - 0.19, x + 0.19, y + 0.19), net))
        else:
            c.box(v, x - 0.13, y - 0.13, x + 0.13, y + 0.13)

    for n in BUSES:
        c.box("metal4", 0.0, y, width, y + bus_w)
        bus_y[n] = (y, y + bus_w)
        fixed.append(("metal4", (0.0, y, width, y + bus_w), n))
        nets.setdefault(n, []).append(("metal4", 0.0, y, width, y + bus_w))
        y += bus_w + bus_gap
    y += gap
    placed = []
    for cell, cmap, x in parts:
        x = 1.0 if x is None else x
        c.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, cell.cell.name)
        placed.append(p)
        for pn, segs in p.pins.items():
            if pn in cmap:
                nets.setdefault(cmap[pn], []).extend(segs)
        y += getattr(cell, "height", lg.H) + gap
    y_lat = y
    c.place(lat.cell, XA, y_lat)
    y_log = y_lat + lat.top + gap
    c.place(logic.cell, X_LOG, y_log)
    pl = bl.Placed(logic, X_LOG, y_log, False, "logic")
    for pn, segs in pl.pins.items():
        nets.setdefault(pn, []).extend(segs)
    assert y_log + lg.H + 4.0 <= height
    pins = {n: [("metal4", 0.0, a, width, bb)] for n, (a, bb) in bus_y.items()}
    gx0 = margin + 0.24
    col = lambda x: gx0 + round((x - gx0) / P) * P
    vc = lambda n: (bus_y[n][0] + bus_y[n][1]) / 2
    # ---- the preamp inputs: [AVDD | INP | INN | AVDD] on four router columns
    pa = placed[0]
    ip, nn_ = pa.cell.pins["INP"][0], pa.cell.pins["INN"][0]
    yp, yn = pa.y + (ip[2] + ip[4]) / 2, pa.y + (nn_[2] + nn_[4]) / 2
    x_inn = col(pa.x + (nn_[1] + nn_[3]) / 2)
    x_inp = x_inn - P
    assert pa.x + nn_[1] + 0.19 <= x_inn <= pa.x + nn_[3] - 0.19
    assert pa.x + ip[1] + 0.19 <= x_inp - P and x_inn + P <= pa.x + ip[3] - 0.19
    y0 = bus_y["INN"][0]
    for x, n, ytop in ((x_inp, "INP", yp), (x_inn, "INN", yn), (x_inp - P, "AVDD", yp), (x_inn + P, "AVDD", yp)):
        c.box("metal3", x - 0.19, y0, x + 0.19, ytop + 0.19)
        c.box("via3", x - 0.13, vc(n) - 0.13, x + 0.13, vc(n) + 0.13)
        if n != "AVDD":
            c.box("via2", x - 0.13, ytop - 0.13, x + 0.13, ytop + 0.13)
    keep = (x_inp - 2 * P - 0.19, x_inn + 2 * P + 0.19)
    # ---- the strobe: [DVSS | CLK | DVSS] on the last three router columns, the latch's
    # CLK lines from there
    last = lambda x: gx0 + int((x - gx0) // P) * P           # last router column at or below x
    x_clk = last(width - margin) - P
    y_clk = y_lat + max(lat.clk)
    for x, n in ((x_clk, "CLK"), (x_clk - P, "DVSS"), (x_clk + P, "DVSS")):
        wire("metal3", x - 0.19, bus_y[n][0], x + 0.19, y_clk + 0.6, n)
        via("via3", x, vc(n), n, pads=False)
    for yc in lat.clk:
        wire("metal4", XA + XS + 0.19, y_lat + yc - 0.19, x_clk + 0.19, y_lat + yc + 0.19, "CLK")
        via("via3", x_clk, y_lat + yc, "CLK", pads=False)
    # ---- the latch's inputs, and the risers to the ports
    pb = placed[-1]
    strap = lambda p, n: (p.pins[n][0][2] + p.pins[n][0][4]) / 2
    ys = {n: strap(pb, n) for n in ("VOP", "VON", "RP", "RN")}
    y_lo = min(ys["VOP"], ys["VON"]) - 0.19
    for n in ("VOP", "VON"):
        xv, yv = XA + lat.pins[n][0], y_lat + lat.pins[n][1]
        wire("metal3", xv - 0.19, y_lo, xv + 0.19, yv + 0.19, n)
        for yy in (ys[n], yv):
            via("via2", xv, yy, n, pads=False)
    ya = {n: strap(pa, n) for n in ("VOP", "VON")}       # the port risers join both pairs' straps
    y_lw = min(ya.values()) - 0.19
    ybot = {"VOP": y_lw, "VON": y_lw, "RP": ys["RP"] - 0.19, "RN": ys["RN"] - 0.19}
    for n, x in WEST.items():
        wire("metal3", x - 0.19, ybot[n], x + 0.19, height - 1.6, n)
        wire("metal3", x - 0.19, height - 1.6, x + 0.19, height, n)    # the port stub
        pins[n] = [("metal3", x - 0.19, height - 1.6, x + 0.19, height)]
    for n in ("VOP", "VON"):
        for yy in (ya[n], ys[n]):
            via("via2", WEST[n], yy, n)              # pads: VOP lands on the straps' west ends
    for n, xl in (("RP", 8.3 * P), ("RN", 9.3 * P)):                  # into the gate pins
        x1, x2 = pb.pins[n][0][1], pb.pins[n][0][3]
        assert x1 + 0.19 <= xl <= x2 - 0.19 and WEST[n] < xl
        wire("metal4", WEST["VOP"] - 0.19, ys[n] - 0.19, xl + 0.19, ys[n] + 0.19, n)
        via("via3", WEST[n], ys[n], n, pads=False)
        via("via3", xl, ys[n], n)
        via("via2", xl, ys[n], n)
    wire("metal3", X_TH - 0.19, height - 1.6, X_TH + 0.19, height, "TH")
    pins["TH"] = [("metal3", X_TH - 0.19, height - 1.6, X_TH + 0.19, height)]
    nets["TH"].append(pins["TH"][0])
    # ---- supplies: DVSS at the west edge, the latch's east shield down to the bus row and
    # both shields up to the SR row's VSS rail; DVDD up to the latch's and the SR row's VDD
    wire("metal3", X_DVSS[0] - 0.19, bus_y["DVSS"][0], X_DVSS[0] + 0.19, height - 0.4, "DVSS")
    via("via3", X_DVSS[0], vc("DVSS"), "DVSS", pads=False)
    wire("metal3", X_DVSS[1] - 0.19, y_lw - 1.0, X_DVSS[1] + 0.19, height - 0.4, "DVSS")
    wire("metal3", XA + XS - 0.19, bus_y["DVSS"][0], XA + XS + 0.19, y_lat - 1.0, "DVSS")
    via("via3", XA + XS, vc("DVSS"), "DVSS", pads=False)
    c.box("metal2", X_DVSS[1] - 0.19, y_log, X_LOG, y_log + 0.6)
    for x in (X_DVSS[1], XA - XS, XA + XS):
        if x != X_DVSS[1]:
            wire("metal3", x - 0.19, y_lat + lat.top - 0.2, x + 0.19, y_log + 0.6, "DVSS")
        via("via2", x, y_log + 0.3, "DVSS", pads=False)
    assert abs(XA + lat.pins["DVDD"][0] - X_DVDD) < 1e-9
    wire("metal3", X_DVDD - 0.19, bus_y["DVDD"][0], X_DVDD + 0.19, y_log + lg.H, "DVDD")
    via("via3", X_DVDD, vc("DVDD"), "DVDD", pads=False)
    via("via2", X_DVDD, y_log + lg.H - 0.3, "DVDD", pads=False)
    # ---- the SR row's inputs from the latch
    for n in ("SETQ", "RSTQ"):
        lay, x1, y1, x2, y2 = lat.pins[n]
        nets[n].append((lay, XA + x1, y_lat + y1, XA + x2, y_lat + y2))
    exits = {tuple(round(v, 3) for v in (XA + s[1], y_lat + s[2], XA + s[3], y_lat + s[4]))
             for s in (lat.pins["SETQ"], lat.pins["RSTQ"])}
    r = route.Router(gx0, 0.0, width - margin, height - 0.2, px=P)
    # keep the router's shapes clear of the side edges: block the first/last columns
    r.obstacle("metal3", -1.0, -1.0, margin - 0.2, height + 1.0)
    r.obstacle("metal4", -1.0, -1.0, margin - 0.2, height + 1.0)
    r.obstacle("metal3", keep[0], -1.0, keep[1], yp + 0.7)
    r.obstacle("metal4", keep[0], bus_y["AVDD"][1] + 0.3, keep[1], yp + 0.7)
    r.obstacle("metal3", x_clk - 2 * P - 0.19, -1.0, x_clk + 2 * P + 0.19, y_clk + 0.8)
    for lay in ("metal3", "metal4"):           # the latch and east of it, the west strip, the inputs
        r.obstacle(lay, XA - XB, y_lat - 1.0, width + 1.0, y_lat + lat.top + 0.6)
        r.obstacle(lay, -1.0, y_lw - 1.5, XA - XB, height + 1.0)
        r.obstacle(lay, XA + lat.pins["VOP"][0] - 1.2, y_lo - 1.5, XA + lat.pins["VON"][0] + 1.2, y_lat - 1.0)
    for lay, box, n in fixed:
        r.obstacle(lay, *box, n)
    for p in placed + [SimpleNamespace(cell=lat, x=XA, y=y_lat, mirror=False), pl]:
        for lay in ("metal3", "metal4"):       # wires inside the parts: obstacles
            for bx in bl.cell_shapes(p, lay):
                if lay == "metal3" and tuple(round(v, 3) for v in bx) in exits:
                    continue
                r.obstacle(lay, *bx)
    for n in ("SETQ", "RSTQ"):
        r.obstacle(*nets[n][-1], n)
    todo = ("SA", "SB", "VBQ", "AVDD", "SETQ", "RSTQ", "Q", "QB", "TH")
    failed = r.route({n: v for n, v in nets.items() if n in todo and len(v) > 1}, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"{name}: unrouted {failed}")
    r.draw(c)
    return bl.Unit(c, width, height, pins, ["RP", "RN", "VOP", "VON", "TH"])


def comparator(b):
    tail = an.strip_cell(b, "qcmp_tail", "p", 8.0, 2.0, ["SA", "VBQ", "AVDD", "VBQ", "SB"],
                         order=["AVDD", "SA", "SB"], bulk="AVDD")
    # gate bars at the bottom (towards the bus rows); INP on the outer, INN on the inner fingers as before
    pa = an.strip_cell(b, "qcmp_pa", "p", 10.0, 1.25, ["VON", "INP", "SA", "INN", "VOP", "INN", "SA", "INP", "VON"],
                       gates={"INP": ("b", 0), "INN": ("b", 1)}, order=["SA", "VON", "VOP"], bulk="SA")
    pb = an.strip_cell(b, "qcmp_pb", "p", 10.0, 1.25, ["VOP", "RP", "SB", "RN", "VON", "RN", "SB", "RP", "VOP"],
                       order=["SB", "VOP", "VON"], bulk="SB")
    p, n = lg.inv_seq(1)
    qinv = lg.cmos_cell(b, "eeg_qinv", p, n, 4.0, 2.0, ["A", "Y"])
    p, n = lg.nor_seq(["A", "B"], 1)
    qnor = lg.cmos_cell(b, "eeg_qnor2", p, n, 4.0, 1.0, ["A", "B", "Y"])
    lat = latch(b, qinv)
    rail = {"VDD": "DVDD", "VSS": "DVSS"}
    logic = Combo(b, "qcmp_logic", [(qnor, rail | {"A": "SETQ", "B": "Q", "Y": "QB"}),
                                    (qnor, rail | {"A": "RSTQ", "B": "QB", "Y": "Q"}),
                                    (qinv, rail | {"A": "QB", "Y": "TH"}), (qinv, rail | {"A": "Q", "Y": "QD"})])
    ident = lambda c: {k: k for k in c.pins}
    parts = [(pa, {k: k for k in pa.pins if k not in ("INP", "INN")}, None), (tail, ident(tail), None),
             (pb, ident(pb), None)]
    # 2 um between parts: neighbouring Nwells of different nets keep 1.4 um (NW.2b)
    return unit_cell(b, "eeg_qcmp", parts, lat, logic, gap=2.0)


def build():
    b = g.Block("eeg_quantizer")
    u = comparator(b)
    nets = {}
    placed = []

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def place(cell, x, y, name, cmap=None, mirror=False):
        b.place(cell.cell, x, y, mirror=mirror)
        p = bl.Placed(cell, x, y, mirror, name)
        for pn, segs in p.pins.items():
            conn((cmap or {}).get(pn, pn), segs)
        placed.append(p)
        return p

    # ---- the middle zone: loads, ladder, bias, strobe buffer
    loads = []
    for k in range(N):
        loads += [("AVSS", f"VOP{k}"), ("AVSS", f"VON{k}")]
    rl = an.res_cell(b, "q_loads", 297.98, 1.0, loads, sub="AVSS", west_bus=True)
    nodes = ["VREFN"] + [f"NB{k}" for k in range(1, 145)] + [f"T{k}" for k in range(31)] + \
            [f"NT{k}" for k in range(1, 145)] + ["VREFP"]
    lad = an.ladder_cell(b, "eeg_qladder", nodes, taps=[f"T{k}" for k in range(31)], sub="AVSS")
    seq = ["AVSS"]
    for j in range(4):
        seq += ["IQ", "IQ", "IQ", "AVSS", "IQ", "VBQ", "IQ", "AVSS"]
    qn = an.strip_cell(b, "q_bias_n", "n", 4.0, 2.0, seq, order=["AVSS", "IQ", "VBQ"], bulk="AVSS")
    qp = an.strip_cell(b, "q_bias_p", "p", 8.0, 2.0, ["AVDD"] + ["VBQ", "VBQ", "VBQ", "AVDD"] * 4,
                       order=["AVDD", "VBQ"], bulk="AVDD")
    cq = an.mim_cell(b, "q_cvbq", 31.46, "VBQ", "AVDD")
    p, n = lg.inv_seq(1)
    strobe1 = lg.cmos_cell(b, "q_strobe1", p, n, 4.0, 2.0, ["A", "Y"])
    strobe2 = lg.driver_cell(b, "q_strobe2", 32.0, 16.0)
    x0 = round((SW + 2.4) / lg.PITCH) * lg.PITCH
    width_u = 16 * u.width
    chan = 14.0                                     # routing channel above row 0 / below row 1
    y_mid = u.height + chan
    keep = []
    x_arr = x0
    gx0 = (x_arr + 1.04) % lg.PITCH
    # the input pair's columns east of the units: AVSS, INN, INP, AVSS (router columns)
    xs1 = gx0 + -(-(x_arr + width_u + 1.0 - gx0) // P) * P
    xf = {"S1": xs1, "INN": xs1 + P, "INP": xs1 + 2 * P, "S2": xs1 + 3 * P}
    band = (xs1 - P - 0.19, xs1 + 4 * P + 0.19)     # kept clear of the router (Metal3)
    xm = x0 + 2.0
    pl_ = place(rl, xm, y_mid, "LOADS")
    xm = max(xm + rl.width + 3.0, band[1] + 1.5)
    place(lad, xm, y_mid, "LADDER")
    xm += lad.width + 3.0
    place(qn, xm, y_mid, "QN")
    place(qp, xm, y_mid + qn.height + 2.0, "QP")
    pc = place(cq, xm + max(qn.width, qp.width) + 3.0, y_mid, "CVBQ")
    keep.append(((pc.x + cq.keepout[0], pc.y + cq.keepout[1], pc.x + cq.keepout[2], pc.y + cq.keepout[3]),
                 (pc.x + cq.keepout4[0], pc.y + cq.keepout4[1], pc.x + cq.keepout4[2], pc.y + cq.keepout4[3])))
    xs = round((pc.x + cq.width + 3.0) / lg.PITCH) * lg.PITCH
    rows = bl.Rows(b, xs, y_mid)
    c1 = rows.add(0, strobe1, "XCB1")
    for pn, segs in c1.pins.items():
        if pn not in ("VDD", "VSS"):
            conn({"A": "CMP_STROBE", "Y": "CLKB"}[pn], segs)
    rows.fill(0, xs + 8 * lg.PITCH)
    d = place(strobe2, xs, y_mid + lg.H + 2.0, "XCB2", {"A": "CLKB", "Y": "CLK", "VDD": "DVDD", "VSS": "DVSS"})
    for net, a, c_ in rows.rails():
        xr = rows.x0 + rows.width()
        b.box("metal2", xr - 0.5, a, xr + 2.0, c_)
        conn("DVSS" if net == "VSS" else "DVDD", [("metal2", xr - 0.5, a, xr + 2.0, c_)])
    h_mid = max(rl.height, lad.height, qn.height + 2.0 + qp.height, cq.height, lg.H + 2.0 + strobe2.height)
    y_top = y_mid + h_mid + chan                    # bottom of row 1's port edge
    # ---- comparator rows: row 0 ports up, row 1 mirrored (ports down)
    for e in range(N):
        r, k = divmod(e, 16)
        x = x_arr + k * u.width
        if r == 0:
            p = place(u, x, 0.0, f"U{e}", {})
        else:
            p = place(u, x, y_top + u.height, f"U{e}", {}, mirror=True)
        nets_map = {"RP": f"T{e}", "RN": f"T{30 - e}", "VOP": f"VOP{e}", "VON": f"VON{e}", "TH": f"TH{e}"}
        for pn, net in nets_map.items():
            segs = p.pins[pn]
            nets.setdefault(pn, [])
            for sg in segs:
                nets[pn].remove(sg)
            conn(net, segs)
    for pn in ("RP", "RN", "VOP", "VON", "TH"):
        nets.pop(pn, None)
    # bus pins: none of the units' bus rows (joined by abutment, fed at the east end
    # below); pins of other cells on these nets stay
    unit_bus = set()
    for p in placed:
        if p.name.startswith("U"):
            for n in BUSES:
                unit_bus.update(tuple(sg) for sg in p.pins[n])
    for n in BUSES:
        nets[n] = [sg for sg in nets.get(n, []) if tuple(sg) not in unit_bus]
    for n in ("INP", "INN"):        # drawn by hand below
        nets.pop(n)
    height = y_top + u.height + 2.0
    width = max(x_arr + width_u, rows.x0 + rows.width() + 3.0, d.x + strobe2.width) + 4.0 + SW
    # ---- power straps (west AVSS, east AVDD) and ports (east, Metal4)
    xv, xd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("AVSS", xv), ("AVDD", xd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
        conn(net, [("metal3", x - SW / 2, -1.0, x + SW / 2, height)])
    ports = ["VREFP", "VREFN", "CMP_STROBE", "IQ", "DVDD", "DVSS"]
    for k, n in enumerate(ports):
        py = y_mid + 2.0 + k * 3.0
        x2 = width - SW - 1.0
        b.box("metal4", x2 - 3.0, py - 0.5, x2, py + 0.5)
        b.label("metal4", n, x2 - 1.5, py)
        conn(n, [("metal4", x2 - 3.0, py - 0.5, x2, py + 0.5)])
    # ---- the inputs (see the module doc): bus rows of both rows of units extended east to
    # the Metal3 pair; from it a Metal4 pair east to the ports, above the middle zone's cells
    x2 = width - SW - 1.0
    y_r1 = y_top + u.height                         # row 1 is mirrored about this
    ub = {n: (u.pins[n][0][2], u.pins[n][0][4]) for n in BUSES}      # bus rows in the unit
    rows01 = [(ub[n][0], ub[n][1], y_r1 - ub[n][1], y_r1 - ub[n][0]) for n in ("INN", "INP")]
    x_e1 = x_arr + (N - 16) * u.width               # row 1 has 15 units: its bus rows continue
    ext1 = [(n, (x_e1 - 0.5, y_r1 - ub[n][1], x_arr + width_u, y_r1 - ub[n][0])) for n in BUSES]
    for n, box in ext1:                             # where a 16th would be
        b.box("metal4", *box)
    for n, (a0, a1, b0, b1) in zip(("INN", "INP"), rows01):
        x = xf[n]
        for y1, y2 in ((a0, a1), (b0, b1)):
            b.box("metal4", x_arr + width_u - 0.5, y1, x + 0.5, y2)
            b.box("via3", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
        b.box("metal3", x - 0.19, a0, x + 0.19, b1)
    y_low, y_high = ub["INN"][0], y_r1 - ub["INN"][0]
    for n in ("S1", "S2"):
        b.box("metal3", xf[n] - 0.19, y_low, xf[n] + 0.19, y_high)
    # the static buses of both rows run on east, past the pair (DVSS, DVDD, VBQ below its
    # lower end, AVDD across it), to their pins; CLK further, under DVDD and VBQ, to a riser
    # east of the strobe buffer that joins both rows, DVSS (below it) on to the DVSS lines
    # on both sides of the riser (the router had run CLK along the channel, beside a
    # comparator's VOP: 10.7 fF; unshielded, the riser met O2P of the ADC: 0.5 fF more than
    # O2N). The router keeps out of that strip on Metal3.
    x_ck = gx0 + round((d.x + strobe2.width + 1.0 - gx0) / P) * P + P
    assert x_ck + P + 0.19 <= x2 - 3.0
    for n in ("DVSS", "DVDD", "VBQ", "AVDD"):
        for y1, y2 in ((ub[n][0], ub[n][1]), (y_r1 - ub[n][1], y_r1 - ub[n][0])):
            bx = ("metal4", x_arr + width_u - 0.5, y1, (x_ck + P + 0.19) if n == "DVSS" else band[1] + 3.0, y2)
            b.box(*bx)
            conn(n, [bx])
    clk, shields = [], []
    for n in ("CLK", "DVSS"):
        for y1, y2 in ((ub[n][0], ub[n][1]), (y_r1 - ub[n][1], y_r1 - ub[n][0])):
            if n == "CLK":
                clk.append(("metal4", x_arr + width_u - 0.5, y1, x_ck + 0.19, y2))
            for x in ((x_ck,) if n == "CLK" else (x_ck - P, x_ck + P)):
                b.box("via3", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
        ya, yb = sum(ub[n]) / 2 - 0.19, y_r1 - sum(ub[n]) / 2 + 0.19
        if n == "CLK":
            clk.append(("metal3", x_ck - 0.19, ya, x_ck + 0.19, yb))
        else:
            shields += [("metal3", x - 0.19, ya, x + 0.19, yb) for x in (x_ck - P, x_ck + P)]
    _, px1, py1, px2, py2 = d.pins["Y"][0]                     # the buffer's output (Metal4) to the riser
    clk.append(("metal4", (px1 + px2) / 2, (py1 + py2) / 2 - 0.19, x_ck + 0.19, (py1 + py2) / 2 + 0.19))
    b.box("via3", x_ck - 0.13, (py1 + py2) / 2 - 0.13, x_ck + 0.13, (py1 + py2) / 2 + 0.13)
    for bx in clk + shields:
        b.box(*bx)
    nets.pop("CLK")
    # the shields on AVSS: the loads' substrate band (Metal2) extended under the pair
    b.box("metal2", pl_.x + rl.width - 1.0, y_mid, xf["S2"] + 0.19, y_mid + an.RING_W)
    for n in ("S1", "S2"):
        b.box("via2", xf[n] - 0.13, y_mid + 0.08, xf[n] + 0.13, y_mid + 0.34)
    east_top = max(y_mid + lad.height, y_mid + qn.height + 2.0 + qp.height, pc.y + cq.keepout4[3],
                   d.y + strobe2.height)
    yf = -1.0 + -(-(east_top + 4.0 + 1.0) // route.P) * route.P      # INN row (router row)
    yfp = yf + route.P
    for n, y, x1 in (("INN", yf, xf["INN"]), ("INP", yfp, xf["INP"]), ("AVSS", yf - route.P, xf["S2"]),
                     ("AVSS", yfp + route.P, xf["S2"])):
        b.box("metal4", x1 - 0.19, y - 0.19, x2, y + 0.19)
        b.box("via3", x1 - 0.13, y - 0.13, x1 + 0.13, y + 0.13)
        if n != "AVSS":
            b.box("metal4", x2 - 3.0, y - 0.19, x2, y + 0.19)
            b.label("metal4", n, x2 - 1.5, y)
    r = route.Router(gx0, -1.0, width, height, px=lg.PITCH)
    r.obstacle("metal3", band[0], -2.0, band[1], height + 1.0)
    r.obstacle("metal4", band[0], yf - 2 * route.P - 0.19, x2 + 0.5, yfp + 2 * route.P + 0.19)
    for n, box in ext1:
        r.obstacle("metal4", *box, None if n in ("INP", "INN", "CLK") else n)
    for n, (a0, a1, b0, b1) in zip(("INN", "INP"), rows01):
        for x1, y1, y2 in ((x_arr + width_u, a0, a1), (x_e1, b0, b1)):
            r.obstacle("metal4", x1 - 0.5, y1 - 0.68, band[1], y2 + 0.68)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    for lay, *bx in clk:
        r.obstacle(lay, *bx, "CLK")
    for lay, *bx in shields:
        r.obstacle(lay, *bx, "DVSS")
    r.obstacle("metal3", x_ck - P - 0.19, -2.0, xd - SW / 2 - 0.5, height + 1.0)    # up to the AVDD strap
    for p in placed:
        if p.name == "XCB2":
            for lay in ("metal3", "metal4"):
                for bx in bl.cell_shapes(p, lay):
                    r.obstacle(lay, *bx, "CLK")
            for bx in bl.cell_shapes(p, "via3"):
                r.via_keepout(*bx)
        elif p.name.startswith("U"):
            # the unit's own wires: obstacles, except its port stubs (pins)
            stubs = {tuple(round(v, 3) for v in sg[1:]) for pn in ("RP", "RN", "VOP", "VON", "TH")
                     for sg in p.pins[pn]}
            for lay in ("metal3", "metal4"):
                for bx in bl.cell_shapes(p, lay):
                    if lay == "metal3" and tuple(round(v, 3) for v in bx) in stubs:
                        continue
                    r.obstacle(lay, *bx)
            # and nothing of the block inside the unit (latch, preamp outputs, strobe) except
            # the port stubs (reached from outside): Metal4 over the whole unit, Metal3 short
            # of the stubs
            ya, yb = (p.y, p.y + u.height) if not p.mirror else (p.y - u.height, p.y)
            xa, xb = p.x, p.x + u.width
            r.obstacle("metal4", xa, ya - 1.0 if not p.mirror else ya, xb, yb if not p.mirror else yb + 1.0)
            if not p.mirror:
                r.obstacle("metal3", xa, ya - 1.0, xb, yb - 2.1)
            else:
                r.obstacle("metal3", xa, ya + 2.1, xb, yb + 1.0)
    # TH outputs (drawn by hand; routed, one ran beside a comparator's VOP in the channel):
    # east-edge stubs beside their row (row 0 below the middle zone, row 1 above it), spread
    # over the row height. From each unit's port stub one Metal4 row in the channel beside its
    # row of units (the west unit's nearest the units), east past the pair to a column of its
    # own, on that to the height of its stub. The units' other ports cross the rows at right
    # angles, VOP and VON of a unit the same ones.
    yrow = lambda j: -1.0 + j * route.P
    j0 = -(-(u.height + 0.66 + 1.0) // route.P)                 # row 0: rows upwards from here
    j1 = int((y_top - 0.66 + 1.0) // route.P)                    # row 1: downwards from here
    x_th = gx0 + -(-(band[1] + 3.0 + P - gx0) // P) * P          # the columns, east of the static pins
    th = []
    for e in range(N):
        r_, k = divmod(e, 16)
        n = f"TH{e}"
        if r_ == 0:
            py = 6.0 + k * (u.height - 12.0) / 15
            yc = yrow(j0 + k)
        else:
            py = y_top + 6.0 + k * (u.height - 12.0) / 15
            yc = yrow(j1 - k)
        py = -1.0 + round((py + 1.0) / route.P) * route.P        # on the router's Metal4 rows
        b.box("metal4", x2 - 3.0, py - 0.19, x2, py + 0.19)
        b.label("metal4", n, x2 - 1.5, py)
        _, sx1, sy1, sx2, sy2 = nets.pop(n)[0]                   # the unit's port stub
        xs_, xc = (sx1 + sx2) / 2, x_th + k * P
        ys_ = sy2 - 1.0 if r_ == 0 else sy1 + 1.0
        assert yc < y_mid - 0.66 if r_ == 0 else yc > y_mid + h_mid + 0.66
        for lay, bx in (("metal3", (xs_ - 0.19, min(ys_, yc) - 0.19, xs_ + 0.19, max(ys_, yc) + 0.19)),
                        ("metal4", (xs_ - 0.19, yc - 0.19, xc + 0.19, yc + 0.19)),
                        ("metal3", (xc - 0.19, min(py, yc) - 0.19, xc + 0.19, max(py, yc) + 0.19)),
                        ("metal4", (xc - 0.19, py - 0.19, x2, py + 0.19))):
            b.box(lay, *bx)
            th.append((lay, bx, n))
        for x, y in ((xs_, yc), (xc, yc), (xc, py)):
            b.box("via3", x - 0.13, y - 0.13, x + 0.13, y + 0.13)
    # the units' other ports straight across the TH rows (Metal3), routed from there
    ye = (yrow(j0 + 16), yrow(j1 - 15))
    for p in placed:
        if not p.name.startswith("U"):
            continue
        e = int(p.name[1:])
        r_ = e // 16
        for pn, n in (("RP", f"T{e}"), ("RN", f"T{30 - e}"), ("VOP", f"VOP{e}"), ("VON", f"VON{e}")):
            sg = p.pins[pn][0]
            nets[n].remove(sg)
            _, sx1, sy1, sx2, sy2 = sg
            bx = (sx1, sy2 - 0.5, sx2, ye[0] + 0.19) if r_ == 0 else (sx1, ye[1] - 0.19, sx2, sy1 + 0.5)
            b.box("metal3", *bx)
            th.append(("metal3", bx, n))
            conn(n, [("metal3", sx1, ye[0] - 0.49, sx2, ye[0] + 0.19) if r_ == 0 else
                     ("metal3", sx1, ye[1] - 0.19, sx2, ye[1] + 0.49)])
    for lay, bx, n in th:
        r.obstacle(lay, *bx, n)
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(b)
    return b, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "eeg_quantizer")
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    b, (w, h) = build()
    print(f"eeg_quantizer: {w:.1f} x {h:.1f} um")
    # DVSS and AVSS both tie to the p-substrate (latch and preamp taps): one net in LVS
    bl.check(b, "eeg_quantizer", [NETLIST], runs, drc=a.drc, lvs=a.lvs, ties=[("DVSS", "AVSS")])


if __name__ == "__main__":
    main()

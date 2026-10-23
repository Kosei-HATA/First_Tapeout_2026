#!/usr/bin/env python3
"""Layout of eeg_quantizer (gf180/tapeout/adc/eeg_quantizer.spice, tracker E4): the
5-bit flash quantizer of the ADC.

Comparator unit (unit_cell below, after blocks.unit_cell), one per threshold, bottom to
top:
  - seven Metal4 bus rows: DVSS, CLK, DVDD, VBQ, INN, INP, AVDD
  - preamp pair A on INP/INN (Nwell on SA), its gate bars facing the bus rows: INP / INN
    rise on two hand-drawn Metal3 lines side by side, between AVDD lines, straight from
    their bus rows to the bars; the router may not come near them (D6: the routed risers
    ran beside the preamp output VOP and the latch node OB, documentation/
    gf180_pex_20261023.md)
  - preamp tails (Nwell on AVDD), pair B on RP/RN (Nwell on SB): the pairs have bulk =
    source, so each sits in its own well
  - StrongARM NMOS (one ring, DVSS): tail XM0, input pair XM1/XM2 on TL, cross pair
  - latch PMOS (Nwell on DVDD): cross pair and the four precharge switches
  - the output logic on DVDD/DVSS: two equal inverters on OA/OB, the NOR SR latch, the
    output inverter (TH) and the dummy inverter
  - ports RP, RN, VOP, VON, TH on the top edge
So the strobe, the latch and its outputs stay in the upper part of the unit, away from
the inputs.
Array: 16 + 15 units in two rows. Below them: the 62 preamp loads (300 kohm,
297.98 x 1 um) in one resistor row with all west ends on AVSS, the ladder (320 units of
2 x 2 um in a serpentine, taps T0..T30), the VBQ bias (NMOS mirror from IQ, PMOS diode,
2 pF MIM) and the strobe buffer. Routing: route.Router, except the inputs.
Inputs (hand-drawn, D6): the INN/INP bus rows of both rows of units are fed at their east
end by one Metal3 pair (INN, INP side by side between AVSS lines) that runs from row 0
through the gap between the loads and the ladder up to row 1, and from it a Metal4 pair
(between AVSS lines) east to the INP / INN ports. Everything that switches crosses the
pairs at right angles, so it couples to INP and INN alike; the router keeps one more
track clear on both sides. The strobe (CLK) is fed at the west end of the rows.
Block ports, all on the east edge (Metal4 stubs; the ADC assembly feeds them from the
east): INP / INN above the bias, the other analog / clock / supply ports beside the
middle zone, TH0..15 beside row 0 and TH16..30 beside row 1 (east of the comparators
the rows leave room for their wires).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/quant_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
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


def unit_cell(b, name, parts, ports, gap=2.0, margin=0.8, bus_w=1.0, bus_gap=0.8):
    """blocks.unit_cell with the preamp inputs and the strobe drawn by hand:
      - parts[0] is the preamp pair with its INP / INN gate bars at the bottom; INP / INN
        rise from their bus rows to the bars on two neighbouring router columns, an AVDD
        line on the column beside each, and the router keeps off the next column on both
        sides and off the space between the bus rows and the bars;
      - CLK rises from its bus row on the last router columns but one (DVSS lines on both
        sides, the router off the next column) and reaches the CLK pins of the latch
        parts on Metal4 rows: a routed CLK riser beside one of the preamp outputs gave
        every comparator the same offset (3 fF more CLK coupling on VON than on VOP).
    Returns a blocks.Unit (pins: bus rows and port stubs)."""
    c = b.new_cell(name)
    nets, fixed = {}, []
    y = 0.6
    bus_y = {}
    w_max = max(cell.width + (x if x is not None else 1.0) for cell, _, x in parts) + margin + 0.2
    width = -(-round(w_max / P, 6) // 1) * P
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
    height = y + 2.0
    pins = {n: [("metal4", 0.0, a, width, bb)] for n, (a, bb) in bus_y.items()}
    gx0 = margin + 0.24
    col = lambda x: gx0 + round((x - gx0) / P) * P
    for k, n in enumerate(ports):
        x = col(margin + (width - 2 * margin) * (k + 0.5) / len(ports))
        c.box("metal3", x - 0.19, height - 1.6, x + 0.19, height)
        fixed.append(("metal3", (x - 0.19, height - 1.6, x + 0.19, height), n))
        nets.setdefault(n, []).append(("metal3", x - 0.19, height - 1.6, x + 0.19, height))
        pins[n] = [("metal3", x - 0.19, height - 1.6, x + 0.19, height)]
    # ---- the preamp inputs: [AVDD | INP | INN | AVDD] on four router columns
    pa = placed[0]
    ip, nn_ = pa.cell.pins["INP"][0], pa.cell.pins["INN"][0]
    yp, yn = pa.y + (ip[2] + ip[4]) / 2, pa.y + (nn_[2] + nn_[4]) / 2
    x_inn = col(pa.x + (nn_[1] + nn_[3]) / 2)
    x_inp = x_inn - P
    assert pa.x + nn_[1] + 0.19 <= x_inn <= pa.x + nn_[3] - 0.19
    assert pa.x + ip[1] + 0.19 <= x_inp - P and x_inn + P <= pa.x + ip[3] - 0.19
    y0 = bus_y["INN"][0]
    vc = lambda n: (bus_y[n][0] + bus_y[n][1]) / 2
    for x, n, ytop in ((x_inp, "INP", yp), (x_inn, "INN", yn), (x_inp - P, "AVDD", yp), (x_inn + P, "AVDD", yp)):
        c.box("metal3", x - 0.19, y0, x + 0.19, ytop + 0.19)
        c.box("via3", x - 0.13, vc(n) - 0.13, x + 0.13, vc(n) + 0.13)
        if n != "AVDD":
            c.box("via2", x - 0.13, ytop - 0.13, x + 0.13, ytop + 0.13)
    keep = (x_inp - 2 * P - 0.19, x_inn + 2 * P + 0.19)
    # ---- the strobe: [DVSS | CLK | DVSS] on the last three router columns
    last = lambda x: gx0 + int((x - gx0) // P) * P           # last router column at or below x
    x_clk = last(width - margin) - P
    clk_pins = [(p, sg) for p in placed[1:] for sg in p.pins.get("CLK", [])]
    if any(p.cell.cell.name != "qcmp_n" and p.cell.cell.name != "qcmp_pl" for p, _ in clk_pins):
        raise ValueError(f"{name}: CLK pins outside the latch parts")
    y_clk = max((sg[2] + sg[4]) / 2 for _, sg in clk_pins)
    for x, n in ((x_clk, "CLK"), (x_clk - P, "DVSS"), (x_clk + P, "DVSS")):
        c.box("metal3", x - 0.19, bus_y[n][0], x + 0.19, y_clk + 0.6)
        c.box("via3", x - 0.13, vc(n) - 0.13, x + 0.13, vc(n) + 0.13)
    jogs = []
    for _, (lay, x1, y1, x2, y2) in clk_pins:
        yc = (y1 + y2) / 2
        xp = last(x2 - 0.19 + 1e-6)                           # the pin's east-most column
        assert xp >= x1 + 0.19 - 1e-6
        c.box("metal4", xp - 0.19, yc - 0.19, x_clk + 0.19, yc + 0.19)
        for x in (xp, x_clk):
            c.box("via3", x - 0.13, yc - 0.13, x + 0.13, yc + 0.13)
        c.box("metal3", xp - 0.19, yc - 0.19, xp + 0.19, yc + 0.19)
        c.box("via2", xp - 0.13, yc - 0.13, xp + 0.13, yc + 0.13)
        jogs.append((xp, yc))
    for n in ("CLK",):              # drawn by hand: the latch parts' CLK pins leave the router
        nets[n] = [sg for sg in nets.get(n, []) if sg[0] == "metal4" and sg[4] - sg[2] > 0.5]
    r = route.Router(gx0, 0.0, width - margin, height - 0.2, px=P)
    # keep the router's shapes clear of the side edges: block the first/last columns
    r.obstacle("metal3", -1.0, -1.0, margin - 0.2, height + 1.0)
    r.obstacle("metal4", -1.0, -1.0, margin - 0.2, height + 1.0)
    r.obstacle("metal3", keep[0], -1.0, keep[1], yp + 0.7)
    r.obstacle("metal4", keep[0], bus_y["AVDD"][1] + 0.3, keep[1], yp + 0.7)
    r.obstacle("metal3", x_clk - 2 * P - 0.19, -1.0, x_clk + 2 * P + 0.19, y_clk + 0.8)
    for xp, yc in jogs:
        r.obstacle("metal4", xp - 0.5, yc - 0.19, x_clk + 2 * P + 0.19, yc + 0.19)
        r.obstacle("metal3", xp - 0.19, yc - 0.19, xp + 0.19, yc + 0.19)
        r.via_keepout(xp - 0.13, yc - 0.13, xp + 0.13, yc + 0.13)
    for lay, box, n in fixed:
        r.obstacle(lay, *box, n)
    for p in placed:   # wires already inside the parts (e.g. driver buses) are obstacles
        for lay in ("metal3", "metal4"):
            for bx in bl.cell_shapes(p, lay):
                r.obstacle(lay, *bx)
    failed = r.route({n: v for n, v in nets.items() if len(v) > 1}, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"{name}: unrouted {failed}")
    r.draw(c)
    return bl.Unit(c, width, height, pins, ports)


def comparator(b):
    ncell = an.multi_strip_cell(b, "qcmp_n", "n", [
        dict(w=4.0, l=0.28, seq=["TL", "CLK", "DVSS", "CLK", "TL"], order=["DVSS", "TL"]),
        dict(w=4.0, l=0.5, seq=["X", "VOP", "TL", "VON", "Y"], order=["TL", "X", "Y"]),
        dict(w=4.0, l=0.28, seq=["X", "OB", "OA"], order=["X", "OA"]),
        dict(w=4.0, l=0.28, seq=["Y", "OA", "OB"], order=["Y", "OB"])], bulk="DVSS")
    pl = an.multi_strip_cell(b, "qcmp_pl", "p", [
        dict(w=4.0, l=0.28, seq=["OA", "OB", "DVDD", "OA", "OB"], order=["DVDD", "OA", "OB"]),
        dict(w=2.0, l=0.28, seq=["OA", "CLK", "DVDD", "CLK", "OB"], order=["DVDD", "OA", "OB"]),
        dict(w=2.0, l=0.28, seq=["X", "CLK", "DVDD", "CLK", "Y"], order=["DVDD", "X", "Y"])], bulk="DVDD")
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
    rail = {"VDD": "DVDD", "VSS": "DVSS"}
    logic = Combo(b, "qcmp_logic", [(qinv, rail | {"A": "OA", "Y": "SETQ"}), (qinv, rail | {"A": "OB", "Y": "RSTQ"}),
                                    (qnor, rail | {"A": "RSTQ", "B": "QB", "Y": "Q"}),
                                    (qnor, rail | {"A": "SETQ", "B": "Q", "Y": "QB"}),
                                    (qinv, rail | {"A": "QB", "Y": "TH"}), (qinv, rail | {"A": "Q", "Y": "QD"})])
    ident = lambda c: {k: k for k in c.pins}
    parts = [(pa, {k: k for k in pa.pins if k not in ("INP", "INN")}, None), (tail, ident(tail), None),
             (pb, ident(pb), None), (ncell, ident(ncell), None), (pl, ident(pl), None), (logic, ident(logic), 1.6)]
    # 2 um between parts: neighbouring Nwells of different nets keep 1.4 um (NW.2b)
    return unit_cell(b, "eeg_qcmp", parts, ["RP", "RN", "VOP", "VON", "TH"], gap=2.0)


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
        for n in BUSES:            # the buses of each row are joined at the west end
            pass
    for pn in ("RP", "RN", "VOP", "VON", "TH"):
        nets.pop(pn, None)
    # bus pins: of the units' bus rows keep only the two west units' pieces (the rest are
    # joined by abutment); pins of other cells on these nets stay
    unit_bus = set()
    for p in placed:
        if p.name.startswith("U") and int(p.name[1:]) % 16 >= 2:
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
        r.obstacle("metal4", *box, None if n in ("INP", "INN") else n)
    for n, (a0, a1, b0, b1) in zip(("INN", "INP"), rows01):
        for x1, y1, y2 in ((x_arr + width_u, a0, a1), (x_e1, b0, b1)):
            r.obstacle("metal4", x1 - 0.5, y1 - 0.68, band[1], y2 + 0.68)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    for p in placed:
        if p.name == "XCB2":
            for lay in ("metal3", "metal4"):
                for bx in bl.cell_shapes(p, lay):
                    r.obstacle(lay, *bx, "CLK")
            for bx in bl.cell_shapes(p, "via3"):
                r.via_keepout(*bx)
        elif p.name.startswith("U"):
            e = int(p.name[1:])
            k = e % 16
            # the unit's own wires: obstacles, except its bus rows (named nets, open only in
            # the two west units of each row) and its port stubs (pins)
            bus_rows = {}
            for n in BUSES:
                sg = p.pins[n][0]
                bus_rows[(round(sg[2], 3), round(sg[4], 3))] = None if n in ("INP", "INN") else n
            stubs = {tuple(round(v, 3) for v in sg[1:]) for pn in ("RP", "RN", "VOP", "VON", "TH")
                     for sg in p.pins[pn]}
            for lay in ("metal3", "metal4"):
                for bx in bl.cell_shapes(p, lay):
                    key = (round(bx[1], 3), round(bx[3], 3))
                    if lay == "metal4" and key in bus_rows:
                        r.obstacle(lay, *bx, bus_rows[key] if k < 2 else None)
                        continue
                    if lay == "metal3" and tuple(round(v, 3) for v in bx) in stubs:
                        continue
                    r.obstacle(lay, *bx)
    # TH outputs: east-edge stubs beside their row (row 0 below the middle zone, row 1
    # above it), spread over the row height
    for e in range(N):
        r_, k = divmod(e, 16)
        n = f"TH{e}"
        if r_ == 0:
            py = 6.0 + k * (u.height - 12.0) / 15
        else:
            py = y_top + 6.0 + k * (u.height - 12.0) / 15
        py = -1.0 + round((py + 1.0) / route.P) * route.P        # on the router's Metal4 rows
        b.box("metal4", x2 - 3.0, py - 0.19, x2, py + 0.19)
        b.label("metal4", n, x2 - 1.5, py)
        conn(n, [("metal4", x2 - 3.0, py - 0.19, x2, py + 0.19)])
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

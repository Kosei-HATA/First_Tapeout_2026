#!/usr/bin/env python3
"""Layout of eeg_quantizer (gf180/tapeout/adc/eeg_quantizer.spice, tracker E4): the
5-bit flash quantizer of the ADC.

Comparator unit (blocks.unit_cell), one per threshold, bottom to top:
  - seven Metal4 bus rows: DVSS, CLK, DVDD, INN, INP, VBQ, AVDD
  - StrongARM NMOS (one ring, DVSS): tail XM0, input pair XM1/XM2 on TL, cross pair
  - latch PMOS (Nwell on DVDD): cross pair and the four precharge switches
  - preamp tails (Nwell on AVDD), pair A on INP/INN (Nwell on SA), pair B on RP/RN
    (Nwell on SB): the pairs have bulk = source, so each sits in its own well
  - the output logic on DVDD/DVSS: two equal inverters on OA/OB, the NOR SR latch, the
    output inverter (TH) and the dummy inverter
  - ports RP, RN, VOP, VON, TH on the top edge
Array: 16 + 15 units in two rows. Below them: the 62 preamp loads (300 kohm,
297.98 x 1 um) in one resistor row with all west ends on AVSS, the ladder (320 units of
2 x 2 um in a serpentine, taps T0..T30), the VBQ bias (NMOS mirror from IQ, PMOS diode,
2 pF MIM) and the strobe buffer. Routing: route.Router.
Block ports, all on the east edge (Metal4 stubs; the ADC assembly feeds them from the
east): the analog / clock / supply ports beside the middle zone, TH0..15 beside row 0 and
TH16..30 beside row 1 (east of the comparators the rows leave room for their wires).

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
BUSES = ["DVSS", "CLK", "DVDD", "INN", "INP", "VBQ", "AVDD"]
N = 31
SW = 2.4


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
    pa = an.strip_cell(b, "qcmp_pa", "p", 10.0, 1.25, ["VON", "INP", "SA", "INN", "VOP", "INN", "SA", "INP", "VON"],
                       order=["SA", "VON", "VOP"], bulk="SA")
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
    parts = [(ncell, ident(ncell), None), (pl, ident(pl), None), (tail, ident(tail), None), (pa, ident(pa), None),
             (pb, ident(pb), None), (logic, ident(logic), 1.6)]
    # 2 um between parts: neighbouring Nwells of different nets keep 1.4 um (NW.2b)
    return bl.unit_cell(b, "eeg_qcmp", parts, BUSES, ["RP", "RN", "VOP", "VON", "TH"], gap=2.0)


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
    xm = x0 + 2.0
    place(rl, xm, y_mid, "LOADS")
    xm += rl.width + 3.0
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
    x_arr = x0
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
    height = y_top + u.height + 2.0
    width = max(x_arr + width_u, rows.x0 + rows.width() + 3.0, d.x + strobe2.width) + 4.0 + SW
    # ---- power straps (west AVSS, east AVDD) and ports (east, Metal4)
    xv, xd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("AVSS", xv), ("AVDD", xd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
        conn(net, [("metal3", x - SW / 2, -1.0, x + SW / 2, height)])
    ports = ["INP", "INN", "VREFP", "VREFN", "CMP_STROBE", "IQ", "DVDD", "DVSS"]
    for k, n in enumerate(ports):
        py = y_mid + 2.0 + k * 3.0
        x2 = width - SW - 1.0
        b.box("metal4", x2 - 3.0, py - 0.5, x2, py + 0.5)
        b.label("metal4", n, x2 - 1.5, py)
        conn(n, [("metal4", x2 - 3.0, py - 0.5, x2, py + 0.5)])
    gx0 = (x_arr + 1.04) % lg.PITCH
    r = route.Router(gx0, -1.0, width, height, px=lg.PITCH)
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
                bus_rows[(round(sg[2], 3), round(sg[4], 3))] = n
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
    x2 = width - SW - 1.0
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

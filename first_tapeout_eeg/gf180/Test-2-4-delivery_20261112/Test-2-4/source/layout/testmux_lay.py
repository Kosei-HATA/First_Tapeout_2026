#!/usr/bin/env python3
"""Layout of eeg_testmux (gf180/tapeout/test/eeg_testmux.spice, tracker A5): the analog
test multiplexer to the ATP pad. First routed block of the flow (logic cells, grid
router, power straps, ports).

Two logic rows (row 1 mirrored onto row 0's VDD rail):
  row 0: the five TEST_CFG inverters, then codes 0..7 (NOR5 decoder, inverter, TG)
  row 1: codes 8..15; code 11 adds the TG that dumps ITST to AVSS, codes 12..15 are
         T switches (two TGs and the NMOS that grounds their middle node)
Power: Metal3 straps at the west edge (AVSS, AVDD) on the row rails. Signal ports:
Metal3 stubs along the top edge. Routing: route.Router on Metal3/Metal4.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/testmux_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import blocks as bl

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "test", "eeg_testmux.spice")
NODES = ["AVSS", "VCM", "VREFP", "VREFN", "VBN", "VBCM", "VBN1", "VNC1", "VPC1", "VBPC2", "VBNC2", "ITST",
         "AOP", "AON", "O2P", "O2N"]
X0 = 4.0          # cells start here; the power straps sit west of it


def build():
    b = g.Block("eeg_testmux")
    p, n = lg.inv_seq(1)
    inv = lg.cmos_cell(b, "eeg_tm_inv", p, n, 2.0, 1.0, ["A", "Y"])
    p, n = lg.nor_seq(["A", "B", "C", "D", "E"], 1)
    nor5 = lg.cmos_cell(b, "eeg_tm_nor5", p, n, 4.0, 1.0, ["A", "B", "C", "D", "E", "Y"])
    tg = lg.tg_cell(b, "eeg_tm_tg", 2, 2, 2.0, 4.0, a="A", y="B", gn="G", gp="GN")
    sh = lg.nmos_cell(b, "tm_shunt", 1.0, 0.28, 1, "D", "G", "VSS")
    rows = bl.Rows(b, X0, 0.0)
    nets = {}

    def conn(net, pin):
        nets.setdefault(net, []).extend(pin)

    for k in range(5):
        c = rows.add(0, inv, f"XIC{k}")
        conn(f"TC{k}", c.pins["A"])
        conn(f"TCB{k}", c.pins["Y"])
    for code in range(16):
        r = 0 if code < 8 else 1
        bits = [(code >> i) & 1 for i in range(4)]
        d = rows.add(r, nor5, f"XD{code}", gap=lg.PITCH)
        # NOR5 inputs: TCB<i> where bit i is 1, else TC<i>; E = TCB4
        for i, pin in enumerate("ABCD"):
            conn(f"TCB{i}" if bits[i] else f"TC{i}", d.pins[pin])
        conn("TCB4", d.pins["E"])
        conn(f"S{code}", d.pins["Y"])
        v = rows.add(r, inv, f"XDB{code}")
        conn(f"S{code}", v.pins["A"])
        conn(f"SB{code}", v.pins["Y"])
        node = NODES[code]
        if code < 12:
            t = rows.add(r, tg, f"XT{code}")
            conn(node, t.pins["A"])
            conn("ATP", t.pins["B"])
            conn(f"S{code}", t.pins["G"])
            conn(f"SB{code}", t.pins["GN"])
            if code == 11:
                t2 = rows.add(r, tg, "XT11D")
                conn("ITST", t2.pins["A"])
                conn("AVSS", t2.pins["B"])
                conn(f"SB{code}", t2.pins["G"])
                conn(f"S{code}", t2.pins["GN"])
        else:
            ta = rows.add(r, tg, f"XT{code}A")
            tb = rows.add(r, tg, f"XT{code}B")
            s = rows.add(r, sh, f"XT{code}G")
            conn(node, ta.pins["A"])
            conn(f"M{code}", ta.pins["B"])
            conn(f"M{code}", tb.pins["A"])
            conn("ATP", tb.pins["B"])
            for t in (ta, tb):
                conn(f"S{code}", t.pins["G"])
                conn(f"SB{code}", t.pins["GN"])
            conn(f"M{code}", s.pins["D"])
            conn(f"SB{code}", s.pins["G"])
    rows.fill_all()
    width = rows.width()
    x1 = X0 + width + 1.0
    y_top = rows.height() + 8.0
    # power straps west of the cells (AVSS outermost)
    straps = bl.power_straps(b, rows, 0.9, 2.6, names=("AVDD", "AVSS"))
    # signal ports along the top edge, spread over the width
    pnames = [f"TC{k}" for k in range(5)] + ["ATP"] + [n for n in NODES if n != "AVSS"]
    step = (x1 - 6.0) / len(pnames)
    gx0 = (X0 + lg.GATE0) % lg.PITCH        # Metal3 columns on the gate centres
    snap = lambda x: gx0 + round((x - gx0) / lg.PITCH) * lg.PITCH
    ports = bl.ports_top(b, pnames, [snap(6.0 + step * (k + 0.5)) for k in range(len(pnames))], y_top)
    for n, pin in ports.items():
        conn(n, [pin])
    obst = [("metal3", *box, net) for net, box in straps] + [(pin[0], *pin[1:], n) for n, pin in ports.items()]
    for net, box in straps:
        if net == "AVSS":
            conn("AVSS", [("metal3", *box)])
    r = bl.route.Router(gx0, -1.0, x1 + 1.0, y_top + 0.5, px=lg.PITCH)
    for lay, x1_, y1_, x2_, y2_, net in obst:
        r.obstacle(lay, x1_, y1_, x2_, y2_, net)
    failed = r.route(nets, rounds=6)
    for n in failed:
        for pin in nets[n]:
            if not r.access(pin, r.index[n]):
                print("no access:", n, pin)
    if failed:
        raise RuntimeError(f"unrouted: {failed}")
    r.draw(b)
    for net, (a, y1_, c_, y2_) in straps:
        b.label("metal3", net, (a + c_) / 2, (y1_ + y2_) / 2)
    return b, (x1 + 1.0, y_top + 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "eeg_testmux")
    os.makedirs(runs, exist_ok=True)
    b, (w, h) = build()
    print(f"eeg_testmux: {w:.1f} x {h:.1f} um")
    bl.check(b, "eeg_testmux", [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

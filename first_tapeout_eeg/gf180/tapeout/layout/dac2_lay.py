#!/usr/bin/env python3
"""Layout of eeg_dac2 (gf180/tapeout/adc/eeg_dac2.spice, tracker A3/B2/E4): the
31-element current-steering DAC of the ADC's second stage.

Unit cell (blocks.unit_cell), one per element, bottom to top:
  - eight Metal4 bus rows across the whole unit: VSS, VBN (= IDN), VBNC, OUTN, OUTP,
    VBPC, VBP (= IDP), VDD; units side by side join them
  - NMOS (one guard ring): the source W1/L20 and its cascode W1/L1 sharing the YS
    diffusion, and the steering pair W0.5/L0.28 on YN
  - PMOS (one guard ring, Nwell): the same on XS / XP
  - the two inverters DB = not SEL, D = not DB
  - SEL on a Metal3 stub at the top edge
Array: 16 units in row 0 and 15 in row 1, mirrored above it, so the SEL stubs of both
rows face a 26 um channel between them and the buses lie on the block's bottom and top
edges (joined by Metal3 risers at the east end). The SEL lines leave the channel at the
west end and run down a west column to their ports on the bottom edge (SEL0 westmost);
eeg_adc_dig sits below the DAC in the ADC (gf180/tapeout/layout/adc_lay.py). East of the
array: the bias diodes (PMOS W1/L20 x 10 on IDP, NMOS on IDN) and the four 1 pF MIM
decouplers; the bias, output and supply ports are Metal4 stubs on the east edge.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/dac2_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import route

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_dac2.spice")
BUSES = ["VSS", "IDN", "VBNC", "OUTN", "OUTP", "VBPC", "IDP", "VDD"]
N_UNITS = 31
SEL_W = 30.0        # west column for the SEL lines down to the bottom-edge ports
CH = 26.0           # channel between the rows: the units' SEL stubs face it


class Combo:
    """Several cells in one cell, side by side, with their pins merged by net."""

    def __init__(self, b, name, items):
        self.cell = b.new_cell(name)
        self.pins = {}
        x = 0.0
        for cell, cmap in items:
            self.cell.place(cell.cell, x, 0.0)
            for pn, segs in cell.pins.items():
                net = cmap.get(pn, pn)
                self.pins.setdefault(net, []).extend((lay, x + a, y1, x + c_, y2) for lay, a, y1, c_, y2 in segs)
            x += cell.width
        self.width, self.height = x, max(getattr(c, "height", lg.H) for c, _ in items)


def unit(b):
    p, n = lg.inv_seq(1)
    inv = lg.cmos_cell(b, "eeg_dac2_inv", p, n, 1.0, 0.5, ["A", "Y"])
    invs = Combo(b, "dac2_invs", [(inv, {"A": "SEL", "Y": "DB"}), (inv, {"A": "DB", "Y": "D"})])
    sw = ["OUTP", "DB", "{}", "D", "OUTN"]
    ncell = an.multi_strip_cell(b, "dac2_n", "n", [
        dict(w=1.0, l=[20.0, 1.0], seq=["VSS", "VBN", "YS", "VBNC", "YN"], gates={"VBN": ("t", 0), "VBNC": ("t", 0)},
             order=["VSS", "YN"]),
        dict(w=0.5, l=0.28, seq=[x.format("YN") for x in sw], gates={"DB": ("t", 0), "D": ("t", 1)},
             order=["YN", "OUTP", "OUTN"])])
    pcell = an.multi_strip_cell(b, "dac2_p", "p", [
        dict(w=1.0, l=[20.0, 1.0], seq=["VDD", "VBP", "XS", "VBPC", "XP"], gates={"VBP": ("t", 0), "VBPC": ("t", 0)},
             order=["VDD", "XP"]),
        dict(w=0.5, l=0.28, seq=[x.format("XP") for x in sw], gates={"DB": ("t", 0), "D": ("t", 1)},
             order=["XP", "OUTP", "OUTN"])])
    ident = lambda cell, extra=None: {pn: pn for pn in cell.pins} | (extra or {})
    parts = [(ncell, ident(ncell, {"VBN": "IDN"}), None), (pcell, ident(pcell, {"VBP": "IDP"}), None),
             (invs, {k: k for k in invs.pins}, 1.6)]
    return bl.unit_cell(b, "eeg_dac2_unit", parts, BUSES, ["SEL"])


def build():
    b = g.Block("eeg_dac2")
    u = unit(b)
    # bias: the two mirror diodes and the decoupling MIMs, east of the array
    pd = an.multi_strip_cell(b, "dac2_pd", "p", [dict(w=1.0, l=20.0, seq=["VDD", "IDP", "IDP", "IDP", "VDD"],
                                                       order=["VDD", "IDP"]) for _ in range(5)])
    nd = an.multi_strip_cell(b, "dac2_nd", "n", [dict(w=1.0, l=20.0, seq=["VSS", "IDN", "IDN", "IDN", "VSS"],
                                                       order=["VSS", "IDN"]) for _ in range(5)])
    mims = [an.mim_cell(b, f"dac2_c{k}", 22.18, top, bot) for k, (top, bot) in
            enumerate((("IDP", "VDD"), ("IDN", "VSS"), ("VBPC", "VDD"), ("VBNC", "VSS")))]
    nets = {}

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def unit_y(seg, y0, mir):
        lay, a, y1, c_, y2 = seg
        return (y0 - y2, y0 - y1) if mir else (y0 + y1, y0 + y2)

    x_arr = round((4.0 + SEL_W) / lg.PITCH) * lg.PITCH
    width_arr = 16 * u.width
    y_row1 = 2 * u.height + CH              # row 1 is mirrored: its origin is its top edge
    rows = [list(range(16)), list(range(16, N_UNITS))]
    # the units' Metal3 / Metal4 shapes are obstacles for the block router except the bus
    # rows (named) and the SEL stubs (pins)
    obst = []
    bus_y = {}
    for r, units in enumerate(rows):
        y0, mir = (0.0, False) if r == 0 else (y_row1, True)
        for k, e in enumerate(units):
            x = x_arr + k * u.width
            b.place(u.cell, x, y0, mirror=mir)
            y1, y2 = unit_y(u.pins["SEL"][0], y0, mir)
            lay, a, _, c_, _ = u.pins["SEL"][0]
            sel = (lay, x + a, y1, x + c_, y2)
            conn(f"SEL{e}", [sel])
            p = bl.Placed(u, x, y0, mir, f"U{e}")
            rows_m4 = {}
            for n in BUSES:
                for sg in p.pins[n]:
                    rows_m4[(round(sg[2], 3), round(sg[4], 3))] = n
            for lay in ("metal3", "metal4"):
                for bx in bl.cell_shapes(p, lay):
                    if lay == "metal4" and (round(bx[1], 3), round(bx[3], 3)) in rows_m4:
                        obst.append((lay, bx, rows_m4[(round(bx[1], 3), round(bx[3], 3))]))
                    elif lay == "metal3" and abs(bx[0] - sel[1]) < 1e-3 and abs(bx[1] - sel[2]) < 1e-3:
                        continue
                    else:
                        obst.append((lay, bx, None))
        # this row's buses, as pins at the east end of the row (towards the bias section)
        for n in BUSES:
            y1, y2 = unit_y(u.pins[n][0], y0, mir)
            xe = x_arr + len(units) * u.width
            conn(n, [("metal4", xe - 2 * u.width, y1, xe, y2)])
    # east side: bias diodes and MIMs
    x = x_arr + width_arr + 6.0
    pd_p = bl.Placed(pd, x, 0.0, False, "PD")
    b.place(pd.cell, x, 0.0)
    nd_p = bl.Placed(nd, x, pd.height + 2.0, False, "ND")
    b.place(nd.cell, x, pd.height + 2.0)
    x_m = x + max(pd.width, nd.width) + 4.0
    keep = []
    for k, mc in enumerate(mims):
        mx, my = x_m + (k % 2) * (mc.width + 2.0), (k // 2) * (mc.height + 2.0)
        b.place(mc.cell, mx, my)
        p = bl.Placed(mc, mx, my, False, f"C{k}")
        keep.append(((mx + mc.keepout[0], my + mc.keepout[1], mx + mc.keepout[2], my + mc.keepout[3]),
                     (mx + mc.keepout4[0], my + mc.keepout4[1], mx + mc.keepout4[2], my + mc.keepout4[3])))
        for n, segs in p.pins.items():
            conn(n, segs)
    for p in (pd_p, nd_p):
        for n, segs in p.pins.items():
            conn(n, segs)
    height = max(y_row1, nd_p.y + nd.height + 2.0, 2 * (mims[0].height + 2.0)) + 4.0
    width = x_m + 2 * (mims[0].width + 2.0) + 6.0
    gx0 = (x_arr + 1.04) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    # block ports: east-edge Metal4 stubs for the bias, outputs and supplies; SEL0..30
    # Metal3 stubs on the bottom edge of the west column (in index order from the west)
    port_nets = ["IDP", "IDN", "VBPC", "VBNC", "OUTP", "OUTN", "VDD", "VSS"]
    for k, n in enumerate(port_nets):
        py = -1.0 + round((height - 2.0 - k * 3.0 + 1.0) / route.P) * route.P
        b.box("metal4", width - 3.0, py - 0.19, width, py + 0.19)
        b.label("metal4", n, width - 1.5, py)
        conn(n, [("metal4", width - 3.0, py - 0.19, width, py + 0.19)])
    pp = bl.ports_bottom(b, [f"SEL{e}" for e in range(N_UNITS)],
                         [snap(4.0 + k * lg.PITCH) for k in range(N_UNITS)], -1.0)
    for n, pin in pp.items():
        conn(n, [pin])
    r = route.Router(gx0, -1.0, width, height, px=lg.PITCH)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    for lay, bx, n in obst:
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
    runs = os.path.join(HERE, "runs", "eeg_dac2")
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    b, (w, h) = build()
    print(f"eeg_dac2: {w:.1f} x {h:.1f} um")
    bl.check(b, "eeg_dac2", [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

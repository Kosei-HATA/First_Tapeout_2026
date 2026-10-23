#!/usr/bin/env python3
"""Layout of adc_rdac (LVS wrapper gf180/tapeout/layout/lvs/adc_rdac.spice, tracker E4):
the ADC's stage-1 input resistors RIN and the DAC1 (gf180/tapeout/adc/eeg_dac1.spice).

Since C1 was halved (10/23) RIN is 16 unit resistors per side and every DAC1 element
two units in series (RIN/RD1 = 31/32 by construction), so all 156 units (300 kohm
ppolyf_u_1k, 291.28 x 1 um) sit in one resistor array. An element is folded: its two
units have the middle node MP / MN on their west ends and VRP, XP (XN, VRN) on their
east ends. Rows per DAC1 cell k, bottom to top: [RIN_P] RPA RPB | RNB RNA [RIN_N]
(RIN rows at even k), mirror images about the element's axis between RPB and RNB; the
axes are 8 um apart.

The even (ISI) error of DAC1 (documentation/gf180_pex_20261023.md, D6) comes from the
couplings of the steering nodes XP / XN, which float during the common break, to the
switching lines; only the difference between the XP and the XN coupling of a line counts.
So each element's steering nodes are drawn by hand and mirror-symmetric:
  - the four switches (dac1_quad) sit at the east ends of the element's rows, two NMOS
    strips [OUTN DB XP D OUTP] below the axis and [OUTP DB XN D OUTN] above it, the DB
    and D fingers shared by both strips and contacted on the axis; XP / XN reach the
    strips on straight Metal2 lines from the RPB / RNB heads;
  - D leaves on Metal2 and DB on Metal4 along the axis to the east, so they couple to XP
    and XN alike; a Metal3 AVSS strap on both sides of the switch column and Metal4 AVSS
    between the DB lines screen the column;
  - no other line (other cells' D / DB / SEL, the latches, the break lines) comes within
    8 um of the column: the router (route.Router) works only east of it, where the logic
    (latch TGs, inverters, NORs of every cell, and the common-break driver
    eeg_dac1_brk) sits in rows, cells 2r and 2r+1 in row r beside their axes.
Between the array and the switch column: Metal3 buses VREFP, VREFN, I1N, I1P (the
switches' outputs and the RIN east ends), west of the array INN, INP; all static.
Ports (for the ADC assembly, gf180/tapeout/layout/adc_lay.py): INN, INP, VREFP, VREFN
above their buses and I1P, I1N at the east end of the top edge (Metal4 runs above the
logic); SEL1_0..30 and DAC_CLK on the bottom edge under the logic, above a 14 um
channel (the SEL1 lines come from eeg_adc_dig along the bottom of the ADC band).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/rdac1_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import fets as f
import netblock as nb
import route

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [os.path.join(HERE, "lvs", "adc_rdac.spice"), os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_dac1.spice")]
SW = 2.4
YB = 14.0           # bottom channel for the SEL1 / DAC_CLK ports
W2 = 0.38           # hand-drawn Metal2 lines
# switch quad (local: axis at y = 0, west edge of its ring at x = 0)
Q_XC = an.RING_W + an.GAP + 0.5          # COMP left edge (0.5 for the dummy poly)
Q_W = 1.0                                # finger width (eeg_dac1_cell: W 1 um, L 0.28)
Q_Y0 = 0.48                              # axis to COMP (poly contacts on the axis, PO_EXT)
Y_X = 0.8                                # XP / XN lines (the RPB / RNB head rows)
Y_O1, Y_O2 = 1.48, 2.18                  # output straps of S/D 0 and S/D 2
RING_IN = 2.66                           # ring inner edge
Y_RB = RING_IN + an.RING_W / 2           # Metal2 band on the ring's bottom / top side
PITCH_AX = 8.0                           # axis to axis (5 resistor rows)


def quad_cell(b):
    """The four steering switches of one element (eeg_dac1_cell XSPP, XSPN, XSNN, XSNP).
    Mirror image of itself about the axis with XP <-> XN and OUTP <-> OUTN (D and DB on
    the axis). Returns (cell, width, {name: x}) with the x of the S/D columns and of the
    gate contacts; every line to the outside starts at the cell's west (XP, XN, outputs,
    ring bands) or east edge (D on Metal2, DB on Metal4, ring bands)."""
    c = b.new_cell("dac1_quad")
    bot = f.Strip("n", Q_W, 0.28, ["OUTN", "DB", "XP", "D", "OUTP"])
    top = f.Strip("n", Q_W, 0.28, ["OUTP", "DB", "XN", "D", "OUTN"])
    yb, yt = -Q_Y0 - Q_W, Q_Y0
    ext_o1, ext_o2 = Y_O1 - (Q_Y0 + Q_W - 0.06) + 0.19, Y_O2 - (Q_Y0 + Q_W - 0.06) + 0.19
    f.draw_strip(c, bot, Q_XC, yb, gates={"DB": ("T", 0.0), "D": ("T", 0.0)},
                 ext={"OUTN": (ext_o1, 0.0), "OUTP": (ext_o2, 0.0)})
    f.draw_strip(c, top, Q_XC, yt, gates={"DB": ("B", 0.0), "D": ("B", 0.0)},
                 ext={"OUTP": (0.0, ext_o1), "OUTN": (0.0, ext_o2)})
    x_sd = [Q_XC + x for x in bot.sdx]                       # OUTN|OUTP, X, OUTP|OUTN columns
    x_g = [Q_XC + gx + 0.14 for gx in bot.gx]               # DB, D finger centres
    width = Q_XC + bot.length + 0.5 + an.GAP + an.RING_W
    for xd in (Q_XC - 0.24 - 0.28, Q_XC + bot.length + 0.24):     # dummy poly at both ends
        c.box("poly2", xd, yb - f.PO_EXT, xd + 0.28, yt + Q_W + f.PO_EXT)
    # gate contacts on the axis
    for x in x_g:
        c.box("poly2", x - f.PO_PAD / 2, -f.PO_PAD / 2, x + f.PO_PAD / 2, f.PO_PAD / 2)
        c.box("contact", x - f.CO / 2, -f.CO / 2, x + f.CO / 2, f.CO / 2)
        c.box("metal1", x - 0.19, -0.19, x + 0.19, 0.19)
        c.box("via1", x - 0.13, -0.13, x + 0.13, 0.13)
    xdb, xd = x_g
    c.box("metal2", xdb - 0.19, -0.19, xdb + 0.19, 0.19)          # DB: via stack to Metal4
    c.box("via2", xdb - 0.13, -0.13, xdb + 0.13, 0.13)
    c.box("metal3", xdb - 0.19, -0.19, xdb + 0.19, 0.19)
    c.box("via3", xdb - 0.13, -0.13, xdb + 0.13, 0.13)
    c.box("metal4", xdb - 0.19, -0.19, width, 0.19)
    c.box("metal2", xd - 0.19, -0.19, width, 0.19)                # D on Metal2
    # S/D lines: (column, y, sign): X on the middle column, outputs on the end columns
    for s in (-1, 1):
        for x, y in ((x_sd[1], Y_X), (x_sd[0], Y_O1), (x_sd[2], Y_O2)):
            c.box("via1", x - 0.13, s * y - 0.13, x + 0.13, s * y + 0.13)
            c.box("metal2", 0.0, s * y - W2 / 2, x + 0.19, s * y + W2 / 2)
    # substrate ring (AVSS) with a Metal2 band on its bottom and top sides
    yr = RING_IN + an.RING_W
    f.ring(c, "p", 0.0, -yr, width, yr, w=an.RING_W, well=False)
    for s in (-1, 1):
        c.box("metal2", 0.0, s * Y_RB - W2 / 2, width, s * Y_RB + W2 / 2)
        x = 0.4
        while x < width - 0.4:
            c.box("via1", x - 0.13, s * Y_RB - 0.13, x + 0.13, s * Y_RB + 0.13)
            x += 0.8
    return c, width, {"sd": x_sd, "g": x_g}


def element_rows(k):
    """Row index of RPB of DAC1 cell k (rows per pair of cells: 10)"""
    return 10 * (k // 2) + (2 if k % 2 == 0 else 7)


def build():
    b = g.Block("adc_rdac")
    subs = nb.parse(FILES)
    items = nb.flatten(subs, "adc_rdac")
    nets = {}

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def m2(x1, y, x2, w=W2):
        b.box("metal2", min(x1, x2), y - w / 2, max(x1, x2), y + w / 2)

    def via2_on(x1, x2, y):
        """via2 between a Metal2 line at y and a Metal3 bus x1..x2 (two vias)"""
        xc = (x1 + x2) / 2
        for x in (xc - 0.3, xc + 0.3):
            b.box("via2", x - 0.13, y - 0.13, x + 0.13, y + 0.13)
        b.box("metal2", x1, y - W2 / 2, x2, y + W2 / 2)

    # ---- sort the leaves: resistors, switch NMOS (per DAC1 cell), gates
    res, sw, gates = [], {}, []
    for path, model, env, cnets in items:
        if model == "dev" and env.model == "ppolyf_u_1k":
            res.append(env)
        elif model == "dev" and env.model == "nfet_03v3" and ".XS" in path:
            cell = path.rsplit(".", 1)[0]
            sw.setdefault(cell, []).append(env)
        else:
            gates.append((path, model, env, cnets))
    cells = sorted(sw, key=lambda s: int(s.split(".XC")[-1]))
    dev = {d.name: d for d in res}
    sw_nets = {}
    for cell in cells:
        d = {(t.d, t.g, t.s) for t in sw[cell]}
        xp, xn = dev[f"{cell}.XRPB"].g, dev[f"{cell}.XRNB"].g
        dd = [t.g for t in sw[cell] if t.d == xp and t.s == "I1P"]
        ddb = [t.g for t in sw[cell] if t.d == xp and t.s == "I1N"]
        if len(d) != 4 or not dd or not ddb:
            raise ValueError(f"{cell}: unexpected switches {sw[cell]}")
        sw_nets[cell] = (xp, xn, dd[0], ddb[0])
    # ---- resistor array: rows [RIN_P] RPA RPB | RNB RNA [RIN_N] per cell (see the doc)
    terms = []
    for k, cell in enumerate(cells):
        ra, rb = dev[f"{cell}.XRPA"], dev[f"{cell}.XRPB"]
        na, nb_ = dev[f"{cell}.XRNA"], dev[f"{cell}.XRNB"]
        rows_k = [(ra.g, ra.d), (rb.d, rb.g), (nb_.d, nb_.g), (na.g, na.d)]   # (west, east)
        if k % 2 == 0:
            rows_k = [("INP", "I1P")] + rows_k + [("INN", "I1N")]
        terms += rows_k
    for k, cell in enumerate(cells):
        assert terms[element_rows(k)][1] == sw_nets[cell][0]
    x_r = SW + 2.0
    ra_ = an.res_cell(b, "rdac_r", 291.28, 1.0, terms, sub="AVSS")
    b.place(ra_.cell, x_r, YB)
    pr = bl.Placed(ra_, x_r, YB, False, "R")
    x_re = x_r + ra_.width

    def head(r, east=True):
        """(x1, x2, y) of the Metal2 pad of row r's east / west head"""
        net = terms[r][1 if east else 0]
        y = YB + (an.RING_W + 0.8 + f.RES_RY) + r * (1.0 + f.RES_GAP) + 0.5
        for lay, x1, y1, x2, y2 in pr.pins[net]:
            if abs((y1 + y2) / 2 - y) < 0.01 and ((x1 > x_r + ra_.width / 2) == east):
                return x1, x2, y
        raise KeyError((r, net, east))
    # ---- buses (Metal3, x ranges) between the array and the switch column
    bus = {}
    x = x_re + 0.5
    for n in ("VREFP", "VREFN", "I1N", "I1P", "AVSS_W"):
        bus[n] = (x, x + 1.0)
        x += 1.6
    x_q = x - 0.1                                   # west edge of the switch quads
    qc, q_w, q_x = quad_cell(b)
    bus["AVSS_E"] = (x_q + q_w + 0.2, x_q + q_w + 1.2)
    axes = [YB + an.RING_W + 0.8 + f.RES_RY + element_rows(k) * (1.0 + f.RES_GAP) + 1.0 + f.RES_GAP / 2
            for k in range(len(cells))]
    assert all(abs(axes[k + 1] - axes[k] - PITCH_AX) < 1e-6 for k in range(len(axes) - 1))
    y_bus0, y_bus1 = YB + 1.0, axes[-1] + 4.0 + 1.0
    x_hd = x_q + 13.4                               # D: Metal2 to here (router pin west of it)
    x_hdb = x_q + 15.0                              # DB: Metal4 to here, then a Metal3 stub
    x_router = x_q + 11.0                           # the router works east of this
    x_logic = round((x_q + 16.4) / lg.PITCH) * lg.PITCH
    gx0 = (x_logic + lg.GATE0) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    # ---- per element: quad, X lines, output straps, heads to the buses, D / DB
    db_m4 = []                      # (net, Metal4 box, via3 box) of the DB lines inside the router's region
    for k, cell in enumerate(cells):
        ya = axes[k]
        xp, xn, dnet, dbnet = sw_nets[cell]
        rb = element_rows(k)
        b.place(qc, x_q, ya)
        for r, y in ((rb, ya - Y_X), (rb + 1, ya + Y_X)):          # XP, XN
            x1, x2, yh = head(r)
            assert abs(yh - y) < 1e-6
            m2(x1, y, x_q + 0.4)
        x1, x2, yh = head(rb - 1)                                  # VREFP head
        m2(x1, yh, bus["VREFP"][1])
        via2_on(*bus["VREFP"], yh)
        x1, x2, yh = head(rb + 2)                                  # VREFN head
        m2(x1, yh, bus["VREFN"][1])
        via2_on(*bus["VREFN"], yh)
        if k % 2 == 0:                                             # RIN east heads
            x1, x2, yh = head(rb - 2)
            m2(x1, yh, bus["I1P"][1])
            via2_on(*bus["I1P"], yh)
            x1, x2, yh = head(rb + 3)
            m2(x1, yh, bus["I1N"][1])
            via2_on(*bus["I1N"], yh)
        # outputs: OUTN at -Y_O1 and +Y_O2, OUTP at -Y_O2 and +Y_O1
        for y, n in ((ya - Y_O1, "I1N"), (ya + Y_O2, "I1N"), (ya - Y_O2, "I1P"), (ya + Y_O1, "I1P")):
            m2(bus[n][0], y, x_q + 0.4)
            via2_on(*bus[n], y)
        for s in (-1, 1):                                          # ring bands to the AVSS straps
            y = ya + s * Y_RB
            m2(bus["AVSS_W"][0], y, x_q + 0.4)
            via2_on(*bus["AVSS_W"], y)
            m2(x_q + q_w - 0.4, y, bus["AVSS_E"][1])
            via2_on(*bus["AVSS_E"], y)
        # D: Metal2 along the axis; its east end is the router pin
        m2(x_q + q_w - 0.4, ya, x_hd)
        conn(dnet, [("metal2", x_hd - 1.8, ya - W2 / 2, x_hd, ya + W2 / 2)])
        # DB: Metal4 along the axis, then a Metal3 stub (router pin) on a router column
        xs = snap(x_hdb)
        b.box("metal4", x_q + q_w - 0.4, ya - 0.19, xs + 0.19, ya + 0.19)
        b.box("via3", xs - 0.13, ya - 0.13, xs + 0.13, ya + 0.13)
        b.box("metal3", xs - 0.19, ya - 0.7, xs + 0.19, ya + 0.7)
        conn(dbnet, [("metal3", xs - 0.19, ya - 0.7, xs + 0.19, ya + 0.7)])
        db_m4.append((dbnet, (x_router - 1.0, ya - 0.19, xs + 0.19, ya + 0.19), (xs - 0.13, ya - 0.13, xs + 0.13, ya + 0.13)))
    # MP / MN: Metal2 bars joining the west heads of RPA-RPB and RNB-RNA
    for k, cell in enumerate(cells):
        rb = element_rows(k)
        for r0, r1 in ((rb - 1, rb), (rb + 1, rb + 2)):
            xa1, xa2, ya0 = head(r0, east=False)
            xb1, xb2, ya1 = head(r1, east=False)
            b.box("metal2", xa1, ya0 - W2 / 2, xa1 + W2, ya1 + W2 / 2)
    # INP / INN buses west of the array (the RIN west heads)
    x1w, x2w, _ = head(0, east=False)
    bus["INP"] = (x2w - 1.2, x2w - 0.2)
    bus["INN"] = (x_r + 0.2, x_r + 1.2)
    for k in range(0, len(cells), 2):
        rb = element_rows(k)
        _, _, y = head(rb - 2, east=False)
        via2_on(*bus["INP"], y)
        x1, x2, y = head(rb + 3, east=False)
        m2(bus["INN"][0], y, x2)
        via2_on(*bus["INN"], y)
    # ---- Metal4 AVSS between the DB lines over the switch column, via3 onto both straps
    xa, xe = bus["AVSS_W"][0], bus["AVSS_E"][1]
    edges = [axes[0] - PITCH_AX / 2] + [a + PITCH_AX / 2 for a in axes[:-1]] + [axes[-1] + PITCH_AX / 2]
    shield = []
    for k, ya in enumerate(axes):
        for y1, y2 in ((edges[k], ya - 0.19 - 0.3), (ya + 0.19 + 0.3, edges[k + 1])):
            shield.append((y1, y2))
    merged = []
    for y1, y2 in shield:
        if merged and abs(merged[-1][1] - y1) < 1e-6:
            merged[-1] = (merged[-1][0], y2)
        else:
            merged.append((y1, y2))
    for y1, y2 in merged:
        b.box("metal4", xa, y1, xe, y2)
        for n in ("AVSS_W", "AVSS_E"):
            b.vias("via3", bus[n][0], y1 + 0.2, bus[n][1], y2 - 0.2)
    # ---- logic leaves in rows east of the router edge: cells 2r, 2r+1 in row r (NORs
    # first, nearest their D / DB pins), the break driver spread over the middle rows
    per = {}
    brk = []
    for item in gates:
        path = item[0]
        if ".XBRK." in path:
            brk.append(item)
        else:
            per.setdefault(int(path.split(".XC")[-1].split(".")[0]), []).append(item)
    order = {"XND": 0, "XNDB": 1, "XI1": 2, "XI2": 3, "XLI": 4, "XLF": 5}
    nrow = (len(cells) + 1) // 2
    plan = [[] for _ in range(nrow)]
    for r in range(nrow):
        items_r = [(k, it) for k in (2 * r, 2 * r + 1) if k in per for it in per[k]]
        key = lambda ki: (order[ki[1][0].rsplit(".", 1)[1]] > 1, ki[0], order[ki[1][0].rsplit(".", 1)[1]])
        plan[r] = [it for _, it in sorted(items_r, key=key)]
    mid = list(range(nrow // 2 - 2, nrow // 2 + 2))
    for j, item in enumerate(brk):
        plan[mid[j * len(mid) // len(brk)]].append(item)
    rows = bl.Rows(b, x_logic, YB)
    for r, row in enumerate(plan):
        for path, model, env, cnets in row:
            if model == "dev":                       # the brk's MOS capacitor (nfet, S/D/B on VSS)
                d = env
                lc = nb.make_leaf(b, "dac1_cd", ["D", "G", "VSS"], [nb.Dev("X", d.model, "D", "G", "VSS", "VSS", d.w, d.l, d.nf)])
                cmap = {"D": "AVSS", "G": d.g, "VSS": "AVSS", "VDD": "AVDD"}
            else:
                ports, devs = nb.leaf_devices(subs, model, env)
                vname = g.variant_name(model, env) if subs[model][1] else model
                lc = nb.make_leaf(b, vname, ports, devs)
                cmap = dict(cnets)
                cmap.setdefault("VDD", "AVDD")
                cmap.setdefault("VSS", "AVSS")
            if getattr(lc, "height", lg.H) != lg.H:
                raise ValueError(f"{path}: driver cell in the DAC1 logic")
            p = rows.add(r, lc, path)
            for pn, segs in p.pins.items():
                if pn in ("VDD", "VSS"):            # rails: joined to the straps at the row ends
                    continue
                conn(cmap.get(pn, pn), segs)
    rows.fill_all()
    y_rows = YB + rows.height()
    width = x_logic + rows.width() + 2.0 + 2 * (SW + 1.0) + 0.6
    y_i1p, y_i1n = y_rows + 1.5, y_rows + 3.3          # Metal4 runs of I1P / I1N (1 um)
    height = y_i1n + 1.0 + 1.7
    # ---- power: AVSS straps on the west edge and east of the logic, AVDD on the east
    # edge; the logic rails run east to their strap (VDD under the AVSS strap)
    xs_vss, xs_vss2, xs_vdd = SW / 2 + 0.4, width - 1.5 * SW - 1.4, width - SW / 2 - 0.4
    for net, x in (("AVSS", xs_vss), ("AVSS", xs_vss2), ("AVDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
    for net, a, c_ in rows.rails():
        x = xs_vss2 if net == "VSS" else xs_vdd
        b.box("metal2", x_logic + rows.width() - 0.5, a, x + SW / 2, c_)
        b.vias("via2", x - SW / 2, a, x + SW / 2, c_)
    nets.pop("AVDD", None)
    conn("AVSS", [("metal3", xs_vss2 - SW / 2, -1.0, xs_vss2 + SW / 2, height)])
    # the array's ring band, the column straps and the logic's bottom rail on one Metal2
    # band along the bottom, via2 onto the west strap and the column straps
    b.box("metal2", xs_vss - SW / 2, YB, x_logic + 1.0, YB + an.RING_W)
    b.vias("via2", xs_vss - SW / 2, YB, xs_vss + SW / 2, YB + an.RING_W)
    for n in ("AVSS_W", "AVSS_E"):
        x1, x2 = bus[n]
        b.box("metal3", x1, YB, x2, axes[-1] + PITCH_AX / 2)
        b.vias("via2", x1, YB, x2, YB + an.RING_W)
    # ---- the Metal3 buses and the top ports
    for n in ("VREFP", "VREFN", "I1N", "I1P", "INP", "INN"):
        x1, x2 = bus[n]
        top = {"I1P": y_i1p + 1.0, "I1N": y_i1n + 1.0}.get(n, height - 1.5)
        b.box("metal3", x1, y_bus0, x2, top)
    tops = {}
    for n in ("INN", "INP", "VREFP", "VREFN"):
        x1, x2 = bus[n]
        xs = snap((x1 + x2) / 2)
        b.box("metal3", min(x1, xs - 0.15), height - 2.0, max(x2, xs + 0.15), height - 1.5)
        tops[n] = xs
    for n, y1, xe in (("I1P", y_i1p, width - 28.0), ("I1N", y_i1n, width - 18.0)):
        x1, x2 = bus[n]
        xs = snap(xe)
        b.box("metal4", x1, y1, xs + 0.5, y1 + 1.0)
        b.vias("via3", x1, y1, x2, y1 + 1.0)
        b.box("metal3", xs - 0.5, y1, xs + 0.5, y1 + 1.0)
        b.vias("via3", xs - 0.5, y1, xs + 0.5, y1 + 1.0)
        b.box("metal3", xs - 0.19, y1, xs + 0.19, height - 1.5)    # as wide as the stub in adc_top (cover)
        tops[n] = xs
    bl.ports_top(b, list(tops), list(tops.values()), height)
    # ---- bottom ports (SEL1, DAC_CLK) under the logic, and the router
    bot = [f"SEL1_{k}" for k in range(31)] + ["DAC_CLK"]
    xb0 = x_logic + 1.0
    stepb = (xs_vss2 - SW / 2 - 3.0 - xb0) / len(bot)
    pp = bl.ports_bottom(b, bot, [snap(xb0 + stepb * (k + 0.5)) for k in range(len(bot))], -1.0)
    for n, pin in pp.items():
        conn(n, [pin])
    i0 = int((x_router - gx0) / lg.PITCH) + 1
    rt = route.Router(gx0 + i0 * lg.PITCH, -1.5, xs_vss2 + SW / 2 + 0.5, y_rows, px=lg.PITCH)
    for n, box, v3 in db_m4:
        rt.obstacle("metal4", *box, n)
        rt.via_keepout(*v3)
    failed = rt.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, rt.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    rt.draw(b)
    return b, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "adc_rdac")
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    b, (w, h) = build()
    print(f"adc_rdac: {w:.1f} x {h:.1f} um")
    bl.check(b, "adc_rdac", FILES, runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

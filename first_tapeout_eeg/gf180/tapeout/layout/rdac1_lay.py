#!/usr/bin/env python3
"""Layout of adc_rdac (LVS wrapper gf180/tapeout/layout/lvs/adc_rdac.spice, tracker E4):
the ADC's stage-1 input resistors RIN and the DAC1 (gf180/tapeout/adc/eeg_dac1.spice).

Since C1 was halved (10/23) RIN is 16 unit resistors per side and every DAC1 element
two units in series (RIN/RD1 = 31/32 by construction), so all 156 units (300 kohm) sit
in one resistor array. Since r11 (11/12) a unit is two ppolyf_u strips of 320.48 x 0.8
um in series (through r10 one ppolyf_u_1k strip of 291.28 x 1 um; the flicker noise of
the 1k poly, documentation/gf180_realistic_eval_20261028.md), 312 strips at 1.2 um
pitch (PRES.2 0.4 apart). A unit is folded: its two strips are joined by a Metal2
jumper on their west heads, so both of its ends are on the east side. Rows per DAC1
cell k, bottom to top: [RINP_A RINP_B] RPA1 RPA2 RPB1 RPB2 | RNB2 RNB1 RNA2 RNA1
[RINN_B RINN_A] (RIN rows at even k), mirror images about the element's axis between
RPB2 and RNB2; the axes are 12 um apart. East heads: VRP (RPA1), MP (RPA2 and RPB1,
joined by a Metal2 bar), XP (RPB2); RIN: INP (RINP_A) and I1P (RINP_B). West: the
jumpers (RPAM, RPBM, ...), and the RIN units' middle nodes RINPM / RINNM, each joined
over the array by a Metal3 bus.

The even (ISI) error of DAC1 (documentation/gf180_pex_20261023.md, D6) comes from the
couplings of the steering nodes XP / XN, which float during the common break, to the
switching lines; only the difference between the XP and the XN coupling of a line counts.
So each element's steering nodes are drawn by hand and mirror-symmetric:
  - the four switches (dac1_quad) sit at the east ends of the element's rows, two NMOS
    strips [OUTN DB XP D OUTP] below the axis and [OUTP DB XN D OUTN] above it, the DB
    and D fingers shared by both strips and contacted on the axis; XP / XN reach the
    strips on straight Metal2 lines from the RPB2 / RNB2 heads (0.6 um from the axis,
    jogged to the quad's 0.8 um just before it);
  - D leaves on Metal2 and DB on Metal4 along the axis to the east, so they couple to XP
    and XN alike; a Metal3 AVSS strap on both sides of the switch column and Metal4 AVSS
    between the DB lines screen the column;
  - no other line (other cells' D / DB / SEL, the latches, the break lines) comes within
    8 um of the column: the router (route.Router) works only east of it, where the logic
    (latch TGs, inverters, NORs of every cell, and the common-break driver
    eeg_dac1_brk) sits in rows, cells 2r and 2r+1 in row r beside their axes (rows apart
    at 23.5 um since r11, from 4 um above the block's bottom).
Between the array and the switch column: Metal3 buses INN, INP, VREFP, VREFN, I1N, I1P
(the RIN ends, the references and the switches' outputs); all static.
Ports (for the ADC assembly, gf180/tapeout/layout/adc_lay.py): INN, INP, VREFP, VREFN
above their buses and I1P, I1N at the east end of the top edge (Metal4 runs above the
logic); SEL1_0..30 and DAC_CLK on the bottom edge under the logic (the SEL1 lines come
from eeg_adc_dig along the bottom of the ADC band).

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
UNIT_L, UNIT_W = 320.48, 0.8        # each 300 kohm unit: two ppolyf_u strips in series (r11)
ROW = UNIT_W + f.PRES_GAP           # strip pitch, 1.2
Y_HX = ROW / 2                      # RPB2 / RNB2 heads from the axis
Y_LOG, ROW_P = 4.0, 23.5            # logic rows: the first one's bottom, and their pitch
W2 = 0.38           # hand-drawn Metal2 lines
# switch quad (local: axis at y = 0, west edge of its ring at x = 0)
Q_XC = an.RING_W + an.GAP + 0.5          # COMP left edge (0.5 for the dummy poly)
Q_W = 1.0                                # finger width (eeg_dac1_cell: W 1 um, L 0.28)
Q_Y0 = 0.48                              # axis to COMP (poly contacts on the axis, PO_EXT)
Y_X = 0.8                                # XP / XN lines in the quad
Y_O1, Y_O2 = 1.48, 2.18                  # output straps of S/D 0 and S/D 2
RING_IN = 2.66                           # ring inner edge
Y_RB = RING_IN + an.RING_W / 2           # Metal2 band on the ring's bottom / top side
PITCH_AX = 10 * ROW                      # axis to axis (10 strips, 12 um)


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


def cell_rows(k):
    """Rows of DAC1 cell k, bottom to top: (device or RIN row name, order) where order "gd"
    puts the device's second node on the west head and "dg" its first one."""
    rows = [("RPA1", "gd"), ("RPA2", "dg"), ("RPB1", "gd"), ("RPB2", "dg"),
            ("RNB2", "dg"), ("RNB1", "gd"), ("RNA2", "dg"), ("RNA1", "gd")]
    if k % 2 == 0:
        rows = [("RINP_A", None), ("RINP_B", None)] + rows + [("RINN_B", None), ("RINN_A", None)]
    return rows


RIN_ROWS = {"RINP_A": ("RINPM", "INP"), "RINP_B": ("RINPM", "I1P"),
            "RINN_B": ("RINNM", "I1N"), "RINN_A": ("RINNM", "INN")}


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
        if model == "dev" and env.model == "ppolyf_u":
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
        xp, xn = dev[f"{cell}.XRPB2"].g, dev[f"{cell}.XRNB2"].g
        dd = [t.g for t in sw[cell] if t.d == xp and t.s == "I1P"]
        ddb = [t.g for t in sw[cell] if t.d == xp and t.s == "I1N"]
        if len(d) != 4 or not dd or not ddb:
            raise ValueError(f"{cell}: unexpected switches {sw[cell]}")
        sw_nets[cell] = (xp, xn, dd[0], ddb[0])
    # ---- resistor array: rows per cell as cell_rows() (see the doc)
    terms, rowof = [], {}                       # (west, east) per strip; (k, name) -> strip index
    for k, cell in enumerate(cells):
        for name, order in cell_rows(k):
            rowof[(k, name)] = len(terms)
            if order is None:
                terms.append(RIN_ROWS[name])
            else:
                dv = dev[f"{cell}.X{name}"]
                terms.append((dv.g, dv.d) if order == "gd" else (dv.d, dv.g))
    for k, cell in enumerate(cells):
        assert terms[rowof[(k, "RPB2")]][1] == sw_nets[cell][0] and terms[rowof[(k, "RNB2")]][1] == sw_nets[cell][1]
    x_r, y_r = SW + 2.0, 0.0
    ra_ = an.pres_cell(b, "rdac_r", UNIT_L, UNIT_W, terms, sub="AVSS")
    b.place(ra_.cell, x_r, y_r)
    x_re = x_r + ra_.width

    def head(r, east=True):
        """(x1, x2, y) of the Metal2 pad of strip r's east / west head"""
        x1, y1, x2, y2 = ra_.pad(r, east)
        return x_r + x1, x_r + x2, y_r + (y1 + y2) / 2

    def bar(r0, r1, east):
        """Metal2 jumper joining the pads of strips r0 and r1 at their outer ends"""
        xa1, xa2, ya = head(r0, east)
        _, _, yb = head(r1, east)
        x = xa2 - W2 if east else xa1
        b.box("metal2", x, min(ya, yb) - W2 / 2, x + W2, max(ya, yb) + W2 / 2)
    # ---- buses (Metal3, x ranges) between the array and the switch column
    bus = {}
    x = x_re + 0.5
    for n in ("INN", "INP", "VREFP", "VREFN", "I1N", "I1P", "AVSS_W"):
        bus[n] = (x, x + 1.0)
        x += 1.6
    x_q = x - 0.1                                   # west edge of the switch quads
    qc, q_w, q_x = quad_cell(b)
    bus["AVSS_E"] = (x_q + q_w + 0.2, x_q + q_w + 1.2)
    axes = [(head(rowof[(k, "RPB2")])[2] + head(rowof[(k, "RNB2")])[2]) / 2 for k in range(len(cells))]
    assert all(abs(axes[k + 1] - axes[k] - PITCH_AX) < 1e-6 for k in range(len(axes) - 1))
    assert all(abs(head(rowof[(k, "RPB2")])[2] - (axes[k] - Y_HX)) < 1e-6 for k in range(len(axes)))
    y_top_col = axes[-1] + 4.0                      # top of the switch column's straps and shield
    y_bus0 = y_r + 1.0
    x_hd = x_q + 13.4                               # D: Metal2 to here (router pin west of it)
    x_hdb = x_q + 15.0                              # DB: Metal4 to here, then a Metal3 stub
    x_router = x_q + 11.0                           # the router works east of this
    x_logic = round((x_q + 16.4) / lg.PITCH) * lg.PITCH
    gx0 = (x_logic + lg.GATE0) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    # ---- per element: quad, X lines, the MP / MN bars, heads to the buses, D / DB
    db_m4 = []                      # (net, Metal4 box, via3 box) of the DB lines inside the router's region
    for k, cell in enumerate(cells):
        ya = axes[k]
        xp, xn, dnet, dbnet = sw_nets[cell]
        b.place(qc, x_q, ya)
        for name, s_ in (("RPB2", -1), ("RNB2", 1)):               # XP, XN: jog to the quad's lines
            x1, x2, yh = head(rowof[(k, name)])
            m2(x1, yh, x_q - 0.5)
            m2(x_q - 0.9, ya + s_ * Y_X, x_q + 0.4)
        bar(rowof[(k, "RPA2")], rowof[(k, "RPB1")], True)          # MP
        bar(rowof[(k, "RNB1")], rowof[(k, "RNA2")], True)          # MN
        for name, n in (("RPA1", "VREFP"), ("RNA1", "VREFN")):
            x1, x2, yh = head(rowof[(k, name)])
            m2(x1, yh, bus[n][1])
            via2_on(*bus[n], yh)
        if k % 2 == 0:                                             # RIN east heads
            for name, n in (("RINP_A", "INP"), ("RINP_B", "I1P"), ("RINN_B", "I1N"), ("RINN_A", "INN")):
                x1, x2, yh = head(rowof[(k, name)])
                m2(x1, yh, bus[n][1])
                via2_on(*bus[n], yh)
        # outputs: OUTN at -Y_O1 and +Y_O2, OUTP at -Y_O2 and +Y_O1
        for y, n in ((ya - Y_O1, "I1N"), (ya + Y_O2, "I1N"), (ya - Y_O2, "I1P"), (ya + Y_O1, "I1P")):
            m2(bus[n][0], y, x_q + 0.4)
            via2_on(*bus[n], y)
        for s_ in (-1, 1):                                         # ring bands to the AVSS straps
            y = ya + s_ * Y_RB
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
    # west jumpers: the two strips of every unit
    for k in range(len(cells)):
        pairs = [("RPA1", "RPA2"), ("RPB1", "RPB2"), ("RNB2", "RNB1"), ("RNA2", "RNA1")]
        if k % 2 == 0:
            pairs += [("RINP_A", "RINP_B"), ("RINN_B", "RINN_A")]
        for r0, r1 in pairs:
            bar(rowof[(k, r0)], rowof[(k, r1)], False)
    # RINPM / RINNM buses over the west heads (the RIN units' middle nodes joined)
    x1w, x2w, _ = head(0, east=False)
    bus["RINPM"] = (x2w - 1.2, x2w - 0.2)
    bus["RINNM"] = (x_r + 0.2, x_r + 1.2)
    for k in range(0, len(cells), 2):
        _, _, y = head(rowof[(k, "RINP_A")], east=False)
        via2_on(*bus["RINPM"], y)
        x1, x2, y = head(rowof[(k, "RINN_A")], east=False)
        m2(bus["RINNM"][0], y, x2)
        via2_on(*bus["RINNM"], y)
    y_rin1 = max(head(rowof[(k, "RINN_A")], east=False)[2] for k in range(0, len(cells), 2)) + 0.5
    for n in ("RINPM", "RINNM"):
        x1, x2 = bus[n]
        b.box("metal3", x1, y_bus0, x2, y_rin1)
    # ---- Metal4 AVSS between the DB lines over the switch column, via3 onto both straps
    xa, xe = bus["AVSS_W"][0], bus["AVSS_E"][1]
    edges = [axes[0] - 4.0] + [a + PITCH_AX / 2 for a in axes[:-1]] + [y_top_col]
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
    rows = bl.Rows(b, x_logic, Y_LOG, pitch=ROW_P)
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
    y_rows = Y_LOG + rows.height()
    width = x_logic + rows.width() + 2.0 + 2 * (SW + 1.0) + 0.6
    y_i1p = max(y_rows, y_top_col) + 0.6               # Metal4 runs of I1P / I1N (1 um), above
    y_i1n = y_i1p + 1.8                                # the logic and the column's shield
    height = max(y_i1n + 1.0 + 1.7, y_r + ra_.height + 0.5)
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
    # the array's ring band and the column straps on one Metal2 band along the bottom, via2
    # onto the west strap and the column straps (the logic rails join the straps east)
    b.box("metal2", xs_vss - SW / 2, y_r, bus["AVSS_E"][1], y_r + an.RING_W)
    b.vias("via2", xs_vss - SW / 2, y_r, xs_vss + SW / 2, y_r + an.RING_W)
    for n in ("AVSS_W", "AVSS_E"):
        x1, x2 = bus[n]
        b.box("metal3", x1, y_r, x2, y_top_col)
        b.vias("via2", x1, y_r, x2, y_r + an.RING_W)
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

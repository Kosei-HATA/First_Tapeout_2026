#!/usr/bin/env python3
"""Layout of the AFE (tracker E3): eeg_afe (gf180/tapeout/afe/eeg_afe.spice) in the AFE
region of the floorplan (1100 x 1447 um, core x 40..1140, y 100..1547). Top cell afe_top;
LVS against lvs/afe_top.spice.

Placement (local um; the differential axis at y = 723.5):
  - Cin arrays (eeg_cin, 636 pF per side) on the east 860.6 um, above and below the core
    band, both buses facing it: Cin_P (TOP = INP outer, BOT = WP), Cin_N mirrored.
  - core band (y 422..1025): the input chopper afe_tgin at the west (its electrode
    spines EP / EN on its west edge, for the pad straps), the core amplifier
    eeg_afe_core in the middle, and the output section in the east part: hold
    capacitors, CC, CFB, CPF, the Cpf trim, the output chopper, the CMFB, the reset and
    DC-path switches.
  - west corners: the offset-DAC halves offdac_p / offdac_n (offdac_lay.py), the clock
    driver eeg_afe_clk and its supply decoupling.
Hand-drawn wiring:
  - the Cin buses extended west (WP / WN to the input chopper's stripes, INP / INN to the
    offset DAC); the chopper's WP / WN stripes run on into those buses;
  - WP / WN taps under the outer buses for the output section (CPF, Cpf trim);
  - the core's INP / INN stubs straight into the buses (7 um);
  - AVSS / AVDD Metal5 rails from the east edge over the output section to the core's
    Metal4 supply bars over its tails (the core's 19 mA comes from the Ch-A side: the
    west of the band is the input chopper's).
Everything else: route.Router on Metal3 / Metal4.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/afe_lay.py [--drc] [--lvs]
"""
import argparse
import os
import time
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import route
import assemble as A
from ota_lay import dev_seq

HERE = os.path.dirname(os.path.abspath(__file__))
AFE = os.path.join(g.REPO, "gf180", "tapeout", "afe")
TOP = "afe_top"
W, H = 1100.0, 1447.0
GRID = (0.24, 0.8, 0.0, route.P)
CIN_X = 239.4
EAST_X = 912.0                 # the output section starts here
HOLD_Y = 692.0                 # hold capacitors: above the top AVDD rail strip (Metal5 to 689.8)


def ring_seq(a, ga, x, gb, y, gc, z, gd, periods):
    """[a ga x gb y gc z gd a ...]: four TGs on a commutator ring of S/D nets"""
    seq = [a]
    for _ in range(periods):
        seq += [ga, x, gb, y, gc, z, gd, a]
    return seq


def section_cells(a):
    """Cells of the output section (east part of the band)."""
    C = {}
    C["hold"] = an.mim_cell(a, "afe_hold", 86.58, "TOP", "BOT")
    C["cc"] = an.mim_cell(a, "afe_cc", 70.65, "TOP", "BOT")
    C["cfb"] = an.mim_cell(a, "afe_cfb", 31.46, "TOP", "BOT")
    C["cpf"] = an.mim_cell(a, "afe_cpf", 30.92, "TOP", "BOT")
    C["m5"] = an.mim_cell(a, "afe_m5", 5.0, "TOP", "BOT")
    C["m717"] = an.mim_cell(a, "afe_m717", 7.17, "TOP", "BOT")
    C["m1023"] = an.mim_cell(a, "afe_m1023", 10.23, "TOP", "BOT")
    # output chopper: OUTP -CDA- OPI -CDB- OUTN -CDA- ONI -CDB- OUTP (XOP_A, XOP_B, XON_A,
    # XON_B); NMOS 16 periods (W 10 um fingers), PMOS 32
    st = lambda ga, gb, n: dict(w=10.0, l=0.28, seq=ring_seq("OUTP", ga, "OPI", gb, "OUTN", ga, "ONI", gb, n),
                                gates={ga: ("t", 0), gb: ("t", 1)}, order=["OUTP", "OPI", "OUTN", "ONI"],
                                straps={"OUTP": 2, "OPI": 2, "OUTN": 2, "ONI": 2})
    C["otg_n"] = an.multi_strip_cell(a, "afe_otg_n", "n", [st("CDA", "CDB", 8) for _ in range(2)], bulk="VSS")
    C["otg_p"] = an.multi_strip_cell(a, "afe_otg_p", "p", [st("NCDA", "NCDB", 8) for _ in range(4)], bulk="VDD")
    # CMFB (eeg_afe_cmfb at the amp level: OUTP = OPI, OUTN = ONI, VCMREF = VCM): pairs L2 m4,
    # tails m2, PMOS mirror m8
    pa = dict(w=10.0, l=2.0, seq=["ND", "OPI", "NTA", "VCM", "VBP", "VCM", "NTA", "OPI", "ND"],
              gates={"OPI": ("t", 0), "VCM": ("t", 1)}, order=["NTA", "ND", "VBP"])
    pb = dict(w=10.0, l=2.0, seq=["ND", "ONI", "NTB", "VCM", "VBP", "VCM", "NTB", "ONI", "ND"],
              gates={"ONI": ("t", 0), "VCM": ("t", 1)}, order=["NTB", "ND", "VBP"])
    tl = dict(w=10.0, l=2.0, seq=["NTA", "VBCM", "VSS", "VBCM", "NTB"], order=["VSS", "NTA", "NTB"])
    C["cmfb_n"] = an.multi_strip_cell(a, "afe_cmfb_n", "n", [pa, pb, pb, pa, tl, tl], bulk="VSS")
    pm = dict(w=10.0, l=2.0, seq=["VDD", "ND", "ND", "ND", "VDD", "ND", "VBP", "ND", "VDD", "ND", "ND", "ND", "VDD",
                                  "ND", "VBP", "ND", "VDD"], order=["VDD", "ND", "VBP"])
    C["cmfb_p"] = an.multi_strip_cell(a, "afe_cmfb_p", "p", [pm, pm], bulk="VDD")
    # reset switches (W1/L1) and the DC-path switched capacitors (W0.5/L0.28, CIA then CIB)
    C["rstp"] = an.strip_cell(a, "afe_rstp", "n", 1.0, 1.0, ["INP", "RST", "ONI"], bulk="VSS")
    C["rstn"] = an.strip_cell(a, "afe_rstn", "n", 1.0, 1.0, ["INN", "RST", "OPI"], bulk="VSS")
    C["scp"] = an.strip_cell(a, "afe_scp", "n", 0.5, 0.28, ["INP", "CIA", "SCP", "CIB", "ONI"],
                             gates={"CIA": ("t", 0), "CIB": ("t", 1)}, bulk="VSS")
    C["scn"] = an.strip_cell(a, "afe_scn", "n", 0.5, 0.28, ["INN", "CIA", "SCN", "CIB", "OPI"],
                             gates={"CIA": ("t", 0), "CIB": ("t", 1)}, bulk="VSS")
    # Cpf trim logic: eeg_afe_tg (NMOS W1, PMOS W2, here two fingers each) and the inverters
    C["tg"] = lg.tg_cell(a, "afe_trim_tg", 2, 2, 0.5, 1.0, a="A", y="Y", gn="G", gp="GN")
    p, n = lg.inv_seq(1)
    C["inv"] = lg.cmos_cell(a, "afe_trim_inv", p, n, 2.5, 1.0, ["A", "Y"])
    return C


def build():
    a = A.Assembly(TOP)
    nets = {}
    keep = []

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def add(inst, power=("VDD", "VSS", "AVDD", "AVSS")):
        for n, segs in inst.pins.items():
            if "." in n or n in power:
                continue
            conn(n, segs)

    def cell_at(cell, x, y, name, cmap, mirror=False):
        a.place(cell.cell, x, y, mirror=mirror)
        p = bl.Placed(cell, x, y, mirror, name)
        for pn, segs in p.pins.items():
            net = cmap.get(pn, pn)
            if pn in ("VDD", "VSS") and isinstance(cell, lg.LogicCell):
                lay, x1, y1, x2, y2 = segs[0]
                a.box("metal2", x1 - 3.0, y1, x1 + 0.5, y2)
                pad = (x1 - 3.0, (y1 + y2) / 2 - 0.5, x1 - 1.6, (y1 + y2) / 2 + 0.5)
                a.vias("via2", *pad)
                a.manual.append(("metal3", pad, net))
                conn(net, [("metal3",) + pad])
                continue
            conn(net, segs)
        if hasattr(cell, "keepout"):
            k3, k4 = cell.keepout, cell.keepout4
            if mirror:
                k3 = (k3[0], -k3[3], k3[2], -k3[1])
                k4 = (k4[0], -k4[3], k4[2], -k4[1])
            keep.append(((x + k3[0], y + k3[1], x + k3[2], y + k3[3]), (x + k4[0], y + k4[1], x + k4[2], y + k4[3])))
        return p

    I = {}
    I["cinp"] = a.put("eeg_cin", CIN_X, 1024.8, name="CINP", nets={"TOP": "INP", "BOT": "WP"}, mim=True)
    I["cinn"] = a.put("eeg_cin", CIN_X, 422.2, mirror=True, name="CINN", nets={"TOP": "INN", "BOT": "WN"}, mim=True)
    I["core"] = a.put("eeg_afe_core", 196.0, 429.3, name="CORE", grid=GRID, nets={
        "OUTP": "OPI", "OUTN": "ONI", "VDD": "AVDD", "VSS": "AVSS"})
    I["tg"] = a.put("afe_tgin", 2.0, 483.5, name="TG", nets={
        "EP": "ELP", "EN": "ELN", "VDD": "AVDD", "VSS": "AVSS"})
    for k in ("core",):
        a.cover(I[k])
    add(I["core"])
    # the input chopper's bulk: the PMOS n-well bar (Metal3), and the NMOS ring (Metal2,
    # run east under the gate lanes and the n-well bar to a Metal3 pad in the gap beside
    # the core)
    conn("AVDD", I["tg"].pins["AVDD"])
    rs = I["tg"].pins["AVSS"][0]
    xg2 = I["tg"].bbox[2]
    ym = (rs[2] + rs[4]) / 2
    a.box("metal2", rs[3] - 0.5, rs[2], xg2 + 2.0, rs[4])
    pad = (xg2 + 0.6, ym - 0.55, xg2 + 2.0, ym + 0.55)
    a.box("metal2", *pad)
    a.vias("via2", *pad)
    a.box("metal3", *pad)
    conn("AVSS", [("metal3",) + pad])
    for n in ("INP", "INN"):                 # the core's INP / INN stubs go straight into the buses
        nets.pop(n, None)

    # ---- output section
    C = section_cells(a)
    x0 = EAST_X
    # hold capacitors 2 x 2 above the supply rails, CC above them, CFB_P / CPF_P on top
    hx = [x0 + 1.0, x0 + 1.0 + C["hold"].width + 3.0]
    yh = HOLD_Y
    hold = [("OUTP", hx[0], yh), ("OUTN", hx[1], yh), ("OUTN", hx[0], yh + C["hold"].height + 3.0),
            ("OUTP", hx[1], yh + C["hold"].height + 3.0)]
    for k, (n, x, y) in enumerate(hold):
        cell_at(C["hold"], x, y, f"HOLD{k}", {"TOP": n, "BOT": "AVSS"})
    ycc = yh + 2 * (C["hold"].height + 3.0)
    cell_at(C["cc"], x0 + 1.0, ycc, "CCP", {"TOP": "VBP", "BOT": "OPI"})
    cell_at(C["cc"], x0 + 1.0 + C["cc"].width + 3.0, ycc, "CCN", {"TOP": "VBP", "BOT": "ONI"})
    ytop = ycc + C["cc"].height + 2.0
    cell_at(C["cfb"], x0 + 1.0, ytop, "CFBP", {"TOP": "INP", "BOT": "ONI"})
    cell_at(C["cpf"], x0 + 1.0 + C["cfb"].width + 3.0, ytop, "CPFP", {"TOP": "WP", "BOT": "OPI"})
    # Cpf trim MIMs, P side (top): bit 0 two in series through MP0
    sw_x = {}
    xt = x0 + 1.0 + C["cfb"].width + C["cpf"].width + 8.0
    for nm, cell, tp, bt in (("CTP0A", "m5", "WP", "MP0"), ("CTP0B", "m5", "MP0", "XP0"), ("CTP1", "m5", "WP", "XP1"),
                             ("CTP2", "m717", "WP", "XP2"), ("CTP3", "m1023", "WP", "XP3")):
        cell_at(C[cell], xt, ytop, nm, {"TOP": tp, "BOT": bt})
        xt += C[cell].width + 2.0
    sw_x["P"] = xt + 1.0
    # N side (bottom, mirrored so the trim plates face the band): CFB_N, CPF_N, trim MIMs
    yb = 425.0
    cell_at(C["cfb"], x0 + 1.0, yb, "CFBN", {"TOP": "INN", "BOT": "OPI"})
    cell_at(C["cpf"], x0 + 1.0 + C["cfb"].width + 3.0, yb, "CPFN", {"TOP": "WN", "BOT": "ONI"})
    xt = x0 + 1.0 + C["cfb"].width + C["cpf"].width + 8.0
    for nm, cell, tp, bt in (("CTN0A", "m5", "WN", "MN0"), ("CTN0B", "m5", "MN0", "XN0"), ("CTN1", "m5", "WN", "XN1"),
                             ("CTN2", "m717", "WN", "XN2"), ("CTN3", "m1023", "WN", "XN3")):
        cell_at(C[cell], xt, yb, nm, {"TOP": tp, "BOT": bt})
        xt += C[cell].width + 2.0
    sw_x["N"] = xt + 1.0
    # switches next to the buses: reset (INP-ONI / INN-OPI) and the DC-path switched
    # capacitor (CIA2 then CIB2, with its 54.5 fF MIM to AVSS)
    sw = {}
    for side, y0_, (rst, sc, csc, scn) in (("P", ytop, ("rstp", "scp", "CSCP", "SCP")), ("N", yb, ("rstn", "scn", "CSCN", "SCN"))):
        x = sw_x[side]
        p1 = cell_at(C[rst], x, y0_, f"XRST{side}", {"VSS": "AVSS", "RST": "RST2"})
        x += C[rst].width + 2.0
        p2 = cell_at(C[sc], x, y0_, f"XSC{side}", {"VSS": "AVSS", "CIA": "CIA2", "CIB": "CIB2"})
        x += C[sc].width + 2.0
        cell_at(C["m5"], x, y0_, csc, {"TOP": scn, "BOT": "AVSS"})
    # the band between the rails: output chopper, CMFB, switches, trim logic
    S = bl.Shelves(a, x0 + 1.0, 527.0, W - x0 - 4.0, gap=2.0)

    def shelf(cell, name, cmap):
        p = S.place(cell, name)
        for pn, segs in p.pins.items():
            conn(cmap.get(pn, pn), segs)
        return p
    clk2 = {"CDA": "CDA2", "CDB": "CDB2", "NCDA": "NCDA2", "NCDB": "NCDB2"}
    shelf(C["otg_n"], "OTGN", dict(clk2, VSS="AVSS"))
    shelf(C["otg_p"], "OTGP", dict(clk2, VDD="AVDD"))
    shelf(C["cmfb_n"], "CMFBN", {"VSS": "AVSS"})
    shelf(C["cmfb_p"], "CMFBP", {"VDD": "AVDD"})
    S.newline()
    rows = bl.Rows(a, round((x0 + 4.0) / lg.PITCH) * lg.PITCH, S.y)
    for k in range(4):
        p = rows.add(0, C["inv"], f"XIB{k}")
        for pn, segs in p.pins.items():
            if pn not in ("VDD", "VSS"):
                conn({"A": f"CPF{k}", "Y": f"BN{k}"}[pn], segs)
    for side, o in (("P", "OPI"), ("N", "ONI")):
        for k in range(4):
            for kind, y, g1, g2 in (("O", o, f"CPF{k}", f"BN{k}"), ("V", "VCM", f"BN{k}", f"CPF{k}")):
                r = 0 if side == "P" else 1
                p = rows.add(r, C["tg"], f"XT{side}{kind}{k}")
                for pn, segs in p.pins.items():
                    if pn not in ("VDD", "VSS"):
                        conn({"A": f"X{side}{k}", "Y": y, "G": g1, "GN": g2}[pn], segs)
    rows.fill_all()
    merged = []                                       # rails of mirrored rows abut: one pad each
    for net, y1, y2 in sorted(rows.rails(), key=lambda t: t[1]):
        if merged and merged[-1][0] == net and y1 <= merged[-1][2] + 0.01:
            merged[-1] = (net, merged[-1][1], max(y2, merged[-1][2]))
        else:
            merged.append((net, y1, y2))
    for net, y1, y2 in merged:
        xr = rows.x0 - 3.0
        a.box("metal2", xr, y1, rows.x0 + 0.5, y2)
        pad = (xr, (y1 + y2) / 2 - 0.5, xr + 1.4, (y1 + y2) / 2 + 0.5)
        a.vias("via2", *pad)
        a.manual.append(("metal3", pad, "AVDD" if net == "VDD" else "AVSS"))
        conn("AVDD" if net == "VDD" else "AVSS", [("metal3",) + pad])
    I["section_top"] = rows.y0 + rows.height()
    for n, segs in corners(a, I).items():
        conn(n, segs)
    return a, nets, keep, I


# west corners: offset-DAC halves (offdac_lay.py), the clock driver eeg_afe_clk and the
# 100 ohm resistors of its supply (AVDD_CLK / AVSS_CLK)
OD_X = 0.8                      # offdac_n / offdac_p origin x (ports on the router columns)
OD_P_Y = 1040.0                 # offdac_p origin y, above the WP bus
CK_X, CK_Y = 14.0, 306.0        # eeg_afe_clk origin (its shapes from y CK_Y - 1)
OD_PORTS = ["VCM", "S", "PH"] + [f"M{k}" for k in range(10)] + [f"EN{k}" for k in range(4)]
OD_NET = dict({"VCM": "VCM", "S": "OFS", "PH": "OFPH"}, **{f"M{k}": f"OFM{k}" for k in range(10)},
              **{f"EN{k}": f"OFEN{k}" for k in range(4)})
CLK_WEST = ["CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CIA", "CIB", "CDA", "NCDA", "CDB", "NCDB",
            "RST", "OFPH"]
TG_JOG = {"CIA": 428.0, "NCIA": 433.0, "CIB": 438.0, "NCIB": 443.0}    # Metal4 jogs to the chopper's gates


def corners(a, I):
    """Place and wire the west corners; returns the router nets {net: [pins]}.

    Bottom-left: offdac_n on the bottom edge (its control ports are AFE ports there, its
    INN stub runs up into the INN bus east of the clock driver), eeg_afe_clk above it.
    The driver's four chopper gates go to the input chopper's gate lanes on wide hand-
    drawn Metal3 / Metal4 (16-33 pF each); its other ports and CIA / CIB go to the west
    edge (the chip routes them on). Its supply: the 105 pF decap under offdac_n's MIMs
    (straps AVDD_CLK / AVSS_CLK on offdac_n's top edge), joined to the driver's straps by
    hand (AVSS_CLK on Metal3, AVDD_CLK on Metal5 over the driver), and two 100 ohm
    resistors (ppolyf_u_1k, 2 x 20 um) to AVDD / AVSS beside the driver.
    Top-left: offdac_p above the WP bus (INP stub down into the INP bus), its control
    ports routed to the west edge; its AVDD / AVSS straps run on to the top edge."""
    pins = {}
    tp, bp = I["cinp"].pin("INP", "metal5"), I["cinp"].pin("WP", "metal5")
    tn, bn = I["cinn"].pin("INN", "metal5"), I["cinn"].pin("WN", "metal5")
    odn = a.put("offdac_n", OD_X, 0.0, name="ODN", grid=GRID,
                nets={p: OD_NET[p] + "_N" for p in OD_PORTS})
    odp = a.put("offdac_p", OD_X, OD_P_Y, name="ODP", grid=GRID,
                nets={p: OD_NET[p] + "_P" for p in OD_PORTS})
    ck = a.put("eeg_afe_clk", CK_X, CK_Y, name="CLK", grid=GRID, nets={"VDD": "AVDD_CLK", "VSS": "AVSS_CLK"})
    I.update(odn=odn, odp=odp, clk=ck)
    a.cover(ck)
    for inst in (odn, odp):
        a.cover(inst)
    # INN / INP stubs of the offset DAC into the Cin buses (crossing WN / WP on Metal3)
    for inst, n, bus in ((odn, "INN", tn), (odp, "INP", tp)):
        s = inst.pin(n, "metal3")
        xc = (s[1] + s[3]) / 2
        if n == "INN":
            a.wire("metal3", xc - 0.6, s[2], xc + 0.6, bus[4] - 0.3, n)
            a.via_stack("metal3", "metal5", xc - 0.6, bus[2] + 0.3, xc + 0.6, bus[4] - 0.3, n)
        else:
            a.wire("metal3", xc - 0.6, bus[2] + 0.3, xc + 0.6, s[4], n)
            a.via_stack("metal3", "metal5", xc - 0.6, bus[2] + 0.3, xc + 0.6, bus[4] - 0.3, n)
    # chopper gates: port stub -> 2 um Metal3 up -> Metal4 jog -> 1.2 um Metal3 into the lane
    for n, yj in TG_JOG.items():
        s = ck.pin(n, "metal3")
        xc = (s[1] + s[3]) / 2
        ln = I["tg"].pin(n, "metal3")
        xl = (ln[1] + ln[3]) / 2
        a.wire("metal3", xc - 0.19, s[2], xc + 0.19, s[4] + 1.2, n)
        a.wire("metal3", xc - 1.0, s[4] + 1.0, xc + 1.0, yj + 2.0, n)
        a.via_stack("metal3", "metal4", xc - 1.0, yj, xc + 1.0, yj + 2.0, n)
        a.wire("metal4", xc - 1.0, yj, xl + 0.6, yj + 2.0, n)
        a.via_stack("metal3", "metal4", xl - 0.6, yj, xl + 0.6, yj + 2.0, n)
        a.wire("metal3", xl - 0.6, yj, xl + 0.6, ln[4], n)
    # driver supply: AVSS_CLK straps joined on Metal3 under the driver's west edge;
    # AVDD_CLK up on Metal5 and over the driver to its east strap
    dvss, dvdd = ck.pin("AVSS_CLK", "metal3"), ck.pin("AVDD_CLK", "metal3")
    cvss = [p for p in odn.pins["AVSS_CLK"] if p[0] == "metal3"][0]
    cvdd = [p for p in odn.pins["AVDD_CLK"] if p[0] == "metal3"][0]
    ytop = odn.bbox[3]
    a.wire("metal3", cvss[1], ytop - 0.6, dvss[3], dvss[2] + 1.0, "AVSS_CLK")
    a.wire("metal3", cvdd[1], ytop - 0.6, cvdd[3], ytop + 6.4, "AVDD_CLK")
    a.via_stack("metal3", "metal5", cvdd[1], ytop + 2.4, cvdd[3], ytop + 6.4, "AVDD_CLK")
    ym = CK_Y + 50.0
    a.box("metal5", cvdd[1], ytop + 2.4, cvdd[3], ym + 6.0)
    a.box("metal5", cvdd[1], ym, dvdd[3], ym + 6.0)
    a.via_stack("metal3", "metal5", dvdd[1], ym, dvdd[3], ym + 6.0, "AVDD_CLK")
    # the two 100 ohm resistors (west end on the driver's supply, east end on AVDD / AVSS)
    rn = an.res_cell(a, "afe_rck_n", 2.0, 20.0, [("AVSS_CLK", "AVSS")], sub="AVSS")
    rp = an.res_cell(a, "afe_rck_p", 2.0, 20.0, [("AVDD_CLK", "AVDD")], sub="AVSS")
    for cell, x, y, nm in ((rn, 0.8, CK_Y + 14.0, "RCKN"), (rp, dvdd[3] + 8.0, CK_Y + 14.0, "RCKP")):
        a.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, nm)
        for n, segs in p.pins.items():
            pins.setdefault(n, []).extend(segs)
    pins.setdefault("AVSS_CLK", []).append(dvss)
    pins.setdefault("AVDD_CLK", []).append(dvdd)
    # supplies of the offset-DAC halves: their straps (offdac_p's run on to the top edge)
    for inst in (odn, odp):
        for n in ("AVDD", "AVSS"):
            s = [p for p in inst.pins[n] if p[0] == "metal3"][0]
            pins.setdefault(n, []).append(s)
            if inst is odp:
                a.wire("metal3", s[1], s[4] - 1.0, s[3], H, n)
    # the driver's other ports and CIA / CIB to the west edge; offdac_p's controls too
    for n in CLK_WEST:
        pins.setdefault(n, []).append(ck.pin(n, "metal3"))
    for p in OD_PORTS:
        n = OD_NET[p] + "_P"
        pins.setdefault(n, []).append(odp.pin(n, "metal3"))
    I["west_ports"] = [(CLK_WEST, ck.bbox[3] + 1.0, 2), ([OD_NET[p] + "_P" for p in OD_PORTS], odp.bbox[3] + 8.0, 4)]
    return pins


EAST_PORTS_LO = ["OUTP", "OUTN", "VBN", "VBCM", "BLP", "BLN", "VCM"]
EAST_PORTS_HI = ["RST2", "CIA2", "CIB2", "CDA2", "NCDA2", "CDB2", "NCDB2", "CPF0", "CPF1", "CPF2", "CPF3"]


def wiring(a, I):
    """Hand-drawn wiring (see the module doc); returns {net: [router pins]}."""
    pins = {}
    cinp, cinn, core, tg = I["cinp"], I["cinn"], I["core"], I["tg"]
    tp, bp = cinp.pin("INP", "metal5"), cinp.pin("WP", "metal5")
    tn, bn = cinn.pin("INN", "metal5"), cinn.pin("WN", "metal5")
    # bus extensions to the west (WP / WN for the input chopper, INP / INN for the offset DAC)
    a.wire("metal5", 5.0, bp[2], bp[1] + 1.0, bp[4], "WP")
    a.wire("metal5", 5.0, bn[2], bn[1] + 1.0, bn[4], "WN")
    a.wire("metal5", 200.0, tp[2], tp[1] + 1.0, tp[4], "INP")
    a.wire("metal5", 200.0, tn[2], tn[1] + 1.0, tn[4], "INN")
    # the input chopper's WP stripes up into the WP bus, WN stripes down into the WN bus
    src, top = tg.src, tg.srctop
    li = src.find_layer(*g.L["metal5"])
    for sh in top.shapes(li).each():
        b = A.pya.DBox(*A._box_um(sh.bbox())).transformed(tg.trans)
        if b.height() < 300 or b.width() > 5.0:
            continue
        if abs(b.top - tg.bbox[3]) < 0.01:           # WP stripe (reaches the block's top)
            a.wire("metal5", b.left, b.top - 1.0, b.right, bp[4], "WP")
        elif abs(b.bottom - tg.bbox[1]) < 0.01:      # WN stripe
            a.wire("metal5", b.left, bn[2], b.right, b.bottom + 1.0, "WN")
    # WP / WN taps for the output section: Metal4 from the inner bus under the outer one
    xt = W - 12.0
    a.wire("metal4", xt, tp[2] - 6.0, xt + 4.0, bp[4] - 0.3, "WP")
    a.via_stack("metal4", "metal5", xt, bp[2] + 0.3, xt + 4.0, bp[4] - 0.3, "WP")
    pins["WP"] = [("metal4", xt, tp[2] - 6.0, xt + 4.0, tp[2] - 2.0)]
    a.wire("metal4", xt, bn[2] + 0.3, xt + 4.0, tn[4] + 6.0, "WN")
    a.via_stack("metal4", "metal5", xt, bn[2] + 0.3, xt + 4.0, bn[4] - 0.3, "WN")
    pins["WN"] = [("metal4", xt, tn[4] + 2.0, xt + 4.0, tn[4] + 6.0)]
    # INP / INN taps for the output section (CFB, reset and DC-path switches): via stacks
    # on the inner buses in the gap between the core and the section, Metal3 into the band
    xi = EAST_X - 2.4
    a.via_stack("metal3", "metal5", xi, tp[2] + 0.3, xi + 1.2, tp[4] - 0.3, "INP")
    a.wire("metal3", xi, tp[2] - 6.0, xi + 1.2, tp[2] + 0.3, "INP")
    pins["INP"] = [("metal3", xi, tp[2] - 6.0, xi + 1.2, tp[2] - 2.0)]
    a.via_stack("metal3", "metal5", xi, tn[2] + 0.3, xi + 1.2, tn[4] - 0.3, "INN")
    a.wire("metal3", xi, tn[4] - 0.3, xi + 1.2, tn[4] + 6.0, "INN")
    pins["INN"] = [("metal3", xi, tn[4] + 2.0, xi + 1.2, tn[4] + 6.0)]
    # the core's INP / INN stubs into the buses
    for n, bus, up in (("INP", tp, True), ("INN", tn, False)):
        s_ = core.pin(n, "metal3")
        xc = (s_[1] + s_[3]) / 2
        if up:
            a.wire("metal3", s_[1], s_[2], s_[3], bus[2] - 1.0, n)
            a.via_stack("metal3", "metal5", xc - 0.6, bus[2] - 2.2, xc + 0.6, bus[2] + 1.0, n)
        else:
            a.wire("metal3", s_[1], bus[4] + 1.0, s_[3], s_[4], n)
            a.via_stack("metal3", "metal5", xc - 0.6, bus[4] - 1.0, xc + 0.6, bus[4] + 2.2, n)
    # supply rails (Metal5) from the east edge over the output section to the core's bars
    bars = {"AVSS": [], "AVDD": []}
    li4 = core.src.find_layer(*g.L["metal4"])
    for sh in core.srctop.shapes(li4).each():
        b = A.pya.DBox(*A._box_um(sh.bbox())).transformed(core.trans)
        if abs(b.height() - 6.0) < 0.01 and b.width() > 150:
            bars["AVSS" if b.left < core.bbox[0] + 100 else "AVDD"].append((b.left, b.bottom, b.right, b.top))
    vss = sorted(bars["AVSS"], key=lambda bx: bx[1])
    yv2 = max(bx[3] for bx in vss)
    vdd = sorted([bx for bx in bars["AVDD"] if bx[1] > yv2 + 4.0], key=lambda bx: bx[1])

    def strips(lst, grow):
        """Metal5 strips under 30 um (MSLOT5.1) over groups of bars: [(y1, y2, bars)]"""
        out = []
        for bx in lst:
            y1, y2 = bx[1] - grow, bx[3] + grow
            if out and y2 - out[-1][0] <= 29.0 and y1 <= out[-1][1] + 6.0:
                out[-1] = (out[-1][0], y2, out[-1][2] + [bx])
            else:
                out.append((y1, y2, [bx]))
        return out
    xw = tg.bbox[2] + 0.6                             # west ends: over the gap beside the chopper
    rails = {"AVSS": strips(vss, 0.0), "AVDD": strips(vdd, 10.0)}
    for net, lst in rails.items():
        for y1, y2, bl_ in lst:
            a.wire("metal5", xw, y1, W, y2, net)
            for bx in bl_:
                a.vias("via4", *bx)
        y1, y2, _ = lst[0]
        a.label("metal5", net, W - 1.0, (y1 + y2) / 2)
        # Metal4 pads under the rails for the router (the chopper's bulk, the section's cells)
        for x in (xw + 0.6, W - 20.0):
            a.via_stack("metal4", "metal5", x, y1 + 1.0, x + 4.0, y2 - 1.0, net)
            pins.setdefault(net, []).append(("metal4", x, y1 + 1.0, x + 4.0, y2 - 1.0))
    I["rails"] = rails
    # ports on the east and west edges (Metal4 stubs on router rows)
    gx0, px, gy0, py = GRID
    sides = [(EAST_PORTS_LO, 470.0, 4, W - 3.0), (EAST_PORTS_HI, 642.0, 4, W - 3.0)] + \
        [(names, y0, step, 0.0) for names, y0, step in I["west_ports"]]
    for names, y0, step, xa in sides:
        j0 = round((y0 - gy0) / py)
        for k, n in enumerate(names):
            y = gy0 + (j0 + step * k) * py
            box = (xa, y - 0.19, xa + 3.0, y + 0.19)
            a.box("metal4", *box)
            a.label("metal4", n, xa + 1.5, y)
            pins.setdefault(n, []).append(("metal4",) + box)
    return pins


def route_all(a, nets, keep):
    t0 = time.time()
    r = route.Router(GRID[0], GRID[2], W, H, px=GRID[1], py=GRID[3])
    a.obstacles(r)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    a.give(r)
    for n in nets:                                   # identical pins (e.g. a rail shared by two
        uniq = []                                    # mirrored rows) would starve each other
        for p_ in nets[n]:
            key = (p_[0],) + tuple(round(v, 3) for v in p_[1:])
            if key not in [(q[0],) + tuple(round(v, 3) for v in q[1:]) for q in uniq]:
                uniq.append(p_)
        nets[n] = uniq
    single = sorted(n for n, p in nets.items() if len(p) < 2)
    if single:
        print("single-pin nets:", single)
    failed = r.route({n: p for n, p in nets.items() if len(p) >= 2}, rounds=4)
    print(f"routed in {time.time() - t0:.0f} s")
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(a)


def labels(a, I):
    """Port labels on the top cell that wiring() does not set: the electrode spines, the
    offdac_n controls on the bottom edge, the corner supplies on the bottom / top edges."""
    for n, net in (("ELP", "ELP"), ("ELN", "ELN")):
        s = I["tg"].pin(net, "metal5")
        a.label("metal5", n, (s[1] + s[3]) / 2, (s[2] + s[4]) / 2)
    for p in OD_PORTS:
        n = OD_NET[p] + "_N"
        s = I["odn"].pin(n, "metal3")
        a.label("metal3", n, (s[1] + s[3]) / 2, s[2] + 0.5)
    for inst, yl in ((I["odn"], 1.0), (I["odp"], H - 1.0)):
        for n in ("AVDD", "AVSS"):
            s = [p for p in inst.pins[n] if p[0] == "metal3"][0]
            a.label("metal3", n, (s[1] + s[3]) / 2, yl)


NETLISTS = [os.path.join(AFE, "eeg_afe.spice"), os.path.join(AFE, "eeg_afe_clk.spice")] + \
    [os.path.join(HERE, "lvs", f"{n}.spice") for n in ("afe_tgin", "offdac_n", "offdac_p", "afe_top")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    args = ap.parse_args()
    runs = os.path.join(HERE, "runs", TOP)
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    a, nets, keep, I = build()
    for n, pins in wiring(a, I).items():
        nets.setdefault(n, []).extend(pins)
    route_all(a, nets, keep)
    labels(a, I)
    a.write(os.path.join(runs, "afe_route.gds"))
    bl.check(a, TOP, NETLISTS, runs, drc=args.drc, lvs=args.lvs, ties=[("AVSS_CLK", "AVSS")])


if __name__ == "__main__":
    main()

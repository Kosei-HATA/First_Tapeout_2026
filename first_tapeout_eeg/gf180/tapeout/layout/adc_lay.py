#!/usr/bin/env python3
"""Layout of the ADC (tracker E4): eeg_adc (gf180/tapeout/adc/eeg_adc.spice) with the
ADC-side digital block eeg_adc_dig, in the ADC region of the floorplan (1210 x 1447 um,
core x 1290..2500, y 100..1547; documentation/gf180_floorplan_20261022.md). Top cell
adc_top; LVS against lvs/adc_top.spice (eeg_adc and eeg_adc_dig).

Placement (local um; the differential axis at y = 723.5):
  - C1 arrays (eeg_c1, 340 pF since 10/23) above and below the band at the west, both
    with their buses facing it: C1P (TOP = I1P outer, BOT = O1N), C1N mirrored (I1N, O1P).
  - band: adc_rdac (RIN + DAC1) at the west, OTA1 east of it, both centred on the axis;
    east of OTA1 the second stage: OTA2, C2P / C2N (MIM cells), the OTA1 chopper driver
    eeg_adc_clk; R21 in the band's top channel.
  - top right: the quantizer (ports on its east edge); bottom right: DAC2 (SEL ports on
    its bottom edge) above eeg_adc_dig (LibreLane macro: SEL1 west, SEL2 north, TH and the
    frame interface east).
Hand-drawn wiring (assemble.Assembly.wire / via_stack):
  - stage-1 nets: I1P straps (Metal5) from the C1P bus to rdac and OTA1; I1N and O1P
    straps (Metal5) up the gap between rdac and OTA1 from the C1N buses (O1P crosses the
    I1N bus on a Metal4 tap); O1N from the C1P bus, extended east of the array; Metal4
    runs to the port stubs. Crossings between two of these nets lie between the two
    plates of one C1 or between the virtual grounds.
  - power: AVSS / AVDD Metal5 rails along the bottom of the band (AVSS next to the I1N
    bus) and in the top channel east of the C1 array, joined by two Metal5 trunks at the
    east; block straps extended to them with via stacks. DVDD / DVSS rails over
    eeg_adc_dig; DVDD for the quantizer's latches from the top edge.
Everything else: route.Router on Metal3 / Metal4 (small cells' supplies included).
Digital lines (SEL1, TH) cross the stage-1 straps only at right angles; the charge they
couple there follows the change of the code (rising minus falling lines), so it is
high-pass shaped in the band.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/adc_lay.py [--drc] [--lvs]
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
from dac2_lay import Combo

HERE = os.path.dirname(os.path.abspath(__file__))
ADC = os.path.join(g.REPO, "gf180", "tapeout", "adc")
SCL7 = os.path.join(g.PDK, "libs.ref", "gf180mcu_fd_sc_mcu7t5v0", "spice", "gf180mcu_fd_sc_mcu7t5v0.spice")
NETLISTS = [os.path.join(ADC, n) for n in ("eeg_adc_otas.spice", "eeg_adc_clk.spice", "eeg_dac1.spice",
                                           "eeg_dac2.spice", "eeg_quantizer.spice", "eeg_adc.spice")] + \
    [os.path.join(HERE, "gds", "eeg_adc_dig.cdl"), SCL7, os.path.join(HERE, "lvs", "adc_top.spice")]
TOP = "adc_top"
W, H = 1210.0, 1447.0
GRID = (0.24, 0.8, 0.0, route.P)          # router: columns x0, pitch; rows y0, pitch
# power rails (y ranges) and the east trunks (x ranges)
R_AVSS_B, R_AVDD_B = (418.0, 426.0), (428.0, 436.0)
R_AVDD_T, R_AVSS_T = (1012.0, 1020.0), (1024.0, 1032.0)
X_TOPRAIL = 545.0
T_AVDD, T_AVSS = (1150.0, 1158.0), (1162.0, 1170.0)
R_DVDD, R_DVSS = (100.0, 106.0), (112.0, 118.0)
X_DVDD = 1203.0                      # DVDD riser along the east edge (Metal5)
# ports
WEST_PORTS = ["INP", "INN", "VREFP", "VREFN", "VCM", "VBN1", "VNC1", "VPC1", "VBCM1", "VBPC2", "VBNC2",
              "IDP", "IDN", "IQ"]
TOP_PORTS = ["CHOP1", "RST", "ADC_ZERO"]
EAST_PORTS = ["MCLK", "ADC_RST_N", "TH_CAPTURE", "DAC_LOAD", "DWA_EN"] + [f"CODE{k}" for k in range(5)] + \
    ["DAC_CLK"]


def small_cells(a):
    """R21, the reset TG, the NRST inverter, the ADC_ZERO switch and the C2 MIM cell, as
    cells of the assembly."""
    r21 = an.res_cell(a, "adc_r21", 291.28, 1.0, [("O1P", "I2P"), ("O1N", "I2N")] * 3, sub="AVSS")
    tg = lg.tg_cell(a, "adc_rst_tg", 2, 2, 0.5, 1.0, a="A", y="B", gn="G", gp="GN")
    p, n = lg.inv_seq(1)
    inv = lg.cmos_cell(a, "adc_inv", p, n, 2.0, 1.0, ["A", "Y"])
    ztg = lg.tg_cell(a, "adc_zero_tg", 4, 4, 2.5, 5.0, a="A", y="B", gn="Z", gp="ZB")
    zero = Combo(a, "adc_zero", [(inv, {"A": "Z", "Y": "ZB"}), (ztg, {})])
    c2 = an.mim_cell(a, "adc_c2", 98.83, "TOP", "BOT")
    return r21, tg, inv, zero, c2


def stub(inst, net):
    """The narrow Metal3 port stub of `net` on a block's edge (x1, y1, x2, y2)."""
    for lay, x1, y1, x2, y2 in inst.pins[net]:
        if lay == "metal3" and x2 - x1 < 0.5:
            return x1, y1, x2, y2
    raise KeyError(f"{inst.name}: no stub {net}")


def rise(a, s, y1, y2, net, top="metal4"):
    """Extend a top-edge stub s up to y1 at its own width, then a 1 um wide pad y1..y2
    with vias up to `top`; returns the pad box."""
    xc = (s[0] + s[2]) / 2
    a.wire("metal3", s[0], s[1], s[2], y1 + 0.5, net)
    a.via_stack("metal3", top, xc - 0.5, y1, xc + 0.5, y2, net)
    return xc - 0.5, y1, xc + 0.5, y2


def stage1(a, I):
    """I1P / I1N / O1P / O1N straps (see the module doc). Returns {net: [router pins]}."""
    c1p, c1n, rdac, ota1 = I["c1p"], I["c1n"], I["rdac"], I["ota1"]
    tp, bp = c1p.pin("I1P", "metal5"), c1p.pin("O1N", "metal5")
    tn, bn = c1n.pin("I1N", "metal5"), c1n.pin("O1P", "metal5")
    so = {n: stub(ota1, n) for n in ("I1P", "I1N", "O1P", "O1N")}
    sr = {n: stub(rdac, n) for n in ("I1P", "I1N")}
    yo, yr = so["I1P"][3], sr["I1P"][3]           # top edges of OTA1 and rdac
    pins = {}
    # I1P: straps down from the C1P TOP bus to rdac's and OTA1's stubs
    for s in (sr["I1P"], so["I1P"]):
        xc = (s[0] + s[2]) / 2
        pad = rise(a, s, s[3] + 1.0, s[3] + 2.0, "I1P", top="metal5")
        a.wire("metal5", xc - 2.0, pad[1], xc + 2.0, tp[2] + 1.0, "I1P")
        pins.setdefault("I1P", []).append(("metal4",) + pad)
    # I1N: Metal5 strap up the gap from the C1N TOP bus; Metal4 runs to rdac and OTA1
    gx = rdac.bbox[2]
    xi1, xi2 = gx + 2.6, gx + 7.6                    # I1N strap
    xo1, xo2 = gx + 11.6, gx + 16.6                  # O1P strap
    assert xo2 + 4.0 < ota1.bbox[0], "gap between rdac and OTA1 too narrow"
    y_i1n_o = (yo + 7.0, yo + 9.0)
    y_i1n_r = (yr + 3.0, yr + 5.0)
    a.wire("metal5", xi1, tn[2], xi2, y_i1n_o[1], "I1N")
    for s, (y1, y2) in ((sr["I1N"], y_i1n_r), (so["I1N"], y_i1n_o)):
        xc = (s[0] + s[2]) / 2
        pad = rise(a, s, y1, y2, "I1N")
        a.wire("metal4", min(xc - 0.5, xi1), y1, max(xc + 0.5, xi2), y2, "I1N")
        a.via_stack("metal4", "metal5", xi1, y1, xi2, y2, "I1N")
        pins.setdefault("I1N", []).append(("metal4",) + pad)
    # O1P: Metal4 tap from the C1N BOT bus under the TOP bus, Metal5 strap up the gap,
    # Metal4 run to OTA1's OUTP stub
    y_o1p = (yo + 11.0, yo + 13.0)
    ys = tn[4] + 1.3
    a.wire("metal4", xo1, bn[2] + 0.3, xo2, ys + 1.0, "O1P")
    a.via_stack("metal4", "metal5", xo1, bn[2] + 0.3, xo2, bn[4] - 0.3, "O1P")
    a.via_stack("metal4", "metal5", xo1, ys, xo2, ys + 1.0, "O1P")
    a.wire("metal5", xo1, ys, xo2, y_o1p[1], "O1P")
    s = so["O1P"]
    xc = (s[0] + s[2]) / 2
    pad = rise(a, s, *y_o1p, "O1P")
    a.wire("metal4", xo1, y_o1p[0], xc + 0.5, y_o1p[1], "O1P")
    a.via_stack("metal4", "metal5", xo1, y_o1p[0], xo2, y_o1p[1], "O1P")
    pins["O1P"] = [("metal4", xo2 + 2.0, y_o1p[0], xc - 2.0, y_o1p[1])]
    # O1N: the C1P BOT bus extended east of the array, a Metal5 strap down to OTA1
    y_o1n = (yo + 3.0, yo + 5.0)
    s = so["O1N"]
    xc = (s[0] + s[2]) / 2
    xs1 = bp[3] + 4.0
    a.wire("metal5", bp[3] - 1.0, bp[2], xs1 + 5.0, bp[4], "O1N")
    a.wire("metal5", xs1, y_o1n[0], xs1 + 5.0, bp[4], "O1N")
    pad = rise(a, s, *y_o1n, "O1N")
    a.wire("metal4", xc - 0.5, y_o1n[0], xs1 + 5.0, y_o1n[1], "O1N")
    a.via_stack("metal4", "metal5", xs1, y_o1n[0], xs1 + 5.0, y_o1n[1], "O1N")
    pins["O1N"] = [("metal4", xc + 2.0, y_o1n[0], xs1 - 2.0, y_o1n[1])]
    return pins


def strap_to_rail(a, inst, net, rail, up):
    """Extend every Metal3 power strap `net` of a block to a Metal5 rail (y1, y2) above
    (up) or below it, with a via stack under the rail."""
    for lay, x1, y1, x2, y2 in inst.pins[net]:
        if lay != "metal3" or x2 - x1 < 1.0:
            continue
        if up:
            a.wire("metal3", x1, y2 - 0.5, x2, rail[1], net)
        else:
            a.wire("metal3", x1, rail[0], x2, y1 + 0.5, net)
        a.via_stack("metal3", "metal5", x1, rail[0], x2, rail[1], net)


def power(a, I):
    """Rails, trunks and block connections; returns {net: [router pins]} (Metal4 pads)."""
    rdac = I["rdac"]
    gx = rdac.bbox[2]
    b2 = gx + 20.0                                   # east end of the Metal4 bridges
    # the rails cross the gap straps on Metal4 bridges; at the west end the AVDD bridge
    # meets rdac's AVDD strap stack, the AVSS bridge has its own via stack (clear of the
    # AVSS strap stack west of it)
    x_avdd = rdac.pin("AVDD", "metal3")[1]
    for net, (y1, y2), xe, xb in (("AVSS", R_AVSS_B, T_AVSS[1], gx - 3.0), ("AVDD", R_AVDD_B, T_AVDD[1], x_avdd)):
        a.wire("metal5", 0.0, y1, gx, y2, net)
        a.wire("metal5", b2 - 1.5, y1, xe, y2, net)
        a.wire("metal4", xb, y1, b2, y2, net)
        if net == "AVSS":
            a.via_stack("metal4", "metal5", xb, y1, xb + 1.5, y2, net)
        a.via_stack("metal4", "metal5", b2 - 1.5, y1, b2, y2, net)
    a.wire("metal5", X_TOPRAIL, R_AVDD_T[0], T_AVDD[1], R_AVDD_T[1], "AVDD")
    a.wire("metal5", X_TOPRAIL, R_AVSS_T[0], T_AVSS[1], R_AVSS_T[1], "AVSS")
    a.wire("metal5", T_AVDD[0], R_AVDD_B[0], T_AVDD[1], R_AVDD_T[1], "AVDD")
    a.wire("metal5", T_AVSS[0], R_AVSS_B[0], T_AVSS[1], R_AVSS_T[1], "AVSS")
    # block straps
    strap_to_rail(a, rdac, "AVSS", R_AVSS_B, up=False)
    strap_to_rail(a, rdac, "AVDD", R_AVDD_B, up=False)
    strap_to_rail(a, I["ota1"], "AVSS", R_AVSS_B, up=False)
    strap_to_rail(a, I["ota1"], "AVDD", R_AVDD_B, up=False)
    strap_to_rail(a, I["ota2"], "AVSS", R_AVSS_B, up=False)
    strap_to_rail(a, I["ota2"], "AVDD", R_AVDD_B, up=False)
    strap_to_rail(a, I["aclk"], "AVDD", R_AVDD_T, up=True)
    strap_to_rail(a, I["aclk"], "AVSS", R_AVSS_T, up=True)
    strap_to_rail(a, I["quant"], "AVSS", R_AVSS_T, up=False)
    strap_to_rail(a, I["quant"], "AVDD", R_AVDD_T, up=False)
    # DVDD / DVSS rails over eeg_adc_dig, Via4 onto its Metal4 straps (DVSS ends short
    # of the DVDD riser at the east edge)
    dig = I["dig"]
    for net, (y1, y2), xe in (("DVDD", R_DVDD, W), ("DVSS", R_DVSS, X_DVDD - 2.0)):
        straps = [s for s in dig.pins[net] if s[0] == "metal4"]
        a.wire("metal5", min(s[1] for s in straps) - 2.0, y1, xe, y2, net)
        for _, x1, _, x2, _ in straps:
            a.vias("via4", x1, y1, x2, y2)
    # DVDD for the quantizer's latches: a Metal5 strap from the top edge to its port, and
    # a riser along the east edge down to the DVDD rail (one DVDD net inside the ADC)
    q = I["quant"].pin("DVDD", "metal4")
    xd = q[3] + 30.0
    a.wire("metal5", xd, q[2] - 1.0, xd + 6.0, H, "DVDD")
    a.wire("metal4", q[1], q[2], xd + 6.0, q[4], "DVDD")
    a.via_stack("metal4", "metal5", xd, q[2], xd + 6.0, q[4], "DVDD")
    a.wire("metal5", xd, q[2] - 1.0, W - 1.0, q[4] + 3.0, "DVDD")
    a.wire("metal5", X_DVDD, R_DVDD[0], W - 1.0, q[4] + 3.0, "DVDD")
    # Metal4 pads under the rails for the router (small cells' supplies, DAC2)
    pads = {}
    for net, x, (y1, y2) in (("AVSS", 548.0, R_AVSS_T), ("AVDD", 556.0, R_AVDD_T), ("AVSS", 440.0, R_AVSS_B),
                             ("AVDD", 448.0, R_AVDD_B), ("AVSS", 1120.0, R_AVSS_B), ("AVDD", 1128.0, R_AVDD_B),
                             ("AVSS", 1100.0, R_AVSS_T), ("AVDD", 1108.0, R_AVDD_T)):
        a.via_stack("metal4", "metal5", x, y1 + 2.0, x + 4.0, y2 - 2.0, net)
        pads.setdefault(net, []).append(("metal4", x, y1 + 2.0, x + 4.0, y2 - 2.0))
    pads["AVSS"].append(rdac.pin("AVSS", "metal3"))
    pads["AVDD"].append(rdac.pin("AVDD", "metal3"))
    return pads


def ports(a):
    """Port stubs on the region's edges (labelled), on the router grid; returns
    {net: [pin]}."""
    gx0, px, gy0, py = GRID
    out = {}
    j0 = round((870.0 - gy0) / py)
    for k, n in enumerate(WEST_PORTS):
        y = gy0 + (j0 + 8 * k) * py
        box = (0.0, y - 0.19, 3.0, y + 0.19)
        a.box("metal4", *box)
        a.label("metal4", n, 1.0, y)
        out[n] = [("metal4",) + box]
    i0 = round((1080.0 - gx0) / px)
    for k, n in enumerate(TOP_PORTS):
        x = gx0 + (i0 + 6 * k) * px
        box = (x - 0.15, H - 1.5, x + 0.15, H)
        a.box("metal3", *box)
        a.label("metal3", n, x, H - 0.3)
        out[n] = [("metal3",) + box]
    j0 = round((12.0 - gy0) / py)
    for k, n in enumerate(EAST_PORTS):
        y = gy0 + (j0 + 8 * k) * py
        box = (W - 3.0, y - 0.19, W, y + 0.19)
        a.box("metal4", *box)
        a.label("metal4", n, W - 1.0, y)
        out[n] = [("metal4",) + box]
    y = gy0 + round((1205.0 - gy0) / py) * py
    box = (W - 3.0, y - 0.19, W, y + 0.19)
    a.box("metal4", *box)
    a.label("metal4", "CMP_STROBE", W - 1.0, y)
    out["CMP_STROBE"] = [("metal4",) + box]
    for net, (y1, y2) in (("AVSS", R_AVSS_B), ("AVDD", R_AVDD_B)):
        a.label("metal5", net, 1.0, (y1 + y2) / 2)
    a.label("metal5", "DVDD", W - 1.0, sum(R_DVDD) / 2)
    a.label("metal5", "DVSS", X_DVDD - 3.0, sum(R_DVSS) / 2)
    return out


def macro_pads(a, inst):
    """Router pins outside a LibreLane macro for its edge pins: Metal3 pads (1.4 um tall)
    on the outer ends of the horizontal Metal3 pins (west / east edges), so that each
    holds a router node, and 3 um Metal2 extensions of the vertical Metal2 pins (north /
    south edges). The macro's own pins are replaced by these in inst.pins."""
    x1m, y1m, x2m, y2m = inst.bbox
    for net, segs in inst.pins.items():
        new = []
        for seg in segs:
            lay, x1, y1, x2, y2 = seg
            box = None
            if lay == "metal3" and y2 - y1 <= 1.0:
                yc = (y1 + y2) / 2
                if abs(x1 - x1m) < 0.01:
                    box = ("metal3", x1 - 2.5, yc - 0.7, x1 + 0.5, yc + 0.7)
                elif abs(x2 - x2m) < 0.01:
                    box = ("metal3", x2 - 0.5, yc - 0.7, x2 + 2.5, yc + 0.7)
            elif lay == "metal2":
                if abs(y2 - y2m) < 0.01:
                    box = ("metal2", x1, y2 - 0.5, x2, y2 + 3.0)
                elif abs(y1 - y1m) < 0.01:
                    box = ("metal2", x1, y1 - 3.0, x2, y1 + 0.5)
            if box is None:
                new.append(seg)
                continue
            if box[0] == "metal3":
                a.wire(*box, net)
            else:
                a.box(*box)
            new.append(box)
        inst.pins[net] = new


def build():
    a = A.Assembly(TOP)
    nets = {}
    keep = []                            # (metal3 box, metal4 box) keep-outs of MIM cells

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def add(inst, power=("AVDD", "AVSS", "DVDD", "DVSS")):
        for n, segs in inst.pins.items():
            if "." in n or n in power:
                continue
            conn(n, segs)

    def cell_at(cell, x, y, name, cmap, mirror=False):
        """Place a small cell; logic cells' supply rails get their router pin outside the
        cell (a Metal2 extension 3 um to the west with a Metal3 pad), so that the rails'
        pin access does not compete with the cell's own pins."""
        a.place(cell.cell, x, y, mirror=mirror)
        p = bl.Placed(cell, x, y, mirror, name)
        for pn, segs in p.pins.items():
            net = cmap.get(pn, pn)
            if pn in ("VDD", "VSS") and isinstance(cell, (lg.LogicCell, Combo)):
                lay, x1, y1, x2, y2 = segs[0]
                a.box("metal2", x1 - 3.0, y1, x1 + 0.5, y2)
                pad = (x1 - 3.0, (y1 + y2) / 2 - 0.5, x1 - 1.6, (y1 + y2) / 2 + 0.5)
                a.vias("via2", *pad)
                a.manual.append(("metal3", pad, net))
                conn(net, [("metal3",) + pad])
                continue
            conn(net, segs)
        return p

    # ---- blocks
    I = {}
    I["c1p"] = a.put("eeg_c1", 0.0, H - 412.32, name="C1P", nets={"TOP": "I1P", "BOT": "O1N"}, mim=True)
    I["c1n"] = a.put("eeg_c1", 0.0, 412.32, mirror=True, name="C1N", nets={"TOP": "I1N", "BOT": "O1P"}, mim=True)
    I["rdac"] = a.put("adc_rdac", 4.0, 585.0, name="RDAC", grid=GRID)
    I["ota1"] = a.put("gf180_inside_cascode_ota", 421.0, 494.2, name="OTA1", grid=GRID, nets={
        "INP": "I1P", "INN": "I1N", "OUTP": "O1P", "OUTN": "O1N", "VCMREF": "VCM", "VBN": "VBN1", "VNC": "VNC1",
        "VPC": "VPC1", "VBCM": "VBCM1", "VDD": "AVDD", "VSS": "AVSS"})
    I["ota2"] = a.put("gf180_ct_ota_tel16_cmfb", 868.0, 600.0, name="OTA2", grid=GRID, nets={
        "INP": "I2P", "INN": "I2N", "OUTP": "O2P", "OUTN": "O2N", "VCMREF": "VCM", "VBN": "VBN1", "VNC": "VNC1",
        "VPC": "VPC1", "VBCM": "VBCM1", "VDD": "AVDD", "VSS": "AVSS"})
    I["aclk"] = a.put("eeg_adc_clk", 880.0, 925.0, name="ACLK", grid=GRID, nets={"VDD": "AVDD", "VSS": "AVSS"})
    I["quant"] = a.put("eeg_quantizer", 560.0, 1042.0, name="Q", grid=GRID, nets={"INP": "O2P", "INN": "O2N"})
    I["dac2"] = a.put("eeg_dac2", 570.0, 262.0, name="DAC2", grid=GRID, nets=dict(
        {"OUTP": "I2P", "OUTN": "I2N", "VBPC": "VBPC2", "VBNC": "VBNC2", "VDD": "AVDD", "VSS": "AVSS"},
        **{f"SEL{k}": f"SEL2_{k}" for k in range(31)}))
    I["dig"] = a.put("eeg_adc_dig", 566.0, 0.0, name="DIG", nets=dict(
        {"RST_N": "ADC_RST_N", "VDD": "DVDD", "VSS": "DVSS"},
        **{f"SEL1[{k}]": f"SEL1_{k}" for k in range(31)}, **{f"SEL2[{k}]": f"SEL2_{k}" for k in range(31)},
        **{f"TH[{k}]": f"TH{k}" for k in range(31)}, **{f"CODE[{k}]": f"CODE{k}" for k in range(5)}))
    macro_pads(a, I["dig"])
    for k in ("rdac", "ota1", "ota2", "aclk", "dac2"):
        a.cover(I[k])
    for k in ("rdac", "ota1", "ota2", "aclk", "quant", "dig"):
        add(I[k])
    add(I["dac2"], power=())             # DAC2's supplies: small currents, through the router
    for n in ("I1P", "I1N", "O1P", "O1N"):
        nets.pop(n, None)

    # ---- small cells
    r21, tg, inv, zero, c2 = small_cells(a)
    cell_at(r21, 560.0, 990.0, "R21", {})
    cell_at(tg, 460.0, 968.0 + 6.0, "XR1P", {"A": "O1N", "B": "I1P", "G": "RST", "GN": "NRST",
                                              "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(tg, 440.0, 474.0, "XR1N", {"A": "O1P", "B": "I1N", "G": "RST", "GN": "NRST",
                                        "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(inv, 500.0, 968.0 + 6.0, "XRSTB", {"A": "RST", "Y": "NRST", "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(zero, 70.0, 868.0, "XZERO", {"A": "INP", "B": "INN", "Z": "ADC_ZERO", "ZB": "ZB0",
                                         "VDD": "AVDD", "VSS": "AVSS"})
    for name, x, cmap in (("C2P", 868.0, {"TOP": "I2P", "BOT": "O2N"}), ("C2N", 975.0, {"TOP": "I2N", "BOT": "O2P"})):
        p = cell_at(c2, x, 800.0, name, cmap)
        k3, k4 = c2.keepout, c2.keepout4
        keep.append(((p.x + k3[0], p.y + k3[1], p.x + k3[2], p.y + k3[3]),
                     (p.x + k4[0], p.y + k4[1], p.x + k4[2], p.y + k4[3])))
    cell_at(tg, 1090.0, 870.0, "XR2P", {"A": "O2N", "B": "I2P", "G": "RST", "GN": "NRST",
                                         "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(tg, 1090.0, 840.0, "XR2N", {"A": "O2P", "B": "I2N", "G": "RST", "GN": "NRST",
                                         "VDD": "AVDD", "VSS": "AVSS"})

    # ---- hand-drawn wiring and ports
    for n, pins in stage1(a, I).items():
        conn(n, pins)
    for n, pins in power(a, I).items():
        conn(n, pins)
    for n, pins in ports(a).items():
        conn(n, pins)

    # ---- routing
    t0 = time.time()
    r = route.Router(GRID[0], GRID[2], W, H, px=GRID[1], py=GRID[3])
    a.obstacles(r)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    a.give(r)
    # nets with one pin (ports of unused functions) are dropped; the rest must connect
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
    hints(a, I["ota1"], "ADC.OTA1.")
    return a, I


def hints(a, inst, prefix):
    """Name-hint labels for the LVS net matcher on a block's internal nets (the block's own
    hints, e.g. OTA1's CIP / CIN and OTA.CORE.D1P..., which the flat LVS loses with the
    subcell labels), renamed to the flattened schematic's hierarchical names."""
    for n in ("CIP", "CIN", "OTA.CORE.D1P", "OTA.CORE.D1N", "OTA.CORE.P1P", "OTA.CORE.P1N"):
        lay, x1, y1, x2, y2 = inst.pins[n][0]
        a.label(lay, prefix + n, (x1 + x2) / 2, (y1 + y2) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    args = ap.parse_args()
    runs = os.path.join(HERE, "runs", TOP)
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    a, I = build()
    print(f"{TOP}: {W:.0f} x {H:.0f} um")
    bl.check(a, TOP, NETLISTS, runs, drc=args.drc, lvs=args.lvs, ties=[("DVSS", "AVSS")])


if __name__ == "__main__":
    main()

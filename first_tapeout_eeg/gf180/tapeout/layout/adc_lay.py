#!/usr/bin/env python3
"""Layout of the ADC (tracker E4): eeg_adc (gf180/tapeout/adc/eeg_adc.spice) with the
ADC-side digital block eeg_adc_dig, in the ADC region of the floorplan (1210 x 1447 um,
core x 1290..2500, y 100..1547; documentation/gf180_floorplan_20261022.md). Top cell
adc_top; LVS against lvs/adc_top.spice (eeg_adc and eeg_adc_dig).

Placement (local um; the differential axis at y = 723.5):
  - C1 (425 pF per side since 10/29, x1.25; eeg_adc.spice): the main arrays (eeg_c1a, 20
    units, 5 x 4) above and below the band at the west, both with their buses facing it:
    C1P (TOP = I1P outer, BOT = O1N), C1N mirrored (I1N, O1P). The rest of C1 (eeg_c1x, 4
    smaller units in a row) lies in the band's west end on each side, its buses facing
    those of the main array: C1PX mirrored right under C1P (the two TOP buses abut), C1NX
    above the bottom rails (c1_extension()).
  - band: adc_rdac (RIN + DAC1) at the west, OTA1 east of it; east of OTA1 the second
    stage: OTA2, C2P / C2N (MIM cells, two units each), the OTA1 chopper driver
    eeg_adc_clk, the stage-2 reset TGs east of OTA2; R21 in the band's top channel. Since
    r11 (11/12, RIN, DAC1 and R21 in ppolyf_u) adc_rdac is 426 x 378 um: it sits right
    above C1NX, everything east of it moved east by DX_BAND (31.2 um) and the AVDD / AVSS
    trunks with it; the west ports and the ADC_ZERO switch moved into the channel between
    adc_rdac and C1PX.
  - top right: the quantizer (ports on its east edge); bottom right: DAC2 (SEL ports on
    its bottom edge) above eeg_adc_dig (LibreLane macro: SEL1 west, SEL2 north, TH and the
    frame interface east).
Hand-drawn wiring (assemble.Assembly.wire / via_stack):
  - stage-1 nets: I1P straps (Metal5) from the C1P bus to rdac and OTA1; I1N and O1P
    straps (Metal5) up the gap between rdac and OTA1 from the C1N buses (O1P crosses the
    I1N bus on a Metal4 tap); O1N from the C1P bus, extended east of the array; Metal4
    runs to the port stubs. Crossings between two of these nets lie between the two
    plates of one C1 or between the virtual grounds. C1's two parts are joined by Metal4
    jumpers: O1N under the abutting I1P buses; I1N and O1P under the bottom rails.
  - power: AVSS / AVDD Metal5 rails along the bottom of the band (AVSS next to the I1N
    bus) and in the top channel east of the C1 array, joined by two Metal5 trunks at the
    east; block straps extended to them with via stacks. DVDD / DVSS rails over
    eeg_adc_dig; DVDD for the quantizer's latches from the top edge. The latches' ground
    (the quantizer's DVSS port) on AVSS since r10 (11/9): a Metal5 strap from the port down
    to the top AVSS rail. Through r9 that port was left open, so the latches, the TH
    inverters, the strobe buffer and the DVSS shields reached ground only through their
    p-taps and the substrate; the LVS (DVSS tied into AVSS) could not see it.
Everything else: route.Router on Metal3 / Metal4 (small cells' supplies included).
Since r12 (11/13) no switching line runs under the I1N / O1P straps unshielded (tunnel()):
SEL1_0..30 and DAC_CLK cross them on Metal2 under a Metal4 AVSS shield, the router keeps
out of the gap between adc_rdac and OTA1 (Metal3 / Metal4, from the C1N buses up to rdac's
top), and the stage-1 reset TG XR1N reaches I1N / O1P on short Metal4 taps from the straps.
Through r11 the router took those lines across on Metal4 right under the straps' Metal5
(I1N and O1P each about 9-14 fF to the SEL1 lines in the extraction), XR1N's I1N / O1P wires
ran inside that bus, and its I1N wire, RST and NRST ran up the gap on Metal3.

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
R_AVSS_B, R_AVDD_B = (422.4, 430.4), (432.4, 440.4)    # 5.68 um above C1N (416.72 tall since 10/29)
R_AVDD_T, R_AVSS_T = (1012.0, 1020.0), (1024.0, 1032.0)
X_TOPRAIL = 545.0
T_AVDD, T_AVSS = (1168.0, 1176.0), (1180.0, 1188.0)   # r11: 18 um east (C2N moved east)
DX_BAND = 31.2                       # r11: OTA1 and the second stage east of adc_rdac (426.2 um wide)
Y_RDAC = 531.0                       # r11: adc_rdac right above C1NX (its bottom ports at 530)
Y_WPORT = 916.5                      # r11: the first west port, in the channel above adc_rdac
R_DVDD, R_DVSS = (100.0, 106.0), (112.0, 118.0)
X_DVDD = 1203.0                      # DVDD riser along the east edge (Metal5)
# C1's rest (eeg_c1x): the west edge of both parts and the bottom of C1NX (3.6 um above the
# AVDD rail); the west edges of the 10 um Metal4 jumpers between C1's parts (in the first
# columns, clear of the arrays' own jumpers at the column edges)
X_C1X, Y_C1NX = 12.0, 444.0
X_JUMP = (40.0, 60.0)
# ports
WEST_PORTS = ["INP", "INN", "VREFP", "VREFN", "VCM", "VBN1", "VNC1", "VPC1", "VBCM1", "VBPC2", "VBNC2",
              "IDP", "IDN", "IQ"]
TOP_PORTS = ["CHOP1", "RST", "ADC_ZERO", "O2P", "O2N"]   # O2P / O2N: to the test multiplexer
EAST_PORTS = ["MCLK", "ADC_RST_N", "TH_CAPTURE", "DAC_LOAD", "DWA_EN"] + [f"CODE{k}" for k in range(5)] + \
    ["DAC_CLK"]


R21_L = 213.54                      # r11: three ppolyf_u strips of 213.54 x 0.8 um make a 300 kohm unit
# r12: the lines that cross the I1N / O1P straps in the tunnel, bottom row first
TUNNEL = ["DAC_CLK"] + [f"SEL1_{k}" for k in range(31)]


def r21_cell(a):
    """R21 (r11): per side three units of three ppolyf_u strips in series, the units'
    middle nodes joined (eeg_adc.spice XR21P1..3, XR21N1..3, m=3). Strips bottom to top:
    O1P -> R21PA (x3), R21PB -> R21PA (x3), R21PB -> I2P (x3), then the N side mirrored;
    Metal2 bars on the heads join each net's strips, so O1P / O1N stay on the west side
    and I2P / I2N on the east side as through r10 (one ppolyf_u_1k strip per unit)."""
    terms = ([("O1P", "R21PA")] * 3 + [("R21PB", "R21PA")] * 3 + [("R21PB", "I2P")] * 3 +
             [("R21NB", "I2N")] * 3 + [("R21NB", "R21NA")] * 3 + [("O1N", "R21NA")] * 3)
    r = an.pres_cell(a, "adc_r21", R21_L, 0.8, terms, sub="AVSS")
    bars = {}
    for e in (0, 1):
        k = 0
        while k < len(terms):
            net, j = terms[k][e], k
            while j + 1 < len(terms) and terms[j + 1][e] == net:
                j += 1
            if j > k:
                x1, y1, x2, _ = r.pad(k, e == 1)
                yt = r.pad(j, e == 1)[3]
                x = x2 - 0.38 if e else x1
                r.cell.box("metal2", x, y1, x + 0.38, yt)
                bars.setdefault(net, []).append(("metal2", x, y1, x + 0.38, yt))
            k = j + 1
    # the router gets one pad per net (the middle one; the bar joins the others): it reaches
    # Metal2 pins as horizontal segments, so the vertical bars are no pins
    for n in ("R21PA", "R21PB", "R21NA", "R21NB"):
        r.pins.pop(n)
    for n in ("O1P", "O1N", "I2P", "I2N"):
        assert len(r.pins[n]) == 3 and bars[n]
        r.pins[n] = [r.pins[n][1]]
    return r


def small_cells(a):
    """R21, the reset TG, the NRST inverter, the ADC_ZERO switch and the C2 MIM cell (two
    units of 61.68 x 98.83 um, 24.41 pF), as cells of the assembly."""
    r21 = r21_cell(a)
    tg = lg.tg_cell(a, "adc_rst_tg", 2, 2, 0.5, 1.0, a="A", y="B", gn="G", gp="GN")
    p, n = lg.inv_seq(1)
    inv = lg.cmos_cell(a, "adc_inv", p, n, 2.0, 1.0, ["A", "Y"])
    ztg = lg.tg_cell(a, "adc_zero_tg", 4, 4, 2.5, 5.0, a="A", y="B", gn="Z", gp="ZB")
    zero = Combo(a, "adc_zero", [(inv, {"A": "Z", "Y": "ZB"}), (ztg, {})])
    c2 = an.mim_cell(a, "adc_c2", 61.68, "TOP", "BOT", n=2, length=98.83)
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
    # O1N: the C1P BOT bus extended east of the array, a Metal5 strap down to OTA1 (west of
    # the top rails), a Metal4 run to OTA1's OUTN stub with the router's pin on it. Since r11
    # (OTA1 31.2 um east) the stub lies east of the strap: the run then also reaches 8 um
    # west of the strap, and the pin is there.
    y_o1n = (yo + 3.0, yo + 5.0)
    s = so["O1N"]
    xc = (s[0] + s[2]) / 2
    xs1 = bp[3] + 4.0
    assert xs1 + 5.0 < X_TOPRAIL - 1.0, "O1N strap under the top rails"
    a.wire("metal5", bp[3] - 1.0, bp[2], xs1 + 5.0, bp[4], "O1N")
    a.wire("metal5", xs1, y_o1n[0], xs1 + 5.0, bp[4], "O1N")
    pad = rise(a, s, *y_o1n, "O1N")
    if xc + 2.0 < xs1 - 6.0:                         # the stub west of the strap (through r10)
        a.wire("metal4", xc - 0.5, y_o1n[0], xs1 + 5.0, y_o1n[1], "O1N")
        pins["O1N"] = [("metal4", xc + 2.0, y_o1n[0], xs1 - 2.0, y_o1n[1])]
    else:
        a.wire("metal4", xs1 - 8.0, y_o1n[0], max(xc + 0.5, xs1 + 5.0), y_o1n[1], "O1N")
        pins["O1N"] = [("metal4", xs1 - 7.5, y_o1n[0], xs1 - 2.0, y_o1n[1])]
    a.via_stack("metal4", "metal5", xs1, y_o1n[0], xs1 + 5.0, y_o1n[1], "O1N")
    return pins


def tunnel(a, I):
    """r12 (11/13): the switching lines that cross the I1N / O1P straps (TUNNEL: DAC_CLK and
    SEL1_0..30, from eeg_adc_dig and the east port to adc_rdac's bottom ports) pass under
    them on Metal2, one router row apart, under a Metal4 AVSS shield; a Metal4 strip joins
    the shield to the bottom AVSS rail (Via4, and OTA1's AVSS strap stack). Metal2, because
    adc_rdac's AVSS / AVDD straps and OTA1's AVSS strap (Metal3, strap_to_rail()) run down
    through the gap. Via stacks up to Metal4 at both ends, on router columns clear of those
    straps, are the router's pins: east of the gap the line keeps its name (to eeg_adc_dig
    or the east port), west of it the router sees a net <name>_W (to adc_rdac's port).
    Also the reset TG XR1N's taps: Metal4 from the I1N and O1P straps east to pads beside
    OTA1's AVSS strap, the router's pins of I1N_R / O1P_R (XR1N's B / A), above the shield.
    Returns ({router net: [pins]}, [(layer, box)] router obstacles: the shield, its strip,
    and the gap between adc_rdac and OTA1 from the C1N buses up to 10 um below rdac's top,
    on Metal3 and Metal4)."""
    gx0, px, gy0, py = GRID
    rdac, ota1 = I["rdac"], I["ota1"]
    gx, ox = rdac.bbox[2], ota1.bbox[0]
    xs1, xo1 = gx + 2.6, gx + 11.6                   # west edges of the I1N and O1P straps (stage1())
    west = min(s[1] for n in ("AVSS", "AVDD") for s in rdac.pins[n]
               if s[0] == "metal3" and s[3] - s[1] >= 1.0 and s[3] > gx - 8.0)
    east = max(s[3] for s in ota1.pins["AVSS"] if s[0] == "metal3" and s[3] - s[1] >= 1.0 and s[1] < ox + 5.0)
    assert west > gx - 8.0 and east < ox + 4.0, (west, east)
    i_w = int((west - 1.0 - gx0) / px)
    i_e = -int(-(east + 1.0 - gx0) // px)
    xw, xe = gx0 + i_w * px, gx0 + i_e * px
    y_sb = R_AVDD_B[1] + 0.6                          # shield bottom, 0.6 um above the AVDD bridge
    j0 = -int(-(y_sb + 2.0 + 0.19 - gy0) // py)
    rows = {n: gy0 + (j0 + k) * py for k, n in enumerate(TUNNEL)}
    y_st = max(rows.values()) + 0.19 + 2.0
    xsh = (xs1 - 3.9, round(east - 0.03, 2))          # the shield over both straps and OTA1's AVSS strap
    assert xsh[0] - (xw + 0.19) > 0.6 and (xe - 0.19) - xsh[1] > 0.6
    pins, obs = {}, []
    h = 0.19
    for n, y in rows.items():
        a.box("metal2", xw - h, y - h, xe + h, y + h)
        for x, rn in ((xw, n + "_W"), (xe, n)):
            for via in ("via2", "via3"):
                a.box(via, x - 0.13, y - 0.13, x + 0.13, y + 0.13)
            for lay in ("metal3", "metal4"):
                a.box(lay, x - h, y - h, x + h, y + h)
                a.manual.append((lay, (x - h, y - h, x + h, y + h), rn))
            a.via3s.append((x - 0.13, y - 0.13, x + 0.13, y + 0.13))
            pins[rn] = [("metal4", x - h, y - h, x + h, y + h)]
    a.box("metal4", xsh[0], y_sb, xsh[1], y_st)
    xa = round(gx + 20.0 + 0.6, 2)                    # the strip: 0.6 um east of the AVDD bridge (power())
    a.box("metal4", xa, R_AVSS_B[0] + 1.0, xsh[1], y_sb + 1.0)
    a.vias("via4", xa, R_AVSS_B[0] + 1.0, xa + 1.8, R_AVSS_B[1] - 1.0)
    obs += [("metal4", (xsh[0] - 0.6, y_sb - 0.6, xsh[1] + 0.6, y_st + 0.6)),
            ("metal4", (xa - 0.6, R_AVSS_B[0] + 0.4, xsh[1] + 0.6, y_sb))]
    # XR1N's taps (Metal4, 1.4 um, two router rows each) from the straps to pads east of the gap
    jt = j0 + len(TUNNEL) + 15
    for n, xs, j in (("I1N_R", xs1, jt), ("O1P_R", xo1, jt + 5)):
        y1 = gy0 + j * py - h
        xp2 = xe + 2 * px + h
        a.wire("metal4", xs, y1, xp2, y1 + 1.4, n)
        a.vias("via4", xs, y1, xs + 5.0, y1 + 1.4)
        pins[n] = [("metal4", xe - h, y1, xp2, y1 + 1.4)]
    assert gy0 + jt * py - h - (y_st + 0.6) > 5.0
    # the gap: no router wire under the straps (the bias lines cross above rdac's top, as before)
    yb, yt = I["c1n"].bbox[3], rdac.bbox[3] - 10.0
    obs += [("metal4", (xs1 - 3.0, yb, ox, yt)), ("metal3", (gx + 0.6, yb, ox - 0.5, yt))]
    return pins, obs


def c1_extension(a, I):
    """C1's rest (eeg_c1x) on both sides, with Metal4 jumpers (Via4 at both ends) between
    the buses of a net: C1PX mirrored right under C1P, its TOP bus abutting C1P's (one I1P
    bus), the O1N jumper under them; C1NX above the bottom rails, the I1N and O1P jumpers
    under the rails (O1P also under both I1N buses)."""
    c1p, c1n = I["c1p"], I["c1n"]
    I["c1px"] = a.put("eeg_c1x", X_C1X, c1p.bbox[1], mirror=True, name="C1PX", nets={"TOP": "I1P", "BOT": "O1N"},
                      mim=True)
    I["c1nx"] = a.put("eeg_c1x", X_C1X, Y_C1NX, name="C1NX", nets={"TOP": "I1N", "BOT": "O1P"}, mim=True)
    for lo, hi, net, x in ((I["c1px"], c1p, "O1N", X_JUMP[0]), (c1n, I["c1nx"], "I1N", X_JUMP[0]),
                           (c1n, I["c1nx"], "O1P", X_JUMP[1])):
        b1, b2 = lo.pin(net, "metal5"), hi.pin(net, "metal5")
        a.wire("metal4", x, b1[2], x + 10.0, b2[4], net)
        a.vias("via4", x, b1[2], x + 10.0, b1[4])
        a.vias("via4", x, b2[2], x + 10.0, b2[4])


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
    # the quantizer's latch ground (r10, 11/9): its DVSS port, the Metal4 stub 2 um above
    # the DVDD port, onto the top AVSS rail. The quantizer's block LVS ties DVSS into AVSS
    # and renames its labels, so the port comes in as a Metal4 "AVSS" pin, and
    # strap_to_rail() takes the Metal3 straps only: through r9 the port stayed open. Via4
    # on the stub, a Metal5 run east of the block and a Metal5 strap down to the rail:
    # Metal5 only, so the router's view (Metal3 / Metal4) is the same as in r9.
    s = I["quant"].pin("AVSS", "metal4")
    assert abs(s[2] - q[4] - 2.0) < 0.1 and abs(s[3] - q[3]) < 0.1, f"quantizer: Metal4 AVSS pin {s} is not the latch port"
    xs = s[3] + 10.0
    a.via_stack("metal4", "metal5", s[1], s[2], s[3], s[4], "AVSS")
    a.wire("metal5", s[1], s[2], xs + 6.0, s[4], "AVSS")
    a.wire("metal5", xs, R_AVSS_T[0], xs + 6.0, s[4], "AVSS")
    # Metal4 pads under the rails for the router (small cells' supplies, DAC2)
    pads = {}
    # (the two on the bottom rails west of OTA1 moved with the band in r11: at 440 / 448 they
    # would sit in the rails' Metal4 bridge over the gap straps, on the O1P strap)
    for net, x, (y1, y2) in (("AVSS", 548.0, R_AVSS_T), ("AVDD", 556.0, R_AVDD_T), ("AVSS", 440.0 + DX_BAND, R_AVSS_B),
                             ("AVDD", 448.0 + DX_BAND, R_AVDD_B), ("AVSS", 1120.0, R_AVSS_B), ("AVDD", 1128.0, R_AVDD_B),
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
    j0 = round((Y_WPORT - gy0) / py)
    for k, n in enumerate(WEST_PORTS):          # r11: two router rows apart (eight through r10)
        y = gy0 + (j0 + 2 * k) * py
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
    h1 = a.load("eeg_c1a")[2][3]                     # the main C1 array's height (buses at y 0)
    I["c1p"] = a.put("eeg_c1a", 0.0, H - h1, name="C1P", nets={"TOP": "I1P", "BOT": "O1N"}, mim=True)
    I["c1n"] = a.put("eeg_c1a", 0.0, h1, mirror=True, name="C1N", nets={"TOP": "I1N", "BOT": "O1P"}, mim=True)
    c1_extension(a, I)
    I["rdac"] = a.put("adc_rdac", 4.0, Y_RDAC, name="RDAC", grid=GRID)
    I["ota1"] = a.put("gf180_inside_cascode_ota", 421.0 + DX_BAND, 494.2, name="OTA1", grid=GRID, nets={
        "INP": "I1P", "INN": "I1N", "OUTP": "O1P", "OUTN": "O1N", "VCMREF": "VCM", "VBN": "VBN1", "VNC": "VNC1",
        "VPC": "VPC1", "VBCM": "VBCM1", "VDD": "AVDD", "VSS": "AVSS"})
    I["ota2"] = a.put("gf180_ct_ota_tel16_cmfb", 868.0 + DX_BAND, 600.0, name="OTA2", grid=GRID, nets={
        "INP": "I2P", "INN": "I2N", "OUTP": "O2P", "OUTN": "O2N", "VCMREF": "VCM", "VBN": "VBN1", "VNC": "VNC1",
        "VPC": "VPC1", "VBCM": "VBCM1", "VDD": "AVDD", "VSS": "AVSS"})
    I["aclk"] = a.put("eeg_adc_clk", 880.0 + DX_BAND, 925.0, name="ACLK", grid=GRID, nets={"VDD": "AVDD", "VSS": "AVSS"})
    I["quant"] = a.put("eeg_quantizer", 560.0, 1042.0, name="Q", grid=GRID, nets={"INP": "O2P", "INN": "O2N"})
    I["dac2"] = a.put("eeg_dac2", 570.0, 262.0, name="DAC2", grid=GRID, nets=dict(
        {"OUTP": "I2P", "OUTN": "I2N", "VBPC": "VBPC2", "VBNC": "VBNC2", "VDD": "AVDD", "VSS": "AVSS"},
        **{f"SEL{k}": f"SEL2_{k}" for k in range(31)}))
    I["dig"] = a.put("eeg_adc_dig", 566.0, 0.0, name="DIG", nets=dict(
        {"RST_N": "ADC_RST_N", "VDD": "DVDD", "VSS": "DVSS"},
        **{f"SEL1[{k}]": f"SEL1_{k}" for k in range(31)}, **{f"SEL2[{k}]": f"SEL2_{k}" for k in range(31)},
        **{f"TH[{k}]": f"TH{k}" for k in range(31)}, **{f"CODE[{k}]": f"CODE{k}" for k in range(5)}))
    A.macro_pads(a, I["dig"])
    for n in TUNNEL:                     # r12: adc_rdac's side of the tunnelled lines (tunnel())
        I["rdac"].pins[n + "_W"] = I["rdac"].pins.pop(n)
    for k in ("rdac", "ota1", "ota2", "aclk", "dac2"):
        a.cover(I[k])
    for k in ("rdac", "ota1", "ota2", "aclk", "quant", "dig"):
        add(I[k])
    add(I["dac2"], power=())             # DAC2's supplies: small currents, through the router
    for n in ("I1P", "I1N", "O1P", "O1N"):
        nets.pop(n, None)

    # ---- small cells
    r21, tg, inv, zero, c2 = small_cells(a)
    cell_at(r21, 560.0 + DX_BAND, 983.0, "R21", {})
    cell_at(tg, 460.0 + DX_BAND, 968.0 + 6.0, "XR1P", {"A": "O1N", "B": "I1P", "G": "RST", "GN": "NRST",
                                                       "VDD": "AVDD", "VSS": "AVSS"})
    # (r12: XR1N's A / B on their own router nets, to the taps from the straps: tunnel())
    cell_at(tg, 440.0 + DX_BAND, 474.0, "XR1N", {"A": "O1P_R", "B": "I1N_R", "G": "RST", "GN": "NRST",
                                                 "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(inv, 500.0 + DX_BAND, 968.0 + 6.0, "XRSTB", {"A": "RST", "Y": "NRST", "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(zero, 345.0, 952.0, "XZERO", {"A": "INP", "B": "INN", "Z": "ADC_ZERO", "ZB": "ZB0",
                                          "VDD": "AVDD", "VSS": "AVSS"})
    for name, x, cmap in (("C2P", 868.0 + DX_BAND, {"TOP": "I2P", "BOT": "O2N"}),
                          ("C2N", 1002.5 + DX_BAND, {"TOP": "I2N", "BOT": "O2P"})):
        p = cell_at(c2, x, 800.0, name, cmap)
        k3, k4 = c2.keepout, c2.keepout4
        keep.append(((p.x + k3[0], p.y + k3[1], p.x + k3[2], p.y + k3[3]),
                     (p.x + k4[0], p.y + k4[1], p.x + k4[2], p.y + k4[3])))
    cell_at(tg, 1050.0 + DX_BAND, 760.0, "XR2P", {"A": "O2N", "B": "I2P", "G": "RST", "GN": "NRST",
                                                  "VDD": "AVDD", "VSS": "AVSS"})
    cell_at(tg, 1050.0 + DX_BAND, 730.0, "XR2N", {"A": "O2P", "B": "I2N", "G": "RST", "GN": "NRST",
                                                  "VDD": "AVDD", "VSS": "AVSS"})

    # ---- hand-drawn wiring and ports
    for n, pins in stage1(a, I).items():
        conn(n, pins)
    for n, pins in power(a, I).items():
        conn(n, pins)
    for n, pins in ports(a).items():
        conn(n, pins)
    tun_pins, tun_obs = tunnel(a, I)
    for n, pins in tun_pins.items():
        conn(n, pins)

    # ---- routing
    t0 = time.time()
    r = route.Router(GRID[0], GRID[2], W, H, px=GRID[1], py=GRID[3])
    a.obstacles(r)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    a.give(r)
    for lay, box in tun_obs:
        r.obstacle(lay, *box)
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

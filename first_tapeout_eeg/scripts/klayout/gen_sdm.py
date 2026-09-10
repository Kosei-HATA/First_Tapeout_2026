#!/usr/bin/env python3
"""
Batch layout generator for the CT 1st-order Sigma-Delta modulator
(subckt eeg_sdm1ct), sky130A.

    scripts/klayout/.venv/bin/python scripts/klayout/gen_sdm.py [CELL]

With no argument, builds GDSII/eeg_sdm1ct.gds (top cell eeg_sdm1ct).
With CELL = nand2|strongarm|ota_nc, builds just that cell into
GDSII/test_<CELL>.gds for standalone DRC/LVS debugging.

Blocks: eeg_fd_ota_full2_nc (non-chopped OTA: bias gen + core + CMFBs +
stage2, built here from gen_full2's verified builders), eeg_tg_lowq (DAC
switches, from the full2 GDS), eeg_strongarm (quantizer), eeg_nand2 (SR
latch), eeg_inv (NBIT1/BIT0 complement; BIT1/NBIT0 are plain wires).
The schematic's behavioral B-sources (BBIT1/BNBIT1/BBIT0/BNBIT0) become:
BIT1 = NBIT0 = BIT (wires), NBIT1 = BIT0 = BITB (one inverter).

All coordinates in um.  See klayout_common.py / README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import *
import gen_full2 as gf2
from gen_pga import build_inv, fet_anchors

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_GDS = os.path.join(PROJECT, "GDSII", "eeg_sdm1ct.gds")
FULL2_GDS = os.path.join(PROJECT, "GDSII", "eeg_fd_ota_chopped_full2.gds")


# ----------------------------------------------------------------------------
# auto tie helper: like Layouter.tie_ring but picks the tie column clear of
# the cell's own m2/via1 columns (gate straps, S/D straps crossing the band)
# ----------------------------------------------------------------------------
def busy_cols(lay, cell, tx, ty, y_lo, y_hi):
    """x-intervals of the placed cell's m2/via1/via2 shapes (RECURSIVE:
    includes nested FET subcells) overlapping y[y_lo, y_hi], expanded by
    half my column + min spacing (m2: 0.19+0.3, via1/via2: ~0.1+0.3)."""
    out = []
    for spec, ex in ((L_M2, 0.49), (L_VIA1, 0.38), (L_VIA2, 0.40)):
        it = cell.begin_shapes_rec(lay.layer(spec))
        while not it.at_end():
            b = it.shape().bbox()
            tr = it.trans()
            p0 = tr * kdb.Point(b.left, b.bottom)
            p1 = tr * kdb.Point(b.right, b.top)
            x0, x1 = min(p0.x, p1.x), max(p0.x, p1.x)
            yy0, yy1 = min(p0.y, p1.y), max(p0.y, p1.y)
            if ty + yy1 / 1000.0 >= y_lo and ty + yy0 / 1000.0 <= y_hi:
                out.append((tx + x0 / 1000.0 - ex, tx + x1 / 1000.0 + ex))
            it.next()
    return out


def ring_tap(lay, cell, tx, ty, xcol, into, side="bottom"):
    """mcon + m1 pad + via1 on a guard-ring band (tie_ring's mechanics,
    but the strap routing is left to the caller).  Returns the band center
    (yc for top/bottom, (xc, yc) for left/right)."""
    tap = kdb.Region(cell.begin_shapes_rec(lay.layer(L_TAP)))
    li = kdb.Region(cell.begin_shapes_rec(lay.layer(L_LI)))
    tb = tap.bbox()
    if side == "bottom":
        strip = kdb.Box(tb.left, tb.bottom, tb.right, tb.bottom + u(0.17))
    elif side == "top":
        strip = kdb.Box(tb.left, tb.top - u(0.17), tb.right, tb.top)
    elif side == "left":
        strip = kdb.Box(tb.left, tb.bottom, tb.left + u(0.17), tb.top)
    else:
        strip = kdb.Box(tb.right - u(0.17), tb.bottom, tb.right, tb.top)
    band = (li & (tap & kdb.Region(strip))).transformed(
        kdb.Trans(0, False, u(tx), u(ty)))
    if side in ("left", "right"):
        pieces = sorted(band.each(), key=lambda p: p.bbox().height(),
                        reverse=True)
        b = pieces[0].bbox()
        x0, x1 = b.left / 1000.0, b.right / 1000.0
        xc = (x0 + x1) / 2
        # tap near the band's TOP: at mid-height the tap pad collides with
        # the gate-bar m1 / strip via1s of the device
        yc = b.top / 1000.0 - 0.2
        lay.box(L_MCON, xc - 0.085, yc - 0.085, xc + 0.085, yc + 0.085, into)
        lay.box(L_M1, xc - 0.3, yc - 0.3, xc + 0.3, yc + 0.3, into)
        lay.via1(xc, yc, into)
        return xc, yc
    pieces = sorted(band.each(), key=lambda p: p.bbox().width(), reverse=True)
    b = pieces[0].bbox()
    y0, y1 = b.bottom / 1000.0, b.top / 1000.0
    yc = (y0 + y1) / 2
    lay.box(L_MCON, xcol - 0.085, yc - 0.085, xcol + 0.085, yc + 0.085, into)
    lay.box(L_M1, xcol - 0.3, y0 - 0.1, xcol + 0.3, y1 + 0.1, into)
    lay.via1(xcol, yc, into)
    return yc


def tie_auto(lay, cell, tx, ty, y_bus, into, side="bottom"):
    """tie_ring with the column picked clear of the cell's own straps AND
    of the routing already drawn into `into` (parent-level m2/via1/via2
    columns are invisible when scanning only the FET subcell)."""
    tap = kdb.Region(cell.begin_shapes_rec(lay.layer(L_TAP)))
    tb = tap.bbox()
    x0, x1 = tb.left / 1000.0 + tx + 0.4, tb.right / 1000.0 + tx - 0.4
    band_y = ty + (tb.bottom if side == "bottom" else tb.top) / 1000.0
    busy = busy_cols(lay, cell, tx, ty, min(band_y, y_bus) - 0.5,
                     max(band_y, y_bus) + 0.5)
    busy += busy_cols(lay, into, 0.0, 0.0, min(band_y, y_bus) - 0.5,
                      max(band_y, y_bus) + 0.5)
    x = x0
    while x <= x1:
        if all(x + 0.19 <= b0 or x - 0.19 >= b1 for b0, b1 in busy):
            break
        x += 0.05
    else:
        merged = []
        for b0, b1 in sorted(busy):
            if merged and b0 <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b1)
            else:
                merged.append([b0, b1])
        raise ValueError(f"no clear tie column in [{x0:.2f},{x1:.2f}] "
                         f"band_y={band_y:.2f} y_bus={y_bus:.2f} "
                         f"busy={[(round(a,2), round(b,2)) for a, b in merged]}")
    lay.tie_ring(cell, kdb.Trans(0, False, u(tx), u(ty)), side, y_bus,
                 (round(x / 0.05) * 0.05,), into=into)


# ----------------------------------------------------------------------------
# eeg_nand2: A B Y VDD18 VSS
#   XMN1 Y A N1 VSS nfet W=1 L=0.15 ; XMN2 N1 B VSS VSS
#   XMP1 Y A VDD18 pfet W=2 ; XMP2 Y B VDD18
# ----------------------------------------------------------------------------
def build_nand2(lay):
    mn1 = lay.make_nfet("nd_n1", 0.15, 1.0, 1)
    mn2 = lay.make_nfet("nd_n2", 0.15, 1.0, 1)
    mp1 = lay.make_pfet("nd_p1", 0.15, 2.0, 1)
    mp2 = lay.make_pfet("nd_p2", 0.15, 2.0, 1)
    c = lay.ly.create_cell("eeg_nand2")

    lay.place(mn1, 0.0, 0.0, into=c)
    lay.place(mn2, 3.4, 0.0, into=c)
    lay.place(mp1, 7.2, 0.0, into=c)
    lay.place(mp2, 11.0, 0.0, into=c)
    g = {"mn1": fet_anchors(lay, mn1, 0.0, 0.0),
         "mn2": fet_anchors(lay, mn2, 3.4, 0.0),
         "mp1": fet_anchors(lay, mp1, 7.2, 0.0),
         "mp2": fet_anchors(lay, mp2, 11.0, 0.0)}

    b1, b2 = mn1.bbox(), mp2.bbox()
    bot = min(b1.bottom, mn2.bbox().bottom, mp1.bbox().bottom,
              b2.bottom) / 1000.0
    top_ = max(b1.top, mn2.bbox().top, mp1.bbox().top, b2.top) / 1000.0
    right = 11.0 + b2.right / 1000.0

    Y_A, Y_B, Y_VSS = bot - 1.2, bot - 2.4, bot - 3.6
    Y_Y, Y_VDD = top_ + 1.2, top_ + 2.4
    XL, XR = -1.0, right + 1.0
    for y in (Y_A, Y_B, Y_VSS, Y_Y, Y_VDD):
        lay.bus_m3(XL, XR, y, cell=c)

    def gate_down(key, x_via, y_bus):
        x_pad, y_pad = g[key]["g"][0]
        lay.box(L_M1, min(x_pad, x_via) - 0.17, y_pad - 0.17,
                max(x_pad, x_via) + 0.17, y_pad + 0.17, c)
        lay.via1(x_via, y_pad, c)
        lay.box(L_M2, x_via - 0.19, y_bus - 0.15, x_via + 0.19, y_pad + 0.17, c)
        lay.via2(x_via, y_bus, c)

    # gate via columns go in the inter-device gaps (an offset via between
    # the 0.93-pitch strips cannot fit); the m1 jog at the pad level is
    # below the strips and clears them.
    gate_down("mn1", -0.5, Y_A)
    gate_down("mp1", 6.6, Y_A)
    gate_down("mn2", 2.9, Y_B)
    gate_down("mp2", 10.4, Y_B)

    # drains -> Y (up): mn1.s0, mp1.s0, mp2.s0 ; sources: mn2.s1 -> VSS (down),
    # mp1.s1/mp2.s1 -> VDD (up)
    lay.strap_up(*g["mn1"]["strips"][0], Y_Y, c)
    lay.strap_up(*g["mp1"]["strips"][0], Y_Y, c)
    lay.strap_up(*g["mp2"]["strips"][0], Y_Y, c)
    lay.strap_down(*g["mn2"]["strips"][1], Y_VSS, c)
    lay.strap_up(*g["mp1"]["strips"][1], Y_VDD, c)
    lay.strap_up(*g["mp2"]["strips"][1], Y_VDD, c)
    # N1: mn1.s1 -- mn2.s0 (m1 jumper between the adjacent strips)
    (ax, ay), (bx, by) = g["mn1"]["strips"][1], g["mn2"]["strips"][0]
    lay.box(L_M1, ax - 0.17, min(ay, by) - 0.17, bx + 0.17, max(ay, by) + 0.17, c)

    # ring ties: coincide with the same-net source straps (the tie's via2
    # lands exactly on the strap's via2 - same net, one legal via2).
    # mn1 has no VSS strap (its source is N1): pick a clear column.
    tie_auto(lay, mn1, 0.0, 0.0, Y_VSS, c)
    lay.tie_ring(mn2, kdb.Trans(0, False, u(3.4), 0), "bottom", Y_VSS,
                 (g["mn2"]["strips"][1][0],), into=c)
    lay.tie_ring(mp1, kdb.Trans(0, False, u(7.2), 0), "top", Y_VDD,
                 (g["mp1"]["strips"][1][0],), into=c)
    lay.tie_ring(mp2, kdb.Trans(0, False, u(11.0), 0), "top", Y_VDD,
                 (g["mp2"]["strips"][1][0],), into=c)

    for net, y in (("A", Y_A), ("B", Y_B), ("Y", Y_Y), ("VDD18", Y_VDD),
                   ("VSS", Y_VSS)):
        lay.label(L_M3L, net, XR - 0.5, y, c)
    anchors = {"A": (XR - 0.5, Y_A), "B": (XR - 0.5, Y_B), "Y": (XR - 0.5, Y_Y),
               "VDD18": (XR - 0.5, Y_VDD), "VSS": (XR - 0.5, Y_VSS)}
    return c, anchors


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# eeg_strongarm: INP INN OUTP OUTN CLK VDD18 VSS  (1-bit SDM quantizer)
#   M0 NTAIL CLK VSS VSS nfet L=0.15 W=8 (clocked tail)
#   M1 D1 INP NTAIL / M2 D2 INN NTAIL  nfet L=0.5 W=4 (input pair)
#   M3 OUTN OUTP D1 / M4 OUTP OUTN D2  nfet L=0.15 W=1 (n-latch)
#   M5 OUTP OUTN VDD / M6 OUTN OUTP VDD  pfet L=0.15 W=1 (p-latch)
#   M7 OUTP CLK VDD / M8 OUTN CLK VDD  pfet W=2 (output precharge)
#   M9 D1 CLK VDD / M10 D2 CLK VDD  pfet W=1 (drain precharge)
#
# make_nfet/make_pfet take W PER FINGER (extraction sums the fingers).
# Rows: M0 tail at the bottom; row A inputs (M1 offset 0.91 so its strap
# via2 comb coincides/clears M0's); row B n-latch + drain precharges; row C
# p-latch + output precharges.  Buses (m3): VSS/CLK below M0; INP/INN/NTAIL
# between M0 and row A; D1|D2 (split x spans) between rows A and B; OUTP/OUTN
# and VSS2 between rows B and C; VDD/CLK2 above row C.  VSS2 (n-latch ring
# ties) and CLK2 join the bottom buses via m2 links at the west end.
# Cross-coupled latch gates: M3/M5 west columns, M4/M6 east columns.
# via2 combs on shared buses were verified collision-free by hand; the
# via2_comb_check below asserts it (>=0.48 um center distance on the same
# bus, or exact coincidence).
# ----------------------------------------------------------------------------
def build_strongarm(lay):
    m0 = lay.make_nfet("sa_m0", 0.15, 2.0, 4)    # W=8 total
    m1 = lay.make_nfet("sa_m1", 0.5, 1.0, 4)     # W=4 total
    m3 = lay.make_nfet("sa_m3", 0.15, 0.5, 2)    # W=1 total
    m9 = lay.make_pfet("sa_m9", 0.15, 1.0, 1)    # W=1
    m5 = lay.make_pfet("sa_m5", 0.15, 0.5, 2)    # W=1 total
    m7 = lay.make_pfet("sa_m7", 0.15, 1.0, 2)    # W=2 total
    c = lay.ly.create_cell("eeg_strongarm")

    # ---- geometry -----------------------------------------------------------
    b0 = m0.bbox()
    lay.place(m0, 0.0, 0.0, into=c)
    g0 = fet_anchors(lay, m0, 0.0, 0.0)
    m0_top, m0_bot = b0.top / 1000.0, b0.bottom / 1000.0

    Y_VSS, Y_CLK = m0_bot - 1.2, m0_bot - 2.4
    Y_INP, Y_INN, Y_NTAIL = m0_top + 0.8, m0_top + 2.0, m0_top + 3.2
    XL = -3.2

    b1 = m1.bbox()
    Y_A = Y_NTAIL + 1.5
    Y_D = Y_A + b1.top / 1000.0 + 1.2
    b3 = m3.bbox()
    Y_B = Y_D + 1.5
    Y_OUTP = Y_B + b3.top / 1000.0 + 1.2
    Y_OUTN = Y_OUTP + 1.2
    Y_VSS2 = Y_OUTN + 1.2
    hp = max(b9.top for b9 in (m9.bbox(), m5.bbox(), m7.bbox())) / 1000.0
    Y_C = Y_VSS2 + 1.5
    Y_VDD = Y_C + hp + 1.2
    Y_CLK2 = Y_VDD + 1.2

    # row x positions (ring gap 1.0): via2-comb-verified against the
    # shared-bus via2 combs (see module comment)
    X_A1, X_A2 = 0.91, 11.5                        # M1 / M2 (row A)
    xb = [0.0, 7.5, 12.31, 17.38]                  # M3 M9 M10 M4 (row B)
    xc = [0.75, 4.99, 10.49, 17.42]                # M5 M7 M8 M6 (row C)
    XR = 20.84           # covers the right-side ties + M2's east descent
    x_clk = 9.05         # shared CLK gate column (M9|M10 and M7|M8 gaps)

    for y in (Y_VSS, Y_CLK, Y_INP, Y_INN, Y_NTAIL, Y_OUTP, Y_OUTN, Y_VSS2,
              Y_VDD, Y_CLK2):
        lay.bus_m3(XL, XR, y, cell=c)
    # D1 (left) / D2 (right) are different nets: separate x spans at Y_D
    D1_R = xb[1] + m9.bbox().right / 1000.0 + 0.3
    D2_L = max(xb[2] + m9.bbox().left / 1000.0 - 0.3, D1_R + 0.41)
    lay.bus_m3(XL, D1_R, Y_D, cell=c)
    lay.bus_m3(D2_L, XR, Y_D, cell=c)

    def gate_bar(ga, x_via, gy_key="g"):
        """m1 bar over all gate pads + jog to x_via + via1.  Returns gy."""
        gx = [p[0] for p in ga[gy_key]]
        gy = ga[gy_key][0][1]
        lay.box(L_M1, min(min(gx), x_via) - 0.17, gy - 0.17,
                max(max(gx), x_via) + 0.17, gy + 0.17, c)
        lay.via1(x_via, gy, c)
        return gy

    def m2_to_bus(x, y_bus, y_other):
        lay.box(L_M2, x - 0.19, min(y_bus, y_other) - 0.15, x + 0.19,
                max(y_bus, y_other) + 0.15, c)
        lay.via2(x, y_bus, c)   # via2 on the BUS end (m3 enclosure there)

    # ---- M0 tail: gates -> CLK, sources -> VSS, drains -> NTAIL -------------
    gx = [p[0] for p in g0["g"]]
    gy = gate_bar(g0, gx[0])
    m2_to_bus(gx[0], Y_CLK, gy)
    for i, (sx, sy) in enumerate(g0["strips"]):
        if i % 2 == 0:
            lay.strap_down(sx, sy, Y_VSS, c)
        else:
            lay.strap_up(sx, sy, Y_NTAIL, c)
    # ring tie: coincident with the first source strap (same net)
    lay.tie_ring(m0, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS,
                 (g0["strips"][0][0],), into=c)

    # ---- row A: M1/M2 input pair --------------------------------------------
    lay.place(m1, X_A1, Y_A, into=c)
    lay.place(m1, X_A2, Y_A, into=c)
    for xx, y_in in ((X_A1, Y_INP), (X_A2, Y_INN)):
        ga = fet_anchors(lay, m1, xx, Y_A)
        strips = ga["strips"]
        gy = gate_bar(ga, xx - 0.6)
        m2_to_bus(xx - 0.6, y_in, gy)
        for i, (sx, sy) in enumerate(strips):
            if i % 2 == 0:
                lay.strap_down(sx, sy, Y_NTAIL, c)
            else:
                lay.strap_up(sx, sy, Y_D, c)
        # ring tie to VSS: tap the ring's WEST/EAST side band and descend
        # OUTSIDE the strip field (it blocks every column)
        if xx < 4:
            xc_t, yc_t = ring_tap(lay, m1, xx, Y_A, 0.0, c, side="left")
            x_down = -1.35
        else:
            xc_t, yc_t = ring_tap(lay, m1, xx, Y_A, 0.0, c, side="right")
            x_down = XR - 0.6
        lay.box(L_M2, min(xc_t, x_down) - 0.19, yc_t - 0.15,
                max(xc_t, x_down) + 0.19, yc_t + 0.15, c)
        lay.box(L_M2, x_down - 0.19, Y_VSS - 0.15, x_down + 0.19,
                yc_t + 0.15, c)
        lay.via2(x_down, Y_VSS, c)

    # ---- row C: M5/M6 p-latch, M7/M8 output precharge ------------------------
    for dev, xx in ((m5, xc[0]), (m7, xc[1]), (m7, xc[2]), (m5, xc[3])):
        lay.place(dev, xx, Y_C, into=c)
    for k2, (xx, dev, y_out) in enumerate(((xc[0], m5, Y_OUTP),
                                           (xc[3], m5, Y_OUTN))):
        ga = fet_anchors(lay, dev, xx, Y_C)
        strips = ga["strips"]
        lay.strap_up(strips[0][0], strips[0][1], Y_VDD, c)
        lay.strap_up(strips[2][0], strips[2][1], Y_VDD, c)
        lay.strap_down(strips[1][0], strips[1][1], y_out, c)
        # ring tie to VDD: coincident with the source strap (same net)
        lay.tie_ring(dev, kdb.Trans(0, False, u(xx), u(Y_C)), "top", Y_VDD,
                     (strips[0][0],), into=c)
        # cross-coupled gate: M5 jogs WEST, M6 (rightmost) jogs EAST;
        # M5.G=OUTN, M6.G=OUTP (opposite bus from the drain!)
        y_g = Y_OUTN if k2 == 0 else Y_OUTP
        xg = xx - 1.2
        gy = gate_bar(ga, xg)
        m2_to_bus(xg, y_g, gy)
    for k2, xx in enumerate((xc[1], xc[2])):            # M7 / M8
        ga = fet_anchors(lay, m7, xx, Y_C)
        strips = ga["strips"]
        lay.strap_up(strips[0][0], strips[0][1], Y_VDD, c)
        lay.strap_up(strips[2][0], strips[2][1], Y_VDD, c)
        lay.strap_down(strips[1][0], strips[1][1], Y_OUTP if k2 == 0 else Y_OUTN, c)
        lay.tie_ring(m7, kdb.Trans(0, False, u(xx), u(Y_C)), "top", Y_VDD,
                     (strips[0][0],), into=c)
        gx = [p[0] for p in ga["g"]]
        gy = ga["g"][0][1]
        lay.box(L_M1, min(min(gx), x_clk) - 0.17, gy - 0.17,
                max(max(gx), x_clk) + 0.17, gy + 0.17, c)
        lay.via1(x_clk, gy, c)

    # ---- row B: M3/M4 n-latch, M9/M10 drain precharge -----------------------
    for dev, xx in ((m3, xb[0]), (m9, xb[1]), (m9, xb[2]), (m3, xb[3])):
        lay.place(dev, xx, Y_B, into=c)
    for k2, (xx, y_out) in enumerate(((xb[0], Y_OUTN), (xb[3], Y_OUTP))):
        ga = fet_anchors(lay, m3, xx, Y_B)
        strips = ga["strips"]
        lay.strap_down(strips[0][0], strips[0][1], Y_D, c)
        lay.strap_down(strips[2][0], strips[2][1], Y_D, c)
        lay.strap_up(strips[1][0], strips[1][1], y_out, c)
        # cross-coupled gate FIRST (the ring tie picks around it): M3 west,
        # M4 east; M3.G=OUTP / M4.G=OUTN (opposite bus from the drain!)
        y_g = Y_OUTP if k2 == 0 else Y_OUTN
        xg = xx - 0.6 if k2 == 0 else 14.85
        gy = gate_bar(ga, xg)
        m2_to_bus(xg, y_g, gy)   # note: m2 UP from the pad level
        # ring tie to VSS: tap the ring's RIGHT side band (the top band is
        # hemmed by the device's own straps), jog east at the band level,
        # then rise to the VSS2 bus
        xc_t, yc_t = ring_tap(lay, m3, xx, Y_B, 0.0, c, side="right")
        x_up = 4.0 if k2 == 0 else 18.9
        lay.box(L_M2, min(xc_t, x_up) - 0.19, yc_t - 0.15,
                max(xc_t, x_up) + 0.19, yc_t + 0.15, c)
        lay.box(L_M2, x_up - 0.19, yc_t - 0.15, x_up + 0.19,
                Y_VSS2 + 0.15, c)
        lay.via2(x_up, Y_VSS2, c)
    X_CLKB = 10.3        # row-B CLK pickup column (x_clk would hit M9's
                         # drain strap at 9.18; 10.3 clears it and M8's S1)
    for k2, xx in enumerate((xb[1], xb[2])):            # M9 / M10
        ga = fet_anchors(lay, m9, xx, Y_B)
        strips = ga["strips"]
        lay.strap_down(strips[1][0], strips[1][1], Y_D, c)   # D (D1/D2 half)
        lay.strap_up(strips[0][0], strips[0][1], Y_VDD, c)   # S
        # ring tie to VDD: tap the LEFT band and jog AWAY from the row-B
        # CLK column: M9 rises at 5.5 (coincident with M7's S strap/tie
        # column, same net), M10 rises on its own source strap column
        xc_t, yc_t = ring_tap(lay, m9, xx, Y_B, 0.0, c, side="left")
        x_up = 5.5 if k2 == 0 else xb[2] + 0.51
        lay.box(L_M2, min(xc_t, x_up) - 0.19, yc_t - 0.15,
                max(xc_t, x_up) + 0.19, yc_t + 0.15, c)
        lay.box(L_M2, x_up - 0.19, yc_t - 0.15, x_up + 0.19, Y_VDD + 0.15, c)
        lay.via2(x_up, Y_VDD, c)
        gx, gy = ga["g"][0]
        lay.box(L_M1, min(gx, X_CLKB) - 0.17, gy - 0.17,
                max(gx, X_CLKB) + 0.17, gy + 0.17, c)
        lay.via1(X_CLKB, gy, c)
    # CLK gate columns: row B rises at X_CLKB, row C at x_clk; both join CLK2
    gyb = fet_anchors(lay, m9, xb[1], Y_B)["g"][0][1]
    gyc = fet_anchors(lay, m7, xc[1], Y_C)["g"][0][1]
    lay.box(L_M2, X_CLKB - 0.19, gyb - 0.17, X_CLKB + 0.19, Y_CLK2 + 0.15, c)
    lay.via2(X_CLKB, Y_CLK2, c)
    lay.box(L_M2, x_clk - 0.19, gyc - 0.17, x_clk + 0.19, Y_CLK2 + 0.15, c)
    lay.via2(x_clk, Y_CLK2, c)

    # ---- bus links at the west end -------------------------------------------
    lay.join_m3_m2(-2.9, Y_VSS, Y_VSS2, c)
    lay.join_m3_m2(-2.2, Y_CLK, Y_CLK2, c)

    for net, y in (("INP", Y_INP), ("INN", Y_INN), ("CLK", Y_CLK),
                   ("VSS", Y_VSS), ("OUTP", Y_OUTP), ("OUTN", Y_OUTN),
                   ("VDD18", Y_VDD)):
        lay.label(L_M3L, net, XR - 0.5, y, c)
    anchors = {"INP": (XR - 0.5, Y_INP), "INN": (XR - 0.5, Y_INN),
               "OUTP": (XR - 0.5, Y_OUTP), "OUTN": (XR - 0.5, Y_OUTN),
               "CLK": (XR - 0.5, Y_CLK), "VDD18": (XR - 0.5, Y_VDD),
               "VSS": (XR - 0.5, Y_VSS)}
    return c, anchors


# ----------------------------------------------------------------------------
# eeg_fd_ota_full2_nc: full2 minus both choppers (bias + core + CMFBs +
# stage2).  Floorplan and trunk routes are gen_full2.build_top's, verbatim,
# minus the chopper/clock parts; core.OUTP/OUTN wire straight to stage2's
# N2P/N2N buses (N1P/N1N).  Ref: ota_nc_ref.spice.
# ----------------------------------------------------------------------------
def build_ota_nc(lay):
    cm1, cm1_a = gf2.build_cmfb(lay, 4.0, "eeg_cmfb_amp_dl2")
    cm2, cm2_a = gf2.build_cmfb(lay, 0.5, "eeg_cmfb_amp_dl2_s2")
    bg, bg_a = gf2.build_bias(lay)
    st2, st2_a = gf2.build_stage2(lay)
    lay.ly.read(gf2.CORE_GDS)     # merge the verified core
    core = lay.ly.cell("eeg_fd_ota_core_soft")

    top = lay.ly.create_cell("eeg_fd_ota_full2_nc")
    P = {"core": (0.0, 0.0), "cm1": (150.0, 54.0), "cm2": (700.0, 54.0),
         "st2": (430.0, -25.0), "bg": (900.0, 0.0)}
    lay.place(core, *P["core"], into=top)
    lay.place(cm1, *P["cm1"], into=top)
    lay.place(cm2, *P["cm2"], into=top)
    lay.place(st2, *P["st2"], into=top)
    lay.place(bg, *P["bg"], into=top)

    XF2 = 430.0 + st2_a["N2P"][0]      # stage2 bus end x (abs)
    XBUS_BG = 900.0 + bg_a["VSS"][0]   # bias bus end x (abs)

    def h3(y, x0, x1): lay.box(L_M3, x0, y - 0.3, x1, y + 0.3, top)
    def v3m(x, y0, y1): lay.box(L_M3, x - 0.3, y0, x + 0.3, y1, top)
    def h4(y, x0, x1): lay.box(L_M4, x0, y - 0.3, x1, y + 0.3, top)
    def v4m(x, y0, y1): lay.box(L_M4, x - 0.3, y0, x + 0.3, y1, top)
    def pad3(x, y): lay.box(L_M3, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)
    def pad4(x, y): lay.box(L_M4, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)
    def via3(x, y):
        pad3(x, y)
        lay.via3(x, y, top)
        pad4(x, y)

    # ---- input pins: labels on the core's INP/INN rails ---------------------
    lay.label(L_M3L, "INP", 103.0, 15.9, top)
    lay.label(L_M3L, "INN", 100.0, 14.6, top)

    # ---- N1P/N1N: core outputs -> stage2 N2P/N2N buses ----------------------
    # No chopper in between.  The hops MUST run at y=45/43.5 (full2's
    # verified lanes): lower lanes cross XCM1's VSS drop (m4 x=162.5,
    # y-12.15..38.3) -> N1x/VSS merge.  The m3 drops at 426.2/425.2 are
    # full2's verified geometry (0.4 clear of stage2's bus starts at 428).
    pad3(-110.0, 13.3); via3(-110.0, 13.3)
    h4(13.3, -110.0, -109.0); v4m(-109.0, 13.3, 45.0)
    h4(45.0, -110.0, 426.2)
    via3(426.2, 45.0); v3m(426.2, -28.5, 45.3); h3(-28.5, 425.9, 430.0)
    pad3(110.0, 12.0); via3(110.0, 12.0)
    v4m(110.0, 12.0, 43.5)
    h4(43.5, 110.0, 425.2)
    via3(425.2, 43.5); v3m(425.2, -29.7, 43.8); h3(-29.7, 424.9, 430.0)

    # ---- VDD18 trunk (m4 y=70) -------------------------------------------
    h4(70.0, -5.3, 984.8)
    pad3(0.0, 31.9); via3(0.0, 31.9); v4m(0.0, 31.9, 40.0)
    via3(0.0, 40.0); pad3(0.0, 40.0); h3(40.0, -3.0, 0.3)
    v3m(-3.0, 40.0, 70.3); via3(-3.0, 70.0)
    v3m(161.8, 70.0, 71.3); via3(161.8, 70.0)
    v3m(711.8, 70.0, 71.3); via3(711.8, 70.0)
    pad3(XF2, 2.6); via3(XF2, 2.6); v4m(XF2, 2.6, 30.0)
    via3(XF2, 30.0); pad3(XF2, 30.0); v3m(XF2, 30.0, 70.3); via3(XF2, 70.0)
    pad3(984.5, 13.5); v3m(984.5, 13.5, 70.3); via3(984.5, 70.0)
    lay.label(L_M4L, "VDD18", 400.0, 70.0, top)

    # ---- VSS trunk (m4 y=-12) --------------------------------------------
    h4(-12.0, -2.3, XBUS_BG)
    pad3(0.0, -6.1); via3(0.0, -6.1); v4m(0.0, -12.15, -6.1)
    pad3(162.5, 38.3); via3(162.5, 38.3); v4m(162.5, -12.15, 38.3)
    pad3(712.5, 38.3); via3(712.5, 38.3); v4m(712.5, -12.15, 38.3)
    pad3(XF2, -30.9); via3(XF2, -30.9); v4m(XF2, -30.9, -11.85)
    pad3(XBUS_BG, -3.5); via3(XBUS_BG, -3.5); v4m(XBUS_BG, -12.15, -3.5)
    lay.label(L_M4L, "VSS", 400.0, -12.0, top)

    # ---- VBN trunk (m4 y=72) ----------------------------------------------
    h4(72.0, 147.8, 1070.3)
    lay.box(L_M1, -0.3, -14.665, 0.3, -14.065, top)
    lay.via1(0.0, -14.365, top)
    lay.box(L_M2, -0.19, -16.15, 0.19, -14.2, top)
    lay.via2(0.0, -16.0, top)
    pad3(0.0, -16.0); via3(0.0, -16.0)
    v4m(0.0, -17.0, -15.85); h4(-17.0, -0.3, 460.0)
    v4m(460.0, -17.0, -14.0); via3(460.0, -14.0); pad3(460.0, -14.0)
    v3m(460.0, -14.0, -10.0); via3(460.0, -10.0); pad3(460.0, -10.0)
    v4m(460.0, -10.0, 37.0); via3(460.0, 37.0); pad3(460.0, 37.0)
    v3m(460.0, 37.0, 72.3); via3(460.0, 72.0)
    h3(39.5, 147.5, 149.8); v3m(147.8, 39.5, 72.3); via3(147.8, 72.0)
    h3(39.5, 697.5, 699.8); v3m(697.8, 39.5, 72.3); via3(697.8, 72.0)
    pad3(XBUS_BG, 6.8); via3(XBUS_BG, 6.8)
    h4(6.8, XBUS_BG, 1070.0); v4m(1070.0, 6.8, 72.3)

    # ---- VCM_REF trunk (m4 y=74) -------------------------------------------
    h4(74.0, 3.0, 855.3)
    pad3(0.0, 35.25); h3(35.25, 0.0, 3.3)
    via3(3.0, 35.25); pad3(3.0, 35.25); v4m(3.0, 35.25, 37.0)
    via3(3.0, 37.0); pad3(3.0, 37.0); v3m(3.0, 37.0, 74.3); via3(3.0, 74.0)
    h3(49.8, 159.5, 164.5); v3m(164.2, 49.8, 74.3); via3(164.2, 74.0)
    h3(49.8, 709.47, 714.5); v3m(714.2, 49.8, 74.3); via3(714.2, 74.0)
    # stage2 VCM_REF: drop EAST of the VBP2 descent (x=855 vs 850) so the
    # m3 drop cannot cross the VBP2 h3 at y=1.4
    h3(-2.0, 844.7, 855.3); v3m(855.0, -2.0, 74.3); via3(855.0, 74.0)
    lay.label(L_M4L, "VCM_REF", 600.0, 74.0, top)

    # ---- VCM1: core.VCM_SENSE (0,33.65) -> XCM1.VCM_SENSE -----------------
    pad3(0.0, 33.65); h3(33.65, -6.3, 0.3)
    via3(-6.0, 33.65); pad3(-6.0, 33.65); v4m(-6.0, 33.65, 37.0)
    via3(-6.0, 37.0); pad3(-6.0, 37.0); v3m(-6.0, 37.0, 60.3)
    via3(-6.0, 60.0); h4(60.0, -6.0, 152.5)
    v4m(152.5, 50.8, 60.0); via3(152.5, 50.8)

    # ---- VCM2: XCM2.VCM_SENSE -> stage2.VCM2 (m4 drop straight down) ------
    pad3(703.77, 50.8); via3(703.77, 50.8)
    v4m(703.77, -3.15, 50.8); via3(703.77, -3.0)

    # ---- VBP1: XCM1.VBP -> core.VBP (0,21.36 m1) ---------------------------
    lay.box(L_M1, -0.3, 21.06, 0.3, 21.66, top)
    lay.via1(0.0, 21.36, top)
    lay.box(L_M2, -0.19, 21.19, 0.19, 24.15, top)
    lay.via2(0.0, 24.0, top)
    pad3(0.0, 24.0); h3(24.0, 0.0, 6.3)
    via3(6.0, 24.0); pad3(6.0, 24.0); v4m(6.0, 24.0, 37.0)
    via3(6.0, 37.0); pad3(6.0, 37.0); v3m(6.0, 37.0, 78.3)
    via3(6.0, 78.0); h4(78.0, 6.0, 161.8)
    via3(161.8, 78.0); v3m(161.8, 72.2, 78.3)

    # ---- VBP2: XCM2.VBP -> stage2.VBP2 (east hop y76, descend x=850) -------
    pad3(711.8, 72.2); v3m(711.8, 72.2, 76.3); via3(711.8, 76.0)
    h4(76.0, 711.8, 850.0)
    via3(850.0, 76.0); pad3(850.0, 76.0); v3m(850.0, 1.4, 76.3)
    h3(1.4, XF2, 850.3)

    # ---- output pins --------------------------------------------------------
    lay.label(L_M3L, "OUTP", 430.0 + st2_a["OUTP"][0],
              -25.0 + st2_a["OUTP"][1], top)
    lay.label(L_M3L, "OUTN", 430.0 + st2_a["OUTN"][0],
              -25.0 + st2_a["OUTN"][1], top)

    return top


# ----------------------------------------------------------------------------
# eeg_sdm1ct top assembly.
#
# Floorplan (abs um):  OTA (ota_nc) at (350,1400) — its cell spans x
# 51.5..1810, y 49.8..1478.  Region A (x 20..340, y 40..1380, west of the
# OTA's core/stage2, open floor) holds all passives + the DAC/digital
# cluster.  Channel plan (all verified against DRC + tracer):
#   - supply verticals at the west edge: VSS m3 x=22, VDD18 m3 x=25, fed from
#     the OTA trunks (VSS: via3 at (348,1388) -> m3 lane y1382; VDD18: m4
#     lane y1470 -> v4m x=25).
#   - INP/INN: via3 on the core's input rails, m4 lanes y1409.5/1410.5 west,
#     m4 verticals x=30/27 south; taps via via3->m3->via2->m2 jogs.
#   - OINTP/OINTN: m3 lanes y1399/1400.2 across the core's top (the core has
#     NO m4/via3 and no m3 in local y -1.5..1.5 — probed); drops at x=38/190
#     to the RF/CI banks; strongarm feeds at x=200.5..206.8 (OINTP crosses
#     OINTN's drop on an m4 hop).
#   - The strongarm's west lanes (CLK/VSS/QP/QN/VDD18) must dodge the QP/QN
#     verticals (x=42/45): VSS/CLK/VDD18 lanes start at x=46.5+ and bridge
#     the verticals on m2 dives; QP/QN rise east of the cell to y1364/1365.2
#     lanes (interleaved: QP rises at 175 to the HIGHER lane, QN at 174).
# ----------------------------------------------------------------------------
def build_sdm(lay):
    tg, tg_a = gf2.build_tg(lay)
    nd, nd_a = build_nand2(lay)        # one cell, two instances
    inv, inv_a = build_inv(lay)
    cmp_, cmp_a = build_strongarm(lay)
    ota = build_ota_nc(lay)

    top = lay.ly.create_cell("eeg_sdm1ct")
    lay.place(ota, 350.0, 1400.0, into=top)

    def h3(y, x0, x1): lay.box(L_M3, x0, y - 0.3, x1, y + 0.3, top)
    def v3m(x, y0, y1): lay.box(L_M3, x - 0.3, y0, x + 0.3, y1, top)
    def h4(y, x0, x1): lay.box(L_M4, x0, y - 0.3, x1, y + 0.3, top)
    def v4m(x, y0, y1): lay.box(L_M4, x - 0.3, y0, x + 0.3, y1, top)
    def pad3(x, y): lay.box(L_M3, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)
    def pad4(x, y): lay.box(L_M4, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)
    def via3(x, y):
        pad3(x, y)
        lay.via3(x, y, top)
        pad4(x, y)

    # ---- passives ------------------------------------------------------------
    seg100 = lay.make_res_seg(34.38)               # 100k per segment
    rfp_a, rfp_b = lay.res_bank(top, 45.0, 60.0, 1000, seg100, ncols=40)
    rfn_a, rfn_b = lay.res_bank(top, 165.0, 60.0, 1000, seg100, ncols=40)
    rinp_a, rinp_b = lay.res_bank(top, 280.0, 100.0, 5, seg100)
    rinn_a, rinn_b = lay.res_bank(top, 280.0, 180.0, 5, seg100)
    rdacp_a, rdacp_b = lay.res_bank(top, 280.0, 260.0, 5, seg100)
    rdacn_a, rdacn_b = lay.res_bank(top, 280.0, 340.0, 5, seg100)
    cip_bot, cip_top, _, _ = lay.mim_array(top, 300.0, 1250.0, 5, 5, 20.0, 20.0)
    cin_bot, cin_top, _, _ = lay.mim_array(top, 420.0, 1250.0, 5, 5, 20.0, 20.0)
    cqn_bot, cqn_top, _, _ = lay.mim_array(top, 60.0, 1145.0, 2, 1, 20.0, 12.5)
    cqp_bot, cqp_top, _, _ = lay.mim_array(top, 110.0, 1165.0, 2, 1, 20.0, 12.5)

    # ---- digital / comparator cluster ----------------------------------------
    P_TG, N_TG = 430.0, 390.0
    lay.place(tg, 270.0, P_TG, into=top)           # XREFP1
    lay.place(tg, 300.0, P_TG, into=top)           # XREFP0
    lay.place(tg, 270.0, N_TG, into=top)           # XREFN1
    lay.place(tg, 300.0, N_TG, into=top)           # XREFN0
    CMPX, CMPY = 150.0, 1340.0
    lay.place(cmp_, CMPX, CMPY, into=top)
    lay.place(nd, 150.0, 1190.0, into=top)         # XND1
    lay.place(nd, 194.0, 1205.0, into=top)         # XND2 (east: clears the
                                                 # OINTP vertical at x=247)
    INVX, INVY = 208.0, 1183.1
    lay.place(inv, INVX, INVY, into=top)           # XINV
    # nand2 bus geometry (from anchors: pins sit at XR-0.5, buses span -1..XR)
    nd1_xr = 150.0 + nd_a["A"][0] + 0.5
    nd1_ya, nd1_yb = 1190.0 + nd_a["A"][1], 1190.0 + nd_a["B"][1]
    nd1_yy, nd1_yvdd = 1190.0 + nd_a["Y"][1], 1190.0 + nd_a["VDD18"][1]
    nd1_yvss = 1190.0 + nd_a["VSS"][1]
    nd2_xr = 194.0 + nd_a["A"][0] + 0.5
    nd2_ya, nd2_yb = 1205.0 + nd_a["A"][1], 1205.0 + nd_a["B"][1]
    nd2_yy, nd2_yvdd = 1205.0 + nd_a["Y"][1], 1205.0 + nd_a["VDD18"][1]
    nd2_yvss = 1205.0 + nd_a["VSS"][1]
    inv_xr = INVX + inv_a["A"][0] + 0.5
    inv_ya, inv_yy = INVY + inv_a["A"][1], INVY + inv_a["Y"][1]
    inv_yvdd, inv_yvss = INVY + inv_a["VDD18"][1], INVY + inv_a["VSS"][1]
    # strongarm bus y (abs); buses span CMPX-3.2 .. CMPX+20.84
    sa = {k: CMPY + v[1] for k, v in cmp_a.items()}
    SA_XL, SA_XR = CMPX - 3.2, CMPX + 20.84

    # ---- supply feeds into region A ------------------------------------------
    # VSS: trunk (m4 y1388) -> via3 -> m2 lane west (the core's floor is
    # shape-free at local y -14.5..-10.5 = abs 1385.5..1389.5 — probed) ->
    # via2 -> the west vertical.  m2 crosses the m3 signal verticals freely.
    via3(348.0, 1388.0)
    lay.box(L_M3, 346.5, 1387.7, 348.3, 1388.3, top)
    lay.via2(346.8, 1388.0, top)
    lay.box(L_M2, 22.31, 1387.85, 346.99, 1388.15, top)
    lay.via2(22.5, 1388.0, top)
    lay.box(L_M3, 21.7, 1387.7, 23.2, 1388.3, top)
    v3m(22.0, 385.4, 1388.3)                     # VSS vertical (m3)
    # VDD18: trunk (m4 y1470) -> m4 lane west -> v4m x=25 -> via3 -> vertical
    h4(1470.0, 24.7, 345.0)
    v4m(25.0, 1361.44, 1470.0)
    v3m(25.0, 384.2, 1361.74)                    # VDD18 vertical (m3)

    # ---- strongarm west lanes (buses span SA_XL..SA_XR) -----------------------
    # QP/QN: stubs east of the cell, rises, high lanes; the verticals are M2
    # (they cross the nand/inv supply lanes, the VSS/CLK lanes and the CQ top
    # jogs — m2 is free over all of them), via2-ing onto the lanes.
    h3(sa["OUTP"], SA_XR - 0.3, 175.3); v3m(175.0, sa["OUTP"], 1365.5)
    h3(1365.2, 52.7, 175.3)
    lay.box(L_M2, 52.81, 1166.3, 53.19, 1365.55, top)      # QP vertical (m2)
    lay.via2(53.0, 1365.2, top)
    h3(sa["OUTN"], SA_XR - 0.3, 174.3); v3m(174.0, sa["OUTN"], 1364.3)
    h3(1364.0, 50.7, 174.3)
    lay.box(L_M2, 50.81, 1146.3, 51.19, 1364.2, top)       # QN vertical (m2)
    lay.via2(51.0, 1364.0, top)
    # VDD18: lane east of the QP/QN verticals + m2 dive to the x=25 vertical
    h3(sa["VDD18"], 47.7, SA_XL + 0.4)
    lay.box(L_M2, 26.01, sa["VDD18"] - 0.15, 48.19, sa["VDD18"] + 0.15, top)
    lay.via2(48.0, sa["VDD18"], top)
    lay.box(L_M3, 24.7, sa["VDD18"] - 0.3, 26.8, sa["VDD18"] + 0.3, top)
    lay.via2(26.2, sa["VDD18"], top)
    via3(25.0, sa["VDD18"])
    # VSS: lane + m2 dive to the x=22 vertical (pad3 must NOT reach the
    # VDD18 vertical at 24.7..25.3!)
    h3(sa["VSS"], 46.5, SA_XL + 0.4)
    lay.box(L_M2, 22.61, sa["VSS"] - 0.15, 48.19, sa["VSS"] + 0.15, top)
    lay.via2(48.0, sa["VSS"], top)
    lay.box(L_M3, 21.7, sa["VSS"] - 0.3, 23.5, sa["VSS"] + 0.3, top)
    lay.via2(22.8, sa["VSS"], top)
    # CLK: lane + m2 dive to the pin stub
    h3(sa["CLK"], 46.5, SA_XL + 0.4)
    lay.box(L_M2, 29.81, sa["CLK"] - 0.15, 48.19, sa["CLK"] + 0.15, top)
    lay.via2(48.0, sa["CLK"], top)
    pad3(30.0, sa["CLK"])
    lay.box(L_M3, 30.0, sa["CLK"] - 0.3, 30.6, sa["CLK"] + 0.3, top)
    lay.via2(30.0, sa["CLK"], top)
    lay.label(L_M3L, "CLK", 30.0, sa["CLK"], top)
    # NCLK: no-connect pin stub (west end must clear the OINTN drop at 37.7)
    h3(sa["CLK"] - 2.0, 30.0, 36.5)
    lay.label(L_M3L, "NCLK", 33.0, sa["CLK"] - 2.0, top)

    # ---- INP/INN: core rails -> m4 lanes -> west verticals --------------------
    via3(453.0, 1415.9)                          # core INP rail
    v4m(453.0, 1409.5, 1415.9)
    h4(1409.5, 29.7, 453.3)
    v4m(30.0, 78.3, 1409.5)                      # INP vertical (m4)
    via3(450.0, 1414.6)                          # core INN rail
    v4m(450.0, 1410.5, 1414.6)
    h4(1410.5, 26.7, 450.3)
    v4m(27.0, 76.5, 1410.5)                      # INN vertical (m4)

    def tap_m2(xv, yj, x_to, y_to=None):
        """m4 vertical at xv -> via3 -> m3 pad -> via2 -> m2 jog -> via1 at
        (x_to, y_to or yj) onto an m1 pad."""
        yt = yj if y_to is None else y_to
        via3(xv, yj)
        lay.box(L_M3, xv - 0.3, yj - 0.3, xv + 1.5, yj + 0.3, top)
        lay.via2(xv + 1.2, yj, top)
        lay.box(L_M2, xv + 1.01, yj - 0.2, x_to + 0.19, yj + 0.2, top)
        if yt != yj:
            lay.box(L_M2, x_to - 0.19, min(yj, yt) - 0.2, x_to + 0.19,
                    max(yj, yt) + 0.2, top)
        lay.via1(x_to, yt, top)

    # INP taps: RFP.a (45,78.27), RINP.b (288,81.73 — the serpentine's END
    # pad; the returned B terminal is mid-chain for even last-k!), RDACP.a
    tap_m2(30.0, 78.3, rfp_a[0], rfp_a[1])
    tap_m2(30.0, 118.3, 288.0, 81.73)
    tap_m2(30.0, 278.3, rdacp_a[0], rdacp_a[1])
    # INN taps: RFN.a (165,78.27) via y76.5 jog, RINN.b (288,161.73), RDACN.a
    tap_m2(27.0, 76.5, rfn_a[0], rfn_a[1])
    tap_m2(27.0, 198.3, 288.0, 161.73)
    tap_m2(27.0, 358.3, rdacn_a[0], rdacn_a[1])

    # VINP/VINN pin stubs on RINP.a / RINN.a (via1 clear of the INP/INN jogs)
    for (ax, ay), net in ((rinp_a, "VINP"), (rinn_a, "VINN")):
        lay.via1(ax, ay - 0.67, top)
        lay.box(L_M2, 275.81, ay - 0.82, ax + 0.19, ay - 0.52, top)
        lay.via2(276.0, ay - 0.67, top)
        pad3(276.0, ay - 0.67)
        lay.label(L_M3L, net, 276.0, ay - 0.67, top)

    # ---- OINTP/OINTN lanes + region-A drops ----------------------------------
    # The lanes hop the ota_nc's N1 drops (m3 at abs x 774.9..776.5, spanning
    # y 1370.3..1445.3) on m4; they merge the stage2's OUTP/OUTN buses (abs
    # 778..1100.3 / 778..1150.3).
    h3(1399.0, 45.0, 774.55)
    via3(774.25, 1399.0)
    h4(1399.0, 774.25, 777.75)
    via3(777.75, 1399.0)
    h3(1399.0, 777.45, 1100.6)                   # OINTP lane (joins OUTP bus)
    h3(1400.2, 38.0, 774.3)
    via3(774.0, 1400.2)
    h4(1400.2, 774.0, 778.0)
    via3(778.0, 1400.2)
    h3(1400.2, 777.7, 1150.6)                    # OINTN lane (joins OUTN bus)
    lay.label(L_M3L, "OINTP", 46.0, 1399.0, top)
    lay.label(L_M3L, "OINTN", 39.0, 1400.2, top)
    # OINTN: drop at x=38: m3 above/below the nand-lane band, m2 through it
    # (1177.6..1210.6).  RFP.b lane at y1143.5 ducks the OINTP drop on m2.
    # CIP's bottom sheet is fed on M4 (free over the m2/m3 lanes; the lane
    # ends west of CIP's m4 top plate).
    v3m(38.0, 1143.5, 1176.7)
    lay.via2(38.0, 1176.5, top)
    lay.box(L_M2, 37.81, 1176.3, 38.19, 1213.4, top)
    lay.via2(38.0, 1213.2, top)
    v3m(38.0, 1213.0, 1400.5)
    h3(1143.5, 37.7, 49.0)
    lay.via2(48.7, 1143.5, top)
    lay.box(L_M2, 48.51, 1143.35, 51.39, 1143.65, top)
    lay.via2(51.2, 1143.5, top)
    h3(1143.5, 50.9, 123.3)
    lay.strap_up(rfp_b[0], rfp_b[1], 1143.5, top)
    lay.box(L_M3, 295.5, 1249.7, 300.1, 1253.3, top)   # CIP bottom junction
    via3(38.0, 1251.5)
    h4(1251.5, 37.7, 297.8)
    via3(297.5, 1251.5)
    # OINTP: drop at x=50 (m3 below the nand band, m2 through it, m3 above).
    # RFN.b lane at y1142.5; CIN's bottom sheet fed on m2 at y1138.5 (below
    # the RF strap columns) + riser at x=240.5 into the RFN.b lane.
    v3m(50.0, 1142.5, 1176.7)
    lay.via2(50.0, 1176.5, top)
    lay.box(L_M2, 49.81, 1176.3, 50.19, 1212.2, top)
    lay.via2(50.0, 1212.0, top)
    # the drop's top crosses the VSS/CLK/VDD18/QP/QN lane band on m4:
    v3m(50.0, 1211.8, 1335.5)
    via3(50.0, 1335.5)
    lay.box(L_M4, 49.7, 1335.3, 50.3, 1399.35, top)
    via3(50.0, 1399.0)
    h3(1142.5, 49.7, 417.8)
    lay.strap_up(rfn_b[0], rfn_b[1], 1142.5, top)
    lay.box(L_M3, 415.5, 1249.7, 420.1, 1254.0, top)   # CIN bottom junction
    lay.via2(417.5, 1142.5, top)
    lay.box(L_M2, 417.31, 1142.3, 417.69, 1253.9, top)
    lay.via2(417.5, 1253.7, top)
    # OINTx -> strongarm INP/INN (east side): the OINTN drop tops out BELOW
    # the OINTP lane and hops it + the OINTP m4 hop on m4 via a west detour;
    # OINTP hops the OINTN drop's m3 part on m4 (the drop tops at 1397.5).
    v3m(203.0, sa["INN"] + 0.135, 1397.5)
    h3(sa["INN"], SA_XR - 0.3, 203.3)
    h3(1397.5, 199.2, 203.3)
    via3(199.2, 1397.5)
    lay.box(L_M4, 198.9, 1397.3, 199.5, 1400.55, top)
    via3(199.2, 1400.2)
    via3(200.5, 1399.0)
    h4(1399.0, 200.5, 206.5)
    via3(206.5, 1399.0)
    v3m(206.5, sa["INP"] + 0.3, 1398.7)
    h3(sa["INP"], SA_XR - 0.3, 206.8)

    # ---- CI top plates: INP (CIP, tab xm=355) / INN (CIN, tab xm=475) --------
    # via3 on the tab (pad4 fully inside), m2 hop north to the clean corridor
    # (y1368/1368.8: above the strongarm + QP/QN lanes + their via2s, below
    # the core's south bus stack at 1393.6), then m2 west to the verticals.
    lay.box(L_M3, 354.7, 1360.65, 356.8, 1361.25, top)
    via3(355.0, 1360.95)
    lay.via2(356.3, 1360.95, top)
    lay.box(L_M2, 356.11, 1360.8, 356.49, 1368.35, top)
    lay.box(L_M2, 31.01, 1367.85, 356.49, 1368.15, top)      # INP jog
    via3(30.0, 1368.0)
    lay.box(L_M3, 29.7, 1367.7, 31.5, 1368.3, top)
    lay.via2(31.2, 1368.0, top)
    lay.box(L_M3, 474.7, 1360.95, 476.8, 1361.55, top)
    via3(475.0, 1361.25)
    lay.via2(476.3, 1361.25, top)
    lay.box(L_M2, 476.11, 1361.0, 476.49, 1369.05, top)
    lay.box(L_M2, 28.01, 1368.65, 476.49, 1368.95, top)      # INN jog
    via3(27.0, 1368.8)
    lay.box(L_M3, 26.7, 1368.5, 28.5, 1369.1, top)
    lay.via2(28.2, 1368.8, top)

    # ---- QP/QN hold caps + feeds to XND1.A / XND2.A ---------------------------
    # Bottom-sheet junctions: a 3.2+-tall m3 box flush with the sheet edge
    # (covers the tab, no eastward poke), then via2/m2 for the thin wiring.
    # CQN bottom = QN:
    lay.box(L_M3, 55.5, 1144.7, 102.7, 1148.3, top)
    lay.box(L_M2, 50.81, 1146.35, 60.19, 1146.65, top)   # QN vertical merges in
    lay.via2(60.0, 1146.5, top)                  # into the junction box — at the
                                                 # tab, CLEAR OF THE capm FIELD
    lay.box(L_M2, 59.0, 1146.35, 188.88, 1146.65, top)   # east to the rise
    lay.box(L_M2, 188.31, 1146.35, 188.69, nd2_ya + 0.2, top)
    h3(nd2_ya, 191.5, 193.5)                     # A2 bus west extension stub
    lay.box(L_M2, 188.5, nd2_ya - 0.2, 192.69, nd2_ya + 0.2, top)
    lay.via2(192.5, nd2_ya, top)
    # CQP bottom = QP:
    lay.box(L_M3, 105.5, 1164.7, 152.7, 1168.3, top)
    lay.box(L_M2, 52.81, 1166.35, 152.19, 1166.65, top)  # QP vert + A1 rise merge in
    lay.via2(108.0, 1166.5, top)                 # into the junction box — ON THE
                                                 # TAB, CLEAR OF THE capm FIELD
                                                 # (via2s under capm DON'T connect!)
    lay.box(L_M2, 151.81, 1166.35, 152.19, nd1_ya + 0.2, top)
    lay.via2(152.0, nd1_ya, top)
    # CQ top plates -> VSS: via3 on each tab.  CQN hops east on m3 at
    # y1158.5 (south of the CQP sheet/junction box, north of its own sheet)
    # to the clear corridor at x=170 (east of XND1's m2 columns, west of
    # the QN rise); CQP drops right at its tab.  m2 north legs join a
    # y1209.75 jog (over XND2's gate columns, under the NBIT/VDD lanes),
    # a north leg at x=196, a west jog at y1145.5 (under the QP/QN m2
    # verticals, over the OINTP drop's m3), and a south leg at x=45 to the
    # y1100 lane -> via2 -> the VSS vertical.
    lay.box(L_M2, 22.31, 1099.85, 45.19, 1100.15, top)
    lay.box(L_M3, 21.7, 1099.7, 23.2, 1100.3, top)
    lay.via2(22.5, 1100.0, top)
    lay.box(L_M2, 44.81, 1100.0, 45.19, 1145.65, top)    # south leg
    lay.box(L_M2, 45.0, 1145.35, 196.19, 1145.65, top)   # west jog
    lay.box(L_M2, 195.81, 1145.5, 196.19, 1209.9, top)   # north leg
    lay.box(L_M2, 132.0, 1209.6, 196.19, 1209.9, top)    # y1209.75 jog
    lay.box(L_M3, cqn_top[0] - 0.3, cqn_top[1] - 0.3, 170.5,
            cqn_top[1] + 0.3, top)
    lay.via3(*cqn_top, top)
    pad4(*cqn_top)
    lay.via2(170.0, cqn_top[1], top)
    lay.box(L_M2, 169.81, 1158.3, 170.19, 1209.8, top)   # CQN north leg
    lay.box(L_M3, cqp_top[0] - 0.3, cqp_top[1] - 0.3, cqp_top[0] + 1.5,
            cqp_top[1] + 0.3, top)
    lay.via3(*cqp_top, top)
    pad4(*cqp_top)
    lay.via2(cqp_top[0] + 1.2, cqp_top[1], top)
    lay.box(L_M2, 132.26, cqp_top[1] - 0.3, 132.64, 1209.8, top)  # CQP leg

    # ---- SR latch cross-coupling + BIT/BITB ----------------------------------
    # NBIT: XND2.Y bus -> lane west (m3 the whole way: the QP/QN verticals are
    # m2, the drops sit south/north of the lane) -> via2 down to XND1.B bus
    # at x=151.7 (dodging the cell's mn2.s1 strap at local 4.89..5.27)
    h3(nd2_yy, 27.5, nd2_xr + 0.2)
    lay.label(L_M3L, "NBIT", 28.5, nd2_yy, top)
    lay.via2(151.4, nd2_yy, top)
    lay.box(L_M2, 151.21, nd1_yb - 0.2, 151.59, nd2_yy + 0.2, top)
    lay.via2(151.4, nd1_yb, top)
    # BIT: XND1.Y bus -> lane east -> via2 -> m2 vertical x=240
    h3(nd1_yy, nd1_xr - 0.5, 240.19)
    lay.via2(240.0, nd1_yy, top)
    lay.box(L_M2, 239.81, 444.8, 240.19, nd1_yy + 0.2, top)
    # BIT -> XND2.B: extend the Y1 lane east (clear of XND2's body/buses),
    # then down into the B2 bus's east end
    h3(nd1_yy, nd1_xr - 0.5, 212.3)
    v3m(212.0, nd1_yy, nd2_yb + 0.3)
    h3(nd2_yb, nd2_xr - 0.31, 212.3)
    # BIT -> XINV.A: via2 + m2 down + lane into the inv A bus
    lay.via2(238.0, nd1_yy, top)
    lay.box(L_M2, 237.81, inv_ya - 0.2, 238.19, nd1_yy + 0.2, top)
    lay.via2(238.0, inv_ya, top)
    h3(inv_ya, INVX - 1.0 + 0.0, 238.19)         # merges inv A bus (starts INVX-1)
    # BITB: XINV.Y bus -> lane east -> via2 -> m2 vertical x=245
    h3(inv_yy, INVX - 1.0, 245.3)
    lay.via2(245.0, inv_yy, top)
    lay.box(L_M2, 244.81, 383.05, 245.19, inv_yy + 0.2, top)

    # ---- TG wiring -------------------------------------------------------------
    # TG bus offsets (local): A=3.8 B=2.6 EN=-2.2 ENB=-3.4 VSS=-4.6 VDD=-5.8,
    # buses span x -1..22 rel. placement.
    # VDACP: RDACP.b is the serpentine's END pad at (288,241.73) -> m2 up ->
    # east -> up x=336 -> via2 -> lane joining P1.A/P0.A
    lay.via1(288.0, 241.73, top)
    lay.box(L_M2, 287.81, 241.53, 288.19, 278.53, top)
    lay.box(L_M2, 287.81, 278.07, 336.19, 278.53, top)
    lay.box(L_M2, 335.81, 278.3, 336.19, P_TG + 4.15, top)
    lay.via2(336.0, P_TG + 3.8, top)
    h3(P_TG + 3.8, 269.0, 336.3)
    # VDACN: RDACN.b at (288,321.73) -> up x=333 -> lane joining N1.A/N0.A
    lay.via1(288.0, 321.73, top)
    lay.box(L_M2, 287.81, 321.53, 288.19, 358.53, top)
    lay.box(L_M2, 287.81, 358.07, 333.19, 358.53, top)
    lay.box(L_M2, 332.81, 358.3, 333.19, N_TG + 4.15, top)
    lay.via2(333.0, N_TG + 3.8, top)
    h3(N_TG + 3.8, 269.0, 333.3)
    # VP: P1.B stub -> via2 (293.5) -> m2 down -> lane into N0.B
    h3(P_TG + 2.6, 291.5, 294.5)
    lay.via2(293.5, P_TG + 2.6, top)
    lay.box(L_M2, 293.31, N_TG + 2.45, 293.69, P_TG + 2.75, top)
    lay.via2(293.5, N_TG + 2.6, top)
    h3(N_TG + 2.6, 293.2, 322.3)
    lay.label(L_M3L, "VP", 293.0, P_TG + 2.6, top)
    # VN: via2 (322.2) on a P0.B stub -> m2 down x=322.2 -> west lane y383.55
    # (between the BITB lane and the TG tie columns) -> rise x=272.35 -> N1.B
    h3(P_TG + 2.6, 321.5, 322.9)
    lay.via2(322.2, P_TG + 2.6, top)
    lay.box(L_M2, 322.01, N_TG - 6.45, 322.39, P_TG + 2.75, top)
    lay.box(L_M2, 272.16, N_TG - 6.6, 322.39, N_TG - 6.3, top)
    lay.box(L_M2, 272.16, N_TG - 6.45, 272.54, N_TG + 2.8, top)
    lay.via2(272.35, N_TG + 2.6, top)
    lay.label(L_M3L, "VN", 320.5, P_TG + 2.6, top)
    # supplies: lanes joining both rows' VDD18/VSS buses to the verticals.
    # The VSS lanes start at the x=22 vertical and cross the VDD18 vertical
    # (24.7..25.3) on short m2 dives.
    h3(P_TG - 5.8, 24.7, 322.3)                  # VDD18, P row
    h3(N_TG - 5.8, 24.7, 322.3)                  # VDD18, N row
    for yv in (P_TG - 4.6, N_TG - 4.6):
        h3(yv, 21.7, 23.5)
        lay.via2(22.8, yv, top)
        lay.box(L_M2, 22.61, yv - 0.15, 26.39, yv + 0.15, top)
        lay.via2(26.2, yv, top)
        h3(yv, 25.9, 322.3)
    # BIT gates: EN of P1/N1 (west column, vertical A=291.5) + ENB of P0/N0
    # (east column, vertical B=323.4 on bus-extension stubs)
    h3(445.0, 26.5, 323.9)                       # BIT lane (m3)
    lay.label(L_M3L, "BIT", 28.0, 445.0, top)
    lay.via2(240.0, 445.0, top)                  # BIT vertical (x=240) joins
    h3(P_TG - 3.4, 321.5, 324.4)                 # P0.ENB extension stub
    h3(N_TG - 3.4, 321.5, 324.4)                 # N0.ENB extension stub
    h3(P_TG - 2.2, 321.5, 323.3)                 # P0.EN extension stub
    h3(N_TG - 2.2, 321.5, 323.3)                 # N0.EN extension stub
    for xg, ybus in ((291.5, P_TG - 2.2), (291.5, N_TG - 2.2),
                     (323.7, P_TG - 3.4), (323.7, N_TG - 3.4)):
        lay.via2(xg, ybus, top)
    lay.box(L_M2, 291.31, N_TG - 2.35, 291.69, 445.15, top)  # A vertical
    lay.box(L_M2, 323.51, N_TG - 3.6, 323.89, 445.15, top)   # B vertical
    lay.via2(291.5, 445.0, top)
    lay.via2(323.7, 445.0, top)
    # BITB gates: ENB of P1/N1 (vertical C=268.9 on bus-extension stubs) + EN
    # of P0/N0 (vertical D=322.9 on the EN stubs); lane at y383.05 (below the
    # N-row tie columns, above the VN lane at 383.55 — different y-ranges)
    lay.box(L_M2, 244.81, 382.9, 322.79, 383.2, top)         # BITB lane (m2)
    h3(P_TG - 3.4, 268.3, 269.2)                 # P1.ENB extension stub
    h3(N_TG - 3.4, 268.3, 269.2)                 # N1.ENB extension stub
    for xg, ybus in ((268.9, P_TG - 3.4), (268.9, N_TG - 3.4),
                     (322.9, P_TG - 2.2), (322.9, N_TG - 2.2)):
        lay.via2(xg, ybus, top)
    lay.box(L_M2, 268.71, 383.05, 269.09, P_TG - 3.1, top)   # C vertical
    lay.box(L_M2, 322.71, 383.05, 323.09, P_TG - 1.8, top)   # D vertical

    # ---- nand/inv supplies -----------------------------------------------------
    # (VSS lanes dive past the VDD18 vertical on m2, like the TG rows)
    for yv, xe in ((nd1_yvss, nd1_xr + 0.2), (nd2_yvss, nd2_xr + 0.2),
                   (inv_yvss, inv_xr + 0.3)):
        h3(yv, 21.7, 23.5)
        lay.via2(22.8, yv, top)
        lay.box(L_M2, 22.61, yv - 0.15, 26.39, yv + 0.15, top)
        lay.via2(26.2, yv, top)
        h3(yv, 25.9, xe)
    h3(nd1_yvdd, 24.7, nd1_xr + 0.2)
    h3(nd2_yvdd, 24.7, nd2_xr + 0.2)
    # XINV.VDD: a direct lane would collide with XND1's A1/B1 buses (the inv
    # and nand bus grids interleave); route north of XND1 and drop on m2.
    h3(1196.5, 24.7, 211.3)
    lay.via2(211.0, 1196.5, top)
    lay.box(L_M2, 210.81, inv_yvdd - 0.16, 211.19, 1196.7, top)
    lay.via2(211.0, inv_yvdd, top)

    # ---- supply/pin labels ------------------------------------------------------
    lay.label(L_M4L, "VDD18", 900.0, 1470.0, top)
    lay.label(L_M4L, "VSS", 900.0, 1388.0, top)
    lay.label(L_M4L, "VCM_REF", 900.0, 1474.0, top)

    return top


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which is None:
        lay = Layouter("scratch")
        cell = build_sdm(lay)
        lay.set_top(cell)
        lay.finish(OUT_GDS)
        return
    if which == "ota_nc":
        lay = Layouter("scratch")
        cell = build_ota_nc(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_ota_nc.gds"))
        return
    if which == "nand2":
        lay = Layouter("scratch")
        cell, _ = build_nand2(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_nand2.gds"))
        return
    if which == "strongarm":
        lay = Layouter("scratch")
        cell, _ = build_strongarm(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_strongarm.gds"))
        return
    raise SystemExit(f"unknown cell {which!r}: nand2|strongarm|ota_nc")


if __name__ == "__main__":
    main()

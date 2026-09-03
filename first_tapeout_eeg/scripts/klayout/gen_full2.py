#!/usr/bin/env python3
"""
Batch layout generator for the fully biased internal-chopper OTA
(subckt eeg_fd_ota_chopped_full2), sky130A.

    scripts/klayout/.venv/bin/python scripts/klayout/gen_full2.py [CELL]

With no argument, builds GDSII/eeg_fd_ota_chopped_full2.gds (top cell
eeg_fd_ota_chopped_full2).  With CELL = tg|chopper|cmfb|bias|stage2, builds
just that block into GDSII/test_<CELL>.gds for standalone DRC/LVS debugging.

Subcells: eeg_tg_lowq, eeg_cmos_chopper_lowq, eeg_cmfb_amp_dl2 (W9=4),
eeg_cmfb_amp_dl2_s2 (W9=0.5), eeg_bias_gen.  The stage-1 core
(eeg_fd_ota_core_soft) is instanced from its verified GDS.  Stage-2 FETs,
output resistors and Miller compensation are drawn at top level.

All coordinates in um.  See klayout_common.py / README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import *

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_GDS = os.path.join(PROJECT, "GDSII", "eeg_fd_ota_chopped_full2.gds")
CORE_GDS = os.path.join(PROJECT, "GDSII", "eeg_fd_ota_core_soft.gds")


def fet_anchors(lay, cell, x, y):
    """Absolute anchors of a placed (unmirrored) FET cell."""
    diff, strips, ptop, pbot = lay.scan_m1(cell)
    return {
        "strips": [(sx + x, (y0 + y1) / 2 + y) for sx, y0, y1 in strips],
        "g": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in pbot],
        "gt": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in ptop],
    }


# ----------------------------------------------------------------------------
# eeg_tg_lowq: A B EN ENB VDD18 VSS
#   XMN  B EN  A VSS nfet L=0.15 W=0.84 ;  XMP  B ENB A VDD pfet W=1.68
#   XMND B ENB B VSS nfet W=0.42 (dummy) ;  XMPD B EN B VDD pfet W=0.84 (dummy)
# ----------------------------------------------------------------------------
def build_tg(lay):
    mn = lay.make_nfet("tg_n", 0.15, 0.84, 1)
    mnd = lay.make_nfet("tg_nd", 0.15, 0.42, 1)
    mp = lay.make_pfet("tg_p", 0.15, 1.68, 1)
    mpd = lay.make_pfet("tg_pd", 0.15, 0.84, 1)

    tg = lay.ly.create_cell("eeg_tg_lowq")
    # wider pitch: leaves clean routing channels between the devices
    pos = {"mn": (mn, 0.0, 0.0), "mnd": (mnd, 3.5, 0.0),
           "mp": (mp, 0.0, 6.0), "mpd": (mpd, 5.0, 6.0)}
    g = {}
    for key, (cell, x, y) in pos.items():
        lay.place(cell, x, y, into=tg)
        g[key] = fet_anchors(lay, cell, x, y)
        assert len(g[key]["strips"]) == 2 and len(g[key]["g"]) == 1, key

    def strip_m1(key, i):
        """(x0,x1,yc) of the m1 S/D contact of device key, strip i."""
        diff, strips, _, _ = lay.scan_m1(pos[key][0])
        sx, y0, y1 = strips[i]
        dx, dy = pos[key][1], pos[key][2]
        return sx - (y1 - y0) / 2 + dx, sx + (y1 - y0) / 2 + dx, (y0 + y1) / 2 + dy

    Y_B, Y_A, Y_EN, Y_ENB, Y_VDD, Y_VSS = 8.5, 10.5, -2.2, -3.2, -4.4, -5.5

    # --- A: mn.s0 + mp.s0 (m1 vertical bridging both strips' m1)
    lay.box(L_M1, 0.2, g["mn"]["strips"][0][1] - 0.17, 0.8,
            g["mp"]["strips"][0][1] + 0.17, tg)
    lay.via1(0.5, 6.35, tg)
    lay.box(L_M2, 0.31, 6.18, 0.69, Y_A, tg)
    lay.via2(0.5, Y_A - 0.15, tg)
    lay.box(L_M3, 0.2, Y_A - 0.5, 0.8, Y_A + 0.15, tg)

    # --- B: mn.s1 + mp.s1 (m1 vertical), dummies via m1 bars + m2 verticals
    lay.box(L_M1, 0.9, g["mn"]["strips"][1][1] - 0.17, 1.6,
            g["mp"]["strips"][1][1] + 0.17, tg)
    lay.via1(1.25, 6.45, tg)
    lay.box(L_M2, 1.06, 6.28, 1.44, Y_B + 0.15, tg)
    lay.via2(1.25, Y_B, tg)
    lay.bus_m3(0.9, 6.9, Y_B, cell=tg)
    # dummy S-D join bars + their verticals
    for k, xbar in (("mnd", 3.5), ("mpd", 5.0)):
        (cx0, cy0), (cx1, cy1) = g[k]["strips"]
        yc = (cy0 + cy1) / 2
        lay.box(L_M1, min(cx0, cx1) - 0.3, yc - 0.15, max(cx0, cx1) + 0.3,
                yc + 0.15, tg)
        lay.strap_up((cx0 + cx1) / 2, yc, Y_B, tg)

    # --- gates: EN = mn.g + mpd.g ; ENB = mp.g + mnd.g
    lay.bus_m3(-1.9, 6.2, Y_EN, cell=tg)
    lay.bus_m3(-1.9, 4.4, Y_ENB, cell=tg)
    lay.strap_down(*g["mn"]["g"][0], Y_EN, tg)
    lay.strap_down(*g["mpd"]["g"][0], Y_EN, tg)
    lay.strap_down(*g["mp"]["g"][0], Y_ENB, tg)
    lay.strap_down(*g["mnd"]["g"][0], Y_ENB, tg)
    # EN / ENB m3 stubs up the left edge (for chopper-level rails)
    lay.box(L_M3, -1.9, Y_EN, -1.3, 10.8, tg)
    lay.box(L_M3, -2.82, Y_ENB, -2.22, 11.4, tg)

    # --- guard rings: nfets -> VSS, pfets -> VDD (down straps)
    lay.tie_ring(mn, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (-0.35,), into=tg)
    lay.tie_ring(mnd, kdb.Trans(0, False, u(3.5), 0), "bottom", Y_VSS, (6.5,), into=tg)
    lay.tie_ring(mp, kdb.Trans(0, False, 0, u(6.0)), "bottom", Y_VDD, (2.4,), into=tg)
    lay.tie_ring(mpd, kdb.Trans(0, False, u(5.0), u(6.0)), "bottom", Y_VDD, (7.1,), into=tg)
    lay.bus_m3(-2.52, 7.4, Y_VDD, cell=tg)
    lay.bus_m3(-2.52, 7.4, Y_VSS, cell=tg)

    lay.label(L_M3L, "A", 0.5, Y_A, tg)
    lay.label(L_M3L, "B", 1.25, Y_B, tg)
    lay.label(L_M3L, "EN", -1.6, 10.8, tg)
    lay.label(L_M3L, "ENB", -2.52, 11.4, tg)
    lay.label(L_M3L, "VDD18", 7.4, Y_VDD, tg)
    lay.label(L_M3L, "VSS", -2.52, Y_VSS, tg)

    anchors = {"A": (0.5, Y_A), "B": (6.9, Y_B),
               "EN": (-1.6, 10.8), "ENB": (-2.52, 11.4),
               "VDD18": (7.4, Y_VDD), "VSS": (-2.52, Y_VSS)}
    return tg, anchors


# ----------------------------------------------------------------------------
# eeg_cmos_chopper_lowq: INP INN OUTP OUTN PHI NPHI PHIB NPHIB VDD18 VSS
# ----------------------------------------------------------------------------
def build_chopper(lay, name="eeg_cmos_chopper_lowq"):
    tg, a = build_tg(lay)
    ch = lay.ly.create_cell(name)
    pitch = 9.0
    ports = {}
    for k, x in (("SP", 0.0), ("SN", pitch), ("CP", 2 * pitch), ("CN", 3 * pitch)):
        lay.place(tg, x, 0.0, into=ch)
        ports[k] = {net: (px + x, py) for net, (px, py) in a.items()}

    # m4 rails
    rails = {"OUTP": 13.0, "OUTN": 14.0, "INP": 15.0, "INN": 16.0,
             "PHI": 17.0, "NPHI": 18.0, "PHIB": 19.0, "NPHIB": 20.0}
    for y in rails.values():
        lay.box(L_M4, -3.5, y - 0.3, 3 * pitch + 6.5, y + 0.3, ch)

    def tap(k, net, rail_y):
        x, y = ports[k][net]
        lay.box(L_M3, x - 0.3, min(y, rail_y) - 0.3, x + 0.3, max(y, rail_y) + 0.3, ch)
        lay.via3(x, rail_y, ch)

    tap("SP", "B", rails["OUTP"]); tap("CN", "B", rails["OUTP"])
    tap("SN", "B", rails["OUTN"]); tap("CP", "B", rails["OUTN"])
    tap("SP", "A", rails["INP"]);  tap("CP", "A", rails["INP"])
    tap("SN", "A", rails["INN"]);  tap("CN", "A", rails["INN"])
    tap("SP", "EN", rails["PHI"]);  tap("SN", "EN", rails["PHI"])
    tap("CP", "EN", rails["PHIB"]); tap("CN", "EN", rails["PHIB"])
    tap("SP", "ENB", rails["NPHI"]);  tap("SN", "ENB", rails["NPHI"])
    tap("CP", "ENB", rails["NPHIB"]); tap("CN", "ENB", rails["NPHIB"])

    # VDD / VSS m3 rails joining the TG buses
    lay.box(L_M3, -3.5, -4.7, 3 * pitch + 6.5, -4.1, ch)
    lay.box(L_M3, -3.5, -5.7, 3 * pitch + 6.5, -5.1, ch)

    for net, y in rails.items():
        lay.label(L_M4L, net, 3 * pitch + 6.5, y, ch)
    lay.label(L_M3L, "VDD18", 3 * pitch + 6.5, -4.4, ch)
    lay.label(L_M3L, "VSS", -3.5, -5.4, ch)

    anch = {net: (3 * pitch + 6.5, y) for net, y in rails.items()}
    anch["VDD18"] = (3 * pitch + 6.5, -4.4)
    anch["VSS"] = (-3.5, -5.4)
    return ch, anch


# ----------------------------------------------------------------------------
# eeg_cmfb_amp_dl2: VCM_SENSE VCM_REF VBN VBP VDD18 VSS
#   XM6 NLEFT VCM_SENSE NTAIL VSS nfet L=2 W=2 ; XM7 VBP VCM_REF NTAIL VSS (same)
#   XM8 NLEFT NLEFT VDD18 pfet L=2 W=2 (diode) ; XM9 VBP VBP VDD18 pfet L=4 W9
#   XM10 NTAIL VBN VSS VSS nfet L=4 W=12 nf=2
# ----------------------------------------------------------------------------
def build_cmfb(lay, w9, name):
    m6 = lay.make_nfet(name + "_m6", 2.0, 2.0, 1)
    m7 = lay.make_nfet(name + "_m7", 2.0, 2.0, 1)
    m8 = lay.make_pfet(name + "_m8", 2.0, 2.0, 1)
    m9 = lay.make_pfet(name + "_m9", 4.0, w9, 1)
    m10 = lay.make_nfet(name + "_m10", 4.0, 6.0, 2)

    c = lay.ly.create_cell(name)
    lay.place(m6, 0.0, 0.0, into=c)
    lay.place(m7, 6.0, 0.0, into=c)
    lay.place(m8, 0.0, 8.0, into=c)
    lay.place(m9, 6.0, 8.0, into=c)
    lay.place(m10, 1.0, -9.0, into=c)
    g = {"m6": fet_anchors(lay, m6, 0.0, 0.0), "m7": fet_anchors(lay, m7, 6.0, 0.0),
         "m8": fet_anchors(lay, m8, 0.0, 8.0), "m9": fet_anchors(lay, m9, 6.0, 8.0),
         "m10": fet_anchors(lay, m10, 1.0, -9.0)}

    Y_VSNS, Y_VREF, Y_VBN, Y_VSS = -3.2, -4.2, -14.5, -15.7
    Y_NL, Y_VDD, Y_VBP = 6.5, 17.0, 18.2

    # NTAIL: m1 bar joining m6.s0 / m7.s0; m3 link below; down to m10 drain
    x6s, y6s = g["m6"]["strips"][0]
    x7s, y7s = g["m7"]["strips"][0]
    lay.box(L_M1, x6s - 0.17, y6s - 0.17, x7s + 0.17, y7s + 0.17, c)
    lay.bus_m3(x6s, x7s, -2.0, cell=c)
    lay.strap_down(x6s, y6s, -2.0, c)
    x10d, y10d = g["m10"]["strips"][1]
    lay.strap_up(x10d, y10d, -2.0, c)

    # m10 sources -> VSS, gate bar -> VBN
    for i in (0, 2):
        lay.strap_down(*g["m10"]["strips"][i], Y_VSS, c)
    gx = [p[0] for p in g["m10"]["g"]]
    gy = g["m10"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    lay.strap_down((min(gx) + max(gx)) / 2, gy, Y_VBN, c)
    lay.bus_m3(0.0, 9.5, Y_VBN, cell=c)
    lay.bus_m3(0.0, 9.5, Y_VSS, cell=c)

    # NLEFT: m6.s1 up to m8 diode (G-D short on m1, drain strap down to Y_NL)
    x8d, y8d = g["m8"]["strips"][1]
    x8g, y8g = g["m8"]["g"][0]
    lay.box(L_M1, x8g - 0.17, y8g - 0.17, x8d + 0.17, y8d + 0.17, c)
    lay.bus_m3(g["m6"]["strips"][1][0], x8d, Y_NL, cell=c)
    lay.strap_up(*g["m6"]["strips"][1], Y_NL, c)
    lay.strap_down(x8d, y8d, Y_NL, c)

    # VBP: m7.s1 up + m9 diode down to Y_VBP bus
    x9d, y9d = g["m9"]["strips"][1]
    x9g, y9g = g["m9"]["g"][0]
    lay.box(L_M1, x9g - 0.17, y9g - 0.17, x9d + 0.17, y9d + 0.17, c)
    lay.bus_m3(min(g["m7"]["strips"][1][0], x9d), 11.5, Y_VBP, cell=c)
    lay.strap_up(*g["m7"]["strips"][1], Y_VBP, c)
    lay.strap_up(x9d, y9d, Y_VBP, c)

    # VDD18: m8.s0 / m9.s0 up + pfet rings
    lay.bus_m3(min(g["m8"]["strips"][0][0], g["m9"]["strips"][0][0]), 11.5, Y_VDD, cell=c)
    lay.strap_up(*g["m8"]["strips"][0], Y_VDD, c)
    lay.strap_up(*g["m9"]["strips"][0], Y_VDD, c)
    lay.tie_ring(m8, kdb.Trans(0, False, 0, u(8.0)), "top", Y_VDD, (2.5,), into=c)
    lay.tie_ring(m9, kdb.Trans(0, False, u(6.0), u(8.0)), "top", Y_VDD, (8.5,), into=c)
    lay.tie_ring(m6, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (3.5,), into=c)
    lay.tie_ring(m7, kdb.Trans(0, False, u(6.0), 0), "bottom", Y_VSS, (7.5,), into=c)
    lay.tie_ring(m10, kdb.Trans(0, False, u(1.0), u(-9.0)), "bottom", Y_VSS, (5.0,), into=c)

    # VCM_SENSE / VCM_REF gate pads
    lay.bus_m3(g["m6"]["g"][0][0], g["m6"]["g"][0][0] + 1.5, Y_VSNS, cell=c)
    lay.strap_down(*g["m6"]["g"][0], Y_VSNS, c)
    lay.bus_m3(g["m7"]["g"][0][0], g["m7"]["g"][0][0] + 1.5, Y_VREF, cell=c)
    lay.strap_down(*g["m7"]["g"][0], Y_VREF, c)

    for net, xy in (("VCM_SENSE", (g["m6"]["g"][0][0] + 1.5, Y_VSNS)),
                    ("VCM_REF", (g["m7"]["g"][0][0] + 1.5, Y_VREF)),
                    ("VBN", (9.5, Y_VBN)), ("VSS", (9.5, Y_VSS)),
                    ("VDD18", (11.5, Y_VDD)), ("VBP", (11.5, Y_VBP))):
        lay.label(L_M3L, net, *xy, c)

    anch = {"VCM_SENSE": (g["m6"]["g"][0][0] + 1.5, Y_VSNS),
            "VCM_REF": (g["m7"]["g"][0][0] + 1.5, Y_VREF),
            "VBN": (9.5, Y_VBN), "VSS": (9.5, Y_VSS),
            "VDD18": (11.5, Y_VDD), "VBP": (11.5, Y_VBP)}
    return c, anch


# ----------------------------------------------------------------------------
# eeg_bias_gen: VBN VBNF VBP VDD18 VSS
#   XMP1 VBN VBP VDD18 pfet L=4 W=10 nf=2 ; XMN1 VBN VBN VSS nfet W=10 nf=2 (diode)
#   XMP2 VBP VBP VDD18 pfet W=10 nf=2 (diode) ; XMN2 VBP VBN SNS2 VSS nfet W=40 nf=8
#   RSET SNS2 VSS 25k ; RSTART VDD18 VBN 20Meg ; RF VBN VBNF 1Meg ; CF VBNF VSS 1n
# ----------------------------------------------------------------------------
def build_bias(lay):
    mp1 = lay.make_pfet("bg_mp1", 4.0, 5.0, 2)
    mn1 = lay.make_nfet("bg_mn1", 4.0, 5.0, 2)
    mp2 = lay.make_pfet("bg_mp2", 4.0, 5.0, 2)
    mn2 = lay.make_nfet("bg_mn2", 4.0, 5.0, 8)

    c = lay.ly.create_cell("eeg_bias_gen")

    # FET row at y=0: nfets left, pfets right
    lay.place(mn1, 0.0, 0.0, into=c)
    lay.place(mn2, 8.0, 0.0, into=c)
    lay.place(mp1, 50.0, 0.0, into=c)
    lay.place(mp2, 58.0, 0.0, into=c)
    g = {"mn1": fet_anchors(lay, mn1, 0.0, 0.0), "mn2": fet_anchors(lay, mn2, 8.0, 0.0),
         "mp1": fet_anchors(lay, mp1, 50.0, 0.0), "mp2": fet_anchors(lay, mp2, 58.0, 0.0)}

    # buses (m3): VBN 8.0, VBP 9.2, SNS2 10.4 above; VSS -3.5 below; VDD 13.5 top
    Y_VBN, Y_VBP, Y_SNS2, Y_VSS, Y_VDD, Y_VBNF = 8.0, 9.2, 10.4, -3.5, 13.5, 6.8
    lay.bus_m3(-1.0, 70.0, Y_VBN, cell=c)
    lay.bus_m3(-1.0, 70.0, Y_VBP, cell=c)
    lay.bus_m3(-1.0, 70.0, Y_SNS2, cell=c)
    lay.bus_m3(-1.0, 70.0, Y_VSS, cell=c)
    lay.bus_m3(-1.0, 70.0, Y_VDD, cell=c)
    lay.bus_m3(20.0, 70.0, Y_VBNF, cell=c)

    # mn1 diode: gate bar + G-D short to middle strip, drain -> VBN; sources -> VSS
    gx = [p[0] for p in g["mn1"]["g"]]
    gy = g["mn1"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    xd, yd = g["mn1"]["strips"][1]
    lay.box(L_M1, min(gx) - 0.17, gy - 0.17, xd + 0.17, yd + 0.17, c)
    lay.strap_up(xd, yd, Y_VBN, c)
    for i in (0, 2):
        lay.strap_down(*g["mn1"]["strips"][i], Y_VSS, c)

    # mn2: gate bar -> VBN ; odd strips (drains) -> VBP ; even -> SNS2
    gx = [p[0] for p in g["mn2"]["g"]]
    gy = g["mn2"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    lay.strap_up((min(gx) + max(gx)) / 2, gy, Y_VBN, c)
    for i, (x, y) in enumerate(g["mn2"]["strips"]):
        if i % 2 == 0:
            lay.strap_up(x, y, Y_SNS2, c)
        else:
            lay.strap_up(x, y, Y_VBP, c)

    # mp1: middle strip (D) -> VBN ; gate pads -> VBP ; outer strips -> VDD
    lay.strap_up(*g["mp1"]["strips"][1], Y_VBN, c)
    for px, py in g["mp1"]["g"]:
        lay.strap_up(px, py, Y_VBP, c)
    for i in (0, 2):
        lay.strap_up(*g["mp1"]["strips"][i], Y_VDD, c)

    # mp2 diode: G-D short -> VBP ; sources -> VDD
    gx = [p[0] for p in g["mp2"]["g"]]
    gy = g["mp2"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    xd, yd = g["mp2"]["strips"][1]
    lay.box(L_M1, min(gx) - 0.17, gy - 0.17, xd + 0.17, yd + 0.17, c)
    lay.strap_up(xd, yd, Y_VBP, c)
    for i in (0, 2):
        lay.strap_up(*g["mp2"]["strips"][i], Y_VDD, c)

    # guard rings
    lay.tie_ring(mn1, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (2.0,), into=c)
    lay.tie_ring(mn2, kdb.Trans(0, False, u(8.0), 0), "bottom", Y_VSS, (12.0,), into=c)
    lay.tie_ring(mp1, kdb.Trans(0, False, u(50.0), 0), "top", Y_VDD, (52.0,), into=c)
    lay.tie_ring(mp2, kdb.Trans(0, False, u(58.0), 0), "top", Y_VDD, (60.0,), into=c)

    # --- resistors ---------------------------------------------------------
    seg25 = lay.make_res_seg(8.505)    # 25 kohm exactly
    seg100 = lay.make_res_seg(34.38)   # 100 kohm exactly

    # RSET: single segment at (66, -30); top pad -> SNS2, bottom pad -> VSS
    lay.place(seg25, 66.0, -30.0, into=c)
    lay.strap_up(66.0, -30.0 + 18.27, Y_SNS2, c)   # long strap ok (m2 over m3)
    lay.via1(66.0, -30.0 - 18.27, c)
    lay.box(L_M1, 66.0 - 0.17, -30.0 - 18.44, 66.0 + 0.17, -30.0 - 18.10, c)
    lay.box(L_M2, 66.0 - 0.19, -30.0 - 18.44, 66.0 + 0.19, Y_VSS + 0.15, c)
    lay.via2(66.0, Y_VSS, c)
    lay.box(L_M3, 66.0 - 0.3, Y_VSS - 0.3, 66.0 + 0.3, Y_VSS + 0.3, c)

    # RFILT: 10 segments at (20..38, -30); a=VBN side, b=VBNF side
    (ra, _), (rb, _) = lay.res_bank(c, 20.0, -30.0, 10, seg100)
    lay.strap_up(ra, -30.0 + 18.27, Y_VBN, c)
    lay.strap_up(rb, -30.0 + 18.27, Y_VBNF, c)

    # RSTART: 200 segments, 4 rows x 50, anchored (80, -210): rows rise upward
    (sa, _), (sb, _) = lay.res_bank(c, 80.0, -210.0, 200, seg100, ncols=50)
    lay.strap_up(sa[0], sa[1], Y_VDD, c)      # -> VDD18
    lay.strap_up(sb[0], sb[1], Y_VBN, c)      # -> VBN

    # --- CFILT: 1 nF MIM array (25x50 of 20x20) below everything
    bot, top, area, perim = lay.mim_array(c, 0.0, -1350.0, 25, 50)
    # bottom plate -> VSS via m3 column on the left edge
    lay.box(L_M3, -3.0, -1350.0, -2.0, Y_VSS, c)
    lay.box(L_M3, -3.0, Y_VSS - 0.3, 0.0, Y_VSS + 0.3, c)
    # top mesh -> VBNF via m4 column at x=25
    lay.box(L_M4, 24.7, top[1], 25.3, Y_VBNF + 1.0, c)
    lay.box(L_M4, 24.7, Y_VBNF + 0.3, 26.2, Y_VBNF + 1.0, c)
    lay.via3(25.6, Y_VBNF + 0.65, c)
    lay.box(L_M3, 25.0, Y_VBNF + 0.3, 26.2, Y_VBNF + 1.0, c)
    # connect that m3 stub down onto the VBNF bus
    lay.box(L_M3, 25.0, Y_VBNF + 0.3, 26.2, Y_VBNF + 0.9, c)  # already overlaps bus

    for net, xy in (("VBN", (70.0, Y_VBN)), ("VBP", (70.0, Y_VBP)),
                    ("VDD18", (70.0, Y_VDD)), ("VSS", (70.0, Y_VSS)),
                    ("VBNF", (70.0, Y_VBNF))):
        lay.label(L_M3L, net, *xy, c)

    anch = {"VBN": (70.0, Y_VBN), "VBP": (70.0, Y_VBP), "VDD18": (70.0, Y_VDD),
            "VSS": (70.0, Y_VSS), "VBNF": (70.0, Y_VBNF)}
    return c, anch


# ----------------------------------------------------------------------------
# stage-2 output stage: M21-24 + RCMO + RLOADO + RZ + Miller CC
# (built as a top-level block; ports exposed as m3/m4 anchors)
# ----------------------------------------------------------------------------
def build_stage2(lay):
    """Returns (cell, anchors).  Nets: N2P N2N OUTP OUTN VBP2 VCM2 VCM_REF
    VDD18 VSS; Miller: NZP NZN inside, CC to OUTP/OUTN."""
    m21 = lay.make_nfet("s2_m21", 12.0, 6.0, 2)
    m22 = lay.make_nfet("s2_m22", 12.0, 6.0, 2)
    m23 = lay.make_pfet("s2_m23", 12.0, 6.0, 8)
    m24 = lay.make_pfet("s2_m24", 12.0, 6.0, 8)

    c = lay.ly.create_cell("stage2")
    lay.place(m21, 0.0, 0.0, into=c)
    lay.place(m23, 0.0, 14.0, into=c)
    lay.place(m22, 45.0, 0.0, into=c)
    lay.place(m24, 45.0, 14.0, into=c)
    g = {"m21": fet_anchors(lay, m21, 0.0, 0.0), "m22": fet_anchors(lay, m22, 45.0, 0.0),
         "m23": fet_anchors(lay, m23, 0.0, 14.0), "m24": fet_anchors(lay, m24, 45.0, 14.0)}

    Y_N2P, Y_N2N, Y_VSS = -3.5, -4.7, -5.9
    Y_OUTP, Y_OUTN, Y_VBP2, Y_VDD = 24.0, 25.2, 26.4, 27.6

    lay.bus_m3(-2.0, 90.0, Y_N2P, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_N2N, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_VSS, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_OUTP, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_OUTN, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_VBP2, cell=c)
    lay.bus_m3(-2.0, 90.0, Y_VDD, cell=c)

    for key, net_g, net_d, y_g, y_d in (("m21", "N2P", "OUTP", Y_N2P, Y_OUTP),
                                        ("m22", "N2N", "OUTN", Y_N2N, Y_OUTN)):
        gx = [p[0] for p in g[key]["g"]]
        gy = g[key]["g"][0][1]
        lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
        lay.strap_down((min(gx) + max(gx)) / 2, gy, y_g, c)
        for i, (x, y) in enumerate(g[key]["strips"]):
            if i % 2 == 1:      # drains
                lay.strap_up(x, y, y_d, c)
            else:               # sources -> VSS
                lay.strap_down(x, y, Y_VSS, c)
    for key in ("m23", "m24"):
        y_g = Y_VBP2
        y_d = Y_OUTP if key == "m23" else Y_OUTN
        gx = [p[0] for p in g[key]["g"]]
        gy = g[key]["g"][0][1]
        lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
        lay.strap_up((min(gx) + max(gx)) / 2, gy, y_g, c)
        for i, (x, y) in enumerate(g[key]["strips"]):
            if i % 2 == 1:
                lay.strap_up(x, y, y_d, c)
            else:
                lay.strap_up(x, y, Y_VDD, c)

    lay.tie_ring(m21, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (2.0,), into=c)
    lay.tie_ring(m22, kdb.Trans(0, False, u(45.0), 0), "bottom", Y_VSS, (47.0,), into=c)
    lay.tie_ring(m23, kdb.Trans(0, False, 0, u(14.0)), "top", Y_VDD, (2.0,), into=c)
    lay.tie_ring(m24, kdb.Trans(0, False, u(45.0), u(14.0)), "top", Y_VDD, (47.0,), into=c)

    # --- RCMO / RLOADO banks (right of the fets) ---------------------------
    seg100 = lay.make_res_seg(34.38)
    (rcmo1a, _), (rcmo1b, _) = lay.res_bank(c, 100.0, 0.0, 50, seg100)
    (rcmo2a, _), (rcmo2b, _) = lay.res_bank(c, 210.0, 0.0, 50, seg100)
    (rl1a, _), (rl1b, _) = lay.res_bank(c, 320.0, 0.0, 20, seg100)
    (rl2a, _), (rl2b, _) = lay.res_bank(c, 370.0, 0.0, 20, seg100)
    Y_VCM2, Y_VCMR = 22.0, 23.0
    lay.bus_m3(100.0, 415.0, Y_VCM2, cell=c)
    lay.bus_m3(100.0, 415.0, Y_VCMR, cell=c)
    lay.strap_up(rcmo1a[0], rcmo1a[1], Y_OUTP, c)   # RCMO1 a -> OUTP
    lay.strap_up(rcmo1b[0], rcmo1b[1], Y_VCM2, c)
    lay.strap_up(rcmo2a[0], rcmo2a[1], Y_OUTN, c)
    lay.strap_up(rcmo2b[0], rcmo2b[1], Y_VCM2, c)
    lay.strap_up(rl1a[0], rl1a[1], Y_OUTP, c)
    lay.strap_up(rl1b[0], rl1b[1], Y_VCMR, c)
    lay.strap_up(rl2a[0], rl2a[1], Y_OUTN, c)
    lay.strap_up(rl2b[0], rl2b[1], Y_VCMR, c)

    # --- Miller RZ + CC ----------------------------------------------------
    segrz = lay.make_res_seg(6.78)   # 20 kohm exactly
    # RZP: N2P -> NZP ; RZN: N2N -> NZN ; vertical segments below the fets
    lay.place(segrz, 20.0, -25.0, into=c)
    lay.place(segrz, 65.0, -25.0, into=c)
    lay.strap_up(20.0, -25.0 + 18.27, Y_N2P, c)
    lay.strap_up(65.0, -25.0 + 18.27, Y_N2N, c)
    Y_NZP, Y_NZN = -46.0, -48.0
    lay.bus_m3(15.0, 25.0, Y_NZP, cell=c)
    lay.bus_m3(60.0, 70.0, Y_NZN, cell=c)
    lay.strap_down(20.0, -25.0 - 18.27, Y_NZP, c)
    lay.strap_down(65.0, -25.0 - 18.27, Y_NZN, c)

    # CCP/CCN: MIM arrays 5x4 of 20x12.5 (A=5000 um2 -> 10 pF at 2 fF/um2)
    botP, topP, a1, p1 = lay.mim_array(c, 100.0, -80.0, 5, 4, cw=20.0, ch=12.5)
    botN, topN, a2, p2 = lay.mim_array(c, 240.0, -80.0, 5, 4, cw=20.0, ch=12.5)
    # bottom plate -> OUTP/OUTN ; top mesh -> NZP/NZN
    lay.box(L_M3, botP[0] - 0.3, botP[1] - 0.3, 20.0, Y_NZP + 0.3, c)  # placeholder
    return c, {}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which == "tg":
        lay = Layouter("scratch")
        cell, _ = build_tg(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_tg.gds"))
        return
    if which == "chopper":
        lay = Layouter("scratch")
        cell, _ = build_chopper(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_chopper.gds"))
        return
    if which == "cmfb":
        lay = Layouter("scratch")
        c1, _ = build_cmfb(lay, 4.0, "eeg_cmfb_amp_dl2")
        lay.set_top(c1)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_cmfb.gds"))
        return
    if which == "bias":
        lay = Layouter("scratch")
        cell, _ = build_bias(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_bias.gds"))
        return
    if which == "stage2":
        lay = Layouter("scratch")
        cell, _ = build_stage2(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_stage2.gds"))
        return
    raise SystemExit("full assembly not yet wired; use a cell name")


if __name__ == "__main__":
    main()

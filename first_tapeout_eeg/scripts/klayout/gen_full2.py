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
#   XMNDA A ENB A VSS nfet W=0.42 (A-side dummy) ; XMPDA A EN A VDD pfet W=0.84
# Single row (all gates down): mn mnd mp mpd mnda mpda.  S/D straps up to
# A/B buses, gates strapped down to EN/ENB buses (with m1 offset extensions
# so the m2 verticals keep 0.3 um spacing to the S/D straps).
# ----------------------------------------------------------------------------
def build_tg(lay):
    mn = lay.make_nfet("tg_n", 0.15, 0.84, 1)
    mnd = lay.make_nfet("tg_nd", 0.15, 0.42, 1)
    mp = lay.make_pfet("tg_p", 0.15, 1.68, 1)
    mpd = lay.make_pfet("tg_pd", 0.15, 0.84, 1)
    mnda = lay.make_nfet("tg_ndA", 0.15, 0.42, 1)
    mpda = lay.make_pfet("tg_pdA", 0.15, 0.84, 1)

    tg = lay.ly.create_cell("eeg_tg_lowq")
    pos = {"mn": (mn, 0.0), "mnd": (mnd, 3.4), "mp": (mp, 6.6), "mpd": (mpd, 12.0),
           "mnda": (mnda, 15.9), "mpda": (mpda, 19.3)}
    g = {}
    for key, (cell, x) in pos.items():
        lay.place(cell, x, 0.0, into=tg)
        g[key] = fet_anchors(lay, cell, x, 0.0)
        assert len(g[key]["strips"]) == 2 and len(g[key]["g"]) == 1, key

    Y_B, Y_A = 2.6, 3.8
    Y_EN, Y_ENB, Y_VSS, Y_VDD = -2.2, -3.4, -4.6, -5.8
    for y in (Y_B, Y_A, Y_EN, Y_ENB, Y_VSS, Y_VDD):
        lay.bus_m3(-1.0, 22.0, y, cell=tg)

    # --- S/D straps up (m1 pad on strip -> via1 -> m2 -> via2 -> bus)
    lay.strap_up(*g["mn"]["strips"][0], Y_A, tg)      # A: mn.s0
    lay.strap_up(*g["mn"]["strips"][1], Y_B, tg)      # B: mn.s1
    lay.strap_up(*g["mp"]["strips"][0], Y_A, tg)      # A: mp.s0
    lay.strap_up(*g["mp"]["strips"][1], Y_B, tg)      # B: mp.s1
    # dummy S/D join bars: B-side dummies -> B, A-side dummies -> A
    for k, ybus in (("mnd", Y_B), ("mpd", Y_B), ("mnda", Y_A), ("mpda", Y_A)):
        (cx0, cy0), (cx1, cy1) = g[k]["strips"]
        yc = (cy0 + cy1) / 2
        lay.box(L_M1, min(cx0, cx1) - 0.3, yc - 0.15, max(cx0, cx1) + 0.3,
                yc + 0.15, tg)
        lay.strap_up((cx0 + cx1) / 2, yc, ybus, tg)

    # --- gates down, with m1 offset extension to a clear via column
    def gate_down(key, x_via, y_bus):
        x_pad, y_pad = g[key]["g"][0]
        lay.box(L_M1, min(x_pad, x_via) - 0.17, y_pad - 0.17,
                max(x_pad, x_via) + 0.17, y_pad + 0.17, tg)
        lay.via1(x_via, y_pad, tg)
        lay.box(L_M2, x_via - 0.19, y_bus - 0.15, x_via + 0.19, y_pad + 0.17, tg)
        lay.via2(x_via, y_bus, tg)

    gate_down("mn", -0.45, Y_EN)      # EN:  mn.g
    gate_down("mpd", 12.00, Y_EN)     # EN:  mpd.g
    gate_down("mpda", 20.80, Y_EN)    # EN:  mpda.g
    gate_down("mnd", 3.00, Y_ENB)     # ENB: mnd.g
    gate_down("mp", 9.00, Y_ENB)      # ENB: mp.g
    gate_down("mnda", 15.40, Y_ENB)   # ENB: mnda.g

    # --- guard rings: nfets -> VSS, pfets -> VDD (down straps)
    lay.tie_ring(mn, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (1.7,), into=tg)
    lay.tie_ring(mnd, kdb.Trans(0, False, u(3.4), 0), "bottom", Y_VSS, (4.3,), into=tg)
    lay.tie_ring(mp, kdb.Trans(0, False, u(6.6), 0), "bottom", Y_VDD, (6.5,), into=tg)
    lay.tie_ring(mpd, kdb.Trans(0, False, u(12.0), 0), "bottom", Y_VDD, (13.5,), into=tg)
    lay.tie_ring(mnda, kdb.Trans(0, False, u(15.9), 0), "bottom", Y_VSS, (16.6,), into=tg)
    lay.tie_ring(mpda, kdb.Trans(0, False, u(19.3), 0), "bottom", Y_VDD, (19.0,), into=tg)

    for net, y in (("A", Y_A), ("B", Y_B), ("EN", Y_EN), ("ENB", Y_ENB),
                   ("VSS", Y_VSS), ("VDD18", Y_VDD)):
        lay.label(L_M3L, net, 21.5, y, tg)

    anchors = {"A": (14.5, Y_A), "B": (13.5, Y_B),
               "EN": (14.7, Y_EN), "ENB": (11.0, Y_ENB),
               "VDD18": (14.0, Y_VDD), "VSS": (14.0, Y_VSS)}
    return tg, anchors


# ----------------------------------------------------------------------------
# eeg_cmos_chopper_lowq: INP INN OUTP OUTN PHI NPHI PHIB NPHIB VDD18 VSS
#   XSP INP OUTP PHI  NPHI  ; XSN INN OUTN PHI  NPHI
#   XCP INP OUTN PHIB NPHIB ; XCN INN OUTP PHIB NPHIB   (all eeg_tg_lowq)
# 4 TGs in a row (pitch 24).  A taps run up on m3 (A bus is the topmost TG
# bus); B/EN/ENB taps run up on m2 (they cross lower m3 buses).  Signals
# land on m4 rails; VDD18/VSS are joined by m3 rails over the TG buses.
# ----------------------------------------------------------------------------
def build_chopper(lay, name="eeg_cmos_chopper_lowq"):
    tg, a = build_tg(lay)
    ch = lay.ly.create_cell(name)
    pitch = 24.0
    ports = {}
    for k, x in (("SP", 0.0), ("SN", pitch), ("CP", 2 * pitch),
                 ("CN", 3 * pitch)):
        lay.place(tg, x, 0.0, into=ch)
        ports[k] = {net: (px + x, py) for net, (px, py) in a.items()}

    XR = 3 * pitch + 22.5   # right end of the rails (past the last via3)
    rails = {"OUTP": 13.0, "OUTN": 14.0, "INP": 15.0, "INN": 16.0,
             "PHI": 17.0, "NPHI": 18.0, "PHIB": 19.0, "NPHIB": 20.0}
    for y in rails.values():
        lay.box(L_M4, -1.0, y - 0.3, XR, y + 0.3, ch)

    def tap_m3(k, net, rail_y):
        x, y = ports[k][net]
        lay.box(L_M3, x - 0.3, y, x + 0.3, rail_y + 0.2, ch)
        lay.via3(x, rail_y, ch)

    def tap_m2(k, net, rail_y):
        x, y = ports[k][net]
        lay.via2(x, y, ch)
        lay.box(L_M2, x - 0.19, y - 0.15, x + 0.19, rail_y + 0.15, ch)
        lay.via2(x, rail_y, ch)
        lay.box(L_M3, x - 0.3, rail_y - 0.3, x + 0.3, rail_y + 0.3, ch)
        lay.via3(x, rail_y, ch)

    tap_m3("SP", "A", rails["INP"]);  tap_m3("CP", "A", rails["INP"])
    tap_m3("SN", "A", rails["INN"]);  tap_m3("CN", "A", rails["INN"])
    tap_m2("SP", "B", rails["OUTP"]); tap_m2("CN", "B", rails["OUTP"])
    tap_m2("SN", "B", rails["OUTN"]); tap_m2("CP", "B", rails["OUTN"])
    tap_m2("SP", "EN", rails["PHI"]);  tap_m2("SN", "EN", rails["PHI"])
    tap_m2("CP", "EN", rails["PHIB"]); tap_m2("CN", "EN", rails["PHIB"])
    tap_m2("SP", "ENB", rails["NPHI"]);  tap_m2("SN", "ENB", rails["NPHI"])
    tap_m2("CP", "ENB", rails["NPHIB"]); tap_m2("CN", "ENB", rails["NPHIB"])

    # VDD18 / VSS m3 rails joining the TG buses across the pitch gaps
    lay.box(L_M3, -1.0, -4.9, XR, -4.3, ch)
    lay.box(L_M3, -1.0, -6.1, XR, -5.5, ch)

    for net, y in rails.items():
        lay.label(L_M4L, net, XR - 0.5, y, ch)
    lay.label(L_M3L, "VDD18", XR - 0.5, -5.8, ch)
    lay.label(L_M3L, "VSS", XR - 0.5, -4.6, ch)

    anch = {net: (XR, y) for net, y in rails.items()}
    anch["VDD18"] = (XR, -5.8)
    anch["VSS"] = (XR, -4.6)
    anch["XR"] = (XR, 0.0)
    anch["pitch"] = (pitch, 0.0)
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
    lay.place(m10, 2.3, -9.0, into=c)
    g = {"m6": fet_anchors(lay, m6, 0.0, 0.0), "m7": fet_anchors(lay, m7, 6.0, 0.0),
         "m8": fet_anchors(lay, m8, 0.0, 8.0), "m9": fet_anchors(lay, m9, 6.0, 8.0),
         "m10": fet_anchors(lay, m10, 2.3, -9.0)}

    Y_VSNS, Y_VREF, Y_VBN, Y_VSS = -3.2, -4.2, -14.5, -15.7
    Y_NL, Y_VDD, Y_VBP = 6.5, 17.0, 18.2

    # NTAIL: m3 link below, strapped up to m6.s0 / m7.s0 and down to m10 drain
    x6s, y6s = g["m6"]["strips"][0]
    x7s, y7s = g["m7"]["strips"][0]
    x10d, y10d = g["m10"]["strips"][1]
    lay.bus_m3(x6s - 0.3, x10d + 0.3, -2.0, cell=c)
    lay.strap_down(x6s, y6s, -2.0, c)
    lay.strap_down(x7s, y7s, -2.0, c)
    lay.strap_up(x10d, y10d, -2.0, c)

    # m10 sources -> VSS, gate bar -> VBN
    for i in (0, 2):
        lay.strap_down(*g["m10"]["strips"][i], Y_VSS, c)
    gx = [p[0] for p in g["m10"]["g"]]
    gy = g["m10"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    lay.strap_down((min(gx) + max(gx)) / 2, gy, Y_VBN, c)
    lay.bus_m3(-0.5, 12.5, Y_VBN, cell=c)
    lay.bus_m3(-0.5, 12.5, Y_VSS, cell=c)

    # NLEFT: m6.s1 up to m8 diode (G-D short on m1, drain strap down to Y_NL)
    x8d, y8d = g["m8"]["strips"][1]
    x8g, y8g = g["m8"]["g"][0]
    lay.box(L_M1, x8g - 0.17, y8g - 0.17, x8d + 0.17, y8d + 0.17, c)
    lay.bus_m3(min(g["m6"]["strips"][1][0], x8d) - 0.3,
               max(g["m6"]["strips"][1][0], x8d) + 0.3, Y_NL, cell=c)
    lay.strap_up(*g["m6"]["strips"][1], Y_NL, c)
    lay.strap_down(x8d, y8d, Y_NL, c)

    # VBP: m7.s1 up + m9 diode down to Y_VBP bus
    x9d, y9d = g["m9"]["strips"][1]
    x9g, y9g = g["m9"]["g"][0]
    lay.box(L_M1, x9g - 0.17, y9g - 0.17, x9d + 0.17, y9d + 0.17, c)
    lay.bus_m3(min(g["m7"]["strips"][1][0], x9d) - 0.3, 11.8, Y_VBP, cell=c)
    lay.strap_up(*g["m7"]["strips"][1], Y_VBP, c)
    lay.strap_up(x9d, y9d, Y_VBP, c)

    # VDD18: m8.s0 / m9.s0 up + pfet rings
    lay.bus_m3(min(g["m8"]["strips"][0][0], g["m9"]["strips"][0][0]) - 0.3,
               11.8, Y_VDD, cell=c)
    lay.strap_up(*g["m8"]["strips"][0], Y_VDD, c)
    lay.strap_up(*g["m9"]["strips"][0], Y_VDD, c)
    lay.tie_ring(m8, kdb.Trans(0, False, 0, u(8.0)), "top", Y_VDD, (2.5,), into=c)
    lay.tie_ring(m9, kdb.Trans(0, False, u(6.0), u(8.0)), "top", Y_VDD, (8.5,), into=c)
    lay.tie_ring(m6, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (3.5,), into=c)
    lay.tie_ring(m7, kdb.Trans(0, False, u(6.0), 0), "bottom", Y_VSS, (5.8,), into=c)
    lay.tie_ring(m10, kdb.Trans(0, False, u(2.3), u(-9.0)), "top", Y_VSS, (10.0,), into=c)

    # VCM_SENSE / VCM_REF gate pads
    lay.bus_m3(g["m6"]["g"][0][0] - 0.3, g["m6"]["g"][0][0] + 1.8, Y_VSNS, cell=c)
    lay.strap_down(*g["m6"]["g"][0], Y_VSNS, c)
    # VCM_REF: m1 offset extension to a clear via column at x=8.5
    x7g, y7g = g["m7"]["g"][0]
    lay.bus_m3(x7g - 0.3, x7g + 1.8, Y_VREF, cell=c)
    lay.box(L_M1, x7g - 0.17, y7g - 0.17, 8.5 + 0.17, y7g + 0.17, c)
    lay.via1(8.5, y7g, c)
    lay.box(L_M2, 8.31, Y_VREF - 0.15, 8.69, y7g + 0.17, c)
    lay.via2(8.5, Y_VREF, c)

    for net, xy in (("VCM_SENSE", (g["m6"]["g"][0][0] + 1.8, Y_VSNS)),
                    ("VCM_REF", (g["m7"]["g"][0][0] + 1.8, Y_VREF)),
                    ("VBN", (12.5, Y_VBN)), ("VSS", (12.5, Y_VSS)),
                    ("VDD18", (11.8, Y_VDD)), ("VBP", (11.8, Y_VBP))):
        lay.label(L_M3L, net, *xy, c)

    anch = {"VCM_SENSE": (g["m6"]["g"][0][0] + 1.8, Y_VSNS),
            "VCM_REF": (g["m7"]["g"][0][0] + 1.8, Y_VREF),
            "VBN": (12.5, Y_VBN), "VSS": (12.5, Y_VSS),
            "VDD18": (11.8, Y_VDD), "VBP": (11.8, Y_VBP)}
    return c, anch


# ----------------------------------------------------------------------------
# eeg_dsl GP GN VCM_REF VDD18 VSS  (DC servo loop, see schematic comments)
# nfet row at y=0 (all gates down), pfet row at y=8, RB1 row at y=-35,
# CINT MIM array (10x16 of 12.5x12.5 -> A=25000 um2, 50 pF) below.
# Buses (m3): above: SAVG SREF VBDSL VBPDSL ST D1 VDD18 VCTL
#             below: VSS GP GN VCM_REF
# ----------------------------------------------------------------------------
def build_dsl(lay):
    spec_n = (  # (key, L, W)
        ("mf1", 2.0, 2.0), ("mf2", 2.0, 2.0), ("mfr", 2.0, 2.0),
        ("mt1", 8.0, 0.5), ("mt2", 8.0, 0.5), ("mtr", 8.0, 1.0),
        ("mb", 8.0, 2.0), ("mbb", 8.0, 1.0),
        ("mm1", 4.0, 2.0), ("mm2", 4.0, 2.0),
        ("ms1", 4.0, 1.0), ("ms2", 4.0, 1.0),
    )
    spec_p = (("mpb", 4.0, 4.0), ("mtl", 4.0, 8.0),
              ("me1", 2.0, 4.0), ("me2", 2.0, 4.0))
    devs = {}
    for k, l, w in spec_n:
        devs[k] = lay.make_nfet("dsl_" + k, l, w, 1)
    for k, l, w in spec_p:
        devs[k] = lay.make_pfet("dsl_" + k, l, w, 1)

    c = lay.ly.create_cell("eeg_dsl")
    g = {}
    x = 0.0
    for k, l, w in spec_n:
        lay.place(devs[k], x, 0.0, into=c)
        g[k] = fet_anchors(lay, devs[k], x, 0.0)
        x += devs[k].bbox().right / 1000.0 + 1.0
    xn_right = x - 1.0
    xp = xn_right + 2.0
    for k, l, w in spec_p:
        lay.place(devs[k], xp, 8.0, into=c)
        g[k] = fet_anchors(lay, devs[k], xp, 8.0)
        xp += devs[k].bbox().right / 1000.0 + 1.0
    XBUS = max(56.0, xn_right + 1.0, xp)

    # buses above (m3); VDD18/VBDSL reach the RB1 bank at x=107..145
    buses = {"SAVG": 18.2, "SREF": 19.4, "VBDSL": 20.6, "VBPDSL": 21.8,
             "ST": 23.0, "D1": 24.2, "VDD18": 25.4, "VCTL": 26.6,
             "VSS": -2.5, "GP": -3.7, "GN": -4.9, "VCM_REF": -6.1}
    for net, y in buses.items():
        x1 = 175.3 if net in ("VDD18", "VBDSL") else XBUS
        if net == "VSS":
            lay.bus_m3(-2.3, x1, y, cell=c)
        else:
            lay.bus_m3(-1.0, x1, y, cell=c)

    def sd_up(key, i, net):
        lay.strap_up(*g[key]["strips"][i], buses[net], c)

    def sd_down(key, i, net):
        lay.strap_down(*g[key]["strips"][i], buses[net], c)

    def gate_strap(key, net, up=True):
        """Gate pad -> m1 offset extension (0.75 um left of the gate) ->
        via1 -> m2 -> bus."""
        x_pad, y_pad = g[key]["g"][0]
        x_via = x_pad - 0.75
        lay.box(L_M1, min(x_pad, x_via) - 0.17, y_pad - 0.17,
                max(x_pad, x_via) + 0.17, y_pad + 0.17, c)
        lay.via1(x_via, y_pad, c)
        if up:
            lay.box(L_M2, x_via - 0.19, y_pad - 0.17, x_via + 0.19,
                    buses[net] + 0.15, c)
        else:
            lay.box(L_M2, x_via - 0.19, buses[net] - 0.15, x_via + 0.19,
                    y_pad + 0.17, c)
        lay.via2(x_via, buses[net], c)

    # nfet row
    sd_up("mf1", 0, "SAVG"); sd_up("mf1", 1, "VDD18"); gate_strap("mf1", "GP", False)
    sd_up("mf2", 0, "SAVG"); sd_up("mf2", 1, "VDD18"); gate_strap("mf2", "GN", False)
    sd_up("mfr", 0, "SREF"); sd_up("mfr", 1, "VDD18"); gate_strap("mfr", "VCM_REF", False)
    sd_down("mt1", 0, "VSS"); sd_up("mt1", 1, "SAVG"); gate_strap("mt1", "VBDSL")
    sd_down("mt2", 0, "VSS"); sd_up("mt2", 1, "SAVG"); gate_strap("mt2", "VBDSL")
    sd_down("mtr", 0, "VSS"); sd_up("mtr", 1, "SREF"); gate_strap("mtr", "VBDSL")
    sd_down("mb", 0, "VSS"); sd_up("mb", 1, "VBDSL"); gate_strap("mb", "VBDSL")
    # XMBB: D=VBPDSL, G=VBDSL (do not swap!)
    sd_down("mbb", 0, "VSS"); sd_up("mbb", 1, "VBPDSL"); gate_strap("mbb", "VBDSL")
    sd_down("mm1", 0, "VSS"); sd_up("mm1", 1, "D1"); gate_strap("mm1", "D1")
    sd_down("mm2", 0, "VSS"); sd_up("mm2", 1, "VCTL"); gate_strap("mm2", "D1")
    sd_down("ms1", 0, "VSS"); sd_down("ms1", 1, "GP"); gate_strap("ms1", "VCTL")
    sd_down("ms2", 0, "VSS"); sd_down("ms2", 1, "GN"); gate_strap("ms2", "VCTL")
    # pfet row
    sd_up("mpb", 0, "VDD18"); sd_up("mpb", 1, "VBPDSL"); gate_strap("mpb", "VBPDSL")
    sd_up("mtl", 0, "VDD18"); sd_up("mtl", 1, "ST"); gate_strap("mtl", "VBPDSL")
    sd_up("me1", 0, "ST"); sd_up("me1", 1, "D1"); gate_strap("me1", "SAVG")
    sd_up("me2", 0, "ST"); sd_up("me2", 1, "VCTL"); gate_strap("me2", "SREF")

    # guard rings: nfets -> VSS, pfets -> VDD18 (ties at gate_x + 0.75,
    # clear of the gate m1 extensions and the S/D straps)
    x = 0.0
    for k, l, w in spec_n:
        bb = devs[k].bbox()
        cx = g[k]["g"][0][0] + 0.75
        lay.tie_ring(devs[k], kdb.Trans(0, False, u(x), 0), "bottom",
                     buses["VSS"], (cx,), into=c)
        x += bb.right / 1000.0 + 1.0
    xp = xn_right + 2.0
    for k, l, w in spec_p:
        bb = devs[k].bbox()
        cx = g[k]["g"][0][0] + 0.75
        # ME1/ME2 nwells tie to ST (schematic bulk=ST); MPB/MTL to VDD18
        bus = buses["ST"] if k in ("me1", "me2") else buses["VDD18"]
        lay.tie_ring(devs[k], kdb.Trans(0, False, u(xp), u(8.0)), "top",
                     bus, (cx,), into=c)
        xp += bb.right / 1000.0 + 1.0

    # --- RB1: 2 Meg (20 x 100k segments), row at y=-35, clear of the FETs
    seg100 = lay.make_res_seg(34.38)
    ra, rb = lay.res_bank(c, 137.0, -35.0, 20, seg100)
    lay.strap_up(*ra, buses["VDD18"], c)
    lay.strap_up(*rb, buses["VBDSL"], c)

    # --- CINT: 50 pF MIM (10x16 of 12.5x12.5), below at y=-350
    bot, top, area, perim = lay.mim_array(c, 0.0, -350.0, 10, 16, cw=12.5, ch=12.5)
    for yy in (-349.6, -348.9):
        lay.via2(-2.0, yy, c)
    lay.box(L_M2, -2.19, -349.75, -1.81, buses["VSS"] + 0.15, c)
    lay.via2(-2.0, buses["VSS"], c)
    xm = top[0]
    lay.box(L_M4, xm - 1.6, top[1], xm + 1.6, buses["VCTL"] + 0.9, c)
    lay.via3(xm, buses["VCTL"] + 0.7, c)
    lay.box(L_M3, xm - 0.3, buses["VCTL"] - 0.3, xm + 0.3, buses["VCTL"] + 1.0, c)

    # label only the port buses: every label becomes a cell pin for LVS
    for net in ("GP", "GN", "VCM_REF", "VDD18", "VSS"):
        lay.label(L_M3L, net, XBUS - 0.5, buses[net], c)
    anch = {net: (XBUS, y) for net, y in buses.items()}
    return c, anch


# ----------------------------------------------------------------------------
# eeg_bias_gen: VBN VBNF VBP VDD18 VSS
#   XMP1 VBN VBP VDD18 pfet L=4 W=10 nf=2 ; XMN1 VBN VBN VSS nfet W=10 nf=2 (diode)
#   XMP2 VBP VBP VDD18 pfet W=10 nf=2 (diode) ; XMN2 VBP VBN SNS2 VSS nfet W=40 nf=8
#   RSET SNS2 VSS 25k ; RSTART VDD18 VBN eeg_pseudo_res ; RF VBN VBNF 10Meg ;
#   CF VBNF VSS 100p      (RSTART/RFILT/CFILT changed 2026-09-11, see canonical
#   source/trials/20260902/xschem/eeg_bias_gen.spice)
# ----------------------------------------------------------------------------
def build_bias(lay):
    mp1 = lay.make_pfet("bg_mp1", 4.0, 5.0, 2)
    mn1 = lay.make_nfet("bg_mn1", 4.0, 5.0, 2)
    mp2 = lay.make_pfet("bg_mp2", 4.0, 5.0, 2)
    mn2 = lay.make_nfet("bg_mn2", 4.0, 5.0, 8)

    c = lay.ly.create_cell("eeg_bias_gen")

    # FET row at y=0: nfets left, pfets right; x from actual cell bboxes
    # (W=10/nf=2 cells are ~11 um wide, W=40/nf=8 ~42 um: do not guess)
    XMN1 = 0.0
    XMN2 = XMN1 + mn1.bbox().right / 1000.0 + 1.0
    XMP1 = XMN2 + mn2.bbox().right / 1000.0 + 1.0
    XMP2 = XMP1 + mp1.bbox().right / 1000.0 + 1.0
    XR4 = XMP2 + mp2.bbox().right / 1000.0
    lay.place(mn1, XMN1, 0.0, into=c)
    lay.place(mn2, XMN2, 0.0, into=c)
    lay.place(mp1, XMP1, 0.0, into=c)
    lay.place(mp2, XMP2, 0.0, into=c)
    g = {"mn1": fet_anchors(lay, mn1, XMN1, 0.0),
         "mn2": fet_anchors(lay, mn2, XMN2, 0.0),
         "mp1": fet_anchors(lay, mp1, XMP1, 0.0),
         "mp2": fet_anchors(lay, mp2, XMP2, 0.0)}

    # buses (m3): VBN 8.0, VBP 9.2, SNS2 10.4 above; VSS -3.5 below; VDD 13.5
    # top.  VBN reaches the XRSTART B link (x=90), VDD its A link (x=96).
    Y_VBN, Y_VBP, Y_SNS2, Y_VSS, Y_VDD, Y_VBNF = 8.0, 9.2, 10.4, -3.5, 13.5, 6.8
    XBUS = XR4 + 1.0
    lay.bus_m3(-1.0, 90.5, Y_VBN, cell=c)
    lay.bus_m3(-1.0, XBUS, Y_VBP, cell=c)
    lay.bus_m3(-1.0, XBUS, Y_SNS2, cell=c)
    lay.bus_m3(-2.3, XBUS, Y_VSS, cell=c)
    lay.bus_m3(-1.0, 96.5, Y_VDD, cell=c)
    lay.bus_m3(20.0, XBUS, Y_VBNF, cell=c)

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
    # (gate strap midway between the s0/s1 strip columns: on a strip
    # column the two m2 straps merge -> VBN/SNS2/VBP short)
    gx = [p[0] for p in g["mn2"]["g"]]
    gy = g["mn2"]["g"][0][1]
    lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
    xs = [p[0] for p in g["mn2"]["strips"]]
    lay.strap_up((xs[0] + xs[1]) / 2, gy, Y_VBN, c)
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
    lay.tie_ring(mn1, kdb.Trans(0, False, u(XMN1), 0), "bottom", Y_VSS, (XMN1 + 2.0,), into=c)
    lay.tie_ring(mn2, kdb.Trans(0, False, u(XMN2), 0), "bottom", Y_VSS, (XMN2 + 2.0,), into=c)
    lay.tie_ring(mp1, kdb.Trans(0, False, u(XMP1), 0), "top", Y_VDD, (XMP1 + 2.0,), into=c)
    lay.tie_ring(mp2, kdb.Trans(0, False, u(XMP2), 0), "top", Y_VDD, (XMP2 + 2.0,), into=c)

    # --- resistors ---------------------------------------------------------
    seg25 = lay.make_res_seg(8.505)    # 25 kohm exactly
    seg100 = lay.make_res_seg(34.38)   # 100 kohm exactly

    # RSET: single segment below mp2; top pad (y=-24.67) -> SNS2, bottom
    # pad (y=-35.33) -> VSS.  NOTE: the 25k segment is short — its pads
    # are at +/-5.33 um, not +/-18.27 like the 100k segments.
    # (bottom route jogs left on m3: two collinear m2s at the segment x
    # would overlap and short the resistor)
    RSET_X = XR4 - 8.0
    lay.place(seg25, RSET_X, -30.0, into=c)
    lay.strap_up(RSET_X, -30.0 + 5.33, Y_SNS2, c)    # long strap ok (m2 over m3)
    lay.via1(RSET_X, -30.0 - 5.33, c)
    lay.box(L_M1, RSET_X - 0.17, -30.0 - 5.50, RSET_X + 0.17, -30.0 - 5.16, c)
    lay.box(L_M2, RSET_X - 0.19, -50.65, RSET_X + 0.19, -30.0 - 5.16, c)
    lay.via2(RSET_X, -50.5, c)
    lay.box(L_M3, RSET_X - 3.0 - 0.3, -50.8, RSET_X + 0.3, -50.2, c)
    lay.via2(RSET_X - 3.0, -50.5, c)
    lay.box(L_M2, RSET_X - 3.0 - 0.19, -50.65, RSET_X - 3.0 + 0.19,
            Y_VSS + 0.15, c)
    lay.via2(RSET_X - 3.0, Y_VSS, c)

    # RFILT: 100 segments (10 Meg), 5 rows x 20 anchored (20, -206.88) so the
    # top row sits at the old y=-30: start pad (20, -188.61) -> VBN (the m2
    # strap crosses the bank — m2 over the res cells is free, same as the old
    # RSTART a-strap), end pad (58, -11.73) -> VBNF.
    rf_a, rf_b = lay.res_bank(c, 20.0, -206.88, 100, seg100, ncols=20)
    lay.strap_up(rf_a[0], rf_a[1], Y_VBN, c)
    lay.strap_up(rf_b[0], rf_b[1], Y_VBNF, c)

    # RSTART: 20Meg resistor -> eeg_pseudo_res (2026-09-11, startup verified
    # in simulation).  A=VDD18, B=VBN; the guard rings tie to the A/B buses
    # internally (floating nwells — NO supply wiring).  Placed east of the
    # FET row, high enough that the cell's M-link vertical (west edge, local
    # y -3.085..3.745) clears the VDD bus top (13.8) by >0.3.  Links rise on
    # m2 from the VDD/VBN bus ends to the A/B buses, in columns clear of the
    # cell's own m2 (gate downs at local x 3.43..3.81 / 13.39..13.77, source
    # straps at 0.32..0.7 / 5.34..5.72 / 10.28..10.66 / 15.3..15.68).
    # WEST EDGE MUST STAY EAST OF x=87: the parents' VDD18 m3 riser runs at
    # abs x 984.2..984.8 (bias-local 84.2..84.8) straight through y13.5..70 —
    # a cell at x=85 puts its M-link/B bus right under it (m3 over m3 merge:
    # M/VBN shorted to VDD18).
    pr, pr_a = build_pseudo_res(lay)
    lay.place(pr, 88.0, 17.5, into=c)            # XRSTART
    lay.join_m3_m2(96.0, Y_VDD, 17.5 + pr_a["A"][1], c)   # A <- VDD18
    lay.join_m3_m2(90.0, Y_VBN, 17.5 + pr_a["B"][1], c)   # B <- VBN

    # --- CFILT: 100 pF MIM array (5x25 of 20x20, 125 units) below everything
    bot, top, area, perim = lay.mim_array(c, 0.0, -790.0, 5, 25)
    # bottom plate -> VSS: via2s on the m3 tab, then m2 up to the VSS bus
    # (an m3 column would trip m3.3ab where it meets the huge bottom sheet)
    for yy in (-789.8, -789.1):
        lay.via2(-2.0, yy, c)
    lay.box(L_M2, -2.19, -790.0, -1.81, Y_VSS + 0.15, c)
    lay.via2(-2.0, Y_VSS, c)
    # top plate tab (m4, at array center xm) -> 3.2-wide m4 column up ->
    # via3 straight onto the VBNF bus: the m3 pad (6.5..7.3) merges the bus
    # and encloses the via by 0.2 on every side, while staying 0.4 clear of
    # the VBN bus bottom (7.7).  (The old stub-to-7.8 + east link worked
    # when xm=280 was east of the VBN bus end; at xm=55 it would overlap
    # the VBN bus and short VBNF to VBN.)  The m4 column crosses the RFILT
    # bank and the buses — m4 is free over all of them.
    xm = top[0]
    lay.box(L_M4, xm - 1.6, top[1], xm + 1.6, Y_VBNF + 0.9, c)
    lay.via3(xm, Y_VBNF + 0.2, c)
    lay.box(L_M3, xm - 0.3, Y_VBNF - 0.3, xm + 0.3, Y_VBNF + 0.5, c)

    for net, xy in (("VBN", (87.0, Y_VBN)), ("VBP", (XBUS, Y_VBP)),
                    ("VDD18", (84.5, Y_VDD)), ("VSS", (XBUS, Y_VSS)),
                    ("VBNF", (XBUS, Y_VBNF))):
        lay.label(L_M3L, net, *xy, c)

    anch = {"VBN": (87.0, Y_VBN), "VBP": (XBUS, Y_VBP), "VDD18": (84.5, Y_VDD),
            "VSS": (XBUS, Y_VSS), "VBNF": (XBUS, Y_VBNF)}
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
    # m23/m24 are ~103 um wide (8 fingers at L=12 pitch): place by bbox
    X2 = max(m21.bbox().right, m23.bbox().right) / 1000.0 + 1.0
    XR = X2 + m24.bbox().right / 1000.0
    lay.place(m21, 0.0, 0.0, into=c)
    lay.place(m23, 0.0, 14.0, into=c)
    lay.place(m22, X2, 0.0, into=c)
    lay.place(m24, X2, 14.0, into=c)
    g = {"m21": fet_anchors(lay, m21, 0.0, 0.0), "m22": fet_anchors(lay, m22, X2, 0.0),
         "m23": fet_anchors(lay, m23, 0.0, 14.0), "m24": fet_anchors(lay, m24, X2, 14.0)}

    Y_N2P, Y_N2N, Y_VSS = -3.5, -4.7, -5.9
    Y_OUTP, Y_OUTN, Y_VBP2, Y_VDD = 24.0, 25.2, 26.4, 27.6
    Y_VCM2, Y_VCMR = 22.0, 23.0
    XF = XR + 1.0

    lay.bus_m3(-2.0, XF, Y_N2P, cell=c)
    lay.bus_m3(-2.0, XF, Y_N2N, cell=c)
    lay.bus_m3(-2.0, XF, Y_VSS, cell=c)
    lay.bus_m3(-2.0, 320.3, Y_OUTP, cell=c)   # reaches CC tab (98) + RL1a (320)
    lay.bus_m3(-2.0, 370.3, Y_OUTN, cell=c)   # reaches CCN tab (238) + RL2a (370)
    lay.bus_m3(-2.0, XF, Y_VBP2, cell=c)
    lay.bus_m3(-2.0, XF, Y_VDD, cell=c)
    lay.bus_m3(100.0, 415.0, Y_VCM2, cell=c)
    lay.bus_m3(100.0, 415.0, Y_VCMR, cell=c)

    for key, y_g, y_d in (("m21", Y_N2P, Y_OUTP), ("m22", Y_N2N, Y_OUTN)):
        gx = [p[0] for p in g[key]["g"]]
        gy = g[key]["g"][0][1]
        lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
        # gate strap on the first gate column (midway between s0/s1 strip
        # columns: a centered strap would merge with the drain strap)
        lay.strap_down(gx[0], gy, y_g, c)
        for i, (x, y) in enumerate(g[key]["strips"]):
            if i % 2 == 1:      # drains
                lay.strap_up(x, y, y_d, c)
            else:               # sources -> VSS
                lay.strap_down(x, y, Y_VSS, c)
    for key in ("m23", "m24"):
        y_d = Y_OUTP if key == "m23" else Y_OUTN
        gx = [p[0] for p in g[key]["g"]]
        gy = g[key]["g"][0][1]
        lay.box(L_M1, min(gx) - 2.0, gy - 0.17, max(gx) + 2.0, gy + 0.17, c)
        lay.strap_up(gx[0], gy, Y_VBP2, c)
        for i, (x, y) in enumerate(g[key]["strips"]):
            if i % 2 == 1:
                lay.strap_up(x, y, y_d, c)
            else:
                lay.strap_up(x, y, Y_VDD, c)

    lay.tie_ring(m21, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS, (2.0,), into=c)
    lay.tie_ring(m22, kdb.Trans(0, False, u(X2), 0), "bottom", Y_VSS, (X2 + 2.0,), into=c)
    lay.tie_ring(m23, kdb.Trans(0, False, 0, u(14.0)), "top", Y_VDD, (2.0,), into=c)
    lay.tie_ring(m24, kdb.Trans(0, False, u(X2), u(14.0)), "top", Y_VDD, (X2 + 2.0,), into=c)

    # --- RCMO / RLOADO banks (row at y=-60, right of the fets) -------------
    seg100 = lay.make_res_seg(34.38)
    rcmo1a, rcmo1b = lay.res_bank(c, 100.0, -60.0, 50, seg100)
    rcmo2a, rcmo2b = lay.res_bank(c, 210.0, -60.0, 50, seg100)
    rl1a, rl1b = lay.res_bank(c, 320.0, -60.0, 20, seg100)
    rl2a, rl2b = lay.res_bank(c, 370.0, -60.0, 20, seg100)
    lay.strap_up(*rcmo1a, Y_OUTP, c)
    lay.strap_up(*rcmo1b, Y_VCM2, c)
    lay.strap_up(*rcmo2a, Y_OUTN, c)
    lay.strap_up(*rcmo2b, Y_VCM2, c)
    lay.strap_up(*rl1a, Y_OUTP, c)
    lay.strap_up(*rl1b, Y_VCMR, c)
    lay.strap_up(*rl2a, Y_OUTN, c)
    lay.strap_up(*rl2b, Y_VCMR, c)

    # --- Miller RZ + CC ----------------------------------------------------
    segrz = lay.make_res_seg(6.78)   # 20 kohm exactly
    rz_top, rz_bot = lay.res_pads(segrz)
    # CCP/CCN: MIM arrays 5x4 of 20x12.5 (A=5000 um2 -> 10 pF at 2 fF/um2)
    botP, topP, a1, p1 = lay.mim_array(c, 100.0, -140.0, 5, 4, cw=20.0, ch=12.5)
    botN, topN, a2, p2 = lay.mim_array(c, 240.0, -140.0, 5, 4, cw=20.0, ch=12.5)
    Y_NZP, Y_NZN = -35.0, -37.4
    lay.bus_m3(19.7, topP[0] + 0.3, Y_NZP, cell=c)
    lay.bus_m3(64.7, topN[0] + 0.3, Y_NZN, cell=c)

    for xz, y_g, y_nz in ((20.0, Y_N2P, Y_NZP), (65.0, Y_N2N, Y_NZN)):
        lay.place(segrz, xz, -25.0, into=c)
        lay.strap_up(xz, -25.0 + rz_top, y_g, c)       # top pad -> N2x bus
        lay.via1(xz, -25.0 + rz_bot, c)                # bottom pad -> NZx bus
        lay.box(L_M1, xz - 0.17, -25.0 + rz_bot - 0.17, xz + 0.17,
                -25.0 + rz_bot + 0.17, c)
        lay.box(L_M2, xz - 0.19, y_nz - 0.15, xz + 0.19,
                -25.0 + rz_bot + 0.17, c)
        lay.via2(xz, y_nz, c)

    # CC top plate tabs (m4) -> 3.2-wide m4 columns -> via3 -> NZx buses
    for top, y_nz in ((topP, Y_NZP), (topN, Y_NZN)):
        xm = top[0]
        lay.box(L_M4, xm - 1.6, top[1], xm + 1.6, y_nz + 0.2, c)
        lay.via3(xm, y_nz, c)
    # CC bottom plate tabs -> via2 + m2 up to OUTP/OUTN
    for bot, y_out in ((botP, Y_OUTP), (botN, Y_OUTN)):
        xb = bot[0]
        for yy in (-139.6, -138.8):
            lay.via2(xb, yy, c)
        lay.box(L_M2, xb - 0.19, -139.75, xb + 0.19, y_out + 0.15, c)
        lay.via2(xb, y_out, c)

    for net, xy in (("N2P", (XF, Y_N2P)), ("N2N", (XF, Y_N2N)),
                    ("VSS", (XF, Y_VSS)), ("VBP2", (XF, Y_VBP2)),
                    ("VDD18", (XF, Y_VDD)), ("OUTP", (320.3, Y_OUTP)),
                    ("OUTN", (370.3, Y_OUTN)), ("VCM2", (415.0, Y_VCM2)),
                    ("VCM_REF", (415.0, Y_VCMR))):
        lay.label(L_M3L, net, *xy, c)

    anch = {"N2P": (XF, Y_N2P), "N2N": (XF, Y_N2N), "VSS": (XF, Y_VSS),
            "VBP2": (XF, Y_VBP2), "VDD18": (XF, Y_VDD),
            "OUTP": (320.3, Y_OUTP), "OUTN": (370.3, Y_OUTN),
            "VCM2": (415.0, Y_VCM2), "VCM_REF": (415.0, Y_VCMR)}
    return c, anch


# ----------------------------------------------------------------------------
# top assembly: eeg_fd_ota_chopped_full2
#
# Floorplan (abs um):
#   XCHIN  (-370,0)    CORE (0,0)          XCHMID (330,0)
#   XCM1   (150,54)    XCM2  (700,54)      stage2 (430,-25)   XBG (900,0)
#
# Routing rules of thumb (hard-won):
#   - m4 verticals/horizontals cross m3 freely, m3 crosses m4 trunks freely,
#     but same-layer crossings of different nets are fatal.
#   - trunks are m4 horizontals; drops are m3 verticals (safe over m4) with
#     via3 at the ends; over block internals use m4 (safe over m3).
#   - VOS1 (INP_M -> INP_MX, DVOS=0) is a direct wire in layout.
# ----------------------------------------------------------------------------
def build_top(lay):
    chop, ch_a = build_chopper(lay)
    cm1, cm1_a = build_cmfb(lay, 4.0, "eeg_cmfb_amp_dl2")
    cm2, cm2_a = build_cmfb(lay, 0.5, "eeg_cmfb_amp_dl2_s2")
    bg, bg_a = build_bias(lay)
    st2, st2_a = build_stage2(lay)
    lay.ly.read(CORE_GDS)     # merge the verified core (no name collisions)
    core = lay.ly.cell("eeg_fd_ota_core_soft")

    top = lay.ly.create_cell("eeg_fd_ota_chopped_full2")
    P = {"chin": (-400.0, 0.0), "core": (0.0, 0.0), "chmid": (330.0, 0.0),
         "cm1": (150.0, 54.0), "cm2": (700.0, 54.0),
         "st2": (430.0, -25.0), "bg": (900.0, 0.0)}
    lay.place(chop, *P["chin"], into=top)
    lay.place(core, *P["core"], into=top)
    lay.place(chop, *P["chmid"], into=top)
    lay.place(cm1, *P["cm1"], into=top)
    lay.place(cm2, *P["cm2"], into=top)
    lay.place(st2, *P["st2"], into=top)
    lay.place(bg, *P["bg"], into=top)

    XF2 = 430.0 + st2_a["N2P"][0]      # stage2 bus end x (abs)
    XBUS_BG = 900.0 + bg_a["VSS"][0]   # bias bus end x (abs)
    CHW = ch_a["XR"][0]                # chopper rail end (local)
    CHIN_R = P["chin"][0] + CHW        # XCHIN rail end (abs)
    CHMID_R = P["chmid"][0] + CHW      # XCHMID rail end (abs)

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

    # ---- left-edge pins + input-chopper signal hops ---------------------
    XL = P["chin"][0] - 1.0
    for net, y in (("INP", 15.0), ("INN", 16.0), ("PHII", 17.0),
                   ("NPHII", 18.0), ("PHIBI", 19.0), ("NPHIBI", 20.0)):
        lay.label(L_M4L, net, XL + 1.0, y, top)
    # mid-chopper clock feeds (pins at the left edge)
    for net, yf, xd, yr in (("PHIM", 80.0, 343.0, 17.0), ("NPHIM", 81.0, 346.0, 18.0),
                            ("PHIBM", 82.0, 349.0, 19.0), ("NPHIBM", 83.0, 355.0, 20.0)):
        h4(yf, XL, xd)
        via3(xd, yf)
        v3m(xd, yr - 0.3, yf + 0.3)
        via3(xd, yr)
        lay.label(L_M4L, net, XL, yf, top)

    # INP_M: XCHIN.OUTP rail (y13) -> core.INP rail (15.6..16.2, via3 at 103).
    # The hop dips to y=9.9 and runs EAST under everything: R2's x=-112
    # descent (y11..14) and R2's y=11 hop block any direct m4 path, and the
    # core's OUTP-rail m3 extension (y13.0..13.6 to x=-298.5) plus the N1P
    # tap verticals (x=+/-240/292, y13..18.3) block every m3 approach.
    # The rise at x=103 is east of R2's x=100 vertical (clear by 2.4).
    via3(CHIN_R, 12.9)
    h4(12.9, CHIN_R - 0.1, -304.5)
    v4m(-304.8, 9.9, 12.9)
    h4(9.9, -304.8, 103.0)
    v4m(103.0, 9.9, 15.9)
    via3(103.0, 15.9)
    # INN_M: XCHIN.OUTN rail (y14) -> core.INN (100,14.6 m3)
    h4(14.0, CHIN_R - 0.1, -112.0)
    v4m(-112.0, 11.0, 14.0)
    h4(11.0, -112.0, 100.0)
    v4m(100.0, 11.0, 14.75)
    via3(100.0, 14.6)
    pad3(100.0, 14.6)

    # ---- core -> mid chopper --------------------------------------------
    # N1P: core.OUTP (-110,13.3) -> hop y13.3 -> rise x=-109 -> hop y45 ->
    # XCHMID.INP rail (y15), drop at x=347.5 (clear of A-tap + clock drops)
    pad3(-110.0, 13.3); via3(-110.0, 13.3)
    h4(13.3, -110.0, -109.0); v4m(-109.0, 13.3, 45.0)
    h4(45.0, -110.0, 347.5)
    via3(347.5, 45.0); v3m(347.5, 15.0, 45.3); via3(347.5, 15.0)
    # N1N: core.OUTN (110,12.0) -> rise to y43.5 (under R3's y45 hop) ->
    # hop east -> over R3's hop end at x=350.5 -> y47 -> descend EAST of
    # XCHMID's m4 rails (end 424.5) and merge the INN rail end on m4.
    # A straight y12 m4 hop crossed XCM1's VSS drop (m4 x=162.5,-12..38.3);
    # m3 hops are blocked by XCHMID's rail-feed verticals (x344.5/368.5).
    pad3(110.0, 12.0); via3(110.0, 12.0)
    v4m(110.0, 12.0, 43.5)
    h4(43.5, 110.0, 350.5)
    v4m(350.5, 43.5, 47.0)
    h4(47.0, 350.5, 426.5)
    v4m(426.5, 16.0, 47.0)
    h4(16.0, 424.4, 426.8)

    # ---- mid chopper -> stage2 (enter N2P/N2N from the left) --------------
    # N2P (upper bus) drops EAST of N2N (lower bus): N2N's m3 drop must not
    # cross N2P's jog above it, and N2N's jog passes under N2P's drop.
    # BOTH drops must fit between XCHMID's m3 buses (end at CHMID_R) and
    # stage2's m3 buses (start at 428): N2N at 425.2, N2P at 426.2 (0.4
    # clear on both sides).  An earlier drop at 420 crossed XCHMID's
    # VDD/VSS/EN/ENB/A/B buses; one at 427.5 sat 0.2 from stage2's buses.
    h4(13.0, CHMID_R, 426.2)
    via3(426.2, 13.0); v3m(426.2, -28.5, 13.3); h3(-28.5, 425.9, 430.0)
    h4(14.0, CHMID_R, 425.2)
    via3(425.2, 14.0); v3m(425.2, -29.7, 14.3); h3(-29.7, 424.9, 430.0)

    # ---- VDD18 trunk (m4 y=70) -------------------------------------------
    # chopper VDD drops jog WEST past the rail ends first: a straight m3
    # drop from the VDD rail would cross the VSS rail (m3, 1.2 um above).
    h4(70.0, -405.3, 984.8)
    h3(-5.8, -405.3, -401.0)
    v3m(-405.0, -5.8, 70.3); via3(-405.0, 70.0)
    h3(-5.8, 324.7, 332.0)
    v3m(325.0, -5.8, 70.3); via3(325.0, 70.0)
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
    # East end stops at 950.0: >=3.0 clear of the CFILT top-plate m4 column
    # (abs 953.4..956.6, rising from the 100p array) — a crossing would
    # short VSS to VBNF (m4 over m4), and even a <3 um gap would notch
    # under m4.5ab's 1.5 um closing.  The bias VSS tap riser moves west to
    # 948.5 accordingly.  (ota_nc keeps the same numbers: gen_afe_top taps
    # this trunk through the SDM at SDM-local (1300,1388) = here (950,-12).)
    h4(-12.0, -400.3, 950.0)
    pad3(-400.0, -4.6); via3(-400.0, -4.6); v4m(-400.0, -12.15, -4.6)
    pad3(332.0, -4.6); via3(332.0, -4.6); v4m(332.0, -12.15, -4.6)
    pad3(0.0, -6.1); via3(0.0, -6.1); v4m(0.0, -12.15, -6.1)
    pad3(162.5, 38.3); via3(162.5, 38.3); v4m(162.5, -12.15, 38.3)
    pad3(712.5, 38.3); via3(712.5, 38.3); v4m(712.5, -12.15, 38.3)
    pad3(XF2, -30.9); via3(XF2, -30.9); v4m(XF2, -30.9, -11.85)
    pad3(948.5, -3.5); via3(948.5, -3.5); v4m(948.5, -12.15, -3.5)
    lay.label(L_M4L, "VSS", 400.0, -12.0, top)

    # ---- VBN trunk (m4 y=72) ----------------------------------------------
    # CMFB VBN/VCM_REF drops jog out from under the blocks' VDD/VBP buses
    # (abs y 71.0/72.2): an m3 drop through them would merge VBN->VDD/VBP.
    h4(72.0, 147.8, 986.3)
    # core VBN (0,-14.365 m1): full stack up, east at y-17, up at x=460
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
    # bias VBNF (filtered output) -> trunk: m4 hop east of the VDD18 trunk
    # end (984.8), then the rise (the rise must not cross the VDD18 trunk —
    # m4 over m4 would merge; the old x=1070 riser dated from the 20Meg
    # RSTART bank / 162-long VBNRAW bus)
    pad3(XBUS_BG, 6.8); via3(XBUS_BG, 6.8)
    h4(6.8, XBUS_BG, 986.0); v4m(986.0, 6.8, 72.3)

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
    # (pad3-only taps at the core rails: a via3 there would punch into the
    #  VDD m4 vertical at x=0)
    # XCM1 end: land the via3 directly on the VCM_SENSE bus and rise on m4.
    # An m3 rise at x=153.77 crosses XCM1's internal NTAIL link (m3, abs
    # y51.7..52.3) and NLEFT pad (m3, abs y60.2..60.8): VCM1 shorted to both
    # (phantom pins $5/$6 on the W9=4 cmfb cell).
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
    lay.label(L_M3L, "OUTP", 430.0 + st2_a["OUTP"][0], -25.0 + st2_a["OUTP"][1], top)
    lay.label(L_M3L, "OUTN", 430.0 + st2_a["OUTN"][0], -25.0 + st2_a["OUTN"][1], top)

    return top


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which is None:
        lay = Layouter("scratch")
        cell = build_top(lay)
        lay.set_top(cell)
        lay.finish(OUT_GDS)
        return
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
    if which == "cmfb2":
        lay = Layouter("scratch")
        c2, _ = build_cmfb(lay, 0.5, "eeg_cmfb_amp_dl2_s2")
        lay.set_top(c2)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_cmfb2.gds"))
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
    if which == "dsl":
        lay = Layouter("scratch")
        cell, _ = build_dsl(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_dsl.gds"))
        return
    raise SystemExit("full assembly not yet wired; use a cell name")


if __name__ == "__main__":
    main()

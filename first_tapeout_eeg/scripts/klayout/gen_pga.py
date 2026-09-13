#!/usr/bin/env python3
"""
Batch layout generator for the chopped PGA front-end (subckt eeg_afe_pga),
sky130A.

    scripts/klayout/.venv/bin/python scripts/klayout/gen_pga.py [CELL]

With no argument, builds GDSII/eeg_afe_pga.gds (top cell eeg_afe_pga).
With CELL = pseudo_res|inv, builds just that cell into GDSII/test_<CELL>.gds
for standalone DRC/LVS debugging.

Blocks: eeg_fd_ota_chopped_full2 (instanced from its verified GDS),
eeg_tg_lowq (rebuilt here, same generator as gen_full2), MIM arrays for
CIN (32p) and the feedback bank (0.5p/0.5p/1.5p/3.5p), eeg_pseudo_res,
eeg_inv (select/reset complements: NS8/NS16/NS32/NRST).

All coordinates in um.  See klayout_common.py / README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import *

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_GDS = os.path.join(PROJECT, "GDSII", "eeg_afe_pga.gds")
FULL2_GDS = os.path.join(PROJECT, "GDSII", "eeg_fd_ota_chopped_full2.gds")
TG_GDS = os.path.join(PROJECT, "GDSII", "test_tg.gds")


def fet_anchors(lay, cell, x, y):
    """Absolute anchors of a placed (unmirrored) FET cell."""
    diff, strips, ptop, pbot = lay.scan_m1(cell)
    return {
        "strips": [(sx + x, (y0 + y1) / 2 + y) for sx, y0, y1 in strips],
        "g": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in pbot],
        "gt": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in ptop],
    }


# eeg_pseudo_res: A B — built by klayout_common.build_pseudo_res (shared,
# idempotent builder; identical cell wherever instanced: PGA input network,
# SDM integrator feedback, bias-gen RSTART).
#   XMP1 M M A A pfet L=4 W=1 nf=1 ; XMP2 M M B B pfet L=4 W=1 nf=1
# Two diode-connected pfets sharing the floating mid node M.  Each device
# sits in its OWN nwell (bulk = its source), so the guard rings tie to the
# A/B buses, not to VDD.


# ----------------------------------------------------------------------------
# eeg_inv: A Y VDD18 VSS  (select/reset complement generator)
#   MNA Y A VSS VSS nfet L=0.15 W=1 ; MPA Y A VDD18 VDD18 pfet L=0.15 W=2
# ----------------------------------------------------------------------------
def build_inv(lay):
    mn = lay.make_nfet("inv_n", 0.15, 1.0, 1)
    mp = lay.make_pfet("inv_p", 0.15, 2.0, 1)
    c = lay.ly.create_cell("eeg_inv")

    bn = mn.bbox()
    xp = bn.right / 1000.0 + 3.0
    lay.place(mn, 0.0, 0.0, into=c)
    lay.place(mp, xp, 0.0, into=c)
    gn = fet_anchors(lay, mn, 0.0, 0.0)
    gp = fet_anchors(lay, mp, xp, 0.0)

    bp = mp.bbox()
    top = max(bn.top, bp.top) / 1000.0
    bot = min(bn.bottom, bp.bottom) / 1000.0
    right = (xp * 1000 + bp.right) / 1000.0

    Y_A, Y_VSS = bot - 1.2, bot - 2.4
    Y_Y, Y_VDD = top + 1.2, top + 2.4
    XL, XR = -1.0, right + 1.0
    for y in (Y_A, Y_VSS, Y_Y, Y_VDD):
        lay.bus_m3(XL, XR, y, cell=c)

    def gate_down(g, x_via):
        x_pad, y_pad = g["g"][0]
        lay.box(L_M1, min(x_pad, x_via) - 0.17, y_pad - 0.17,
                max(x_pad, x_via) + 0.17, y_pad + 0.17, c)
        lay.via1(x_via, y_pad, c)
        lay.box(L_M2, x_via - 0.19, Y_A - 0.15, x_via + 0.19, y_pad + 0.17, c)
        lay.via2(x_via, Y_A, c)

    gate_down(gn, gn["g"][0][0] - 0.6)
    gate_down(gp, gp["g"][0][0] - 0.6)

    # drains -> Y (up), sources: mn -> VSS (down), mp -> VDD (up)
    lay.strap_up(*gn["strips"][0], Y_Y, c)
    lay.strap_up(*gp["strips"][0], Y_Y, c)
    lay.strap_down(*gn["strips"][1], Y_VSS, c)
    lay.strap_up(*gp["strips"][1], Y_VDD, c)

    lay.tie_ring(mn, kdb.Trans(0, False, 0, 0), "bottom", Y_VSS,
                 (gn["strips"][1][0] + 0.8,), into=c)
    lay.tie_ring(mp, kdb.Trans(0, False, u(xp), 0), "bottom", Y_VDD,
                 (gp["strips"][1][0] + 0.8,), into=c)

    for net, y in (("A", Y_A), ("Y", Y_Y), ("VDD18", Y_VDD), ("VSS", Y_VSS)):
        lay.label(L_M3L, net, XR - 0.5, y, c)
    anchors = {"A": (XR - 0.5, Y_A), "Y": (XR - 0.5, Y_Y),
               "VDD18": (XR - 0.5, Y_VDD), "VSS": (XR - 0.5, Y_VSS)}
    return c, anchors


# ----------------------------------------------------------------------------
# eeg_afe_pga: full assembly.
#
# Floorplan (XAFE = verified full2 cell at origin; its west edge has the
# INP/INN/PHI* pins on XCHIN's m4 rails, outputs on stage2's m3 buses east):
#   x -760..-582 : CINP/CINN 32p MIM arrays (8x5 of 20x20)
#   x -575..-410 : bank caps (P staircase y60..238, N row y250..353),
#                  select TGs (P row y45, N row y24), pseudo-Rs (y5),
#                  inverters (y-30), select lanes (m3, y-38..-48)
#   summing buses: m4, INP y=15 / INN y=16, x -580..-400 (extend XCHIN rails)
#   outputs: stage2 buses -> east at y=-1/0.2 (under everything; m3
#   underpass at x 949.9..960.1 below the bias CFILT m4 column) -> up at
#   x=1073/1078 (east of the VBNF m4 column at 986) -> west lanes y=88/90
#   (above all full2 trunks) -> down into the bank bottom-plate buses.
# Rules honored throughout: m2 crosses m3/m4 freely (no via2 at crossings),
# m3 crosses m4 freely, m4-over-m4 / m3-over-m3 merges are the fatal ones;
# via3s never land near MIM top tabs (m3 pad would clip the bottom sheet).
# ----------------------------------------------------------------------------
def build_pga(lay):
    lay.ly.read(FULL2_GDS)     # full2 hierarchy incl. eeg_tg_lowq
    afe = lay.ly.cell("eeg_fd_ota_chopped_full2")
    tg = lay.ly.cell("eeg_tg_lowq")
    pr, pr_a = build_pseudo_res(lay)
    inv, inv_a = build_inv(lay)

    top = lay.ly.create_cell("eeg_afe_pga")
    lay.place(afe, 0.0, 0.0, into=top)

    def h3(y, x0, x1): lay.box(L_M3, x0, y - 0.3, x1, y + 0.3, top)
    def v3m(x, y0, y1): lay.box(L_M3, x - 0.3, y0, x + 0.3, y1, top)
    def h4(y, x0, x1): lay.box(L_M4, x0, y - 0.3, x1, y + 0.3, top)
    def v4m(x, y0, y1): lay.box(L_M4, x - 0.3, y0, x + 0.3, y1, top)
    def via3(x, y):
        lay.box(L_M3, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)
        lay.via3(x, y, top)
        lay.box(L_M4, x - 0.3, y - 0.3, x + 0.3, y + 0.3, top)

    def m2col(x, y0, y1, taps=()):
        """m2 vertical with via2 taps at each y (the m3 bus/jog encloses
        below, this box above)."""
        lay.box(L_M2, x - 0.19, min(y0, y1) - 0.15, x + 0.19,
                max(y0, y1) + 0.15, top)
        lay.via2(x, y0, top)
        lay.via2(x, y1, top)
        for t in taps:
            lay.via2(x, t, top)

    # -- column allocation ---------------------------------------------------
    # Every m2 column must dodge the placed cells' internal m2/via1/via2
    # (m2 over via1/via2 connects!) as well as previously drawn columns.
    # Rectangles are y-aware: a column only dodges what it actually passes.
    def busy_rects(cell, tx, ty):
        out = []
        for spec in (L_M2, L_VIA1, L_VIA2):
            for s in cell.shapes(lay.layer(spec)).each():
                b = s.bbox()
                out.append((tx + b.left / 1000.0 - 0.55,
                            tx + b.right / 1000.0 + 0.55,
                            ty + b.bottom / 1000.0 - 0.3,
                            ty + b.top / 1000.0 + 0.3))
        return out

    used = []   # (x0, x1, y0, y1) of m2 columns already drawn

    def note(x, y0, y1):
        used.append((x - 0.6, x + 0.6, min(y0, y1), max(y0, y1)))

    def pick_x(x_lo, x_hi, y_lo, y_hi, busy):
        x = x_lo + 0.25
        while x <= x_hi - 0.25 + 1e-9:
            ok = all(x + 0.19 <= b0 or x - 0.19 >= b1 or
                     y_hi < b2 or y_lo > b3
                     for b0, b1, b2, b3 in busy)
            if ok:
                return round(x / 0.05) * 0.05
            x += 0.05
        raise ValueError(f"no clear column in x[{x_lo},{x_hi}] y[{y_lo},{y_hi}]")

    # ---- cell placements ----------------------------------------------------
    # TG cell-local m3 buses: A 3.8, B 2.6, EN -2.2, ENB -3.4, VSS -4.6,
    # VDD -5.8; x span -1..22.
    YP, YN = 45.0, 24.0
    prow = {"S32": -560.0, "S16": -534.0, "S8": -508.0, "RST": -460.0}
    nrow = {"S32": -560.0, "RST": -534.0, "S8": -508.0, "S16": -482.0}
    for x in prow.values():
        lay.place(tg, x, YP, into=top)
    for x in nrow.values():
        lay.place(tg, x, YN, into=top)
    PA, PB, PEN, PENB, PVSS, PVDD = (YP + 3.8, YP + 2.6, YP - 2.2,
                                     YP - 3.4, YP - 4.6, YP - 5.8)
    NA, NB, NEN, NENB, NVSS, NVDD = (YN + 3.8, YN + 2.6, YN - 2.2,
                                     YN - 3.4, YN - 4.6, YN - 5.8)
    lay.place(pr, -445.0, 5.0, into=top)   # XPRP
    lay.place(pr, -425.0, 5.0, into=top)   # XPRN (east edge clears the VDD18
    # m3 rise at x=-405: an internal via2 at -404.5 clipped it before)
    invs = {"S8": -560.0, "S16": -535.0, "S32": -510.0, "RST": -485.0}
    for x in invs.values():
        lay.place(inv, x, -30.0, into=top)

    all_busy = []
    for x in list(prow.values()) + list(nrow.values()):
        all_busy += busy_rects(tg, x, YP if x in prow.values() else YN)
    # prow/nrow share x values; redo explicitly (both rows, correct ty):
    all_busy = []
    for x in prow.values():
        all_busy += busy_rects(tg, x, YP)
    for x in nrow.values():
        all_busy += busy_rects(tg, x, YN)
    all_busy += busy_rects(pr, -445.0, 5.0) + busy_rects(pr, -425.0, 5.0)
    for x in invs.values():
        all_busy += busy_rects(inv, x, -30.0)

    def busy():
        return all_busy + used

    # ---- input caps (bottom plate m3 = ELx, top plate m4 = INx) -----------
    # tab_h=3.6: MR_capm.SP.2 keeps m3 1.2 um off the sized (0.14) bottom
    # plate, so a via3 landing on the top tab must sit ~3 um above the raw
    # sheet top (1.6-tall tabs forced the m3 pad 0.5 um over the sheet).
    lay.mim_array(top, -760.0, 40.0, 8, 5, cw=20.0, ch=20.0, tab_h=3.6)    # CINP
    lay.mim_array(top, -760.0, -80.0, 8, 5, cw=20.0, ch=20.0, tab_h=3.6)   # CINN
    lay.label(L_M3L, "ELP", -762.0, 41.0, top)   # on CINP bottom tab
    lay.label(L_M3L, "ELN", -762.0, -79.0, top)  # on CINN bottom tab

    # ---- feedback bank (bottom m3 = OUTN/OUTP, top m4 = Fx/INx) -----------
    lay.mim_array(top, -570.0, 60.0, 1, 1, cw=20.0, ch=12.5, tab_h=3.6)    # CFB32P
    lay.mim_array(top, -535.0, 85.0, 1, 3, cw=20.0, ch=12.5, tab_h=3.6)    # CFB16P
    lay.mim_array(top, -518.0, 135.0, 1, 7, cw=20.0, ch=12.5, tab_h=3.6)   # CFB8P
    lay.mim_array(top, -490.0, 60.0, 1, 1, cw=20.0, ch=12.5, tab_h=3.6)    # CF64P
    lay.mim_array(top, -552.0, 250.0, 1, 1, cw=20.0, ch=12.5, tab_h=3.6)   # CFB32N
    lay.mim_array(top, -504.0, 250.0, 1, 7, cw=20.0, ch=12.5, tab_h=3.6)   # CFB8N
    lay.mim_array(top, -478.0, 250.0, 1, 3, cw=20.0, ch=12.5, tab_h=3.6)   # CFB16N
    lay.mim_array(top, -455.0, 60.0, 1, 1, cw=20.0, ch=12.5, tab_h=3.6)    # CF64N (south:
    # short INN drop from here; only F-caps live in the N row)

    # ---- summing buses (extend XCHIN's INP/INN rails west) ----------------
    h4(15.0, -580.0, -400.0)    # INP
    h4(16.0, -580.0, -400.0)    # INN

    # ---- cap top-plate taps ------------------------------------------------
    # NEVER hang thin (<3.2 um) metal off a MIM plate: the huge-metal
    # closing (3 um) leaves a notch -> m3.3ab/m4.5ab.  via3 lands on the
    # 3.6-tall top tab with its m4 pad fully inside the tab and its m3 pad
    # 2.8 um above the bottom sheet (MR_capm.SP.2: m3 must clear the sized
    # (0.14) plate by 1.2 um); then a thin m3 jog and an m2 descent
    # (m2 crosses m3 sheets / m4 plates / buses freely - no via1s up there).
    def fx_drop(xm, sheet_top, a_span, a_y):
        """Cap top tab (m4) -> TG A bus (m3): via3 on tab, m3 jog, m2 down."""
        vy = sheet_top + 3.0
        via3(xm, vy)
        x_tap = pick_x(a_span[0], a_span[1], a_y - 0.15, vy + 0.15, busy())
        note(x_tap, a_y, vy)
        h3(vy, min(xm, x_tap) - 0.2, max(xm, x_tap) + 0.2)
        m2col(x_tap, a_y, vy)

    fx_drop(-560.0, 72.7, (-560.75, -538.25), PA)    # F32P -> XS32P.A
    fx_drop(-525.0, 127.7, (-534.75, -512.25), PA)   # F16P -> XS16P.A
    fx_drop(-508.0, 237.7, (-508.75, -486.25), PA)   # F8P  -> XS8P.A
    fx_drop(-542.0, 262.7, (-560.75, -538.25), NA)   # F32N -> XS32N.A
    fx_drop(-494.0, 352.7, (-508.75, -486.25), NA)   # F8N  -> XS8N.A
    fx_drop(-468.0, 292.7, (-482.75, -460.25), NA)   # F16N -> XS16N.A

    def cf64_route(xm, sheet_top, xr, y_bus):
        """CF64 top tab -> summing bus (m4): via3 on tab, m3 jog, m2 down,
        pad3 -> v3m -> via3 landing.  INN is the upper bus, so the m3 drop
        to INP (y=15) passes under the INN bus freely."""
        vy = sheet_top + 3.0
        via3(xm, vy)
        x_tap = pick_x(xr[0], xr[1], 16.9, vy + 0.15, busy())
        note(x_tap, 16.9, vy)
        h3(vy, min(xm, x_tap) - 0.2, max(xm, x_tap) + 0.2)
        m2col(x_tap, 17.2, vy)
        lay.box(L_M3, x_tap - 0.3, 16.9, x_tap + 0.3, 17.5, top)
        v3m(x_tap, y_bus, 17.2)
        via3(x_tap, y_bus)

    cf64_route(-480.0, 72.7, (-481.5, -470.0), 15.0)   # CF64P top -> INP
    cf64_route(-445.0, 72.7, (-446.5, -439.0), 16.0)   # CF64N top -> INN

    # ---- bank bottom-plate buses (m3, 3.2 tall = flush with the tabs; the
    # verticals to the higher tabs are 3.2 wide - huge-metal closing safe)
    lay.box(L_M3, -573.0, 59.8, -462.0, 63.0, top)      # OUTN, P-row tabs
    lay.box(L_M3, -539.1, 61.0, -535.9, 86.3, top)      # up to CFB16P tab
    lay.box(L_M3, -521.6, 61.0, -518.0, 136.3, top)     # up to CFB8P tab
    lay.box(L_M3, -575.5, 249.8, -445.0, 253.0, top)    # OUTP, N-row tabs
    # CF64N's bottom plate sits in the P row: OUTP sneaks from the N-row bus
    # down on m2 at x=-574.5 (west of the OUTN bus), east on a 3.2-tall m3
    # lane at y=52 (between the joined P-row buses and the VCM_REF lane),
    # and up via a 3.2x3.2 m3 stub merging CF64N's bottom tab/sheet.
    lay.box(L_M3, -575.1, 250.7, -573.9, 251.7, top)   # pad inside OUTP bus
    lay.via2(-574.5, 251.2, top)
    lay.box(L_M2, -574.69, 51.7, -574.31, 251.35, top)
    note(-574.5, 51.7, 251.35)
    lay.via2(-574.5, 52.0, top)
    lay.box(L_M3, -574.8, 50.4, -456.5, 53.6, top)     # 3.2-tall sneak lane
    # up on m2 (crosses the VCM_REF lane freely) -> via2 into CF64N's bottom
    # tab (m3, x -459.2..-455.2, y 59.8..63)
    lay.via2(-457.0, 52.0, top)
    lay.box(L_M2, -457.19, 51.85, -456.81, 61.15, top)
    lay.via2(-457.0, 61.0, top)

    # ---- TG B sides -> summing nodes ----------------------------------------
    # P row: XS32P/XS16P/XS8P B buses join into one INP bus; XRSTP.B is
    # VCM_REF and stays separate (gap -486..-461).
    h3(PB, -561.0, -486.0)
    via3(-487.5, PB); v4m(-487.5, 17.0, PB)
    via3(-487.5, 17.0); v3m(-487.5, 15.0, 17.0); via3(-487.5, 15.0)
    # XRSTP.A -> INP (same underpass pattern)
    via3(-450.0, PA); v4m(-450.0, 17.0, PA)
    via3(-450.0, 17.0); v3m(-450.0, 15.0, 17.0); via3(-450.0, 15.0)
    # N row: XS8N/XS16N B buses join into INN; XS32N.B separate drop;
    # XRSTN.B is VCM_REF (separate).
    h3(NB, -509.0, -460.0)
    via3(-462.0, NB); v4m(-462.0, 16.0, NB)
    via3(-550.0, NB); v4m(-550.0, 16.0, NB)
    # XRSTN.A -> INN (straight down onto the upper bus)
    via3(-525.0, NA); v4m(-525.0, 16.0, NA)

    # ---- VCM_REF: m3 lane y=57 + hop over XCHIN onto XAFE's m4 trunk (74) --
    h3(57.0, -550.0, -406.5)  # ends clear of the VDD18 m3 rise
    via3(-428.0, 57.0); v4m(-428.0, 57.0, 74.0); h4(74.0, -428.0, 3.3)
    # consumers: pseudo-R B sides, reset-TG B sides
    lay.join_m3_m2(-445.0, PB, 57.0, top)            # XRSTP.B
    note(-445.0, PB, 57.15)
    lay.join_m3_m2(-516.0, NB, 57.0, top)            # XRSTN.B
    note(-516.0, NB, 57.15)

    # ---- pseudo-resistors ----------------------------------------------------
    ypa, ypb = 5.0 + pr_a["A"][1], 5.0 + pr_a["B"][1]
    # XPRP.A -> INP (INP is the lower bus: direct m4 landing from below)
    via3(-440.0, ypa); v4m(-440.0, ypa, 15.0)
    # XPRP.B -> VCM_REF lane
    xb = pick_x(-445.75, -430.0, ypb - 0.15, 57.15, busy())
    note(xb, ypb, 57.15)
    lay.join_m3_m2(xb, ypb, 57.0, top)
    # XPRN.A -> INN (underpass below INP, then up)
    via3(-420.0, ypa); v4m(-420.0, ypa, 14.0)
    via3(-420.0, 14.0); v3m(-420.0, 14.0, 16.0); via3(-420.0, 16.0)
    # XPRN.B -> VCM_REF lane
    xb2 = pick_x(-425.75, -406.9, ypb - 0.15, 57.15, busy())
    note(xb2, ypb, 57.15)
    lay.join_m3_m2(xb2, ypb, 57.0, top)

    # ---- select/reset lanes (m3) ---------------------------------------------
    lanes = {"S8": -38.0, "S16": -39.2, "S32": -40.4, "RST": -41.6,
             "NS8": -44.0, "NS16": -45.2, "NS32": -46.4, "NRST": -47.6}
    lane_end = {"S8": -497.0, "S16": -466.0, "S32": -495.0, "RST": -444.0,
                "NS8": -487.0, "NS16": -461.0, "NS32": -496.0, "NRST": -442.0}
    for net, y in lanes.items():
        h3(y, -570.0, lane_end[net])
    comp = {"S8": "NS8", "S16": "NS16", "S32": "NS32", "RST": "NRST"}

    # ---- inverters: all four buses extend 3 um WEST into the empty
    # inter-cell gap; the join columns land on the extensions (the cell
    # interior is too crowded to pick clean columns, and the east side
    # belongs to the select-column windows)
    iya = -30.0 + inv_a["A"][1]
    iyy = -30.0 + inv_a["Y"][1]
    ivss = -30.0 + inv_a["VSS"][1]
    ivdd = -30.0 + inv_a["VDD18"][1]
    for k, x in invs.items():
        xw0 = x - 1.0                              # bus west end (local XL)
        for yy in (iya, iyy, ivss, ivdd):
            h3(yy, xw0 - 3.2, xw0 + 0.5)             # extend the bus west
        xa, xy, xv, xw = xw0 - 0.6, xw0 - 1.3, xw0 - 2.0, xw0 - 2.7
        lay.join_m3_m2(xa, iya, lanes[k], top)         # A -> select lane
        note(xa, lanes[k], iya)
        lay.join_m3_m2(xy, iyy, lanes[comp[k]], top)   # Y -> complement lane
        note(xy, lanes[comp[k]], iyy)
        lay.join_m3_m2(xv, ivss, -4.6, top)            # VSS rail
        note(xv, ivss, -4.6)
        lay.join_m3_m2(xw, ivdd, -5.8, top)            # VDD18 rail
        note(xw, ivdd, -5.8)
        lay.join_m3_m2(xa, iya, lanes[k], top)         # A -> select lane
        note(xa, lanes[k], iya)
        lay.join_m3_m2(xy, iyy, lanes[comp[k]], top)   # Y -> complement lane
        note(xy, lanes[comp[k]], iyy)
        lay.join_m3_m2(xv, ivss, -4.6, top)            # VSS rail
        note(xv, ivss, -4.6)
        lay.join_m3_m2(xw, ivdd, -5.8, top)            # VDD18 rail
        note(xw, ivdd, -5.8)

    # ---- select lanes -> TG EN buses; complement lanes -> ENB buses --------
    # (m2 columns cross all intermediate m3 buses and the m4 summing buses
    # freely; x picked clear of the TG cells' internal straps)
    note(-455.0, -4.75, 40.55)   # power columns drawn below
    note(-452.0, -5.95, 39.35)

    def sel_col(x_lo, x_hi, lane_y, bus_ys):
        x = pick_x(x_lo, x_hi, lane_y - 0.15, max(bus_ys) + 0.15, busy())
        note(x, lane_y, max(bus_ys))
        m2col(x, lane_y, max(bus_ys))
        for by in bus_ys[:-1]:
            lay.via2(x, by, top)

    sel_col(-560.5, -539.6, lanes["S32"], (NEN, PEN))   # XS32N.EN + XS32P.EN
    sel_col(-560.5, -539.6, lanes["NS32"], (NENB, PENB))
    sel_col(-534.5, -513.0, lanes["S16"], (PEN,))       # XS16P.EN
    sel_col(-482.5, -466.5, lanes["S16"], (NEN,))       # XS16N.EN
    sel_col(-534.5, -513.0, lanes["NS16"], (PENB,))     # XS16P.ENB
    sel_col(-482.5, -461.5, lanes["NS16"], (NENB,))     # XS16N.ENB
    sel_col(-508.5, -497.5, lanes["S8"], (NEN, PEN))
    sel_col(-508.5, -487.5, lanes["NS8"], (NENB, PENB))
    sel_col(-534.5, -513.0, lanes["RST"], (NEN,))       # XRSTN.EN
    sel_col(-460.5, -444.5, lanes["RST"], (PEN,))       # XRSTP.EN
    sel_col(-534.5, -513.0, lanes["NRST"], (NENB,))     # XRSTN.ENB
    sel_col(-460.5, -442.5, lanes["NRST"], (PENB,))     # XRSTP.ENB

    # ---- CINP/CINN top plates -> summing buses (same pattern) --------------
    via3(-671.25, 153.2)
    xc = pick_x(-560.5, -530.0, 16.9, 153.35, busy())
    note(xc, 16.9, 153.2)
    h3(153.2, -671.6, xc + 0.2)
    m2col(xc, 17.2, 153.2)
    lay.box(L_M3, xc - 0.3, 16.9, xc + 0.3, 17.5, top)
    v3m(xc, 15.0, 17.2); via3(xc, 15.0)                   # -> INP
    via3(-671.25, 33.2)
    xc2 = pick_x(-558.5, -530.0, 16.9, 33.35, busy())
    note(xc2, 16.9, 33.2)
    h3(33.2, -671.6, xc2 + 0.2)
    m2col(xc2, 17.2, 33.2)
    lay.box(L_M3, xc2 - 0.3, 16.9, xc2 + 0.3, 17.5, top)
    v3m(xc2, 16.0, 17.2); via3(xc2, 16.0)                 # -> INN


    # ---- power rails west (m3) ----------------------------------------------
    # VDD18: extend XCHIN's VDD rail/jog (y=-5.8) west; it merges the VDD18
    # rise (m3, x -405.3..-404.7) - same net, intended.
    h3(-5.8, -565.0, -405.0)    # VDD18
    # VSS: the extension at y=-4.6 must NOT cross that rise -> stop at -406.5
    # and close the gap on m2 (m2 crosses the m3 rise freely)
    h3(-4.6, -565.0, -406.5)    # VSS
    lay.via2(-407.0, -4.6, top)
    lay.box(L_M2, -407.19, -4.75, -400.51, -4.45, top)
    lay.via2(-400.7, -4.6, top)              # onto XCHIN's VSS rail
    # TG-row power: join the colinear buses, one m2 column each to the rails
    h3(PVSS, -561.0, -438.0)    # P-row VSS
    h3(PVDD, -561.0, -438.0)    # P-row VDD18
    h3(NVSS, -561.0, -450.0)    # N-row VSS
    h3(NVDD, -561.0, -450.0)    # N-row VDD18
    lay.box(L_M2, -455.19, -4.75, -454.81, 40.55, top)
    lay.via2(-455.0, -4.6, top); lay.via2(-455.0, NVSS, top)
    lay.via2(-455.0, PVSS, top)
    lay.box(L_M2, -452.19, -5.95, -451.81, 39.35, top)
    lay.via2(-452.0, -5.8, top); lay.via2(-452.0, NVDD, top)
    lay.via2(-452.0, PVDD, top)

    # ---- outputs: stage2 buses -> east under everything -> up at x=1073/8 ---
    # -> west lanes above all full2 trunks -> down into the bank bottom-plate
    # buses.  The lanes at y=88/90 end at x=-465/-455: further west they'd
    # cross CFB16P's m4 top plate (x -477.8..-457.8, y 250.2..292.3 and the
    # P-row plates).
    # 2026-09-11: the bias CFILT top-plate m4 column now rises at
    # x 953.4..956.6 (100p array is 5x25, xm=55): BOTH lanes duck under it
    # on m3 (m3 under the m4 column is free).  via3 m4 pads and the lane
    # ends keep a 3.2 um gap to the column — closer than 3.0 and m4.5ab's
    # 1.5 um closing merges them into the huge sheet -> notch violation.
    via3(749.0, -1.0)                                # OUTP tap (stage2 bus)
    h4(-1.0, 749.0, 950.2)
    via3(949.9, -1.0); h3(-1.0, 949.9, 960.1); via3(960.1, -1.0)
    h4(-1.0, 959.8, 1078.0)
    v4m(1078.0, -1.0, 90.0)
    h4(90.0, -455.0, 1078.0)
    v4m(-455.0, 90.0, 251.0)
    via3(-455.0, 251.0)                              # -> OUTP bank bus
    via3(799.0, 0.2)                                 # OUTN tap
    h4(0.2, 799.0, 950.2)
    via3(949.9, 0.2); h3(0.2, 949.9, 960.1); via3(960.1, 0.2)
    h4(0.2, 959.8, 1073.0)
    v4m(1073.0, 0.2, 88.0)
    h4(88.0, -465.0, 1073.0)
    v4m(-465.0, 61.4, 88.0)
    via3(-465.0, 61.4)                               # -> OUTN bank bus

    # ---- PGA pins -------------------------------------------------------------
    lay.label(L_M4L, "VCM_REF", 500.0, 74.0, top)
    lay.label(L_M4L, "VDD18", 450.0, 70.0, top)
    lay.label(L_M4L, "VSS", 450.0, -12.0, top)
    lay.label(L_M3L, "OUTP", 748.0, -1.0, top)
    lay.label(L_M3L, "OUTN", 798.0, 0.2, top)
    for net in ("S8", "S16", "S32", "RST"):
        lay.label(L_M3L, net, -569.0, lanes[net], top)
    lay.box(L_M3, -570.5, -50.3, -568.5, -49.7, top)   # S64: unused in the
    lay.label(L_M3L, "S64", -569.5, -50.0, top)        # schematic (x64 = all
    # switches open); labeled stub so the pin exists for LVS
    # chopper clock pins: land on the full2's pin spots (XL+1, ch_a rail y —
    # clock rails moved +1 um for the PHI/INN coupling fix, see gen_full2)
    for net, y in (("PHII", 18.0), ("NPHII", 19.0), ("PHIBI", 20.0),
                   ("NPHIBI", 21.0)):
        lay.label(L_M4L, net, -400.0, y, top)
    for net, y in (("PHIM", 80.0), ("NPHIM", 81.0), ("PHIBM", 82.0),
                   ("NPHIBM", 83.0)):
        lay.label(L_M4L, net, -400.0, y, top)

    return top


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which is None:
        lay = Layouter("scratch")
        cell = build_pga(lay)
        lay.set_top(cell)
        lay.finish(OUT_GDS)
        return
    if which == "pseudo_res":
        lay = Layouter("scratch")
        cell, _ = build_pseudo_res(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_pseudo_res.gds"))
        return
    if which == "inv":
        lay = Layouter("scratch")
        cell, _ = build_inv(lay)
        lay.set_top(cell)
        lay.finish(os.path.join(PROJECT, "GDSII", "test_inv.gds"))
        return
    raise SystemExit(f"unknown cell {which!r}: pseudo_res|inv")


if __name__ == "__main__":
    main()

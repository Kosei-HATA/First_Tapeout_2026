#!/usr/bin/env python3
"""
Batch layout generator for the EEG AFE analog top (subckt eeg_afe_top),
sky130A.

    scripts/klayout/.venv/bin/python scripts/klayout/gen_afe_top.py

Builds GDSII/eeg_afe_top.gds (top cell eeg_afe_top): the verified blocks
eeg_afe_pga (GDSII/eeg_afe_pga.gds) + eeg_sdm1ct (GDSII/eeg_sdm1ct.gds),
merged with SkipNewCell conflict resolution (all shared cells probed
geometrically IDENTICAL, labels aside, 2026-09-05).  RST is tied to VSS
at top level (XAFE pin 18 = VSS in the schematic).

Ref: afe_top_ref.spice (mirror of
source/trials/20260902/xschem/eeg_afe_top.spice).

Top-level wiring strategy: the blocks use nothing above m4, so the five
inter-block nets (PGA_OUTP/N, VDD18, VCM_REF, VSS+RST) run on m5
(width 2.0, spacing >= 1.6, via4 0.8 pads); every other block pin just
gets a same-layer tap shape (m4 extension/pad, or via3 + m4 pad for m3
pins) plus an m4L label — unlabeled top-level geometry over child metal
creates the subcircuit port, the label makes the top-level pin.
ADC_OUTP/ADC_OUTN (SDM OINTP/OINTN) are internal nets: tapped but NOT
labeled (a label would create an extra top pin).

2026-09-11: STACKED floorplan (was side-by-side).  The caravan analog
user area is 2928 x 3528 um; the side-by-side top was 3321 um wide.
Now: PGA at (0,0), SDM ABOVE it, nested inside the PGA's x-span
(die = max block width).  PGA_OUTP/OUTN are tapped on the PGA's y=90/88
m4 lanes at x=-450/-460 and run straight up the west side on m5 to the
SDM's VINP/VINN stubs — nothing crosses the inter-block gap.  Supplies:
three m5 trunks above the SDM top; every riser ascends from its block's
m4 lane to its trunk; trunk ends are flush with the riser edges and
nested/staggered (VSS outermost, VDD18 innermost) so no riser crosses a
foreign trunk.

All coordinates in um.  See klayout_common.py / README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import *

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PGA_GDS = os.path.join(PROJECT, "GDSII", "eeg_afe_pga.gds")
SDM_GDS = os.path.join(PROJECT, "GDSII", "eeg_sdm1ct.gds")
OUT_GDS = os.path.join(PROJECT, "GDSII", "eeg_afe_top.gds")

STACK_DX = -725.0    # SDM west edge abs -703.3 (nested inside the PGA's
                     # x-span); puts the SDM VINP/VINN stubs (local x=276)
                     # at abs x=-449, 2.0 um west of the RST riser (-445)
STACK_GAP = 10.0     # PGA top -> SDM bottom (was 12.0: the CIN/CFB MIM top
                     # tabs grew +2.0 for MR_capm.SP.2 via3 clearance; the
                     # -2.0 keeps DY - hence the north supply trunks and the
                     # macro's north pins - at the wrapper's verified y)


def build_top(lay):
    opt = kdb.LoadLayoutOptions()
    opt.cell_conflict_resolution = kdb.LoadLayoutOptions.SkipNewCell
    lay.ly.read(PGA_GDS)
    lay.ly.read(SDM_GDS, opt)
    pga = lay.ly.cell("eeg_afe_pga")
    sdm = lay.ly.cell("eeg_sdm1ct")
    top = lay.top
    # Stacked placement from measured bboxes: SDM above the PGA with a
    # fixed inter-block gap; supply trunks sit above the SDM top.
    pga_bb, sdm_bb = pga.bbox(), sdm.bbox()
    DX = STACK_DX
    DY = pga_bb.top / 1000.0 + STACK_GAP - sdm_bb.bottom / 1000.0
    lay.place(pga, 0.0, 0.0, into=top)
    lay.place(sdm, DX, DY, into=top)
    sdm_hi = DY + sdm_bb.top / 1000.0      # abs y of the SDM's north edge
    T_VDD, T_VCM, T_VSS = sdm_hi + 8.0, sdm_hi + 14.0, sdm_hi + 20.0

    def ax(x): return x + DX     # SDM-local -> absolute
    def ay(y): return y + DY

    def m4pad(x, y, w=1.24):
        lay.box(L_M4, x - w / 2, y - w / 2, x + w / 2, y + w / 2, top)

    def m5pad(x, y, w=2.0):
        lay.box(L_M5, x - w / 2, y - w / 2, x + w / 2, y + w / 2, top)

    def h5(y, x0, x1): lay.box(L_M5, x0, y - 1.0, x1, y + 1.0, top)
    def v5(x, y0, y1): lay.box(L_M5, x - 1.0, y0, x + 1.0, y1, top)

    def lab4(name, x, y): lay.label(L_M4L, name, x, y, top)
    def lab5(name, x, y): lay.label(L_M5L, name, x, y, top)

    # ---- PGA west pins --------------------------------------------------
    # ELP/ELN: m3 sheets reach the block west edge; the CIN cap m4 starts
    # 4.4 um in (x=-759.8), so via3 stacks at x=-762 sit on bare m3.
    for name, y in (("ELP", 41.0), ("ELN", -79.0)):
        lay.via3(-762.0, y, top)
        m4pad(-762.0, y)
        lab4(name, -762.0, y)
    # gain-select / reset stubs (m3, x=-570..): staggered via3+m4 taps
    for name, x, y in (("S8", -560.0, -38.0), ("S16", -556.0, -39.2),
                       ("S32", -552.0, -40.4), ("S64", -569.5, -50.0)):
        lay.via3(x, y, top)
        m4pad(x, y)
        lab4(name, x, y)
    # RST (m3 stub) -> via3/via4 -> short m5 riser -> y=-6 run east into the
    # PGA VSS riser at x=500 (RST = VSS at top level).  The y=-6 run passes
    # UNDER the OUT risers (they start at y=88/90); the jog starts flush at
    # the riser's west edge (m5.1 neck rule).
    lay.via3(-445.0, -41.6, top)
    m4pad(-445.0, -41.6)
    lay.via4(-445.0, -41.6, top)
    m5pad(-445.0, -41.6)
    v5(-445.0, -41.6, -5.0)
    h5(-6.0, -446.0, 501.0)

    # ---- PGA chopper clock lanes (m4): staggered east extensions + labels
    # (pads/vias cannot sit on the 0.6-wide 1.0-pitch lanes without
    # breaching m4.2, so each lane is extended past all lane ends, longest
    # = lowest lane, and labeled on the extension)
    for name, yc, x1, lx in (
            ("PHII", 18.0, -284.91, -290.0), ("NPHII", 19.0, -288.41, -292.0),
            ("PHIBI", 20.0, -291.91, -295.0), ("NPHIBI", 21.0, -295.41, -300.0)):
        lay.box(L_M4, -305.6, yc - 0.3, x1, yc + 0.3, top)
        lab4(name, lx, yc)
    for name, yc, x0, x1, lx in (
            ("PHIM", 80.0, 343.2, 366.59, 365.5),
            ("NPHIM", 81.0, 346.2, 363.09, 362.0),
            ("PHIBM", 82.0, 349.2, 359.59, 358.5),
            ("NPHIBM", 83.0, 355.2, 356.09, 355.65)):
        lay.box(L_M4, x0, yc - 0.3, x1, yc + 0.3, top)
        lab4(name, lx, yc)

    # ---- PGA_OUTP / PGA_OUTN -> SDM VINP/VINN (m5, up the west side) ------
    # The PGA's OUTP/OUTN nets run on its internal 0.6-wide m4 lanes y=90
    # (OUTP, x -455..1078) and y=88 (OUTN, x -465..1073): tapped at
    # x=-450/-460 (1.18 pads widen the lanes for via4 enclosure), then
    # straight up to the SDM's VINP/VINN stubs (0.6x0.6 m3 at local
    # (276,117.6/197.6), abs x=vx=-449).  OUTP's riser merges its VINP
    # m5pad directly (x-overlap); OUTN's hops east at the VINN pad level.
    # The risers pass over the PGA bank/CFB m4 plates and the SDM's
    # southern region — m5 is free over all of it.
    vx = ax(276.0)
    m4pad(-450.0, 90.0, 1.18)       # OUTP tap (y90 lane)
    lay.via4(-450.0, 90.0, top)
    m5pad(-450.0, 90.0)
    v5(-450.0, 90.0, ay(117.6) + 1.0)
    lay.via3(vx, ay(117.6), top)
    m4pad(vx, ay(117.6))
    lay.via4(vx, ay(117.6), top)
    m5pad(vx, ay(117.6))
    m4pad(-460.0, 88.0, 1.18)       # OUTN tap (y88 lane)
    lay.via4(-460.0, 88.0, top)
    m5pad(-460.0, 88.0)
    v5(-460.0, 88.0, ay(197.6) + 1.0)
    lay.via3(vx, ay(197.6), top)
    m4pad(vx, ay(197.6))
    lay.via4(vx, ay(197.6), top)
    m5pad(vx, ay(197.6))
    h5(ay(197.6), -461.0, vx + 1.0)  # OUTN hop: flush at the riser west
                                     # edge, ends at the pad east edge

    # ---- supplies: m5 trunks above the SDM (T_VDD/T_VCM/T_VSS) -------------
    # Every riser ASCENDS from its block's m4 lane to its trunk; trunk ends
    # are flush with the riser edges (m5.1 neck rule) and nested/staggered so
    # no riser crosses a foreign trunk (a riser to a higher trunk sits OUTSIDE
    # every lower trunk's x-span on BOTH sides):
    #   VDD18  trunk x -396..451   risers: PGA x=-395 (lane y=70),  SDM x=450
    #   VCM_REF trunk x  459..471  risers: PGA x=460  (lane y=74),  SDM x=470
    #   VSS    trunk x  499..576   risers: PGA x=500  (lane y=-12, joined by
    #                                  the RST y=-6 run), SDM x=575
    # The PGA risers cross the inter-block gap east/west of the OUT risers
    # (x=-460/-450); nothing else runs on m5 there.
    # VDD18: PGA lane y=70 + SDM lane local y=1470
    m4pad(-395.0, 70.0)
    lay.via4(-395.0, 70.0, top)
    m5pad(-395.0, 70.0)
    v5(-395.0, 70.0, T_VDD + 1.0)
    h5(T_VDD, -396.0, 451.0)
    m4pad(ax(1175.0), ay(1470.0))
    lay.via4(ax(1175.0), ay(1470.0), top)
    m5pad(ax(1175.0), ay(1470.0))
    v5(ax(1175.0), ay(1470.0), T_VDD + 1.0)
    lab5("VDD18", 0.0, T_VDD)
    # VCM_REF: PGA lane y=74 + SDM lane local y=1474
    m4pad(460.0, 74.0)
    lay.via4(460.0, 74.0, top)
    m5pad(460.0, 74.0)
    v5(460.0, 74.0, T_VCM + 1.0)
    h5(T_VCM, 459.0, 471.0)
    m4pad(ax(1195.0), ay(1474.0))
    lay.via4(ax(1195.0), ay(1474.0), top)
    m5pad(ax(1195.0), ay(1474.0))
    v5(ax(1195.0), ay(1474.0), T_VCM + 1.0)
    lab5("VCM_REF", 465.0, T_VCM)
    # VSS: PGA mesh lane y=-12 + SDM mesh lane local y=1388 + the RST run
    # (y=-6, joining the PGA riser at x=500).  The PGA-side tap sits at
    # x=500: the full2 VSS trunk ends at x=950 (clear of the bias CFILT
    # top-plate m4 column at 953.4..956.6).
    m4pad(500.0, -12.0)
    lay.via4(500.0, -12.0, top)
    m5pad(500.0, -12.0)
    v5(500.0, -12.0, T_VSS + 1.0)
    h5(T_VSS, 499.0, 576.0)
    m4pad(ax(1300.0), ay(1388.0))
    lay.via4(ax(1300.0), ay(1388.0), top)
    m5pad(ax(1300.0), ay(1388.0))
    v5(ax(1300.0), ay(1388.0), T_VSS + 1.0)
    lab5("VSS", 540.0, T_VSS)

    # ---- SDM west-side pins (m3): via3 + m4 pad + label -----------------
    # CLK16: the CLK stub sits on top of an m4 column, so extend the stub
    # east on m3 first and tap clear of the columns (SDM-local x=30.6..33.6).
    lay.box(L_M3, ax(30.6), ay(1336.195), ax(33.6), ay(1336.795), top)
    lay.via3(ax(33.0), ay(1336.5), top)
    m4pad(ax(33.0), ay(1336.5))
    lab4("CLK16", ax(33.0), ay(1336.5))
    lay.via3(ax(36.2), ay(1334.4), top)
    m4pad(ax(36.2), ay(1334.4))
    lab4("NCLK16", ax(36.2), ay(1334.4))
    # bitstream outputs / references
    for name, lx, ly in (("BIT", 300.0, 445.0), ("NBIT", 150.0, 1209.14),
                         ("VP", 285.0, 432.6), ("VN", 310.0, 432.6)):
        lay.via3(ax(lx), ay(ly), top)
        m4pad(ax(lx), ay(ly))
        lab4(name, ax(lx), ay(ly))
    # ADC_OUTP/ADC_OUTN internal nets: tap the OINTP/OINTN m3 lanes so the
    # subcircuit ports exist; deliberately UNLABELED (not top-level pins).
    lay.via3(ax(755.0), ay(1399.0), top)
    m4pad(ax(755.0), ay(1399.0))
    lay.via3(ax(762.0), ay(1400.2), top)
    m4pad(ax(762.0), ay(1400.2))

    return top


def main():
    lay = Layouter("eeg_afe_top")
    cell = build_top(lay)
    lay.set_top(cell)
    lay.finish(OUT_GDS)


if __name__ == "__main__":
    main()

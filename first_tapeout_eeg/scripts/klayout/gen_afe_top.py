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

DX, DY = 1578.5, -1100.0   # eeg_sdm1ct instance offset (west edge x=1600.2,
                           # 140 um routing gap east of the PGA)


def build_top(lay):
    opt = kdb.LoadLayoutOptions()
    opt.cell_conflict_resolution = kdb.LoadLayoutOptions.SkipNewCell
    lay.ly.read(PGA_GDS)
    lay.ly.read(SDM_GDS, opt)
    pga = lay.ly.cell("eeg_afe_pga")
    sdm = lay.ly.cell("eeg_sdm1ct")
    top = lay.top
    lay.place(pga, 0.0, 0.0, into=top)
    lay.place(sdm, DX, DY, into=top)

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
    # RST (m3 stub) -> via3/via4 -> m5 riser into the VSS trunk (RST=VSS)
    lay.via3(-445.0, -41.6, top)
    m4pad(-445.0, -41.6)
    lay.via4(-445.0, -41.6, top)
    m5pad(-445.0, -41.6)
    v5(-445.0, -41.6, 433.0)

    # ---- PGA chopper clock lanes (m4): staggered east extensions + labels
    # (pads/vias cannot sit on the 0.6-wide 1.0-pitch lanes without
    # breaching m4.2, so each lane is extended past all lane ends, longest
    # = lowest lane, and labeled on the extension)
    for name, yc, x1, lx in (
            ("PHII", 17.0, -284.91, -290.0), ("NPHII", 18.0, -288.41, -292.0),
            ("PHIBI", 19.0, -291.91, -295.0), ("NPHIBI", 20.0, -295.41, -300.0)):
        lay.box(L_M4, -305.6, yc - 0.3, x1, yc + 0.3, top)
        lab4(name, lx, yc)
    for name, yc, x0, x1, lx in (
            ("PHIM", 80.0, 343.2, 366.59, 365.5),
            ("NPHIM", 81.0, 346.2, 363.09, 362.0),
            ("PHIBM", 82.0, 349.2, 359.59, 358.5),
            ("NPHIBM", 83.0, 355.2, 356.09, 355.65)):
        lay.box(L_M4, x0, yc - 0.3, x1, yc + 0.3, top)
        lab4(name, lx, yc)

    # ---- PGA_OUTP / PGA_OUTN: PGA m4 lanes -> m5 -> SDM VINP/VINN -------
    # PGA side: via4 on the lanes (pads widen the 0.6 lanes for via4
    # enclosure); OUTP rises to the y=4 trunk, OUTN dives to the y=-6
    # trunk so the two never cross.
    m4pad(900.0, -1.0, 1.18)  # on OUTP lane y-1.3..-0.7
    lay.via4(900.0, -1.0, top)
    m5pad(900.0, -1.0)
    v5(900.0, -1.0, 5.0)
    h5(4.0, 899.0, 1859.5)      # PGA_OUTP trunk
    m4pad(904.0, 0.2, 1.18)     # on OUTN lane y-0.1..0.5
    lay.via4(904.0, 0.2, top)
    m5pad(904.0, 0.2)
    v5(904.0, -6.0, 1.2)
    h5(-6.0, 903.0, 1851.0)     # PGA_OUTN trunk
    # SDM side: VINP/VINN are 0.6x0.6 m3 stubs at local (276,117.6/197.6).
    # OUTP drops at x=1858.5 (jogs west into the VINP pad), OUTN at
    # x=1850 (jogs east into the VINN pad) — 2.0 um m5 clearance between
    # the OUTP drop and the VINN pad/jog.
    lay.via3(ax(276.0), ay(117.6), top)
    m4pad(ax(276.0), ay(117.6))
    lay.via4(ax(276.0), ay(117.6), top)
    m5pad(ax(276.0), ay(117.6))
    v5(1858.5, ay(117.6), 5.0)
    h5(ay(117.6), 1855.0, 1859.5)
    lay.via3(ax(276.0), ay(197.6), top)
    m4pad(ax(276.0), ay(197.6))
    lay.via4(ax(276.0), ay(197.6), top)
    m5pad(ax(276.0), ay(197.6))
    v5(1850.0, ay(197.6), -5.0)
    h5(ay(197.6), 1849.0, 1855.5)

    # ---- supplies: m5 trunks above both blocks ---------------------------
    # VDD18: PGA lane y=70 + SDM lane local y=1470, trunk y=420
    m4pad(960.0, 70.0)
    lay.via4(960.0, 70.0, top)
    m5pad(960.0, 70.0)
    h5(70.0, 959.0, 971.0)
    v5(970.0, 70.0, 421.0)
    h5(420.0, 969.0, 2754.5)
    m4pad(ax(1175.0), ay(1470.0))
    lay.via4(ax(1175.0), ay(1470.0), top)
    m5pad(ax(1175.0), ay(1470.0))
    v5(ax(1175.0), ay(1470.0), 421.0)
    lab5("VDD18", 1500.0, 420.0)
    # VCM_REF: PGA lane y=74 + SDM lane local y=1474, trunk y=426
    m4pad(845.0, 74.0)
    lay.via4(845.0, 74.0, top)
    m5pad(845.0, 74.0)
    v5(845.0, 74.0, 427.0)
    h5(426.0, 844.0, 2774.5)
    m4pad(ax(1195.0), ay(1474.0))
    lay.via4(ax(1195.0), ay(1474.0), top)
    m5pad(ax(1195.0), ay(1474.0))
    v5(ax(1195.0), ay(1474.0), 427.0)
    lab5("VCM_REF", 1500.0, 426.0)
    # VSS: PGA mesh lane y=-12 + SDM mesh lane local y=1388 + RST riser,
    # trunk y=432.  The PGA riser runs at x=836 (west of the VCM riser and
    # the OUT trunks) and joins the trunk from below.
    m4pad(960.0, -12.0)
    lay.via4(960.0, -12.0, top)
    m5pad(960.0, -12.0)
    h5(-12.0, 835.0, 961.0)
    v5(836.0, -12.0, 433.0)
    h5(432.0, -445.0, 2879.5)
    m4pad(ax(1300.0), ay(1388.0))
    lay.via4(ax(1300.0), ay(1388.0), top)
    m5pad(ax(1300.0), ay(1388.0))
    v5(ax(1300.0), ay(1388.0), 433.0)
    lab5("VSS", 1500.0, 432.0)

    # ---- SDM west-side pins (m3): via3 + m4 pad + label -----------------
    # CLK16: the CLK stub sits on top of an m4 column, so extend the stub
    # east on m3 first and tap clear of the columns (x=1608.2..1608.8).
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

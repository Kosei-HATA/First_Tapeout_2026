#!/usr/bin/env python3
"""Layout of eeg_ref (gf180/tapeout/adc/eeg_ref.spice): the reference filter between the
VREFP/VREFN pads and the ADC. First block of the layout flow (tracker E1/E5): PDK pcells,
DRC with the PDK deck, LVS against the simulation netlist.

A strip for the west part of the north channel (60 um tall, floorplan y 1547..1607):
  y  0..3    VSS, Metal1 (MOS-capacitor source/drain, resistor substrate taps)
  y  4..7    VREFN, Metal5 (MIM bottom plates through Via4, C_g of VREFN, R_f of VREFN)
  y  9.5..53.5  devices
  y 56..59   VREFP, Metal5 (MIM top plates, C_g of VREFP, R_f of VREFP)
From west to east: the two R_f (ppolyf_u, L 2 um, W 7 um), C_g of VREFP and of VREFN
(cap_nmos_03v3, four units of 28.6 x 44 um each, 20 pF per side), C_d as three MIM caps
(MIM-B, 190 x 44 um, 16.7 pF each).
  - MIM: one cap may not exceed 10,000 um2 (MIMTM.8b/11), and its bottom plate on Metal4
    may only be connected up through Via4 (MIMTM.10).
  - C_g units: Metal1 wider than 30 um in both directions needs slots (MSLOT1.1), and the
    pcell covers the whole gate with Metal1, so a unit stays under 30 um wide. Each unit
    has the pcell's P+ guard ring (substrate tap within 20 um of N+, DF.14_LV), tied to VSS
    together with the source/drain bar.
Pins: VREFP_PAD, VREFN_PAD (Metal2, west edge), VREFP, VREFN (Metal5), VSS (Metal1).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/eeg_ref_lay.py [--drc] [--lvs]
Writes gf180/tapeout/layout/gds/eeg_ref.gds; DRC/LVS results in gf180/tapeout/layout/runs/eeg_ref/.
"""
import argparse
import os
import gf180lay as g

HERE = os.path.dirname(os.path.abspath(__file__))
GDS = os.path.join(HERE, "gds", "eeg_ref.gds")
RUNS = os.path.join(HERE, "runs", "eeg_ref")
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")

Y_DEV0, Y_DEV1 = 9.5, 53.5           # device band
MOS_L, MOS_W, MOS_N, MOS_PITCH = 28.6, 44.0, 4, 38.0   # C_g units, cap_nmos_03v3 (x, y)
MIM_W, MIM_L, MIM_N, MIM_GAP = 190.0, 44.0, 3, 6.0   # C_d units (x, y)


def build():
    b = g.Block("eeg_ref")
    x_mim = 16.0 + 2 * MOS_N * MOS_PITCH + 5.0
    x_end = x_mim + MIM_N * (MIM_W + MIM_GAP)
    # straps
    b.box("metal1", 0, 0, x_end, 3)                   # VSS
    b.box("metal5", 9, 4, x_end, 7)                   # VREFN
    b.box("metal5", 9, 56, x_end, 59)                 # VREFP
    # ---- R_f: VREFP_PAD -> VREFP (upper), VREFN_PAD -> VREFN (lower)
    for y0, pad, up in ((40.0, "VREFP_PAD", True), (15.0, "VREFN_PAD", False)):
        b.pcell("ppolyf_u_resistor", {"l_res": 2.0, "w_res": 7.0}, x=8.0, y=y0)
        # west terminal (x 7.48..7.86): Via1 to a Metal2 run to the west edge, pin there
        ym = y0 + 3.5
        b.box("via1", 7.54, ym - 0.13, 7.80, ym + 0.13)
        b.box("metal2", 0, ym - 0.5, 7.86, ym + 0.5)
        b.label("metal2", pad, 0.3, ym)
        # east terminal (x 10.14..10.52): Metal1 pad, stack to Metal5, riser to the strap
        b.box("metal1", 10.14, ym - 1.5, 12.6, ym + 1.5)
        b.stack("metal1", "metal5", 10.3, ym - 1.3, 12.5, ym + 1.3)
        b.box("metal5", 10.3, ym - 1.3 if up else 4.0, 12.5, 59.0 if up else ym + 1.3)
    b.box("metal1", 6.11, 0, 6.49, 46.75)             # substrate taps of both R_f to VSS
    # ---- C_g: gate to VREFP / VREFN, source-drain and guard ring to VSS
    for k in range(2 * MOS_N):
        x0, up = 16.0 + k * MOS_PITCH, k < MOS_N
        b.pcell("cap_nmos", {"volt": "3.3V", "lc": MOS_L, "wc": MOS_W, "pcmpgr": True}, x=x0, y=Y_DEV0)
        # S/D bottom bar (y0-1.955..y0-0.955) through the guard ring down to the VSS strap
        b.box("metal1", x0 + 1.0, 1.0, x0 + MOS_L - 1.0, Y_DEV0 - 0.955)
        gx0, gx1 = x0 + 3.0, x0 + MOS_L - 3.0
        if up:
            b.stack("metal1", "metal5", gx0, Y_DEV1 - 3.0, gx1, Y_DEV1 - 0.5)
            b.box("metal5", gx0, Y_DEV1 - 3.0, gx1, 59.0)
        else:
            b.stack("metal1", "metal5", gx0, Y_DEV0 + 0.5, gx1, Y_DEV0 + 3.0)
            b.box("metal5", gx0, 4.0, gx1, Y_DEV0 + 3.0)
    # ---- C_d: MIM units, top plate (Metal5) to VREFP, bottom plate (Metal4) to VREFN
    for k in range(MIM_N):
        xm = x_mim + k * (MIM_W + MIM_GAP)
        b.pcell("cap_mim", {"mim_option": "MIM-B", "metal_level": "M5", "wc": MIM_W, "lc": MIM_L},
                x=xm, y=Y_DEV0)
        b.box("metal4", xm, 4.0, xm + MIM_W, Y_DEV0 - 0.5)        # bottom plate down to the strap
        b.vias("via4", xm + 0.5, 4.3, xm + MIM_W - 0.5, 6.7)
        b.box("metal5", xm, Y_DEV1, xm + MIM_W, 59.0)             # top plate up to the strap
    b.label("metal1", "VSS", 1.0, 1.5)
    b.label("metal5", "VREFN", x_end - 2, 5.5)
    b.label("metal5", "VREFP", x_end - 2, 57.5)
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    os.makedirs(RUNS, exist_ok=True)
    os.chdir(RUNS)  # the pcells (gdsfactory) leave temporary GDS files in the working directory
    b = build()
    b.write(GDS)
    bb = b.top.bbox()
    print(f"wrote {GDS}: {bb.width() / 1000:.1f} x {bb.height() / 1000:.1f} um")
    if a.drc:
        counts = g.drc(GDS, "eeg_ref", RUNS)
        print("DRC:", "clean" if not counts else counts)
    if a.lvs:
        cdl = os.path.join(RUNS, "eeg_ref.cdl")
        open(cdl, "w").write(g.to_cdl([NETLIST], "eeg_ref"))
        ok, lines = g.lvs(GDS, cdl, "eeg_ref", RUNS)
        print("LVS:", "match" if ok else "MISMATCH", *lines, sep="\n  ")


if __name__ == "__main__":
    main()

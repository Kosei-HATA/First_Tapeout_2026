#!/usr/bin/env python3
"""MIM capacitor arrays of the AFE and the ADC (tracker E1/E2), one GDS each:

  eeg_cin  Cin, one side of the AFE input capacitor (636 pF): 32 units of 99.70 um square,
           8 x 4. Top plates INP side (TOP), bottom plates the chopper side WP (BOT).
  eeg_c1   C1, one side of the ADC first integrator (680.51 pF): 35 units of 98.61 um,
           7 x 5. TOP to the OTA1 input (I1), BOT to the OTA1 output (O1).
  eeg_c2   C2, one side of the ADC second integrator (19.53 pF): one unit of 98.83 um.

The units are equal squares sized with the cap_mim_2f0ff model (area and perimeter terms)
so the totals match the netlists; one MIM cap may not exceed 10,000 um2 (MIMTM.8b). The
high-impedance node (the amplifier input) is on the top plate, whose parasitic
capacitance is the smaller one. Routing: gf180lay.mim_array (both nets on Metal5).
LVS compares against the array subcircuits of the netlists (eeg_cin in
gf180/tapeout/afe/eeg_afe.spice, eeg_c1 and eeg_c2 in gf180/tapeout/adc/eeg_adc.spice).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/mim_arrays_lay.py [--drc] [--lvs]
       [--only eeg_cin eeg_c1 eeg_c2]
"""
import argparse
import os
import gf180lay as g

HERE = os.path.dirname(os.path.abspath(__file__))
AFE = os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
ADC = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_adc.spice")

# name: (nx, ny, side um, netlist)
ARRAYS = {
    "eeg_cin": (8, 4, 99.70, AFE),
    "eeg_c1": (7, 5, 98.61, ADC),
    "eeg_c2": (1, 1, 98.83, ADC),
}


def build(name):
    nx, ny, a, _ = ARRAYS[name]
    b = g.Block(name)
    x0, y0, x1, y1 = g.mim_array(b, nx, ny, a, a, top="TOP", bot="BOT")
    return b, (x1 - x0, y1 - y0), nx * ny * g.mim_cap(a, a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    ap.add_argument("--only", nargs="+", default=list(ARRAYS))
    a = ap.parse_args()
    for name in a.only:
        runs = os.path.join(HERE, "runs", name)
        os.makedirs(runs, exist_ok=True)
        os.chdir(runs)  # the pcells (gdsfactory) leave temporary GDS files in the working directory
        b, (w, h), c = build(name)
        gds = b.write(os.path.join(HERE, "gds", f"{name}.gds"))
        print(f"{name}: {w:.1f} x {h:.1f} um ({w * h / 1e6:.3f} mm2), {c * 1e12:.3f} pF")
        if a.drc:
            counts = g.drc(gds, name, runs)
            print("  DRC:", "clean" if not counts else counts)
        if a.lvs:
            cdl = os.path.join(runs, f"{name}.cdl")
            open(cdl, "w").write(g.to_cdl([ARRAYS[name][3]], name))
            ok, lines = g.lvs(gds, cdl, name, runs)
            print("  LVS:", "match" if ok else "MISMATCH", *([] if ok else lines), sep="\n    ")


if __name__ == "__main__":
    main()

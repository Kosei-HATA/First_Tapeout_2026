#!/usr/bin/env python3
"""MIM capacitor arrays of the AFE and the ADC (tracker E1/E2), one GDS each:

  eeg_cin  Cin, one side of the AFE input capacitor (636 pF): 32 units of 99.70 um square,
           8 x 4. Top plates INP side (TOP), bottom plates the chopper side WP (BOT).
  eeg_c1a  C1, one side of the ADC first integrator (425.37 pF since 10/29, x1.25: see
           gf180/tapeout/adc/eeg_adc.spice), the main array: 20 units of 98.33 um, 5 x 4
           (386.69 pF). TOP to the OTA1 input (I1), BOT to the OTA1 output (O1).
  eeg_c1x  the rest of C1 (38.68 pF): 4 units of 69.47 um in a row, which the ADC places in
           its band, its buses facing those of eeg_c1a (the 5 x 4 grid is as large as the
           ADC region allows, and one unit may not exceed 10,000 um2).
  eeg_c2   C2, one side of the ADC second integrator (24.41 pF since 10/29, x1.25): two units
           of 61.68 x 98.83 um (the ADC itself draws C2 as analog.mim_cell adc_c2 of the same
           units; this array is the netlist's check).
Cin and C1 have both buses on their south edge (gf180lay.mim_array south=True; TOP
outermost): the AFE and ADC place them mirrored above and below their circuits, which
then reach both nets along one edge. Cin's wiring is widened (OPTIONS).

The units are equal rectangles (squares but for C2) per array, sized with the cap_mim_2f0ff
model (area and perimeter terms) so the totals match the netlists; one MIM cap may not
exceed 10,000 um2 (MIMTM.8b). The high-impedance node (the amplifier input) is on the top
plate, whose parasitic capacitance is the smaller one. Routing: gf180lay.mim_array (both
nets on Metal5).
LVS compares against the array subcircuits of the netlists (eeg_cin in
gf180/tapeout/afe/eeg_afe.spice, eeg_c1a, eeg_c1x and eeg_c2 in gf180/tapeout/adc/eeg_adc.spice).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/mim_arrays_lay.py [--drc] [--lvs]
       [--only eeg_cin eeg_c1a eeg_c1x eeg_c2]
"""
import argparse
import os
import gf180lay as g

HERE = os.path.dirname(os.path.abspath(__file__))
AFE = os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
ADC = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_adc.spice")

# name: (nx, ny, unit width um, unit length um, netlist, count, buses on the south edge)
ARRAYS = {
    "eeg_cin": (8, 4, 99.70, 99.70, AFE, 32, True),
    "eeg_c1a": (5, 4, 98.33, 98.33, ADC, 20, True),
    "eeg_c1x": (4, 1, 69.47, 69.47, ADC, 4, True),
    "eeg_c2": (2, 1, 61.68, 98.83, ADC, 2, False),
}
# Cin is in series with the electrode signal (tracker D6): its plates' wiring is made wide
# (gf180lay.mim_array: top plates bridged into columns, 80 um jumpers into the TOP bus, BOT
# islands and a Metal3 plane under the array that the AFE feeds from the input chopper)
OPTIONS = {"eeg_cin": dict(bridge=True, jumper_w=80.0, feet=True, plane=True)}


def build(name):
    nx, ny, w, l, _, count, south = ARRAYS[name]
    b = g.Block(name)
    x0, y0, x1, y1 = g.mim_array(b, nx, ny, w, l, top="TOP", bot="BOT", count=count, south=south,
                                 **OPTIONS.get(name, {}))
    return b, (x1 - x0, y1 - y0), count * g.mim_cap(w, l)


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
            open(cdl, "w").write(g.to_cdl([ARRAYS[name][4]], name))
            ok, lines = g.lvs(gds, cdl, name, runs)
            print("  LVS:", "match" if ok else "MISMATCH", *([] if ok else lines), sep="\n    ")


if __name__ == "__main__":
    main()

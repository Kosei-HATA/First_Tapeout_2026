#!/usr/bin/env python3
"""Measure GF180MCU-D pcell bounding boxes for the FET sizes used in the
independent-environment AFE (CCIA, cpf210) and CT ADC (gain10) candidates.
For each (type, w_finger, l) it measures nf = 1, 8, 32 and fits
area(nf) = a + b*nf, so an m-multiplied device can be costed as a set of
nf=32 multi-finger devices. Prints JSON to stdout (after gdsfactory log lines);
the fitted values are copied into gf180/size_estimate_ccia_ct.py.
Run: gf180/tools/venv310/bin/python gf180/klayout/measure_candidate_fets.py
"""
import json
import os
import sys

PDK = os.path.expanduser(
    "~/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD")
sys.path.insert(0, os.path.join(PDK, "libs.tech/klayout/tech/pymacros"))

import pya  # noqa: E402
import cells  # noqa: E402

SIZES = [
    ("nfet", 10.0, 0.28), ("pfet", 10.0, 0.28),
    ("nfet", 10.0, 1.0), ("pfet", 10.0, 1.0),
    ("nfet", 10.0, 2.0), ("pfet", 10.0, 2.0),
    ("nfet", 10.0, 4.0), ("pfet", 10.0, 4.0),
    ("nfet", 20.0, 0.28), ("pfet", 40.0, 0.28),
    ("nfet", 1.0, 1.0), ("nfet", 1.0, 0.28), ("pfet", 2.0, 0.28),
]
NFS = [1, 8, 32]


def main():
    cells.gf180mcu()
    lay = pya.Layout()
    lay.dbu = 0.001
    out = []
    for typ, w, l in SIZES:
        pts = {}
        for nf in NFS:
            params = {"volt": "3.3V", "w_gate": w, "l_gate": l, "nf": nf,
                      "bulk": "None"}
            c = lay.create_cell(typ, "gf180mcu", params)
            bb = c.bbox()
            pts[nf] = (bb.width() * lay.dbu, bb.height() * lay.dbu)
        a1 = pts[1][0] * pts[1][1]
        a32 = pts[32][0] * pts[32][1]
        b = (a32 - a1) / 31.0
        out.append({"type": typ, "w": w, "l": l,
                    "bbox_um": {str(k): [round(v[0], 3), round(v[1], 3)]
                                for k, v in pts.items()},
                    "area_nf1_um2": a1, "area_nf32_um2": a32,
                    "per_finger_um2": b, "fixed_um2": a1 - b})
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()

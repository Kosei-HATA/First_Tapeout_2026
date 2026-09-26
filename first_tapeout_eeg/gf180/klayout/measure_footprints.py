#!/usr/bin/env python3
"""Measure GF180MCU-D pcell footprints for the devices used in the ported
chopped AFE OTA + CT SDM ADC. Prints a per-device table (bbox WxH, area).
Run: gf180/tools/venv310/bin/python gf180/klayout/measure_footprints.py
"""
import os
import sys

PDK = os.path.expanduser(
    "~/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD")
sys.path.insert(0, os.path.join(PDK, "libs.tech/klayout/tech/pymacros"))

import pya  # noqa: E402
import cells  # noqa: E402

DEVICES = [
    # (label, pcell, params)
    ("OTA s1 input pair nfet 120/4 nf=12", "nfet",
     {"volt": "3.3V", "w_gate": 120.0, "l_gate": 4.0, "nf": 12, "bulk": "None"}),
    ("OTA s1 load pfet 48/4 nf=4", "pfet",
     {"volt": "3.3V", "w_gate": 48.0, "l_gate": 4.0, "nf": 4, "bulk": "None"}),
    ("OTA s1 tail nfet 48/4 nf=8", "nfet",
     {"volt": "3.3V", "w_gate": 48.0, "l_gate": 4.0, "nf": 8, "bulk": "None"}),
    ("OTA s2 pair nfet 4/20", "nfet",
     {"volt": "3.3V", "w_gate": 4.0, "l_gate": 20.0, "nf": 1, "bulk": "None"}),
    ("OTA s2 load pfet 12/4 nf=2", "pfet",
     {"volt": "3.3V", "w_gate": 12.0, "l_gate": 4.0, "nf": 2, "bulk": "None"}),
    ("biasgen pfet 10/4 nf=2", "pfet",
     {"volt": "3.3V", "w_gate": 10.0, "l_gate": 4.0, "nf": 2, "bulk": "None"}),
    ("biasgen nfet 40/4 nf=8", "nfet",
     {"volt": "3.3V", "w_gate": 40.0, "l_gate": 4.0, "nf": 8, "bulk": "None"}),
    ("cmfb nfet 2/2", "nfet",
     {"volt": "3.3V", "w_gate": 2.0, "l_gate": 2.0, "nf": 1, "bulk": "None"}),
    ("cmfb tail nfet 12/2 nf=2", "nfet",
     {"volt": "3.3V", "w_gate": 12.0, "l_gate": 2.0, "nf": 2, "bulk": "None"}),
    ("chopper TG nfet 1.5/0.28", "nfet",
     {"volt": "3.3V", "w_gate": 1.5, "l_gate": 0.28, "nf": 1, "bulk": "None"}),
    ("chopper TG pfet 3/0.28", "pfet",
     {"volt": "3.3V", "w_gate": 3.0, "l_gate": 0.28, "nf": 1, "bulk": "None"}),
    ("pseudo-res pfet 1/2", "pfet",
     {"volt": "3.3V", "w_gate": 1.0, "l_gate": 2.0, "nf": 1, "bulk": "None"}),
    ("strongarm-ish nfet 2/2", "nfet",
     {"volt": "3.3V", "w_gate": 2.0, "l_gate": 2.0, "nf": 1, "bulk": "None"}),
    ("MIM 20x20 (0.8 pF)", "cap_mim",
     {"mim_option": "MIM-B", "metal_level": "M5", "wc": 20.0, "lc": 20.0}),
    ("MIM 71x71 (10 pF)", "cap_mim",
     {"mim_option": "MIM-B", "metal_level": "M5", "wc": 70.7, "lc": 70.7}),
    ("ppolyf_u_high_Rs R=40k w=1", "ppolyf_u_high_Rs_resistor",
     {"w": 1.0, "l": 13.33}),
]


def main():
    cells.gf180mcu()
    lay = pya.Layout()
    lay.dbu = 0.001
    print(f"{'device':40s} {'W um':>8s} {'H um':>8s} {'area um2':>10s}")
    for label, pc, params in DEVICES:
        try:
            c = lay.create_cell(pc, "gf180mcu", dict(params))
        except Exception as e:
            print(f"{label:40s}  FAILED: {e}")
            continue
        bb = c.bbox()
        w = bb.width() * lay.dbu
        h = bb.height() * lay.dbu
        print(f"{label:40s} {w:8.2f} {h:8.2f} {w*h:10.1f}")


if __name__ == "__main__":
    main()

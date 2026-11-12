#!/usr/bin/env python3
"""Layouts of the clock drivers, built from the netlists by netblock.logic_block:
  eeg_afe_clk  AFE chopper drivers (gf180/tapeout/afe/eeg_afe_clk.spice, tracker B8)
  eeg_adc_clk  OTA1 chopper drivers (gf180/tapeout/adc/eeg_adc_clk.spice)
Logic rows at the bottom, the large stages (PMOS 60 um and up) as driver cells on shelves
above them with their outputs on Metal4 buses; Metal3 power straps on the west (VSS) and
east (VDD) edges; ports on the top edge.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/clkdrv_lay.py [--drc] [--lvs]
       [--only eeg_afe_clk eeg_adc_clk]
"""
import argparse
import os
import gf180lay as g
import blocks as bl
import netblock as nb

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(g.REPO, "gf180", "tapeout")
BLOCKS = {"eeg_afe_clk": [os.path.join(T, "afe", "eeg_afe_clk.spice")],
          "eeg_adc_clk": [os.path.join(T, "adc", "eeg_adc_clk.spice")]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    ap.add_argument("--only", nargs="+", default=list(BLOCKS))
    a = ap.parse_args()
    for name in a.only:
        runs = os.path.join(HERE, "runs", name)
        os.makedirs(runs, exist_ok=True)
        b, (w, h) = nb.logic_block(name, BLOCKS[name])
        print(f"{name}: {w:.1f} x {h:.1f} um")
        bl.check(b, name, BLOCKS[name], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

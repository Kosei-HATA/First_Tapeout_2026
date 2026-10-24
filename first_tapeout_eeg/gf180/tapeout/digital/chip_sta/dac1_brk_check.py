#!/usr/bin/env python3
"""Common-break timing of DAC1 with DAC_CLK as on the chip (tracker C3, chip_sta).

The brk test of gf180/tapeout/sim/dac1/dac1_check.py (eeg_dac1: BRK width, BRK to the
cell's D / DB, the latch inside the break), with DAC_CLK from the output buffer of
eeg_digital_top (buf_1 as in run f2, buf_16 as in d1) on DVDD through the extracted
net (build/nets.json, C_iso + C_cpl, 20 sections). "DAC_CLK to BRK" is then measured
from the buffer input (the ideal edge at e4).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/dac1_brk_check.py
       [--cases ss:125:3.0 typical:27:3.3 ff:-40:3.6]
"""
import argparse
import json
import os
import sys
import types
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "dac1"))
import dac1_check as d1  # noqa: E402
import drive_check as dc  # noqa: E402

NETS = json.load(open(os.path.join(HERE, "build", "nets.json")))
_deck = d1.deck


def deck_with_buffer(o, sels, nframes, seed, save):
    text = _deck(o, sels, nframes, seed, save)
    old = [ln for ln in text.splitlines() if ln.startswith("VDCLK DAC_CLK")][0]
    n = NETS["DAC_CLK"]
    lad = dc.ladder("dclk", "DCZ", "DAC_CLK", n["r_typ"][0][1], n["c_iso_fF"] + n["c_cpl_fF"], 0.0)
    new = [f".include {dc.CELLS}", f"VDVDD DVDD 0 {o.dvdd}",
           old.replace("VDCLK DAC_CLK", "VDCLK DCI").replace(f"PULSE(0 {d1.VDD}", f"PULSE(0 {o.dvdd}"),
           f"XB DCI DCZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{o.cell}"] + lad
    return text.replace(old, "\n".join(new))


def one(corner, temp, dvdd, cell):
    o = types.SimpleNamespace(corner=corner, temp=temp, tol="A", voff=0.0, dvdd=dvdd, cell=cell)
    return corner, temp, dvdd, cell, d1.brk(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["ss:125:3.0", "typical:27:3.3", "ff:-40:3.6"])
    a = ap.parse_args()
    d1.deck = deck_with_buffer
    cases = []
    for c in a.cases:
        corner, temp, vdd = c.split(":")
        for cell in ("buf_1", "buf_16"):
            cases.append((corner, float(temp), float(vdd), cell))
    # each case writes its own run directory (dac1_check names it after corner and temp)
    res = []
    for c in cases:
        d1.HERE = os.path.join(HERE, "build", "spice", f"dac1brk_{c[3]}")
        os.makedirs(os.path.join(d1.HERE, "runs"), exist_ok=True)
        res.append(one(*c))
    keys = list(res[0][4])
    print("| quantity | " + " | ".join(f"{cell} {corner} {temp:g} C" for corner, temp, _, cell, _ in res) + " |")
    print("|---|" + "---|" * len(res))
    for k in keys:
        print(f"| {k} | " + " | ".join(f"{r[4][k]:.2f}" for r in res) + " |")


if __name__ == "__main__":
    main()

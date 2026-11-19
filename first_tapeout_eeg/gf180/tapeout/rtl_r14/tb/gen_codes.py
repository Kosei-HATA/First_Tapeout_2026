#!/usr/bin/env python3
"""The quantizer code streams the r14 benches read (audit round 2, 11/20: written by hand on 11/19, now reproducible).

  build/top_r14.codes  tb_top_r14's CODE stream: 262,144 frames of the full-scale behavioural stream s4 of the CT
                       loop model (gf180/tapeout/rtl/build/e2e/s4.codes, uint8 per frame), from frame 256,000 (after
                       the model's start-up).
  build/ovl.codes      tb_ovl's stream: the two extracted ADC overload runs (gf180/tapeout/pex/runs/adc_overload_r12/*/
                       out.csv, the quantizer's normalized input in column 19, sampled once per frame and quantized to
                       0..31), then 300,000 frames of s4 (the full scale, where the overload rule must never fire).

A missing input is an error (the test that needs the file then fails instead of being skipped).
Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/gen_codes.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R14 = os.path.normpath(os.path.join(HERE, ".."))
S4 = os.path.normpath(os.path.join(R14, "..", "rtl", "build", "e2e", "s4.codes"))
OVL_RUNS = os.path.normpath(os.path.join(R14, "..", "pex", "runs", "adc_overload_r12"))
FR = 1 / 1.024e6


def main():
    if not os.path.exists(S4):
        sys.exit(f"missing {S4} (the CT loop model's full-scale stream; gf180/tapeout/rtl e2e flow)")
    s4 = np.fromfile(S4, dtype=np.uint8)
    os.makedirs(os.path.join(R14, "build"), exist_ok=True)
    top = s4[256000:256000 + 262144]
    with open(os.path.join(R14, "build", "top_r14.codes"), "w") as f:
        f.write("\n".join(str(int(x)) for x in top) + "\n")
    codes, runs = [], 0
    for d in sorted(os.listdir(OVL_RUNS)) if os.path.isdir(OVL_RUNS) else []:
        p = os.path.join(OVL_RUNS, d, "out.csv")
        if not os.path.exists(p):
            continue
        x = np.loadtxt(p)
        t, norm1 = x[:, 0], x[:, 19]
        tf = np.arange(t[0] + 0.5 * FR, t[-1], FR)
        codes += list(np.round((np.interp(tf, t, norm1) + 0.5) * 31).astype(int))
        runs += 1
    if runs != 2:
        sys.exit(f"expected the two extracted overload runs in {OVL_RUNS}, found {runs}")
    n_ovl = len(codes)
    codes += list(s4[256000:556000].astype(int))
    with open(os.path.join(R14, "build", "ovl.codes"), "w") as f:
        f.write("\n".join(str(int(c)) for c in codes) + "\n")
    with open(os.path.join(R14, "build", "ovl.split"), "w") as f:
        f.write(f"{n_ovl}\n")                         # frames of the overload runs; the rest is the full scale
    print(f"build/top_r14.codes: {len(top)} frames; build/ovl.codes: {n_ovl} overload + 300000 full-scale frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())

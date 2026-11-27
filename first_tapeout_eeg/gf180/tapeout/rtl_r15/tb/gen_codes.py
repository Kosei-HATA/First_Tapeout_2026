#!/usr/bin/env python3
"""The quantizer code streams the r14 benches read (audit round 2, 11/20: written by hand on 11/19, now reproducible).

  build/top_r14.codes  tb_top_r14's CODE stream: 262,144 frames of the full-scale behavioural stream s4 of the CT
                       loop model (gf180/tapeout/rtl/build/e2e/s4.codes, uint8 per frame), from frame 256,000 (after
                       the model's start-up).
  build/ovl.codes      tb_ovl's stream: the two extracted ADC overload runs (gf180/tapeout/pex/runs/adc_overload_r12/*/
                       out.csv, the quantizer's normalized input in column 19, sampled once per frame and quantized to
                       0..31); synthetic bursts (audit round 6): 20 extreme codes ending at every phase of tb_ovl's
                       37-frame intervals (the detector's tail then falls into intervals without an extreme code),
                       4 extreme codes in 32 frames (detected) and 3 (never); then 300,000 frames of s4 (the full
                       scale, where the overload rule must never fire).

A missing input is an error (the test that needs the file then fails instead of being skipped), and so is an input
whose SHA-256 is not the one recorded here (they are gitignored build and run outputs; audit round 7).
build/ovl.split: one line per segment, "run <first> <end> <name>" for each extracted run, "synth <first> <end>",
"full <first> <end>" (frame indices, end excluded); check_ovl.py requires detection in every extracted run.
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
SHA256 = {"s4.codes": "fbc092845489d9b7df1bb48cd158a6b95006cb59a0e7e30c2c7510dd78632f11",
          "typical_ov2.5V_150u_then_dc-39mV_300u": "28c464e1950946e762b3608d49bd75510c3bef22e6e4604ec265cf382b285632",
          "typical_ov2.5V_50u_rec60u_f20k_a0.28": "dd360de33340f371345e7f7480fadab61c5132d2e6e3444542bbd23160faa9bb"}


def sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if not os.path.exists(S4):
        sys.exit(f"missing {S4} (the CT loop model's full-scale stream; gf180/tapeout/rtl e2e flow)")
    if sha(S4) != SHA256["s4.codes"]:
        sys.exit(f"{S4} is not the stream recorded on 11/19 (SHA-256)")
    s4 = np.fromfile(S4, dtype=np.uint8)
    os.makedirs(os.path.join(R14, "build"), exist_ok=True)
    top = s4[256000:256000 + 262144]
    with open(os.path.join(R14, "build", "top_r14.codes"), "w") as f:
        f.write("\n".join(str(int(x)) for x in top) + "\n")
    codes, runs, segs = [], 0, []
    for d in sorted(os.listdir(OVL_RUNS)) if os.path.isdir(OVL_RUNS) else []:
        p = os.path.join(OVL_RUNS, d, "out.csv")
        if not os.path.exists(p):
            continue
        if SHA256.get(d) != sha(p):
            sys.exit(f"{p}: not one of the extracted runs recorded (SHA-256)")
        x = np.loadtxt(p)
        t, norm1 = x[:, 0], x[:, 19]
        tf = np.arange(t[0] + 0.5 * FR, t[-1], FR)
        first = len(codes)
        codes += list(np.round((np.interp(tf, t, norm1) + 0.5) * 31).astype(int))
        segs.append(f"run {first} {len(codes)} {d}")
        runs += 1
    if runs != 2:
        sys.exit(f"expected the two extracted overload runs in {OVL_RUNS}, found {runs}")
    first = len(codes)
    for p in range(37):                                # a burst whose last frame has index p (mod 37)
        gap = 64 + ((p - (len(codes) + 64 + 19)) % 37)
        codes += [16] * gap + [31 if p % 2 else 0] * 20
    codes += [16] * 64 + [0, 16, 16, 16, 16, 16, 16, 16] * 4 + [16] * 64        # 4 extremes in 32 frames: detected
    codes += [31] + [16] * 10 + [31] + [16] * 10 + [31] + [16] * 64            # 3 extremes: never
    # the edge of FLG-04's set (audit round 11, auditor A: no stimulus had the codes next to the rails, and an RTL that
    # also counted 1 and 30 passed every test): bursts of 1, 30, 2 and 29, never detected; three extremes among codes
    # next to the rails, never detected
    for c in (1, 30, 2, 29):
        codes += [16] * 64 + [c] * 40
    codes += [16] * 64 + [1, 30, 0, 1, 30, 31, 1, 30, 0, 1, 30] + [16] * 64
    n_ovl = len(codes)
    segs.append(f"synth {first} {n_ovl}")
    codes += list(s4[256000:556000].astype(int))
    segs.append(f"full {n_ovl} {len(codes)}")
    with open(os.path.join(R14, "build", "ovl.codes"), "w") as f:
        f.write("\n".join(str(int(c)) for c in codes) + "\n")
    with open(os.path.join(R14, "build", "ovl.split"), "w") as f:
        f.write("\n".join(segs) + "\n")
    print(f"build/top_r14.codes: {len(top)} frames; build/ovl.codes: {n_ovl} overload (2 runs, 39 synthetic bursts and 5 at the edge of the extreme set) "
          f"+ 300000 full-scale frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())

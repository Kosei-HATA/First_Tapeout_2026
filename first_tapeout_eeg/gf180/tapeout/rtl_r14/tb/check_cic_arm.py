#!/usr/bin/env python3
"""Codes for tb_cic_arm and the check of its outputs against rtl/model/cic_golden.py.

The r14 CIC cleared (armed) at output number K (counted from 1) must give: outputs 1..K as the golden run of the
whole stream, and outputs K+1.. as the golden run of the stream from input K * R on (zero state, the first two
flagged invalid), i.e. the output grid unchanged. With a second clear at K2 > K (audit round 33, auditor C: in the
filter's settling, K2 = K + 1 or K + 2), outputs K+1..K2 are the first K2 - K of that run and outputs K2+1.. the
golden run of the stream from input K2 * R on.
Usage: check_cic_arm.py gen [K] [n_outputs] [build] | check [K] [K2] [build] (build: the folder of the codes and the
outputs, default ../build; the mutation runner's copies, audit round 22)
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "model"))
import cic_golden as G  # noqa: E402

R = 1024
B = os.path.join(HERE, "..", "build")


def gen(k, nout, seed=5):
    rnd = random.Random(seed)
    # a slow random walk around mid-scale plus noise, codes 0..31 (some extremes too)
    codes, v = [], 16.0
    for i in range(nout * R + 40):
        v += rnd.uniform(-0.3, 0.3)
        v = min(max(v, 2), 29)
        codes.append(min(max(int(round(v + rnd.gauss(0, 2))), 0), 31))
    with open(os.path.join(B, "cic_arm.codes"), "w") as f:
        f.write("\n".join(str(c) for c in codes) + "\n")


def check(k, k2=None):
    codes = [int(x) for x in open(os.path.join(B, "cic_arm.codes"))]
    got = [tuple(map(int, l.split())) for l in open(os.path.join(B, "cic_arm.out"))]
    full, _ = G.cic3_run(codes)
    after, _ = G.cic3_run(codes[k * R:])
    if k2 is None:
        exp = [(d, int(v)) for d, v in full[:k]] + [(d, int(v)) for d, v in after]
    else:
        after2, _ = G.cic3_run(codes[k2 * R:])
        exp = ([(d, int(v)) for d, v in full[:k]] + [(d, int(v)) for d, v in after[:k2 - k]] +
               [(d, int(v)) for d, v in after2])
    n = min(len(got), len(exp))
    bad = [(i + 1, got[i], exp[i]) for i in range(n) if got[i] != exp[i]]
    print(f"{n} outputs compared (armed at output {k}" + (f" and again at {k2}" if k2 else "") + f"): {len(bad)} mismatches")
    for b in bad[:10]:
        print(f"  output {b[0]}: RTL {b[1]}, golden {b[2]}")
    ok = n >= max(k, k2 or 0) + 4 and not bad
    print("PASS: r14 CIC clear at an output time == golden (grid kept)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) > 1 and os.path.isdir(args[-1]):
        B = args.pop()
    if args[0] == "gen":
        gen(int(args[1]) if len(args) > 1 else 5, int(args[2]) if len(args) > 2 else 10)
    else:
        sys.exit(check(int(args[1]) if len(args) > 1 else 5, int(args[2]) if len(args) > 2 else None))

#!/usr/bin/env python3
"""tb_top_r14's samples against the golden CIC (rtl/model/cic_golden.py).

build/top_r14_cic.log: every CIC input ('I code') and every output time ('O seq armed'); a clear (armed) at the
output with SEQ s restarts the filter from the next input, (s + 1) * R. build/top_r14_samples.log: 'seq data status'
of every sample read over SPI. Each sample must equal the golden output with its SEQ, bit for bit, and be valid.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "model"))
import cic_golden as G  # noqa: E402

R = 1024
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "build")     # the build folder (mutation runs)


def main():
    codes, clears, seqs = [], [], []
    for line in open(os.path.join(B, "top_r14_cic.log")):
        f = line.split()
        if f[0] == "I":
            codes.append(int(f[1]))
        elif f[0] == "O":
            seqs.append(int(f[1]))
            if f[2] == "1":
                clears.append(int(f[1]))
    # SEQ counts every output time in every state from the RESET_N release (DAT-03; audit round 7: a table that left
    # IDLE, WARMUP, PRE and PULSE uncounted passed every test): the logged output times carry 0, 1, 2, ...
    gaps = [k for k in range(len(seqs)) if seqs[k] != k % 65536]
    print(f"{len(seqs)} output times logged: SEQ " + ("0, 1, 2, ... at every one" if not gaps else
                                                     f"breaks at output {gaps[0]} (SEQ {seqs[gaps[0]]})"))
    if gaps or not seqs:
        print("FAIL: SEQ does not count every output time")
        return 1
    # golden per segment between clears; seq s closes inputs [s R, (s + 1) R)
    gold = {}
    starts = [0] + [s + 1 for s in clears]
    for k, s0 in enumerate(starts):
        s1 = starts[k + 1] if k + 1 < len(starts) else len(codes) // R
        out, _ = G.cic3_run(codes[s0 * R: s1 * R])
        for j, (d, valid) in enumerate(out):
            gold[s0 + j] = (d, valid)
    n, bad = 0, []
    for line in open(os.path.join(B, "top_r14_samples.log")):
        seq, data, st = map(int, line.split())
        n += 1
        g = gold.get(seq)
        if g is None or g[0] != data or not g[1]:
            bad.append((seq, data, g))
    print(f"{n} samples compared with the golden CIC ({len(clears)} clears at SEQ {clears}): {len(bad)} mismatches")
    for b in bad[:10]:
        print(f"  SEQ {b[0]}: RTL {b[1]}, golden {b[2]}")
    ok = n > 0 and not bad
    print("PASS: every sample == golden CIC output of its SEQ" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

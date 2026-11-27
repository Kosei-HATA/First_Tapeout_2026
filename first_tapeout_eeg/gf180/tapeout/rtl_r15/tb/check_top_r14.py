#!/usr/bin/env python3
"""tb_top_r14's samples against the golden CIC (rtl/model/cic_golden.py).

build/top_r14_cic.log: every CIC input ('I code') and every output time ('O seq armed'); a clear (armed) at the
output with SEQ s restarts the filter from the next input, (s + 1) * R. build/top_r14_samples.log: 'seq data status'
of every sample read over SPI. Each sample must equal the golden output with its SEQ, bit for bit, and be valid.
Every store is logged ('S seq err alert_mask dflag alert_mask_d', the registers as the host reads them in the store's
cycle), and each sample's status byte must carry VALID 1, OVERRUN = DFLAG.OVERRUN and ERR = ALERT ((ERR & ALERT_MASK)
or (DFLAG & ALERT_MASK_D)) of that cycle, with the reserved bits 0 (spec 3.4, FLG-03; audit round 19, auditor C: the
status column was read and ignored, and an ALERT without DFLAG in the samples passed all 16 groups). OVL and
CHANGED are checked by the bench's phases (J, T; the CHANGED counts).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "model"))
import cic_golden as G  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "spec"))
import regmap as RM  # noqa: E402

SB = {n: b for n, b, _d in RM.SAMPLE_STATUS if n != "0"}           # the sample status bits (regmap)
RESERVED = 0xFF & ~sum(1 << b for b in SB.values())
DF_OVERRUN = next(f["lsb"] for r in RM.REGS if r[1] == "DFLAG" for f in r[4] if f["name"] == "OVERRUN")

R = 1024
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "build")     # the build folder (mutation runs)


def main():
    codes, clears, seqs, stores, twice = [], [], [], {}, []
    for line in open(os.path.join(B, "top_r14_cic.log")):
        f = line.split()
        if f[0] == "I":
            codes.append(int(f[1]))
        elif f[0] == "O":
            seqs.append(int(f[1]))
            if f[2] == "1":
                clears.append(int(f[1]))
        elif f[0] == "S":
            s_ = int(f[1])
            if s_ in stores:
                twice.append(s_)
            stores[s_] = tuple(int(x) for x in f[2:6])
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
    n, bad, seen, dup, sbad = 0, [], set(), [], []
    for line in open(os.path.join(B, "top_r14_samples.log")):
        seq, data, st = map(int, line.split())
        n += 1
        if seq in seen:                                # audit round 13: J7 logged its samples twice (counts of 123
            dup.append(seq)                            # samples were 118 distinct ones)
        seen.add(seq)
        g = gold.get(seq)
        if g is None or g[0] != data or not g[1]:
            bad.append((seq, data, g))
        rec = stores.get(seq)                           # the status byte as at the store (audit round 19)
        if rec is None:
            sbad.append((seq, st, None))
        else:
            err, mask, dfl, mskd = rec
            want = (1 << SB["VALID"]) | (((dfl >> DF_OVERRUN) & 1) << SB["OVERRUN"]) | \
                (int(bool((err & mask) | (dfl & mskd))) << SB["ERR"])
            keep = (1 << SB["VALID"]) | (1 << SB["OVERRUN"]) | (1 << SB["ERR"]) | RESERVED
            if st & keep != want:
                sbad.append((seq, st, want))
    print(f"{n} samples compared with the golden CIC ({len(clears)} clears at SEQ {clears}): {len(bad)} mismatches, "
          f"{len(dup)} logged twice")
    for b in bad[:10]:
        print(f"  SEQ {b[0]}: RTL {b[1]}, golden {b[2]}")
    print(f"{n} sample status bytes against the flags of their store ({len(stores)} stores logged): VALID, OVERRUN, "
          f"ERR = ALERT and the reserved bits: {len(sbad)} mismatches, {len(twice)} SEQ stored twice")
    for b in sbad[:10]:
        print(f"  SEQ {b[0]}: status 0x{b[1]:02X}, " + ("no store logged" if b[2] is None else
                                                     f"expected 0x{b[2]:02X} in the bits VALID, OVERRUN, ERR, reserved"))
    if dup:
        print(f"  logged twice (a sample read twice, or logged twice): SEQ {dup[:10]}")
    ok = n > 0 and not bad and not dup and not sbad and not twice
    print("PASS: every sample == golden CIC output of its SEQ, its status flags as at its store" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

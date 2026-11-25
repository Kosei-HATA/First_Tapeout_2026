#!/usr/bin/env python3
"""tb_ovl's output against the overload rule of the specification (regmap.OVL_RULE). Per frame: the detector after the
frame (>= threshold extreme codes among the last window frames, counting this one) and the hit (this frame's code is
extreme and the detector holds); per interval of K = 37 frames: the flag (a hit in the interval). The overload runs
must be detected, the full scale after them never (no false alarm). Audit round 6: the interval flag counts hits
only (the detector's tail after the last extreme code marks nothing). Audit round 7: build/ovl.split gives each
segment ("run" per extracted run, "synth", "full"); every extracted run must hold a sustained overload (threshold
consecutive extreme codes; a lone start-up code of the loop does not count) and be detected no later than its
threshold-th consecutive extreme code.
Usage: check_ovl.py [build directory]
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import regmap  # noqa: E402

K = 37


def main():
    b = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "build")
    R = regmap.OVL_RULE
    c = np.loadtxt(os.path.join(b, "ovl.codes"), dtype=int)
    g = np.loadtxt(os.path.join(b, "ovl.out"), dtype=int).reshape(-1, 3)
    v = np.loadtxt(os.path.join(b, "ovl_iv.out"), dtype=int).reshape(-1)
    segs = [ln.split() for ln in open(os.path.join(b, "ovl.split")) if ln.strip()]
    full = [sg for sg in segs if sg[0] == "full"]
    runs = [sg for sg in segs if sg[0] == "run"]
    if len(full) != 1 or len(runs) != 2:
        print(f"FAIL: build/ovl.split has {len(runs)} extracted runs and {len(full)} full-scale segments (2 and 1)")
        return 1
    split = int(full[0][1]) + R["window"]               # the full scale after the window left the runs
    ext = np.isin(c, R["codes"]).astype(int)
    det = (np.convolve(ext, np.ones(R["window"], dtype=int))[:len(c)] >= R["threshold"]).astype(int)
    hit = det & ext
    n = len(g)
    bad_det = int((g[:, 0] != det[:n]).sum()) if n == len(c) else -1
    bad_hit = int((g[:, 1] != hit[:n]).sum()) if n == len(c) else -1
    # OVL_NOW during a frame's own input cycle is still the rule of the frames before it (audit round 47, auditor C)
    det_before = np.concatenate(([0], det[:-1]))
    bad_in = int((g[:, 2] != det_before[:n]).sum()) if n == len(c) else -1
    ni = n // K
    want_iv = hit[:ni * K].reshape(ni, K).max(axis=1)
    bad_iv = int((v[:ni] != want_iv).sum()) if len(v) == ni else -1
    tails = int(((det[:ni * K].reshape(ni, K).max(axis=1) == 1) & (want_iv == 0)).sum())
    print(f"{n} of {len(c)} frames: detector {bad_det} mismatches, hits {bad_hit}, detector in the input cycle {bad_in}; "
          f"{ni} intervals of {K} frames: {bad_iv} mismatches ({int(want_iv.sum())} flagged, {tails} with only the detector's tail, unflagged); "
          f"detections: overload runs {int(det[:split].sum())}, full scale {int(det[split:].sum())}")
    run_ok = True
    for _, a, e, name in runs:                         # each extracted run on its own (audit round 7)
        a, e = int(a), int(e)
        xi = np.flatnonzero(ext[a:e])
        di = np.flatnonzero(det[a:e])
        cons = np.flatnonzero(np.convolve(ext[a:e], np.ones(R["threshold"], dtype=int), mode="valid") == R["threshold"])
        onset = int(cons[0]) if len(cons) else None    # the first of threshold consecutive extreme codes
        good = onset is not None and len(di) > 0 and di[0] <= onset + R["threshold"] - 1
        run_ok &= good
        print(f"  run {name}: frames {a}..{e - 1}, {len(xi)} extreme codes, sustained overload from frame {onset}, "
              f"first detection at frame {int(di[0]) if len(di) else None} ({len(di)} frames detected)"
              + ("" if good else "  <- FAIL"))
    ok = (bad_det == 0 and bad_hit == 0 and bad_in == 0 and bad_iv == 0 and run_ok and det[split:].sum() == 0 and tails > 0)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

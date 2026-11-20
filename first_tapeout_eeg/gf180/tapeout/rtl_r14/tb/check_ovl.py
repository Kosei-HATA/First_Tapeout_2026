#!/usr/bin/env python3
"""tb_ovl's output against the overload rule of the specification (regmap.OVL_RULE). Per frame: the detector after the
frame (>= threshold extreme codes among the last window frames, counting this one) and the hit (this frame's code is
extreme and the detector holds); per interval of K = 37 frames: the flag (a hit in the interval). The overload runs
(before build/ovl.split) must be detected, the full scale after them never (no false alarm). Audit round 6: the
interval flag counts hits only (the detector's tail after the last extreme code marks nothing).
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
    g = np.loadtxt(os.path.join(b, "ovl.out"), dtype=int).reshape(-1, 2)
    v = np.loadtxt(os.path.join(b, "ovl_iv.out"), dtype=int).reshape(-1)
    split = int(open(os.path.join(b, "ovl.split")).read()) + R["window"]   # the full scale after the window left the runs
    ext = np.isin(c, R["codes"]).astype(int)
    det = (np.convolve(ext, np.ones(R["window"], dtype=int))[:len(c)] >= R["threshold"]).astype(int)
    hit = det & ext
    n = len(g)
    bad_det = int((g[:, 0] != det[:n]).sum()) if n == len(c) else -1
    bad_hit = int((g[:, 1] != hit[:n]).sum()) if n == len(c) else -1
    ni = n // K
    want_iv = hit[:ni * K].reshape(ni, K).max(axis=1)
    bad_iv = int((v[:ni] != want_iv).sum()) if len(v) == ni else -1
    tails = int(((det[:ni * K].reshape(ni, K).max(axis=1) == 1) & (want_iv == 0)).sum())
    print(f"{n} of {len(c)} frames: detector {bad_det} mismatches, hits {bad_hit}; {ni} intervals of {K} frames: "
          f"{bad_iv} mismatches ({int(want_iv.sum())} flagged, {tails} with only the detector's tail, unflagged); "
          f"detections: overload runs {int(det[:split].sum())}, full scale {int(det[split:].sum())}")
    ok = bad_det == 0 and bad_hit == 0 and bad_iv == 0 and det[:split].sum() > 0 and det[split:].sum() == 0 and tails > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

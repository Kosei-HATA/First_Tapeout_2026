#!/usr/bin/env python3
"""Robustness screen for the top sweep candidates: vary kappa (int1 settling
calibration uncertainty), input amplitude, quadratic settling term, and
multibit DAC element mismatch. The headline number of a chaotic limit-cycle
system is only as good as its worst perturbation."""
import numpy as np
from sdm import simulate, analyze, SettleProfile, IDEAL

CANDS = [
    ("L2/sdm3 4b 512k", dict(order=2, coeffs=(2.,2.,.5,1.), bits=4, fs=512e3)),
    ("L2/sdm3 4b 256k", dict(order=2, coeffs=(2.,2.,.5,1.), bits=4, fs=256e3)),
    ("L2/lowgain 4b 512k", dict(order=2, coeffs=(1.,1.,1.,1.), bits=4, fs=512e3)),
    ("L2/lowgain 4b 256k", dict(order=2, coeffs=(1.,1.,1.,1.), bits=4, fs=256e3)),
    ("L2/sdm3 2b 512k", dict(order=2, coeffs=(2.,2.,.5,1.), bits=2, fs=512e3)),
]

for name, kw in CANDS:
    print(f"\n=== {name} ===")
    worst = np.inf
    best = -np.inf
    for kap in (3e-4, 1e-3, 3e-3):
        for amp in (0.5, 0.6, 0.7):
            s = SettleProfile(gamma=0.086, kappa=kap, eta=1e-3)
            y, _ = simulate(amp=amp, settle=(s, IDEAL), **kw)
            r = analyze(y, fs=kw['fs'])
            worst = min(worst, r['sndr']); best = max(best, r['sndr'])
            print(f"  kappa={kap:7.1e} amp={amp:.1f}: SNDR={r['sndr']:7.2f} dB")
    print(f"  -> kappa/amp envelope: {worst:.2f}..{best:.2f} dB")
    if kw['bits'] > 1:
        for mm in (1e-3, 1e-2):
            res = []
            for seed in (1, 2, 3):
                s = SettleProfile(gamma=0.086, kappa=1e-3, eta=1e-3)
                y, _ = simulate(settle=(s, IDEAL), dac_mismatch=mm, seed=seed, **kw)
                res.append(analyze(y, fs=kw['fs'])['sndr'])
            print(f"  DAC mismatch {mm*100:.1f}% of step: SNDR={['%.2f'%v for v in res]}")

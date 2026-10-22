#!/usr/bin/env python3
"""Quantizer requirements from the exact per-clock loop model of
gf180/behavioral/ct2_dac2_options.py: stage 2 scaled x10, finite OTA gains
(A1 2710, A2 3000), ELD 9.4 % (RTL DAC_LOAD_CYCLE = 2), ideal DACs.

Comparator imperfections, one at a time:
  offset  static random threshold error per comparator, sigma (V); the worst
          of several seeds is reported
  scale   threshold spacing x scale (quantizer gain error)
  noise   Gaussian input-referred noise per decision, sigma (V)
  hyst    memory of the previous decision: the threshold moves by -hyst after
          a 1 and +hyst after a 0 (negative: the other sign)
  meta    a decision with |overdrive| < meta is a coin flip (metastability)
  kick    differential charge into the stage-2 integrator per decision,
          kick * (2c - 31) / 31 of the DAC2 unit charge per clock, plus a
          code-squared part kick2 * ((2c - 31) / 31)^2 (worst case for a
          code-dependent kickback that the OTA does not absorb)

Run: python3 quantizer_spec.py   (markdown table: SNDR 0.5-100 Hz, peak |x2|)
"""
import os
import sys
import numpy as np
from numba import njit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "behavioral"))
import ct2_dac2_options as m  # noqa: E402

ELD = 3 / 32  # CMP_STROBE -> SEL change, 3 MCLK of 32


@njit(cache=True)
def simulate(ad, b, ad0, b0, u, thr, noise, hyst, meta, kick, kick2, seed):
    """Code c[n] (0..31) or -1 after a runaway, and the peak |x2|."""
    np.random.seed(seed)
    n = u.shape[0]
    out = np.empty(n, np.int64)
    prev = np.zeros(31)
    x1 = 0.0
    x2 = 0.0
    yp = 0.0
    x2max = 0.0
    for i in range(n):
        mx1 = ad0[0, 0] * x1 + ad0[0, 1] * x2 + b0[0, 0] * u[i] + (b0[0, 1] + b0[0, 2]) * yp
        mx2 = ad0[1, 0] * x1 + ad0[1, 1] * x2 + b0[1, 0] * u[i] + (b0[1, 1] + b0[1, 2]) * yp
        c = 0
        for k in range(31):
            t = thr[k] - hyst * (2.0 * prev[k] - 1.0)
            v = x2 + noise * np.random.randn() - t
            if abs(v) < meta:
                d = 1.0 if np.random.rand() < 0.5 else 0.0
            else:
                d = 1.0 if v > 0.0 else 0.0
            prev[k] = d
            c += int(d)
        out[i] = c
        y = (2.0 * c - 31.0) / 31.0  # = 1 - 2 k_on / 31, k_on = 31 - c
        # kickback as an extra DAC2-like charge (b[1, 2] is the DAC2 column)
        yk = kick * y + kick2 * y * y
        x1 = ad[0, 0] * mx1 + ad[0, 1] * mx2 + b[0, 0] * u[i] + (b[0, 1] + b[0, 2]) * y
        x2 = (ad[1, 0] * mx1 + ad[1, 1] * mx2 + b[1, 0] * u[i] + b[1, 1] * y
              + b[1, 2] * (y + yk))
        yp = y
        if i > n // 20:
            x2max = max(x2max, abs(x2))
        if abs(x2) > 10.0:
            out[i:] = -1
            break
    return out, x2max


def run(offset=0.0, scale=1.0, noise=0.0, hyst=0.0, meta=0.0, kick=0.0, kick2=0.0,
        ain=m.AIN, seeds=(1,)):
    ad0, b0 = m.discretize(10.0, 1.0, 2710, 3000, ELD * m.T)
    ad, b = m.discretize(10.0, 1.0, 2710, 3000, (1 - ELD) * m.T)
    n = int(round((m.T_SETTLE + m.T_REC + m.T_TAIL) * m.FS))
    u = ain * np.sin(2 * np.pi * m.F0 * (np.arange(n) + 0.5) * m.T)
    worst, x2w = np.inf, 0.0
    for s in seeds:
        rng = np.random.default_rng(1000 + s)
        thr = m.THR * scale + offset * rng.standard_normal(31)
        c, x2max = simulate(ad, b, ad0, b0, u, thr, noise, hyst, meta, kick, kick2, s)
        v = m.sndr(c)
        worst, x2w = min(worst, v), max(x2w, x2max)
    return worst, x2w


CASES = [("ideal comparators", {})] + [
    (f"offset sigma {o*1e3:g} mV (worst of 8)", dict(offset=o, seeds=range(1, 9)))
    for o in (1e-3, 3e-3, 6e-3, 10e-3)] + [
    (f"threshold spacing x{s}", dict(scale=s)) for s in (0.5, 0.7, 1.4, 2.0)] + [
    (f"noise {v*1e3:g} mVrms", dict(noise=v)) for v in (0.3e-3, 1e-3, 3e-3)] + [
    (f"hysteresis {h*1e3:+g} mV", dict(hyst=h)) for h in (1e-3, -1e-3, 3e-3)] + [
    (f"metastable window {v*1e6:g} uV", dict(meta=v)) for v in (10e-6, 100e-6, 1e-3)] + [
    (f"kickback {k:g} of a DAC2 unit (linear in code)", dict(kick=k)) for k in (0.01, 0.1)] + [
    (f"kickback {k:g} of a DAC2 unit (code squared)", dict(kick2=k)) for k in (0.001, 0.01)] + [
    ("offset 6 mV, noise 1 mV, hysteresis 1 mV, ain 0.4 V (worst of 8)",
     dict(offset=6e-3, noise=1e-3, hyst=1e-3, ain=0.4, seeds=range(1, 9))),
]


def main():
    print("| case | SNDR 0.5-100 Hz (dB) | peak abs(x2) (mV) |")
    print("|---|---|---|")
    for label, kw in CASES:
        v, x2 = run(**kw)
        print(f"| {label} | {v:.1f} | {x2*1e3:.1f} |", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Behavioral check of DAC2 implementation options for the CT 2nd-order 5-bit
Sigma-Delta (independent-environment gain10 candidate, 2026-10-20).

Circuit values from ct_candidate/afe_adc_cap2_direct_threshold1u_20261020:
  stage 1: RIN 9375, DAC1 300k/31 (lumped 9677), C1 680.5137683p
  stage 2: R21 1Meg, DAC2 (320Meg/3)/31 (lumped 3.441Meg), C2 1.953125p
  quantizer on O2 (diff): 31 thresholds -46.875..+46.875 mV, step 3.125 mV
  DAC diff level = -VREF*y, VREF = 0.5 V, y = 1 - 2k/31 (k units at VP);
  fs = 1.024 MHz.
The loop is solved exactly per clock (matrix exponential, NRZ DAC, zero ELD).
Leaky integrators model finite OTA DC gain (A1 includes the R21 load on OTA1).
Quantization only: no device noise, no OTA nonlinearity.

Stage-2 options (all keep R21*C2 and RD2*C2, i.e. the same ideal NTF):
  s   : R21/s, RD2/s, C2*s   (poly rescale, or current DAC with C2*s)
  k2  : DAC2 coefficient error (current-DAC reference tolerance, pseudo-R spread)
  eps : DAC2 charge error per toggled unit, relative to the unit charge per
        clock (current-steering switch injection; shrinks as 1/s)

Run: python3 gf180/behavioral/ct2_dac2_options.py   (prints a markdown table)
"""
import numpy as np
from numba import njit
from scipy.linalg import expm
from scipy.signal import resample_poly

FS = 1.024e6
T = 1.0 / FS
VREF = 0.5
RIN, RD1, C1 = 9375.0, 300e3 / 31, 680.5137683e-12
R21_0, RD2_0, C2_0 = 1e6, (320e6 / 3) / 31, 1.953125e-12
THR = -46.875e-3 + 3.125e-3 * np.arange(31)
AIN, F0 = 0.3, 32.0  # differential peak at the ADC input
T_SETTLE, T_REC, T_TAIL = 0.25, 4.0, 0.25  # tail keeps FIR edge effects out


def discretize(s=1.0, k2=1.0, a1=np.inf, a2=np.inf, tseg=T):
    """x(t+tseg) = Ad x(t) + b[:,0] u + b[:,1] y1 + b[:,2] y2 (exact for
    inputs held constant over the segment)."""
    r21, rd2, c2 = R21_0 / s, RD2_0 / s / k2, C2_0 * s
    g1 = (1 / RIN + 1 / RD1) / (a1 * C1)
    g2 = (1 / r21 + 1 / rd2) / (a2 * c2)
    m = np.zeros((5, 5))
    m[:2, :2] = [[-g1, 0.0], [1 / (r21 * c2), -g2]]
    m[:2, 2:] = [[1 / (RIN * C1), -VREF / (RD1 * C1), 0.0],
                 [0.0, 0.0, -VREF / (rd2 * c2)]]
    e = expm(m * tseg)
    return e[:2, :2].copy(), e[:2, 2:].copy()


@njit(cache=True)
def simulate(ad, b, u, thr, eps, sigma1, sigma2, seed, eps1=0.0, eps_odd=0.0,
             odd_sigma=0.0, ad0=np.eye(2), b0=np.zeros((2, 3)), eps1_sigma=0.0):
    """Quantizer count c[n] (0..31), or -1 after a loop runaway, plus the peak
    |x1|, |x2|. Both DACs use DWA over 31 units with static mismatch
    sigma1/sigma2; eps (eps1) adds a DAC2 (DAC1) charge error of eps*unit per
    toggled element each clock (even part, same sign for on and off). eps_odd
    adds +e_j when DAC2 element j turns on and -e_j when it turns off (odd
    part, e.g. gate feedthrough), e_j = eps_odd*(1 + odd_sigma*N(0,1)).
    One unit = one element's per-clock differential charge (2*Iu*T).
    Excess loop delay: (ad0, b0) propagate the first ELD part of each clock
    with the previous DAC levels; (ad, b) then cover the rest with the new
    levels. ad0 = I, b0 = 0 means zero ELD."""
    np.random.seed(seed)
    w1 = 1.0 + sigma1 * np.random.randn(31)
    w2 = 1.0 + sigma2 * np.random.randn(31)
    e_odd = eps_odd * (1.0 + odd_sigma * np.random.randn(31))
    # DAC1 even (toggle) error per element: common part eps1 + static random part
    e1 = eps1 + eps1_sigma * np.random.randn(31)
    w1 *= 31.0 / w1.sum()
    w2 *= 31.0 / w2.sum()
    n = u.shape[0]
    out = np.empty(n, np.int64)
    x1 = 0.0
    x2 = 0.0
    p1 = 0
    p2 = 0
    prev1 = np.zeros(31)
    sel1 = np.zeros(31)
    prev2 = np.zeros(31)
    sel2 = np.zeros(31)
    x1max = 0.0
    x2max = 0.0
    y1p = 0.0
    y2p = 0.0
    for i in range(n):
        # ELD segment with the previous DAC levels (no-op when ad0 = I, b0 = 0)
        mx1 = ad0[0, 0] * x1 + ad0[0, 1] * x2 + b0[0, 0] * u[i] + b0[0, 1] * y1p + b0[0, 2] * y2p
        mx2 = ad0[1, 0] * x1 + ad0[1, 1] * x2 + b0[1, 0] * u[i] + b0[1, 1] * y1p + b0[1, 2] * y2p
        c = 0
        for k in range(31):
            if x2 > thr[k]:
                c += 1
        out[i] = c
        k_on = 31 - c
        s1 = 0.0
        for j in range(31):
            sel1[j] = 0.0
        for j in range(k_on):
            idx = (p1 + j) % 31
            sel1[idx] = 1.0
            s1 += w1[idx]
        toggles1 = 0.0  # DAC1 even error, summed over toggled elements
        for j in range(31):
            if sel1[j] != prev1[j]:
                toggles1 += e1[j]
            prev1[j] = sel1[j]
        p1 = (p1 + k_on) % 31
        s2 = 0.0
        for j in range(31):
            sel2[j] = 0.0
        for j in range(k_on):
            idx = (p2 + j) % 31
            sel2[idx] = 1.0
            s2 += w2[idx]
        toggles = 0.0
        odd = 0.0
        for j in range(31):
            if sel2[j] != prev2[j]:
                toggles += 1.0
                odd += e_odd[j] if sel2[j] > 0.5 else -e_odd[j]
            prev2[j] = sel2[j]
        p2 = (p2 + k_on) % 31
        y1 = 1.0 - 2.0 * s1 / 31.0 + toggles1 / 31.0
        y2 = 1.0 - 2.0 * s2 / 31.0 + (eps * toggles + odd) / 31.0
        nx1 = ad[0, 0] * mx1 + ad[0, 1] * mx2 + b[0, 0] * u[i] + b[0, 1] * y1 + b[0, 2] * y2
        nx2 = ad[1, 0] * mx1 + ad[1, 1] * mx2 + b[1, 0] * u[i] + b[1, 1] * y1 + b[1, 2] * y2
        x1 = nx1
        x2 = nx2
        y1p = y1
        y2p = y2
        if i > n // 20:
            x1max = max(x1max, abs(x1))
            x2max = max(x2max, abs(x2))
        if abs(x2) > 10.0:
            out[i:] = -1
            break
    return out, x1max, x2max


def sndr(c):
    """SNDR in 0.5-100 Hz from the code stream: CIC4 (R=256) then FIR /10 to
    400 S/s; coherent 4 s window (128 cycles of 32 Hz), rectangular FFT."""
    if (c < 0).any():
        return float("nan")
    r = 256
    acc = c.astype(np.int64)  # integer CIC, wraps modulo 2^64 like the RTL
    for _ in range(4):
        acc = np.cumsum(acc)
    acc = acc[r - 1::r]
    for _ in range(4):
        acc = np.diff(acc, prepend=np.int64(0))
    y = 1.0 - 2.0 * (acc / float(r ** 4)) / 31.0
    d = resample_poly(y, 1, 10, window=("kaiser", 12.0))
    fs2 = FS / r / 10
    nrec = int(round(T_REC * fs2))
    i0 = int(round(T_SETTLE * fs2))
    spec = np.abs(np.fft.rfft(d[i0:i0 + nrec])) ** 2
    f = np.arange(spec.size) * fs2 / nrec
    ks = int(round(F0 * nrec / fs2))
    band = (f >= 0.5) & (f <= 100.0)
    band[ks] = False
    return 10 * np.log10(spec[ks] / spec[band].sum())


def run_case(s=1.0, k2=1.0, a1=np.inf, a2=np.inf, eps=0.0, sigma1=0.0,
             sigma2=0.0, seed=1, ain=AIN, eps1=0.0, eps_odd=0.0, odd_sigma=0.0,
             eld=0.0, eps1_sigma=0.0, swings=False):
    """eld: excess loop delay as a fraction of the clock period."""
    if eld > 0:
        ad0, b0 = discretize(s, k2, a1, a2, eld * T)
        ad, b = discretize(s, k2, a1, a2, (1 - eld) * T)
    else:
        ad, b = discretize(s, k2, a1, a2)
        ad0, b0 = np.eye(2), np.zeros((2, 3))
    n = int(round((T_SETTLE + T_REC + T_TAIL) * FS))
    u = ain * np.sin(2 * np.pi * F0 * (np.arange(n) + 0.5) * T)
    c, x1max, x2max = simulate(ad, b, u, THR, eps, sigma1, sigma2, seed, eps1,
                               eps_odd, odd_sigma, ad0, b0, eps1_sigma)
    return (sndr(c), x1max, x2max) if swings else sndr(c)


CASES = [
    ("as drawn, ideal OTAs", dict(s=1)),
    ("as drawn, A1=21300 (R21 1Meg load), A2=3000", dict(s=1, a1=21300, a2=3000)),
    ("s=10 (C2 19.5p, R21 100k), A1=2710, A2=3000", dict(s=10, a1=2710, a2=3000)),
    ("s=47.6 (C2 93p, R21 21k), A1=600, A2=3000", dict(s=47.6, a1=600, a2=3000)),
] + [(f"s=10, DAC2 coefficient x{k2}", dict(s=10, k2=k2, a1=2710, a2=3000))
     for k2 in (0.3, 0.5, 0.7, 0.85, 1.15, 1.3, 1.5, 2.0, 3.0, 10.0)] + [
    (f"s=1, DAC2 injection eps={e}", dict(s=1, a1=21300, a2=3000, eps=e))
    for e in (0.01, 0.03, 0.1)] + [
    (f"s=10, DAC2 injection eps={e}", dict(s=10, a1=2710, a2=3000, eps=e))
    for e in (0.001, 0.003, 0.01)] + [
    ("s=10, DAC mismatch 0.5%/2% with DWA", dict(s=10, a1=2710, a2=3000,
                                                sigma1=0.005, sigma2=0.02)),
] + [(f"s=10, DAC1 injection eps1={e}", dict(s=10, a1=2710, a2=3000, eps1=e))
     for e in (1e-5, 1e-4, 1e-3)] + [
    # transistor DAC2 cell (gf180/sim/dac2_cell): odd part -2.50 fC of
    # 2*Iu*T = 45.78 fC -> 5.5 %, MC spread ~1 %; even part 3 sigma 0.004 fC
    ("s=10, DAC2 cell odd part +-5.5% (feedthrough)", dict(s=10, a1=2710, a2=3000,
                                                           eps_odd=0.055)),
    ("s=10, DAC2 cell odd part -5.5%", dict(s=10, a1=2710, a2=3000, eps_odd=-0.055)),
    ("s=10, DAC2 cell odd 5.5% +-1%/elem, even 1e-4, mismatch 3%",
     dict(s=10, a1=2710, a2=3000, eps_odd=0.055, odd_sigma=0.01, eps=1e-4, sigma2=0.03)),
]


def main():
    print("| case | SNDR 0.5-100 Hz (dB) |")
    print("|---|---|")
    for label, kw in CASES:
        print(f"| {label} | {run_case(**kw):.1f} |", flush=True)


if __name__ == "__main__":
    main()

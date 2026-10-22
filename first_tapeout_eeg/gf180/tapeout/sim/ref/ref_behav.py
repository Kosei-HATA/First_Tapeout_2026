#!/usr/bin/env python3
"""Behavioral check of the DAC1 reference path (tracker B6): code-dependent
reference current through the path resistance.

Every DAC1 unit cell (gf180/sim/dac1_cell, TG-switched, complementary) draws
q_t = 11.9 fC from VREFP per toggle and returns the same to VREFN
(gf180/sim/dac1_cell/ref_charge.py; 11.5..12.1 fC over corners). With DWA the
number of toggles N per frame depends on the code (about 2 min(k, 31 - k)), so
the references carry q_t N fs on top of their constant current. Through a path
resistance R per side, VREFP - VREFN drops by 2 R q_t N fs, which scales the DAC1
level of that frame. The drop follows the frames with time constant tau (on-chip
decoupling times the path resistance; 0 = within the frame).

Loop as in gf180/tapeout/sim/quantizer/quantizer_spec.py: stage 2 scaled x10,
A1 2710, A2 3000, ELD 3/32, DWA on both DACs, ideal quantizer and DAC2, 0.3 V pk
32 Hz input. SNDR in 0.5..100 Hz and HD3 (96 Hz) from the decimated output.

--steered applies, instead, the even error of the steered DAC1 cell, proportional to
the virtual-ground difference at the switching instant (x 1, 10, 100 for margin).

Usage: python3 ref_behav.py [--qt 11.9e-15] [--r 0 1 3 10 30 100] [--tau 0 1e-6 1e-5]
       [--steered -3e-13]
"""
import argparse
import os
import sys
import numpy as np
from numba import njit
from scipy.signal import resample_poly

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "behavioral"))
import ct2_dac2_options as m  # noqa: E402

ELD = 3 / 32
RIN_, RD1_, VREF_ = m.RIN, m.RD1, m.VREF


@njit(cache=True)
def simulate(ad, b, ad0, b0, u, thr, kref, alpha, kvd=0.0, gi=31.1, go=1 / 3218.0, vd_out=np.zeros(1)):
    """kref = 2 R q_t fs / VREF: relative VREF drop per toggled element; the drop
    of frame i is the first-order filtered kref * N with pole alpha.
    kvd: even charge error per toggled element per volt of virtual-ground
    difference v_vd, in units of the element's per-frame differential charge
    (steered DAC1 cell); v_vd = gi * I_diff + go * x1 with the differential
    integrator current I_diff of the frame (loop fit: 62.2 ohm per side current
    and 1/3218 of v_o1). vd_out (length n) receives v_vd per frame when given."""
    n = u.shape[0]
    out = np.empty(n, np.int64)
    prev1 = np.zeros(31)
    sel1 = np.zeros(31)
    prev2 = np.zeros(31)
    sel2 = np.zeros(31)
    p1 = 0
    p2 = 0
    x1 = 0.0
    x2 = 0.0
    y1p = 0.0
    y2p = 0.0
    dv = 0.0
    for i in range(n):
        mx1 = ad0[0, 0] * x1 + ad0[0, 1] * x2 + b0[0, 0] * u[i] + b0[0, 1] * y1p + b0[0, 2] * y2p
        mx2 = ad0[1, 0] * x1 + ad0[1, 1] * x2 + b0[1, 0] * u[i] + b0[1, 1] * y1p + b0[1, 2] * y2p
        c = 0
        for k in range(31):
            if x2 > thr[k]:
                c += 1
        out[i] = c
        k_on = 31 - c
        for j in range(31):
            sel1[j] = 0.0
            sel2[j] = 0.0
        for j in range(k_on):
            sel1[(p1 + j) % 31] = 1.0
            sel2[(p2 + j) % 31] = 1.0
        tog = 0.0
        for j in range(31):
            if sel1[j] != prev1[j]:
                tog += 1.0
            prev1[j] = sel1[j]
            prev2[j] = sel2[j]
        p1 = (p1 + k_on) % 31
        p2 = (p2 + k_on) % 31
        dv = alpha * dv + (1.0 - alpha) * kref * tog
        y = 1.0 - 2.0 * k_on / 31.0
        # virtual-ground difference when this frame's elements switch: set by the
        # previous frame's integrator current and the stage-1 output
        vd = gi * (u[i] / RIN_ - VREF_ * y1p / RD1_) + go * mx1
        if vd_out.shape[0] == n:
            vd_out[i] = vd
        y1 = y * (1.0 - dv) + kvd * vd * tog / 31.0
        y2 = y
        nx1 = ad[0, 0] * mx1 + ad[0, 1] * mx2 + b[0, 0] * u[i] + b[0, 1] * y1 + b[0, 2] * y2
        nx2 = ad[1, 0] * mx1 + ad[1, 1] * mx2 + b[1, 0] * u[i] + b[1, 1] * y1 + b[1, 2] * y2
        x1 = nx1
        x2 = nx2
        y1p = y1
        y2p = y2
        if abs(x2) > 10.0:
            out[i:] = -1
            break
    return out


def spectrum(c):
    """Decimated output as in ct2_dac2_options.sndr: SNDR 0.5..100 Hz and HD3 (dBc)."""
    r = 256
    acc = c.astype(np.int64)
    for _ in range(4):
        acc = np.cumsum(acc)
    acc = acc[r - 1::r]
    for _ in range(4):
        acc = np.diff(acc, prepend=np.int64(0))
    y = 1.0 - 2.0 * (acc / float(r ** 4)) / 31.0
    d = resample_poly(y, 1, 10, window=("kaiser", 12.0))
    fs2 = m.FS / r / 10
    nrec = int(round(m.T_REC * fs2))
    i0 = int(round(m.T_SETTLE * fs2))
    spec = np.abs(np.fft.rfft(d[i0:i0 + nrec])) ** 2
    f = np.arange(spec.size) * fs2 / nrec
    ks = int(round(m.F0 * nrec / fs2))
    band = (f >= 0.5) & (f <= 100.0)
    band[ks] = False
    return 10 * np.log10(spec[ks] / spec[band].sum()), 10 * np.log10(spec[3 * ks] / spec[ks])


def run(r_side, qt, tau, kvd=0.0, report_vd=False):
    ad0, b0 = m.discretize(10.0, 1.0, 2710, 3000, ELD * m.T)
    ad, b = m.discretize(10.0, 1.0, 2710, 3000, (1 - ELD) * m.T)
    n = int(round((m.T_SETTLE + m.T_REC + m.T_TAIL) * m.FS))
    u = m.AIN * np.sin(2 * np.pi * m.F0 * (np.arange(n) + 0.5) * m.T)
    kref = 2 * r_side * qt * m.FS / m.VREF
    alpha = np.exp(-m.T / tau) if tau > 0 else 0.0
    vd = np.zeros(n)
    c = simulate(ad, b, ad0, b0, u, m.THR, kref, alpha, kvd, 31.1, 1 / 3218.0, vd)
    if report_vd:
        print(f"model v_vd at the DAC update: std {vd[n // 10:].std() * 1e6:.1f} uV")
    return spectrum(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qt", type=float, default=11.9e-15)
    ap.add_argument("--r", type=float, nargs="+", default=[0, 1, 3, 10, 30, 100])
    ap.add_argument("--tau", type=float, nargs="+", default=[0.0, 1e-6, 1e-5])
    ap.add_argument("--steered", type=float, nargs="*", default=None,
                    help="steered DAC1 cell: even charge per toggle per volt of v_vd (C/V), "
                         "e.g. -3e-13 (gf180/sim/dac1_cell/run_cell.py --arch steered --voff)")
    a = ap.parse_args()
    if a.steered is not None:
        unit = 2 * 0.25 / 300e3 * m.T  # element's per-frame differential charge
        print("| steered even charge per toggle (fC/mV) | x | SNDR 0.5-100 Hz (dB) | HD3 (dBc) |")
        print("|---|---|---|---|")
        for k in a.steered:
            for x in (1, 10, 100):
                s_, h3 = run(0.0, a.qt, 0.0, k * x / unit, report_vd=(x == 1))
                print(f"| {k * 1e12:g} | {x} | {s_:.1f} | {h3:.1f} |", flush=True)
        return
    print(f"q_t {a.qt * 1e15:g} fC per toggle, 0.3 V pk 32 Hz")
    print("| R per side (ohm) | tau (us) | SNDR 0.5-100 Hz (dB) | HD3 (dBc) |")
    print("|---|---|---|---|")
    for r in a.r:
        for tau in a.tau:
            s, h3 = run(r, a.qt, tau)
            print(f"| {r:g} | {tau * 1e6:g} | {s:.1f} | {h3:.1f} |", flush=True)
            if r == 0:
                break


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Short-window checks of the transistor ADC (adc_deck.py, make_deck.py) and E2E
(e2e_deck.py) runs: sine fits at the input frequency over [--t0, end].

  ADC decks:  v(sig) (ADC input, differential), O1, O2 swings, the DAC1 level v(norm1)
              sampled at mid-frame and fitted: the loop's signal gain is
              norm1 amplitude x 0.96875 V / input amplitude (1 for a working loop)
  E2E deck:   v(sig) (electrode, differential), the AFE output OUTP - OUTN (gain about
              277 chopped, averaged over each 7.8125 us chopper period before the fit),
              the DAC1 level: the overall gain electrode -> ADC

The residual of the norm1 fit (rms over the window) is mostly quantization noise at
these lengths; a working loop keeps it below about 0.1 (DAC levels).

Usage: python3 tr_window.py <run folder> [--kind adc|e2e] [--fsig 20e3] [--t0 20e-6]
"""
import argparse
import os
import numpy as np

FS = 1.024e6
T = 1 / FS
T0_LOAD = 2.0784625e-06
TCH = 1 / 128e3


def fit(t, y, f):
    """least-squares a cos + b sin + c; returns amplitude, phase (deg), offset, rms residual"""
    m = np.vstack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones_like(t)]).T
    c, *_ = np.linalg.lstsq(m, y, rcond=None)
    r = y - m @ c
    return np.hypot(c[0], c[1]), np.degrees(np.arctan2(-c[1], c[0])), c[2], r.std()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--kind", choices=["adc", "e2e"], default="adc")
    ap.add_argument("--fsig", type=float, default=20e3)
    ap.add_argument("--t0", type=float, default=20e-6)
    a = ap.parse_args()
    x = np.loadtxt(os.path.join(a.folder, "out.csv"))
    t = x[:, 0]
    col = lambda k: x[:, 2 * k + 1]
    sig = col(0)
    m = t >= a.t0
    s_amp, s_ph, _, _ = fit(t[m], sig[m], a.fsig)
    k0 = int(np.ceil((a.t0 - T0_LOAD) / T))
    k1 = int((t[-1] - T0_LOAD) / T) - 1
    tk = T0_LOAD + (np.arange(k0, k1) + 0.5) * T
    n1 = np.interp(tk, t, col(9))
    n_amp, n_ph, n_off, n_res = fit(tk, n1, a.fsig)
    idd = -col(10)[m].mean()
    print(f"{a.folder}: window {a.t0 * 1e6:g}..{t[-1] * 1e6:.1f} us, {len(tk)} frames, AVDD {idd * 1e3:.2f} mA")
    if a.kind == "adc":
        o1 = col(1) - col(2)
        o2 = col(5) - col(6)
        print(f"  input {s_amp:.4f} V pk; DAC1 level {n_amp:.4f} (x 0.96875 V = {n_amp * 0.96875:.4f} V), "
              f"phase {n_ph - s_ph:+.1f} deg vs input, offset {n_off:+.4f}, residual {n_res:.4f} rms")
        print(f"  loop gain {n_amp * 0.96875 / s_amp:.4f}; O1 {o1[m].min() * 1e3:.1f}..{o1[m].max() * 1e3:.1f} mV, "
              f"O2 {o2[m].min() * 1e3:.1f}..{o2[m].max() * 1e3:.1f} mV; O1 CM {(col(1) + col(2))[m].mean() / 2:.4f} V, "
              f"O2 CM {(col(5) + col(6))[m].mean() / 2:.4f} V")
    else:
        vo = col(1) - col(2)
        q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
        e = np.arange(np.ceil(a.t0 / TCH), np.floor(t[-1] / TCH)) * TCH
        per = np.diff(np.interp(e, t, q)) / TCH
        tp = e[:-1] + TCH / 2
        o_amp, o_ph, o_off, o_res = fit(tp, per, a.fsig)
        print(f"  electrode {s_amp * 1e3:.4f} mV pk; AFE output (period averages) {o_amp * 1e3:.2f} mV pk, "
              f"gain {o_amp / s_amp:.1f}, phase {o_ph - s_ph:+.1f} deg, offset {o_off * 1e3:+.2f} mV")
        print(f"  DAC1 level {n_amp:.4f} (x 0.96875 V = {n_amp * 0.96875 * 1e3:.2f} mV), ADC gain "
              f"{n_amp * 0.96875 / o_amp:.3f}, overall {n_amp * 0.96875 / s_amp:.1f}, residual {n_res:.4f} rms")
        print(f"  AFE output CM {(col(1) + col(2))[m].mean() / 2:.4f} V; O1 "
              f"{(col(3) - col(4))[m].min() * 1e3:.1f}..{(col(3) - col(4))[m].max() * 1e3:.1f} mV")


if __name__ == "__main__":
    main()

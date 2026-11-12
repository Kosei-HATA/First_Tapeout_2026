#!/usr/bin/env python3
"""In-band error from the OTA1 chopper edges, from an unchopped loop run.

Each chopper edge changes the first-integrator charge by q = beta I + gamma v_o1 per
side (ota1_edge.py: I the OTA1 current into C1 per side, v_o1 the differential O1
voltage just before the edge; the same for A->B and B->A edges). On the input that is
an impulse of area 2 RIN q. The edges come every N = fs / (2 fch) frames, so the
sequence q_k samples the loop state at 2 fch: the shaped quantization noise in I
(largest near fs/2) folds into the band. The in-band density of the impulse train is
sqrt(r^2 S_q(f)) (r = 2 fch, S_q the one-sided density of the sequence per Hz at rate
r), taken as the mean over the low-frequency bins away from the input tone.

I and v_o1 come from a loop run of make_deck.py with OTA1 held in phase A (its
out.csv: v(sig), v(o1p), v(o1n), v(i1p), v(i1n), v(norm1)), sampled at --phase frames
after each DAC load (the edge position in the frame).

Usage: python3 chop1_fold.py <run folder> --beta -6.36e-9 --gamma -0.077e-12
       [--fsig 1e3] [--fch 2e3 4e3 8e3 16e3 32e3 64e3 128e3] [--phase 0.5] [--fmax 3e3]
"""
import argparse
import os
import numpy as np
import pandas as pd

FS = 1.024e6
T = 1 / FS
T0 = 2.0784625e-06  # first DAC load (make_deck.py)
RIN = 9375.0
RD1 = 300e3 / 31
VREF = 0.5
BAND = (0.5, 100.0)
GAIN_AFE = 277.0


def load(folder, phase, start=0.25e-3):
    d = pd.read_csv(os.path.join(folder, "out.csv"), sep=r"\s+", header=None,
                    usecols=[0, 1, 3, 5, 7, 9, 19], engine="c", dtype=np.float64).to_numpy()
    t, sig, o1p, o1n, i1p, i1n, n1 = d.T
    k0 = int(np.ceil((start - T0) / T))
    n = int((t[-1] - T0) / T) - k0 - 2
    tk = T0 + (k0 + np.arange(n) + phase) * T
    g = lambda x: np.interp(tk, t, x)
    vip = g(i1p) - 1.65
    i = (g(sig) / 2 - vip) / RIN + (g(n1) * VREF - vip) / RD1
    return i, g(o1p) - g(o1n)


def fold(i, vo, beta, gamma, fch, fsig, fmax):
    """In-band density (V/rtHz at the ADC input) of the edge errors at chopper frequency fch."""
    nper = FS / (2 * fch)
    if abs(nper - round(nper)) > 1e-9:
        raise SystemExit(f"fch {fch:g}: the half period must be a whole number of frames")
    nper = int(round(nper))
    r = 2 * fch
    a = 2 * RIN * (beta * i[::nper] + gamma * vo[::nper])
    w = np.hanning(len(a))
    s = 2 * np.abs(np.fft.rfft((a - a.mean()) * w)) ** 2 / (r * np.sum(w ** 2))
    f = np.fft.rfftfreq(len(a), 1 / r)
    bad = f < 2 * f[1]
    for h in range(1, 20):  # the tone and its harmonics, aliased at rate r
        fa = abs(((h * fsig + r / 2) % r) - r / 2)
        bad |= np.abs(f - fa) <= 3 * f[1]
    sel = ~bad & (f <= min(fmax, r / 2))
    if sel.sum() < 3:
        sel = ~bad & (f <= r / 2)
    return np.sqrt(np.mean(s[sel]) * r ** 2), int(sel.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--beta", type=float, required=True, help="edge charge per OTA1 current (s)")
    ap.add_argument("--gamma", type=float, required=True, help="edge charge per v_o1 (C/V)")
    ap.add_argument("--fsig", type=float, default=1e3)
    ap.add_argument("--fch", type=float, nargs="+", default=[2e3, 4e3, 8e3, 16e3, 32e3, 64e3, 128e3])
    ap.add_argument("--phase", type=float, default=0.5)
    ap.add_argument("--fmax", type=float, default=3e3, help="highest bin used for the in-band level")
    a = ap.parse_args()
    i, vo = load(a.folder, a.phase)
    print(f"{len(i)} frames; I per side std {i.std() * 1e6:.3f} uA, v_o1 std {vo.std() * 1e3:.1f} mV; "
          f"beta {a.beta * 1e9:g} ns, gamma {a.gamma * 1e12:g} pC/V")
    print("| fch (kHz) | edges used | bins | density at the ADC input (nV/rtHz) | electrode, 0.5-100 Hz (nVrms) |")
    print("|---|---|---|---|---|")
    for fch in a.fch:
        dens, nb = fold(i, vo, a.beta, a.gamma, fch, a.fsig, a.fmax)
        n = len(i) // int(round(FS / (2 * fch)))
        print(f"| {fch / 1e3:g} | {n} | {nb} | {dens * 1e9:.2f} | "
              f"{dens * np.sqrt(BAND[1] - BAND[0]) / GAIN_AFE * 1e9:.3f} |")


if __name__ == "__main__":
    main()

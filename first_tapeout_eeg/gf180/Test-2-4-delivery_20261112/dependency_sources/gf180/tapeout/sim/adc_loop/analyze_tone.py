#!/usr/bin/env python3
"""Harmonic distortion of the transistor ADC loop deck (make_deck.py) from its
quantizer output.

The DAC1 level v(norm1) is constant over each modulator clock; it is sampled in
the middle of every clock after T_START and analysed over an integer number of
signal periods with a Blackman-Harris window. A rectangular window lets any slow
start-up transient leak into every bin (seen on 10/22: a flat -91 dBc floor that
the window removed). HD2..HD5 are the bins of the coherent harmonics relative to
the fundamental; the floor is the median bin at least 5 bins away from DC and
the harmonics (Blackman-Harris main lobe +-4 bins), up to the 6th harmonic.

Usage: python3 analyze_tone.py <deck folder> [--fsig 1e3] [--start 0.25e-3]
"""
import argparse
import os
import numpy as np
import pandas as pd
from scipy.signal.windows import blackmanharris

FS = 1.024e6
T = 1 / FS
T_LOAD0 = 2.0784625e-06  # first DAC load (events.txt of make_deck.py)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--fsig", type=float, default=1e3)
    ap.add_argument("--start", type=float, default=0.25e-3)
    a = ap.parse_args()
    # only time and v(norm1): a 32 ms run writes an 11.6 GB out.csv
    d = pd.read_csv(os.path.join(a.folder, "out.csv"), sep=r"\s+", header=None, usecols=[0, 19],
                    engine="c", dtype=np.float64).to_numpy()
    t, norm1 = d[:, 0], d[:, 1]
    n_per = int(round(FS / a.fsig))
    k0 = int(np.ceil((a.start - T_LOAD0) / T))
    n_avail = int((t[-1] - T_LOAD0) / T) - k0 - 1
    n = (n_avail // n_per) * n_per
    tk = T_LOAD0 + (k0 + np.arange(n) + 0.5) * T
    y = np.interp(tk, t, norm1)
    w = blackmanharris(n)
    x = np.abs(np.fft.rfft((y - y.mean()) * w))
    cyc = n // n_per
    fund = x[cyc]
    amp = 2 * fund / w.sum()  # coherent tone: sine amplitude from the bin
    harm = {k: x[k * cyc] for k in range(2, 6)}
    # floor: bins at least 5 bins away from DC and every harmonic, up to the 6th harmonic
    b = np.arange(5, 6 * cyc)
    far = np.min(np.abs(b[:, None] - cyc * np.arange(0, 7)[None, :]), axis=1) >= 5
    floor = np.median(x[b[far]]) if far.any() else float("nan")
    print(f"{cyc} periods of {a.fsig:g} Hz ({n} clocks): amplitude {amp:.5f} (DAC level), "
          + ", ".join(f"HD{k} {20*np.log10(v/fund):.1f}" for k, v in harm.items())
          + f" dBc; median bin floor up to {6*a.fsig/1e3:g} kHz {20*np.log10(floor/fund):.1f} dBc"
          + (" (harmonics below the floor are not resolved)" if min(harm.values()) < floor else ""))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Noise folding by the output-chopper blanking of the AFE (tracker A6, chopper
artifacts).

During each blanking (7 MCLK = 214 ns after every chopper edge, 256 kHz) the output
TGs are open and OUTP/OUTN are held on 30 pF (discharging into the ADC's RIN). The
output therefore carries a sample of the amplifier's wideband noise taken every
3.9 us, instead of the noise itself, for 5.5 % of the time. Wideband noise can fold
into the band that way; the frozen-phase noise analysis (afe_noise.py) cannot see it.

Method: the chopped transient of afe_offset.py (eeg_afe with the ideal clocks, offset
DAC off, RS 100 ohm per leg, load 9375 ohm and 4 pF) with a white noise source of
--en V/rtHz (ngspice trnoise, --nt sample step, smoothed at 30 MHz) in series with each
input of the amplifier core, i.e. an input-referred amplifier noise. Two runs with the same noise
realization: blanking --blank MCLK and none (the output phases then follow the input
phases with their 5 ns dead time). The output averaged over every chopper period gives
a 128 kHz sequence; its density at low frequencies (--fmax) is the in-band level. The
ratio of the two runs is the folding penalty for the amplifier's white noise.

Usage: python3 afe_blank_noise.py [--en 30e-9] [--nt 5e-9] [--tstop 2.1e-3] [--blank 7]
       [--fmax 20e3] [--seed 1]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_offset

HERE = os.path.dirname(os.path.abspath(__file__))
TCH = afe_offset.TCH
T_START = 0.1e-3


def noisy_afe(en, nt):
    """eeg_afe.spice with trnoise sources between the INP/INN nodes and the core inputs"""
    txt = open(afe_offset.AFE).read()
    old = "XAMP ELP ELN WP WN INP INN OPI ONI "
    assert txt.count(old) == 1
    na = en / np.sqrt(2 * nt)  # rms of the samples for a one-sided density en up to 1/(2 nt)
    # the trnoise samples are breakpoints; driving the large core gate capacitance from
    # them directly stopped the solver where one fell next to a chopper edge, so the
    # noise is smoothed (RC at 30 MHz, far above the AFE bandwidth) and applied through
    # a controlled source
    txt = txt.replace(old, f"VNZSP NZPR 0 DC 0 TRNOISE({na:.6e} {nt:g} 0 0)\n"
                           "RNZP NZPR NZP 1k\nCNZP NZP 0 5.3p\n"
                           f"VNZSN NZNR 0 DC 0 TRNOISE({na:.6e} {nt:g} 0 0)\n"
                           "RNZN NZNR NZN 1k\nCNZN NZN 0 5.3p\n"
                           "ENZP INPX INP NZP 0 1\nENZN INNX INN NZN 0 1\n"
                           "XAMP ELP ELN WP WN INPX INNX OPI ONI ")
    return txt


def run(blank_mclk, o):
    d = os.path.join(HERE, "runs", f"blank_noise_bl{blank_mclk}_en{o.en * 1e9:g}n_s{o.seed}")
    os.makedirs(d, exist_ok=True)
    afe = os.path.join(d, "afe_noisy.spice")
    open(afe, "w").write(noisy_afe(o.en, o.nt))
    deck = afe_offset.deck(0.0, 0, 0, o.rs, o.tstop, blank_mclk / 32.768e6, afe)
    # same noise realization in both runs; output every 4 ns is enough for period averages
    deck = deck.replace(".control\nset noaskquit\n", f".control\nset noaskquit\nset rndseed={o.seed}\n", 1)
    deck = re.sub(r"wrdata tr\.csv vo va v\(cda\) v\(cdb\)", "wrdata tr.csv vo", deck)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    os.remove(os.path.join(d, "tr.csv"))
    t, vo = x[:, 0], x[:, 1]
    q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
    n = int((t[-1] - T_START) / TCH)
    edges = T_START + TCH * np.arange(n + 1)
    return np.diff(np.interp(edges, t, q)) / TCH  # output averaged over each chopper period


def density(seq, fmax):
    """mean one-sided density (V^2/Hz) of the 128 kHz sequence over (1 bin .. fmax)"""
    w = np.hanning(len(seq))
    s = 2 * np.abs(np.fft.rfft((seq - seq.mean()) * w)) ** 2 / (afe_offset.FCH * np.sum(w ** 2))
    f = np.fft.rfftfreq(len(seq), TCH)
    sel = (f > f[1]) & (f <= fmax)
    return np.mean(s[sel]), int(sel.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=float, default=30e-9, help="input-referred white noise per core input (V/rtHz)")
    ap.add_argument("--nt", type=float, default=3.14159265e-9,
                    help="trnoise sample step (s); off the 1 ns grid of the clock breakpoints, which an "
                         "exact multiple hit at 250 us and stopped the solver")
    ap.add_argument("--tstop", type=float, default=2.1e-3)
    ap.add_argument("--blank", type=int, default=7, help="blanking in MCLK")
    ap.add_argument("--fmax", type=float, default=20e3)
    ap.add_argument("--rs", type=float, default=100.0)
    ap.add_argument("--seed", type=int, default=1)
    o = ap.parse_args()
    with ThreadPoolExecutor(2) as ex:
        seq0, seq1 = list(ex.map(lambda b: run(b, o), (0, o.blank)))
    if len(seq0) != len(seq1):
        print(f"warning: the runs ended at {len(seq0)} and {len(seq1)} chopper periods (see run.log)")
        n = min(len(seq0), len(seq1))
        seq0, seq1 = seq0[:n], seq1[:n]
    s0, nb = density(seq0, o.fmax)
    s1, _ = density(seq1, o.fmax)
    sd, _ = density(seq1 - seq0, o.fmax)
    g = afe_offset.GAIN
    print(f"input-referred core noise {o.en * 1e9:g} nV/rtHz per input, {len(seq0)} chopper periods, "
          f"{nb} bins up to {o.fmax / 1e3:g} kHz")
    print(f"  output density without blanking {np.sqrt(s0) * 1e9:.1f} nV/rtHz "
          f"(electrode-referred {np.sqrt(s0) / g * 1e9:.3f} nV/rtHz)")
    print(f"  with blanking {o.blank} MCLK          {np.sqrt(s1) * 1e9:.1f} nV/rtHz "
          f"(ratio {np.sqrt(s1 / s0):.3f}; difference of the runs {np.sqrt(sd) * 1e9:.1f} nV/rtHz)")


if __name__ == "__main__":
    main()

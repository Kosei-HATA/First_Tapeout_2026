#!/usr/bin/env python3
"""Compare stage-2 rescale variants (orig / s10 / s47) of the ADC loop deck.
Usage: python3 analyze.py <out_dir>   (directory holding orig/s10/s47/out.csv)"""
import os
import sys
import numpy as np

HERE = sys.argv[1]
T = 1 / 1.024e6
T_LOAD0 = 2.0784625e-06
F_SIG = 1e3
COLS = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "idd"]


def load(name):
    d = np.loadtxt(os.path.join(HERE, name, "out.csv"))
    return d[:, 0], {c: d[:, 2 * i + 1] for i, c in enumerate(COLS)}


def per_clock(t, x, t_from=50e-6):
    edges = T_LOAD0 + T * np.arange(int((t[-1] - T_LOAD0) / T))
    edges = edges[edges >= t_from]
    idx = np.searchsorted(t, edges)
    out = [np.trapezoid(x[a:b + 1], t[a:b + 1]) / (t[b] - t[a])
           for a, b in zip(idx[:-1], idx[1:])]
    return np.array(out), edges[:-1] + T / 2


def sine(tc, x, f=F_SIG):
    X = np.column_stack([np.sin(2 * np.pi * f * tc), np.cos(2 * np.pi * f * tc),
                         np.ones_like(tc)])
    c, *_ = np.linalg.lstsq(X, x, rcond=None)
    return np.hypot(c[0], c[1]), np.degrees(np.arctan2(c[1], c[0]))


def main():
    res = {}
    for name in ("orig", "s10", "s47"):
        if not os.path.exists(os.path.join(HERE, name, "out.csv")):
            print(f"{name}: missing")
            continue
        t, v = load(name)
        if t[-1] < 100e-6:
            print(f"| {name} | {t[-1]*1e3:.4f} | aborted during start-up | | | | | | | |")
            continue
        m = t > 50e-6
        o1, o2 = v["o1p"] - v["o1n"], v["o2p"] - v["o2n"]
        vg1, vg2 = v["i1p"] - v["i1n"], v["i2p"] - v["i2n"]
        o1c, tc = per_clock(t, o1)
        vg1c, _ = per_clock(t, vg1)
        dac, _ = per_clock(t, v["norm1"])
        a_o1, _ = sine(tc, o1c)
        a_vg1, _ = sine(tc, vg1c)
        a_dac, ph_dac = sine(tc, dac)
        cm1 = 0.5 * (v["o1p"] + v["o1n"])[m]
        cm2 = 0.5 * (v["o2p"] + v["o2n"])[m]
        res[name] = (tc, dac)
        print(f"| {name} | {t[-1]*1e3:.3f} | {np.abs(o1[m]).max()*1e3:.1f} | "
              f"{np.abs(o2[m]).max()*1e3:.1f} | {np.abs(vg1[m]).max()*1e6:.0f} | "
              f"{np.abs(vg2[m]).max()*1e6:.0f} | {a_o1/a_vg1:.0f} | "
              f"{cm1.mean():.4f} / {cm2.mean():.4f} | {-v['idd'][m].mean()*1e3:.3f} | "
              f"{a_dac:.4f} @ {ph_dac:.2f} deg |")
    if "orig" in res:
        tc0, ref = res["orig"]
        k = np.ones(32) / 32
        for name in ("s10", "s47"):
            if name in res:
                tc1, d = res[name]
                n = min(len(ref), len(d))
                a = np.convolve(ref[:n], k, "valid")
                b = np.convolve(d[:n], k, "valid")
                print(f"{name} vs orig: 32-clock-averaged output difference "
                      f"{20*np.log10(np.std(a - b) / np.std(a)):.1f} dB re signal rms")


if __name__ == "__main__":
    print("| case | t_end ms | O1 pk mV | O2 pk mV | VG1 pk uV | VG2 pk uV | "
          "O1/VG1 @1k | CM1 / CM2 V | IDD mA | DAC level @1 kHz |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    main()

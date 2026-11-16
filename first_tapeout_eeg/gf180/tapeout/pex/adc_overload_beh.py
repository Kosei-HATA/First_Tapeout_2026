#!/usr/bin/env python3
"""The ADC loop after an overload, behavioral (11/16): adc_beh_mc.py's exact per-clock model of the loop (DWA on both
DACs, the excess loop delay, the dies of its block corners and Monte Carlo) started from given states, with the
integrator outputs clipped where the extracted run (adc_overload.py) shows the OTAs' rails (O1 +-2.27 V, O2 +-3.25 V,
differential). The quantizer saturates by itself (31 thresholds, +-46.9 mV). Not modelled: the OTAs' own recovery
(the virtual grounds pulled away while an OTA sits on its rail; about 40 us for OTA2 in the extracted run), noise.

  validate  start at a strobe of the extracted two-sided run (adc_overload.py, typical_ov2.5V_50u_rec60u_f20k_a0.28)
            once OTA2 has its virtual ground back, with the extracted O1 / O2 there and the same input, and compare
            the codes and O2 clock by clock until the next overload
  long      from the same state for 2 ms: the 20 kHz sine of that run continued, and DC inputs instead
  sweep     random states at the end of an overload (x1 uniform in +-2.27 V, x2 in +-3.25 V, 300 of them, random
            input phase) for the typical die, the block corners and the Monte Carlo dies, inputs DC / 32 Hz / 2 kHz
            (0.1 .. 0.42 V) and 10 / 20 kHz: back = from when on |x2| and |x1| stay inside 1.5 x the normal swings
            of the same die and input started from zero (at least 46.9 mV / 0.2 V); the 1-bit mode = |x1| > 0.5 V
            in the last 100 clocks of 2 ms

Model sign: code c = the thresholds below x2 (31 when x2 is high); the extracted bench's code is 31 - c.
Output: runs/adc_overload_<rev>/beh_<what>.json (ELD 0.22 of a clock, which reproduces the transistor-level loop
(figs_perf.BEH_ELD); --eld 0.09375 for the RTL's 3/32).

Usage: EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_overload_beh.py validate|long|sweep [--eld 0.22]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import adc_beh_mc as B  # noqa: E402

T = B.m.T
REV = os.environ.get("EEG_PEX_REV", "")
RUNS = os.path.join(HERE, "runs", "adc_overload" + (f"_{REV}" if REV else ""))
TWO = os.path.join(RUNS, "typical_ov2.5V_50u_rec60u_f20k_a0.28")
TS0 = 1.9866597656e-06                     # the first CMP_STROBE edge of adc_deck.py
SINE0 = 60.0337e-6                         # the sine of recovery 1 starts (adc_overload.py: 60 us + 13.7 + 10 + 10 ns)
X1MAX, X2MAX = 2.27, 3.25                  # the extracted run's rails (differential)
NAMES = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]


def run(x1_0, x2_0, u, die=None, eld=0.22, clip=True):
    """S cases at once from states x1_0, x2_0 (S,) with inputs u (n, S): codes c (n, S), x1, x2 after each clock"""
    die = die or B.Die("typ")
    ad, b, ad0, b0 = die.coeffs(eld)
    S, n = len(x1_0), u.shape[0]
    thr = die.thr
    cs1 = B.prefix(die.w1[None, :])[0]
    cs2 = B.prefix(die.w2[None, :])[0]
    x1, x2 = np.array(x1_0, float), np.array(x2_0, float)
    c0 = (x2[:, None] > thr).sum(1)                       # the DAC levels held from before the first clock
    y1p = 1.0 - 2.0 * (31 - c0) / 31.0
    y2p = y1p.copy()
    p = np.zeros(S, np.int64)
    C, X1, X2 = np.empty((n, S), np.int8), np.empty((n, S)), np.empty((n, S))
    for i in range(n):
        ui = u[i]
        mx1 = ad0[0, 0] * x1 + ad0[0, 1] * x2 + b0[0, 0] * ui + b0[0, 1] * y1p + b0[0, 2] * y2p
        mx2 = ad0[1, 0] * x1 + ad0[1, 1] * x2 + b0[1, 0] * ui + b0[1, 1] * y1p + b0[1, 2] * y2p
        c = (x2[:, None] > thr).sum(1)
        C[i] = c
        k = 31 - c
        y1 = 1.0 - 2.0 * cs1[p, k] / 31.0
        y2 = 1.0 - 2.0 * cs2[p, k] / 31.0
        p = (p + k) % 31
        x1 = ad[0, 0] * mx1 + ad[0, 1] * mx2 + b[0, 0] * ui + b[0, 1] * y1 + b[0, 2] * y2
        x2 = ad[1, 0] * mx1 + ad[1, 1] * mx2 + b[1, 0] * ui + b[1, 1] * y1 + b[1, 2] * y2
        if clip:
            np.clip(x1, -X1MAX, X1MAX, out=x1)
            np.clip(x2, -X2MAX, X2MAX, out=x2)
        X1[i], X2[i] = x1, x2
        y1p, y2p = y1, y2
    return C, X1, X2


def extracted(d=TWO):
    import pandas as pd
    x = pd.read_csv(os.path.join(d, "out.csv"), sep=r"\s+", header=None, engine="c").to_numpy()
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    v["t"] = x[:, 0]
    v["o1"], v["o2"] = v["o1p"] - v["o1n"], v["o2p"] - v["o2n"]
    v["code"] = np.round((v["norm1"] + 0.5) * 31)
    return v


def validate(eld):
    v = extracted()
    t = v["t"]
    out = []
    for k0, tend in ((97, 120e-6), (99, 120e-6)):
        ts = TS0 + np.arange(k0, k0 + 60) * T
        n = int((tend - ts[0]) / T)
        tm = ts + T / 2
        u = np.where(tm >= SINE0, 0.28 * np.sin(2 * np.pi * 20e3 * (tm - SINE0)), 0.0)
        x1_0, x2_0 = np.interp(ts[0], t, v["o1"]), np.interp(ts[0], t, v["o2"])
        C, X1, X2 = run(np.array([x1_0]), np.array([x2_0]), u[:, None], eld=eld)
        ce = [int(v["code"][np.searchsorted(t, s + 0.5 * T)]) for s in ts[:n]]
        cm = [int(31 - c) for c in C[:n, 0]]
        o2e = np.interp(ts[1:n + 1], t, v["o2"])
        vg2 = float(np.interp(ts[0], t, v["i2p"] - v["i2n"]))
        out.append(dict(k0=k0, t0_us=ts[0] * 1e6, x1_0=x1_0, x2_0=x2_0, vg2_0_mv=vg2 * 1e3, clocks=n,
                        codes_ext=ce, codes_beh=cm, same=int(sum(a == b for a, b in zip(ce, cm))),
                        t_us=[float(q * 1e6) for q in ts[1:n + 1]], o2_ext=o2e.tolist(), o2_beh=X2[:n, 0].tolist(),
                        o1_ext=np.interp(ts[1:n + 1], t, v["o1"]).tolist(), o1_beh=X1[:n, 0].tolist()))
        print(f"start {ts[0] * 1e6:.3f} us (vg2 {vg2 * 1e3:+.1f} mV), x1 {x1_0 * 1e3:+.1f} x2 {x2_0 * 1e3:+.1f} mV: "
              f"{out[-1]['same']} of {n} codes the same; O2 at the end {o2e[-1] * 1e3:+.0f} (extracted) / "
              f"{X2[n - 1, 0] * 1e3:+.0f} mV (model)", flush=True)
    return out


def long(eld):
    v = extracted()
    k0 = 97
    ts = TS0 + np.arange(k0, k0 + 2048) * T
    tm = ts + T / 2
    x1_0, x2_0 = np.interp(ts[0], v["t"], v["o1"]), np.interp(ts[0], v["t"], v["o2"])
    cases = [("sine 0.28 V 20 kHz (continued)", 0.28 * np.sin(2 * np.pi * 20e3 * (tm - SINE0)))]
    cases += [(f"DC {u * 1e3:+g} mV", np.full(tm.size, u)) for u in (-0.3, -0.039, 0.0, 0.3)]
    cases += [("sine 0.28 V 2 kHz", 0.28 * np.sin(2 * np.pi * 2e3 * (tm - SINE0)))]
    out = []
    for lab, u in cases:
        C, X1, X2 = run(np.array([x1_0]), np.array([x2_0]), u[:, None], eld=eld)
        bad = (np.abs(X2[:, 0]) >= 46.9e-3) | (np.abs(X1[:, 0]) >= 0.2)
        last = int(np.nonzero(bad)[0][-1]) + 1 if bad.any() else 0
        sw = int((np.diff(C[:, 0].astype(int)) != 0).sum())
        env = [float(np.abs(X2[i:i + 32, 0]).max()) for i in range(0, X2.shape[0], 32)]
        out.append(dict(case=lab, back_clock=last, back_us=last * T * 1e6, switches=sw, x2_env=env,
                        t_env_us=[float((ts[i] - ts[0]) * 1e6) for i in range(0, X2.shape[0], 32)],
                        x2=X2[:256, 0].tolist(), x1=X1[:256, 0].tolist(), codes=[int(31 - c) for c in C[:256, 0]]))
        print(f"{lab}: {'back after ' + format(last * T * 1e6, '.0f') + ' us' if last < 2048 - 100 else 'not back in 2 ms'}, "
              f"{sw} code changes in 2 ms", flush=True)
    return dict(t0_us=ts[0] * 1e6, x1_0=x1_0, x2_0=x2_0, cases=out)


def sweep(eld):
    N, S = 2048, 300
    rng = np.random.RandomState(11)
    x1_0 = rng.uniform(-X1MAX, X1MAX, S)
    x2_0 = rng.uniform(-X2MAX, X2MAX, S)
    ph = rng.uniform(0, 2 * np.pi, S)
    tm = (np.arange(N) + 0.5) * T
    j = B.load_block()
    dies = [B.Die("typ")] + B.corner_dies(j) + B.mc_dies(j)[0]
    cases = [(0.0, 0.1), (0.0, 0.28), (0.0, 0.42), (32.0, 0.28), (32.0, 0.42), (2e3, 0.28), (2e3, 0.42), (10e3, 0.28),
             (20e3, 0.1), (20e3, 0.28)]
    rows = []
    for d in dies:
        for f, a in cases:
            u = (np.broadcast_to(a * np.cos(ph)[None, :], (N, S)) if f == 0.0       # DC: uniform-ish in [-a, a]
                 else a * np.sin(2 * np.pi * f * tm[:, None] + ph[None, :]))
            u = np.ascontiguousarray(u)
            _, Z1, Z2 = run(np.zeros(S), np.zeros(S), u, die=d, eld=eld)
            n1, n2 = np.abs(Z1[100:]).max(0), np.abs(Z2[100:]).max(0)
            C, X1, X2 = run(x1_0, x2_0, u, die=d, eld=eld)
            bad = (np.abs(X2) >= np.maximum(46.9e-3, 1.5 * n2)) | (np.abs(X1) >= np.maximum(0.2, 1.5 * n1))
            last = np.where(bad.any(0), N - 1 - np.argmax(bad[::-1], axis=0), -1) + 1
            onebit = (np.abs(X1[-100:]) > 0.5).any(0)
            out = last >= N - 100
            rec = last[~out] * T * 1e6
            rows.append(dict(die=d.label, f=f, a=a, onebit_share=float(onebit.mean()), out_share=float(out.mean()),
                             t_med_us=float(np.median(rec)) if len(rec) else None,
                             t_p99_us=float(np.percentile(rec, 99)) if len(rec) else None,
                             t_max_us=float(rec.max()) if len(rec) else None,
                             normal_x1_max=float(n1.max()), normal_x2_max=float(n2.max()),
                             normal_onebit_share=float((np.abs(Z1[-100:]) > 0.5).any(0).mean())))
        r = [x for x in rows if x["die"] == d.label]
        print(d.label[:30].ljust(30), " ".join(f"{x['f'] / 1e3:g}k/{x['a']:g}:{100 * x['onebit_share']:.0f}%,"
                                                f"{x['t_max_us'] or 0:.0f}" for x in r), flush=True)
    return dict(states=S, clocks=N, rows=rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["validate", "long", "sweep"])
    ap.add_argument("--eld", type=float, default=0.22)
    s = ap.parse_args()
    res = {"validate": validate, "long": long, "sweep": sweep}[s.what](s.eld)
    os.makedirs(RUNS, exist_ok=True)
    tag = "" if abs(s.eld - 0.22) < 1e-9 else f"_eld{s.eld:g}"
    path = os.path.join(RUNS, f"beh_{s.what}{tag}.json")
    json.dump(dict(eld=s.eld, result=res), open(path, "w"), indent=1, default=float)
    print("wrote", path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 4 (behavioral): the ADC loop through the start deck's whole sequence, and from
figure 40's overloaded states with the spike waveform.

seq    beh_spike.py's per-clock-exact loop (adc_beh_mc.py's model, clipped at adc_overload_beh.py's rails) fed with
       the start deck's ADC input from t_reset (4.8 ms, the loop from rest) to the end of the run: the saturated AFE
       (+1.3..+2.3 V at the ADC input for ~1 ms), the DAC write, the AFE_RST pulse, the release (6.122 ms) and the
       spike pattern. Input: qo's exact charge per 100 ns, piecewise constant, with qo repaired within +-200 ns of
       each CHOP_OUT edge (its grid point next to the edge is off by up to +-24 mV us, an interpolation artifact):
       there the samples' trapezoid integral is used and the difference to qo's exact charge over the 400 ns is spread
       evenly in time (the charge over the 400 ns stays exact). Reported per run and die (ss and typical): the
       saturated phase, the time after the release until the loop is back for good (O1 inside 0.2 V and O2 inside the
       outermost thresholds, figure 40's criterion), the peaks and codes afterwards, the 1-bit mode at the end, and the
       last 1024 clocks' code mean against the input mean.
sweep  figure 40's random states (adc_overload_beh.sweep: O1 uniform in +-2.27 V, O2 in +-3.25 V, 300 per die, seed
       11, here also a random start clock in the 1 ms window) with the steady-state inputs of beh_spike.py (A actual,
       A dc, B actual), 2 ms, all 41 dies: the share still in the 1-bit mode (|O1| > 0.5 V in the last 100 clocks),
       the share not back, and the slowest recovery (back: inside 1.5 x the same die's swings from rest, at least
       0.2 V and 46.9 mV).

Inputs: runs/ver07_r14/adc_spike/data/ (extract.py), runs/adc_mc_r11/adc_block_mc.json.
Outputs: runs/ver07_r14/adc_spike/beh_seq.json, beh_sweep.json.
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/beh_seq.py seq|sweep
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beh_spike as BS  # noqa: E402  (the loop, the kernels, the repository's adc_beh_mc / adc_overload_beh)
import wave as W  # noqa: E402  (this folder's wave.py)

B = BS.B
T = BS.T
OUT = BS.OUT
NF = 1000
J0 = 220
X1B, X2B = 0.2, 46.9e-3                       # figure 40's "back" limits (at least)


def qo_fixed(tag):
    """grid t, qo repaired around the CHOP_OUT edges, the run's meta, the number of edges repaired"""
    d = np.load(os.path.join(OUT, "data", f"{tag}.npz"))
    meta = json.load(open(os.path.join(OUT, "data", f"{tag}_meta.json")))
    t, qo = d["t"].copy(), d["qo"].copy()
    u = d["outp_adc"] - d["outn_adc"]
    tr = meta["t_reset"]
    fixed = 0
    for k in np.arange(1, int((t[-1] - tr) / W.TE)):
        e = tr + k * W.TE
        ia = np.searchsorted(t, e - 200e-9) - 1          # clean grid points outside +-200 ns
        ib = np.searchsorted(t, e + 200e-9)
        if ia < 0 or ib >= len(t):
            continue
        seg = np.arange(ia, ib + 1)
        cum = np.concatenate(([0.0], np.cumsum(0.5 * (u[seg][1:] + u[seg][:-1]) * np.diff(t[seg]))))
        total = qo[ib] - qo[ia]
        qo[seg] = qo[ia] + cum + (total - cum[-1]) * (t[seg] - t[ia]) / (t[ib] - t[ia])
        fixed += 1
    return t, qo, meta, fixed


def seq():
    j = B.load_block()
    corners = B.corner_dies(j)
    out = {}
    for tag, die in (("A", corners[1]), ("A", corners[0]), ("B", corners[0]), ("B", corners[1])):
        t, qo, meta, fixed = qo_fixed(tag)
        tr, trel, tstop = meta["t_reset"], meta["afe_rst_again"][1], meta["tstop"]
        n = int((tstop - tr) / T) - 1
        s = tr + np.arange(n) * T
        Qf = np.interp(s[:, None] + np.arange(NF + 1)[None, :] * (T / NF), t, qo)
        U = np.diff(Qf, axis=1) / (T / NF)                  # (n, NF): exact sub-step means
        _, _, K0, K1 = BS.kernels(die, NF, J0)
        C, X, Y, nclip = BS.loop([die], (U[:, :J0] @ K0)[:, None, :], (U[:, J0:] @ K1)[:, None, :])
        x1, x2, c = X[1:, 0, 0], X[1:, 0, 1], C[:, 0].astype(int)
        tt = s + T                                           # time of X[1:]
        rel = tt > trel
        bad = rel & ((np.abs(x1) > X1B) | (np.abs(x2) > X2B))
        last_bad = tt[np.nonzero(bad)[0][-1]] if bad.any() else trel
        dw = (s >= meta["t_dac"]) & (s < trel)
        pre = (s >= meta["t_afe"]) & (s < meta["t_dac"])
        a1 = len(s) - 1024                                   # the last 1024 clocks
        um = float((np.interp(s[-1] + T, t, qo) - np.interp(s[a1], t, qo)) / (1024 * T))
        box = float(((2 * c[a1:] - 31) / 31).mean() * die.vfs)
        late = rel & (tt > tstop - 0.1e-3)
        aft = tt > last_bad + T
        r = dict(tag=tag, die=die.label, edges_repaired=fixed, clocks=n,
                 saturated=dict(o1_range_v=(float(x1[pre].min()), float(x1[pre].max())),
                                o2_range_v=(float(x2[pre].min()), float(x2[pre].max())),
                                rail_code_share=float(((c[pre] == 0) | (c[pre] == 31)).mean()),
                                clip_clocks=int(((np.abs(x1[pre]) >= BS.X1MAX - 1e-9)
                                                 | (np.abs(x2[pre]) >= BS.X2MAX - 1e-9)).sum())),
                 write_to_release=dict(o1_range_v=(float(x1[dw].min()), float(x1[dw].max())),
                                       o2_range_v=(float(x2[dw].min()), float(x2[dw].max())),
                                       rail_code_share=float(((c[dw] == 0) | (c[dw] == 31)).mean())),
                 back_after_release_us=float((last_bad - trel) * 1e6),
                 after_back=dict(o1_peak_mv=float(np.abs(x1[aft]).max() * 1e3), o2_peak_mv=float(np.abs(x2[aft]).max() * 1e3),
                                 codes=(int(c[aft].min()), int(c[aft].max())),
                                 rail_codes=int(((c[aft] == 0) | (c[aft] == 31)).sum())),
                 onebit_end=bool((np.abs(x1[late]) > 0.5).any()),
                 last_ms=dict(input_mean_mv=um * 1e3, code_mean_mv=box * 1e3, diff_uv=(box - um) * 1e6))
        out[f"{tag} / {die.label}"] = r
        print(f"{tag} / {die.label}: saturated O1 {r['saturated']['o1_range_v'][1]:.2f} V, O2 {r['saturated']['o2_range_v'][1]:.2f} V, "
              f"rail codes {r['saturated']['rail_code_share'] * 100:.0f} %; back {r['back_after_release_us']:.1f} us after the "
              f"release; then O1 <= {r['after_back']['o1_peak_mv']:.1f} mV, O2 <= {r['after_back']['o2_peak_mv']:.1f} mV, codes "
              f"{r['after_back']['codes'][0]}..{r['after_back']['codes'][1]}, rail codes {r['after_back']['rail_codes']}, 1-bit at "
              f"the end {r['onebit_end']}; last 1024 clocks: codes {r['last_ms']['code_mean_mv']:.3f} mV against the input "
              f"{r['last_ms']['input_mean_mv']:.3f} mV", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "beh_seq.json"), "w"), indent=1)


def sweep(S=300, N=2048):
    j = B.load_block()
    dies = B.corner_dies(j) + B.mc_dies(j)[0]
    waves = {tag: W.Wave(tag) for tag in "AB"}
    rng = np.random.RandomState(11)
    x1_0 = rng.uniform(-BS.X1MAX, BS.X1MAX, S)
    x2_0 = rng.uniform(-BS.X2MAX, BS.X2MAX, S)
    off = rng.randint(0, W.N_CLK, S)
    rows = []
    h = T / NF
    U = {}
    for tag, var in (("A", "actual"), ("A", "dc"), ("B", "actual")):
        w = waves[tag]
        s = w.t0 + np.arange(W.N_CLK) * T
        U[(tag, var)] = w.u(s[:, None] + (np.arange(NF)[None, :] + 0.5) * h, var)
    t0 = time.time()
    for d in dies:
        _, _, K0, K1 = BS.kernels(d, NF, J0)
        for (tag, var), Uw in U.items():
            v0w, v1w = Uw[:, :J0] @ K0, Uw[:, J0:] @ K1          # (1024, 2), periodic
            idx = (off[None, :] + np.arange(N)[:, None]) % W.N_CLK  # (N, S)
            idz = (np.arange(N)[:, None]) % W.N_CLK
            _, Z, _, _ = BS.loop([d], v0w[idz], v1w[idz])       # the same die and input from rest
            n1 = max(X1B, 1.5 * float(np.abs(Z[101:, 0, 0]).max()))
            n2 = max(X2B, 1.5 * float(np.abs(Z[101:, 0, 1]).max()))
            C, X, _, nclip = BS.loop([d] * S, v0w[idx], v1w[idx], x_init=(x1_0, x2_0), y_init=0.0)
            x1, x2 = X[1:, :, 0], X[1:, :, 1]
            bad = (np.abs(x2) >= n2) | (np.abs(x1) >= n1)
            last = np.where(bad.any(0), N - 1 - np.argmax(bad[::-1], axis=0), -1) + 1
            onebit = (np.abs(x1[-100:]) > 0.5).any(0)
            notback = last >= N - 100
            rec = last[~notback] * T * 1e6
            rows.append(dict(die=d.label, tag=tag, variant=var, onebit_share=float(onebit.mean()),
                             not_back_share=float(notback.mean()),
                             t_med_us=float(np.median(rec)) if len(rec) else None,
                             t_max_us=float(rec.max()) if len(rec) else None, normal_x1=n1 / 1.5, normal_x2=n2 / 1.5))
        r = [x for x in rows if x["die"] == d.label]
        print(d.label[:30].ljust(30), " ".join(f"{x['tag']}-{x['variant']}: 1-bit {100 * x['onebit_share']:.0f}%, "
                                                f"not back {100 * x['not_back_share']:.0f}%, max {x['t_max_us'] or 0:.0f} us"
                                                for x in r), f"({time.time() - t0:.0f} s)", flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(states=S, clocks=N, rows=rows), open(os.path.join(OUT, "beh_sweep.json"), "w"), indent=1)
    for key in (("A", "actual"), ("A", "dc"), ("B", "actual")):
        r = [x for x in rows if (x["tag"], x["variant"]) == key]
        print(key, f"all dies: 1-bit share max {max(x['onebit_share'] for x in r) * 100:.1f} %, not back max "
                   f"{max(x['not_back_share'] for x in r) * 100:.1f} %, slowest {max(x['t_max_us'] or 0 for x in r):.0f} us, "
                   f"median of the medians {np.median([x['t_med_us'] for x in r if x['t_med_us'] is not None]):.0f} us")


if __name__ == "__main__":
    {"seq": seq, "sweep": sweep}[sys.argv[1]]()

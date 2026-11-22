#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 6: analysis of deck_spike.py's extracted run (figure 40's ADC loop with ss models,
run A's ADC input). After the deck's own reset transient (--settle, the first 4 frames): the integrator outputs and
virtual grounds at the raw time points (differential and common mode), O1 / O2 at the strobes, the codes, and per
spike the O1 step and OTA1's virtual-ground excursion (against its excursions at ordinary DAC updates). Then
beh_spike.py's loop (the repository's adc_beh_mc model, the block ss die) restarted from the extracted O1 / O2 and DAC
level at strobes on CHOP_OUT edges (the spike in the first clock), with the deck's own PWL input, compared strobe by
strobe until the codes part, and inside the spike clock.

Inputs: runs/ver07_r14/adc_spike/<run>/ (raw.csv, out.csv, circuit.spice, meta.json), runs/adc_mc_r11/adc_block_mc.json.
Output: runs/ver07_r14/adc_spike/<run>/xan.json.
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/xan.py [xrun_A_actual_ss_30u] [--die ss]
           [--k0 8 12 16 20 24] [--settle 6e-6]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beh_spike as BS  # noqa: E402  (loop, kernels, the repository's adc_beh_mc)

B = BS.B
T = BS.T
OUT = BS.OUT
NAMES = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]


def load(path):
    x = pd.read_csv(path, sep=r"\s+", header=None, engine="c").to_numpy()
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    v["t"] = x[:, 0]
    v["o1"], v["o2"] = v["o1p"] - v["o1n"], v["o2p"] - v["o2n"]
    v["vg1"], v["vg2"] = v["i1p"] - v["i1n"], v["i2p"] - v["i2n"]
    v["o1cm"], v["vg1cm"] = 0.5 * (v["o1p"] + v["o1n"]), 0.5 * (v["i1p"] + v["i1n"])
    v["o2cm"], v["vg2cm"] = 0.5 * (v["o2p"] + v["o2n"]), 0.5 * (v["i2p"] + v["i2n"])
    v["code"] = np.round((v["norm1"] + 0.5) * 31)          # DAC elements on (the model's code is 31 - this)
    return v


def pwl_input(path):
    txt = open(path).read()
    i = txt.index("VSIG SIG 0 PWL(")
    j = txt.index("+ )", i)
    body = " ".join(ln[2:] for ln in txt[i:j].splitlines()[1:])
    p = np.array(body.split(), float).reshape(-1, 2)
    return p[:, 0], p[:, 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", default="xrun_A_actual_ss_30u")
    ap.add_argument("--die", default="ss", choices=["ss", "typical"])
    ap.add_argument("--k0", type=int, nargs="+", default=[8, 12, 16, 20, 24],
                    help="strobes on CHOP_OUT edges to restart the behavioral loop from (deck frame index)")
    ap.add_argument("--settle", type=float, default=6e-6, help="the deck's own reset transient ends (s)")
    a = ap.parse_args()
    d = a.run if os.path.isabs(a.run) else os.path.join(OUT, a.run)
    meta = json.load(open(os.path.join(d, "meta.json")))
    E0, tstop = meta["e0"], meta["tstop"]
    raw = load(os.path.join(d, "raw.csv"))
    grid = load(os.path.join(d, "out.csv"))
    t = raw["t"]
    s = t >= a.settle
    res = dict(run=os.path.basename(d), raw_points=int(len(t)), settle_us=a.settle * 1e6)
    for k in ("o1", "o2", "vg1", "vg2"):
        res[f"{k}_peak_mv"] = float(np.abs(raw[k][s]).max() * 1e3)
    for k in ("o1cm", "o2cm", "vg1cm", "vg2cm"):
        res[f"{k}_range_v"] = (float(raw[k][s].min()), float(raw[k][s].max()))
    ks = np.arange(int(np.ceil((a.settle - E0) / T)), int((tstop - E0) / T))
    te = E0 + ks * T
    res["o2_at_strobes_peak_mv"] = float(np.abs(np.interp(te - 1e-9, t, raw["o2"])).max() * 1e3)
    res["o1_at_strobes_peak_mv"] = float(np.abs(np.interp(te - 1e-9, t, raw["o1"])).max() * 1e3)
    codes = np.array([grid["code"][np.searchsorted(grid["t"], x + 0.5 * T)] for x in te])
    res["codes_dac_elements"] = (int(codes.min()), int(codes.max()))
    res["rail_codes"] = int(((codes == 0) | (codes == 31)).sum())
    # the first frames: the deck's reset release (RST until 1 us) with the first spike in them
    k1 = np.arange(0, int(np.ceil((a.settle - E0) / T)))
    res["reset_transient"] = dict(o2_at_strobes_mv=[float(v * 1e3) for v in np.interp(E0 + k1 * T - 1e-9, t, raw["o2"])],
                                  codes_dac_elements=[int(grid["code"][np.searchsorted(grid["t"], E0 + k * T + 0.5 * T)])
                                                      for k in k1])
    # per spike: the edges are at E0 + 4 j T, the spike starts 458 ns after them
    spikes = []
    quiet = np.ones(len(t), bool)
    for j in range(0, int((tstop - E0) / (4 * T)) + 2):
        e = E0 + 4 * j * T
        win = (t >= e + 0.40e-6) & (t <= e + 0.95e-6)
        quiet &= ~win
        if e + 1.2e-6 > tstop or e < a.settle - 1e-6:
            continue
        b0 = np.interp(e + 0.455e-6, t, raw["o1"])
        spikes.append(dict(edge_us=e * 1e6, o1_before_mv=b0 * 1e3, o1_max_mv=float(raw["o1"][win].max() * 1e3),
                           o1_step_mv=float((raw["o1"][win].max() - b0) * 1e3),
                           vg1_max_mv=float(raw["vg1"][win].max() * 1e3), vg1_min_mv=float(raw["vg1"][win].min() * 1e3),
                           vg1cm_range=(float(raw["vg1cm"][win].min()), float(raw["vg1cm"][win].max())),
                           o2_range_mv=(float(raw["o2"][win].min() * 1e3), float(raw["o2"][win].max() * 1e3))))
    res["spikes"] = spikes
    res["vg1_peak_outside_spikes_mv"] = float(np.abs(raw["vg1"][s & quiet]).max() * 1e3)
    res["vg2_peak_outside_spikes_mv"] = float(np.abs(raw["vg2"][s & quiet]).max() * 1e3)
    # the behavioral loop from the extracted state at strobe k0 with the deck's PWL input, clock by clock
    j = B.load_block()
    corners = B.corner_dies(j)
    die = {"ss": corners[1], "typical": corners[0]}[a.die]
    tp, up = pwl_input(os.path.join(d, "circuit.spice"))
    nf, j0 = 1000, 220
    Ah, Bh, K0, K1 = BS.kernels(die, nf, j0)
    res["beh"] = []
    for k0 in a.k0:
        s0 = E0 + k0 * T
        n = int((tstop - s0) / T) - 1
        if n < 2:
            continue
        U = np.interp(s0 + np.arange(n)[:, None] * T + (np.arange(nf)[None, :] + 0.5) * T / nf, tp, up)
        x0 = np.array([np.interp(s0 - 1e-9, t, raw["o1"]), np.interp(s0 - 1e-9, t, raw["o2"])])
        kprev = grid["code"][np.searchsorted(grid["t"], s0 - 0.5 * T)]
        C, X, Y, _ = BS.loop([die], (U[:, :j0] @ K0)[:, None, :], (U[:, j0:] @ K1)[:, None, :], x_init=x0,
                             y_init=1.0 - 2.0 * kprev / 31.0)
        tk = s0 + np.arange(1, n + 1) * T
        o1e, o2e = np.interp(tk - 1e-9, t, raw["o1"]), np.interp(tk - 1e-9, t, raw["o2"])
        ce = np.array([grid["code"][np.searchsorted(grid["t"], x + 0.5 * T)] for x in s0 + np.arange(n) * T])
        cm = 31 - C[:, 0].astype(int)
        first = int(np.argmax(cm != ce)) if (cm != ce).any() else n
        Z, zt = X[0, 0].copy(), []                            # O1 inside the first clock (the spike's)
        for q in range(nf):
            ya = Y[0, 0, 0:2] if q < j0 else Y[0, 0, 2:4]
            Z = Ah @ Z + U[0, q] * Bh[:, 0] + ya[0] * Bh[:, 1] + ya[1] * Bh[:, 2]
            zt.append(Z.copy())
        zt = np.array(zt)
        we = (t >= s0) & (t <= s0 + T)
        o1m = np.interp(t[we], s0 + (np.arange(nf) + 1) * T / nf, zt[:, 0])
        res["beh"].append(dict(die=die.label, k0=k0, start_us=s0 * 1e6, x0_mv=(x0 * 1e3).tolist(), clocks=n,
                               codes_same_before_first_diff=first,
                               spike_clock_o1_max_ext_mv=float(raw["o1"][we].max() * 1e3),
                               spike_clock_o1_max_beh_mv=float(zt[:, 0].max() * 1e3),
                               spike_clock_o1_maxdiff_mv=float(np.abs(o1m - raw["o1"][we]).max() * 1e3),
                               t_us=(tk * 1e6).round(4).tolist(),
                               o1_ext_mv=(o1e * 1e3).round(3).tolist(), o1_beh_mv=(X[1:, 0, 0] * 1e3).round(3).tolist(),
                               o2_ext_mv=(o2e * 1e3).round(3).tolist(), o2_beh_mv=(X[1:, 0, 1] * 1e3).round(3).tolist(),
                               codes_ext=ce.astype(int).tolist(), codes_beh=cm.tolist()))
    json.dump(res, open(os.path.join(d, "xan.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("spikes", "beh", "reset_transient")}, indent=1))
    print("reset transient (deck frames 0..): O2 at strobes", [round(v, 1) for v in res["reset_transient"]["o2_at_strobes_mv"]],
          "codes", res["reset_transient"]["codes_dac_elements"])
    for q in spikes:
        print(f"  spike at edge {q['edge_us']:.3f} us: O1 {q['o1_before_mv']:+.1f} -> {q['o1_max_mv']:+.1f} mV (step "
              f"{q['o1_step_mv']:+.1f}), VG1 {q['vg1_min_mv']:+.2f}..{q['vg1_max_mv']:+.2f} mV (CM {q['vg1cm_range'][0]:.4f}.."
              f"{q['vg1cm_range'][1]:.4f} V), O2 {q['o2_range_mv'][0]:+.1f}..{q['o2_range_mv'][1]:+.1f} mV")
    for b in res["beh"]:
        print(f"behavioral ({b['die']}) from strobe {b['k0']} ({b['start_us']:.3f} us): codes the same for "
              f"{b['codes_same_before_first_diff']} of {b['clocks']} clocks; spike clock O1 max ext {b['spike_clock_o1_max_ext_mv']:.1f}"
              f" / beh {b['spike_clock_o1_max_beh_mv']:.1f} mV (max difference {b['spike_clock_o1_maxdiff_mv']:.1f} mV)")


if __name__ == "__main__":
    main()

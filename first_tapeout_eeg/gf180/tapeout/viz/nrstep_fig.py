#!/usr/bin/env python3
"""Figure 49 (r13 analog, r14 digital; 11/21): one offset-DAC step without AFE_RST (APPLY_NR) across the binary carry.

afe_nr_step.py's runs (gf180/tapeout/pex/runs/nr_step/run_nr_step.sh, 11/20): afe_startup.py's start deck (power-on; the
extracted afe_top of r13, eeg_bias and eeg_ref on the chip wiring with the pads, bond wires and the board; typical,
27 C, AFE_IBIAS 3, legs of 100 ohm, electrode offset +159.1 mV, range 4), the AFE released at its tick, and at
6.497 ms one step of the offset DAC's magnitude at the sequencer's tick (frame cycle 24, the register outputs at e25)
with no AFE_RST pulse, as APPLY_NR does: 511 -> 512 and 512 -> 511 (the carry: 10 bits, 20 DAC lines) against
510 -> 511 (1 bit, 2 lines). 512 -> 511 and 510 -> 511 end at the same code, so their difference after the step is the
carry's own transient (audit of 11/20, round 10, A1: the requirements made a step that changes M[9:4] an APPLY).
  (a) the AFE's output OUTP - OUTN at the step (raw, 100 ns grid);
  (b) the summing node INN at the step (raw);
  (c) the carry's transient in chopper-period means (from the exact integral qo, on a grid a quarter period after the
      tick): 512 -> 511 minus 510 -> 511, the end difference removed;
  (d) the static output at the codes 510, 511 and 512 (chopper-period means before and 2-3 ms after the step).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/nrstep_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, HAIR, INK, INK2, MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r13", "20261119"
V.CHIP_LABEL = "Chip r13 · r14 control"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RUNS = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL = "#0d9488"
NAME = "start_c1e-08_v3.3_typical_+159.1mV_m{m1}_afe5.00486ms_ib3_nr{m1}to{m2}_chip_r13"
CASES = [((510, 511), INK2, "-", "510 -> 511 (1 bit, 2 lines)"),
         ((511, 512), ACCENT, "-", "511 -> 512 (carry, 20 lines)"),
         ((512, 511), TEAL, (0, (4, 2)), "512 -> 511 (carry, 20 lines)")]
T = 1 / 128e3                                       # the chopper period at 128 kHz
KEEP = ("qo", "outp_adc", "outn_adc", "inp", "inn", "opi", "oni")


def load(m1, m2):
    d = os.path.join(RUNS, NAME.format(m1=m1, m2=m2))
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    idx = [meta["vectors"].index(k) for k in KEEP]
    a = np.loadtxt(os.path.join(d, "tr.csv"), usecols=[0] + [2 * i + 1 for i in idx])
    return meta, a[:, 0], {k: a[:, 1 + j] for j, k in enumerate(KEEP)}


def means(t, qo, t0, n):
    tk = t0 + np.arange(n + 1) * T
    q = np.interp(tk, t, qo)
    return tk[:-1], np.diff(q) / T


def main():
    V.apply()
    data = {c[0]: load(*c[0]) for c in CASES}
    ts = data[(510, 511)][0]["t_step"]
    for k, (m, _t, _v) in data.items():
        assert abs(m["t_step"] - ts) < 1e-12 and m["apply_nr"], k
    t0 = ts - 64 * T + T / 4
    n = int((min(t[-1] for _m, t, _v in data.values()) - t0) / T) - 1
    pm = {k: means(t, v["qo"], t0, n) for k, (_m, t, v) in data.items()}
    tk = pm[(510, 511)][0]
    pre, post = tk < ts - T, tk > ts + 2e-3
    level = {}                                       # code -> output levels (mV) seen before or after a step
    for (m1, m2), (_t, mm) in pm.items():
        level.setdefault(m1, []).append(mm[pre].mean() * 1e3)
        level.setdefault(m2, []).append(mm[post].mean() * 1e3)
    step1 = np.mean(level[510]) - np.mean(level[511])      # one unit at the output, mV
    e = pm[(512, 511)][1] - pm[(510, 511)][1]
    e = (e - e[post].mean()) * 1e3                   # the carry's transient at the output, mV
    after = tk >= ts
    last = {lim: (tk[np.where(after & (np.abs(e) > lim))[0][-1]] - ts) * 1e6 for lim in (1.0, 0.1)}
    area = e[after].sum() * T * 1e6                  # mV us
    print(f"one unit {step1:.2f} mV at the output; the carry's transient: first period {e[np.searchsorted(tk, ts)]:.2f} mV, "
          f"below 1 mV after {last[1.0]:.1f} us, below 0.1 mV after {last[0.1]:.1f} us, area {area:.0f} mV us")
    print("levels (mV):", {k: [round(x, 3) for x in v] for k, v in sorted(level.items())})

    fig = V.figure(7.6, 6.4, "APPLY_NR across the offset DAC's carry 511 <-> 512",
                   "afe_nr_step.py: power-on start deck, extracted afe_top r13 with eeg_bias and eeg_ref on the chip wiring, "
                   "typical, legs 100 Ω, electrode offset +159.1 mV, range 4; at 6.497 ms one step at the sequencer's tick "
                   "with no AFE_RST pulse (APPLY_NR). Operating point beyond the ADC's range (see the note)",
                   note="Runs: gf180/tapeout/pex/runs/startup/start_…_nr<m1>to<m2>_chip_r13 (run_nr_step.sh, 11/20). "
                        "Chopper-period means from the exact integral of OUTP − OUTN, on a grid a quarter period after the "
                        "tick. (c): 512 -> 511 minus 510 -> 511, which end at the same code; its tail near 0.1 mV is the "
                        "two runs' slow settling after the release at 5.0 ms (about 0.4 mV in every run, slightly different "
                        "per code), not the carry. Audit round 16: 159.1 mV against M 511 with the measured step of about "
                        "0.301 mV (not the nominal 0.3113 mV) leaves the ADC input at about +0.94 V, beyond its +-0.484 V range, "
                        "where values are compressed: an in-range rerun (154.0 mV, r14's reset trims) replaces this figure.")
    gs = fig.add_gridspec(2, 2)
    us = lambda t: (t - ts) * 1e6

    ax = fig.add_subplot(gs[0, 0])
    for (mm, col, ls, lab) in CASES:
        _m, t, v = data[mm]
        w = (t > ts - 15e-6) & (t < ts + 45e-6)
        ax.plot(us(t[w]), (v["outp_adc"][w] - v["outn_adc"][w]) * 1e3, color=col, ls=ls, lw=1.1, label=lab)
    ax.axvline(0, color=HAIR, lw=0.8, zorder=0)
    ax.set_xlabel("time from the step's tick (µs)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    ax.set_title("(a) The AFE's output at the step (raw): the carry's spike\nlasts about two chopper periods", loc="left")
    ax.legend(loc="upper right")

    ax = fig.add_subplot(gs[0, 1])
    for (mm, col, ls, lab) in CASES:
        _m, t, v = data[mm]
        w = (t > ts - 5e-6) & (t < ts + 25e-6)
        ax.plot(us(t[w]), v["inn"][w] * 1e3, color=col, ls=ls, lw=1.1, label=lab)
    ax.axvline(0, color=HAIR, lw=0.8, zorder=0)
    ax.set_xlabel("time from the step's tick (µs)")
    ax.set_ylabel("INN (mV)")
    ax.set_title("(b) The summing node INN: the off-going units pull it\ndown for a moment (no AFE stage saturates)", loc="left")

    ax = fig.add_subplot(gs[1, 0])
    w = after & (tk < ts + 300e-6)
    x = (tk[w] - ts) * 1e6 + T * 1e6 / 2
    ax.semilogy(x, np.abs(e[w]), color=ACCENT, lw=1.2, marker="o", ms=2.5)
    for lim in (1.0, 0.1):
        ax.axhline(lim, color=MUTED, lw=0.8, ls=(0, (3, 2)))
        ax.text(298, lim * 1.15, f"{lim:g} mV (after {last[lim]:.0f} µs)", color=MUTED, fontsize=8, ha="right", va="bottom")
    ax.set_xlim(0, 300)
    ax.set_ylim(1e-3, 30)
    ax.set_xlabel("time after the step's tick (µs)")
    ax.set_ylabel("|carry's transient| at the output (mV)")
    ax.set_title(f"(c) The carry's transient, chopper-period means:\n{e[np.searchsorted(tk, ts)]:.1f} mV "
                 f"in the first period, below 1 mV after {last[1.0]:.0f} µs", loc="left")

    ax = fig.add_subplot(gs[1, 1])
    codes = sorted(level)
    for c in codes:
        ax.plot([c] * len(level[c]), level[c], ls="none", marker="o", ms=5, color=ACCENT, mfc="white", mew=1.2)
    ax.plot(codes, [np.mean(level[510]) - step1 * (c - 510) for c in codes], color=MUTED, lw=0.9, ls=(0, (3, 2)),
            label="one unit per code (510 -> 511)")
    ax.set_xticks(codes)
    ax.set_xlabel("offset-DAC code M (range 4)")
    ax.set_ylabel("output, chopper-period mean (mV)")
    d512 = np.mean(level[512]) - np.mean(level[511])
    ax.set_title(f"(d) The static output (compressed): 512 gives the output of 511\n(the carry step {d512:+.2f} mV, "
                 f"{d512 / -step1:+.3f} of a {step1:.1f} mV unit: DNL ≈ −1 LSB?)", loc="left")
    ax.legend(loc="upper right")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_49_nr_carry.png")
    fig.savefig(path)
    print("wrote", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Figure 49 (r13 analog, r14 digital; 11/21): one offset-DAC step without AFE_RST (APPLY_NR) across the binary carry.

afe_nr_step.py's runs (gf180/tapeout/pex/runs/nr_step/run_nr_step_r14.sh, 11/21): afe_startup.py's start deck (power-on;
the extracted afe_top of r13, eeg_bias and eeg_ref on the chip wiring with the pads, bond wires and the board; typical,
27 C, r14's reset trims (AFE_IBIAS 3 from reset, BTRIM_P 1, BTRIM_N 0), legs of 100 ohm, electrode offset +154.0 mV
(511.5 measured steps of about 0.301 mV), range 4), the AFE released at its tick, and at 6.497 ms one step of the
offset DAC's magnitude at the sequencer's tick (frame cycle 24, the register outputs at e25) with no AFE_RST pulse, as
APPLY_NR does: 511 -> 512 and 512 -> 511 (the carry: 10 bits, 20 DAC lines) against 510 -> 511 (1 bit, 2 lines). Every
operating point lies within the ADC's range. 512 -> 511 and 510 -> 511 end at the same code, so their difference after
the step is the carry's own transient (audit of 11/20, round 10, A1: the requirements made a step that changes M[9:4]
an APPLY). The 11/20 runs (run_nr_step.sh: 159.1 mV from the nominal step) sat beyond the ADC's range, where values
are compressed (audit round 16); this figure replaces them.
  (a) the AFE's output OUTP - OUTN at the step (raw, 100 ns grid), the ADC's range marked;
  (b) the summing node INN at the step (raw);
  (c) chopper-period means (from the exact integral qo, on a grid a quarter period after the tick) against each run's
      final level, and the carry's own transient (512 -> 511 minus 510 -> 511, the end difference removed);
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
NAME = "start_c1e-08_v3.3_typical_+154mV_m{m1}_afe5.00486ms_ib3_ibr3_bt10_rng4_nr{m1}to{m2}_chip_r13"
CASES = [((510, 511), INK2, "-", "510 -> 511 (1 bit, 2 lines)"),
         ((511, 512), ACCENT, "-", "511 -> 512 (carry, 20 lines)"),
         ((512, 511), TEAL, (0, (4, 2)), "512 -> 511 (carry, 20 lines)")]
T = 1 / 128e3                                       # the chopper period at 128 kHz
ADC_FS = 0.484                                      # DAC1's full scale at the ADC's input (V, differential)
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
        assert abs(_t[-1] - m["tstop"]) < 1e-6, f"{k}: the run ended at {_t[-1]} s before its tstop"
    t0 = ts - 64 * T + T / 4
    n = int((min(t[-1] for _m, t, _v in data.values()) - t0) / T) - 1
    pm = {k: means(t, v["qo"], t0, n) for k, (_m, t, v) in data.items()}
    tk = pm[(510, 511)][0]
    pre, post = tk < ts - T, tk > ts + 2e-3
    level = {}                                       # code -> output levels (mV) seen before or after a step
    for (m1, m2), (_t, mm) in pm.items():
        level.setdefault(m1, []).append(mm[pre][-16:].mean() * 1e3)
        level.setdefault(m2, []).append(mm[post].mean() * 1e3)
    allv = [x for v in level.values() for x in v]
    assert max(abs(x) for x in allv) < ADC_FS * 1e3, "an operating point beyond the ADC's range"
    step1 = np.mean(level[510]) - np.mean(level[511])      # the bit-0 step at the output, mV
    d512 = np.mean(level[511]) - np.mean(level[512])       # the carry step, mV
    e = pm[(512, 511)][1] - pm[(510, 511)][1]
    e = (e - e[post].mean()) * 1e3                   # the carry's own transient at the output, mV
    after = tk >= ts
    emax = np.abs(e[after]).max()
    over = {}
    for k, (_m, t, v) in data.items():
        vo = v["outp_adc"] - v["outn_adc"]
        a = (t >= ts) & (np.abs(vo) > ADC_FS)
        idx = np.nonzero(a)[0]
        over[k] = (a.sum() * np.median(np.diff(t)) * 1e6, np.abs(vo[t >= ts]).max(),
                   v["opi"][(t > ts - 5e-6) & (t < ts + 40e-6)].min(), v["opi"][(t > ts - 5e-6) & (t < ts + 40e-6)].max(),
                   v["oni"][(t > ts - 5e-6) & (t < ts + 40e-6)].min(), v["oni"][(t > ts - 5e-6) & (t < ts + 40e-6)].max())
    stage = (min(min(o[2], o[4]) for o in over.values()), max(max(o[3], o[5]) for o in over.values()))
    print(f"bit-0 step {step1:.2f} mV, carry step {d512:.2f} mV (ratio {d512 / step1:.3f}); the carry's transient in "
          f"chopper-period means at most {emax * 1e3:.1f} uV; beyond the ADC's range "
          + ", ".join(f"{k[0]}->{k[1]} {o[0]:.2f} us (max {o[1]:.3f} V)" for k, o in over.items())
          + f"; first-stage outputs {stage[0]:.2f}..{stage[1]:.2f} V")
    print("levels (mV):", {k: [round(x, 3) for x in v] for k, v in sorted(level.items())})

    fig = V.figure(7.6, 6.6, "APPLY_NR across the DAC's carry 511 <-> 512 (in range)",
                   "afe_nr_step.py: power-on start deck, extracted afe_top r13 with eeg_bias and eeg_ref on the chip wiring, "
                   "typical, r14's reset trims (AFE_IBIAS 3, BTRIM_P 1, BTRIM_N 0), legs 100 Ω, electrode offset +154.0 mV "
                   "(511.5 measured steps), range 4; at 6.497 ms one step at the sequencer's tick with no AFE_RST pulse "
                   "(APPLY_NR)",
                   note="Runs: gf180/tapeout/pex/runs/startup/start_…_ib3_ibr3_bt10_rng4_nr<m1>to<m2>_chip_r13 "
                        "(run_nr_step_r14.sh, 11/21). Chopper-period means from the exact integral of OUTP − OUTN, on a "
                        "grid a quarter period after the tick. Every level lies within the ADC's range (±0.484 V). The "
                        "11/20 runs (159.1 mV from the nominal step 0.3113 mV) sat at about +0.94 V, beyond the range, where "
                        "values are compressed: their 12.4 mV transient and DNL ≈ −1 LSB were the compression, and this "
                        "figure replaces them. The ADC's modulator is not in this deck: the spike beyond its range is far "
                        "shorter and smaller than the overloads it recovers from (figure 40).")
    gs = fig.add_gridspec(2, 2)
    us = lambda t: (t - ts) * 1e6

    ax = fig.add_subplot(gs[0, 0])
    for lim in (-ADC_FS, ADC_FS):
        ax.axhline(lim * 1e3, color=MUTED, lw=0.8, ls=(0, (3, 2)), zorder=0)
    for (mm, col, ls, lab) in CASES:
        _m, t, v = data[mm]
        w = (t > ts - 5e-6) & (t < ts + 25e-6)
        ax.plot(us(t[w]), (v["outp_adc"][w] - v["outn_adc"][w]) * 1e3, color=col, ls=ls, lw=1.1, label=lab)
    ax.axvline(0, color=HAIR, lw=0.8, zorder=0)
    ax.set_xlabel("time from the step's tick (µs)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    oc = max(o[0] for k, o in over.items() if k != (510, 511))
    ax.set_title(f"(a) The output at the step (raw): the carry\nreaches {over[(511, 512)][1]:.2f} V, beyond the ADC's "
                 f"range\n(dashed) for ≤ {oc:.1f} µs", loc="left")
    ax.legend(loc="upper right")

    ax = fig.add_subplot(gs[0, 1])
    for (mm, col, ls, lab) in CASES:
        _m, t, v = data[mm]
        w = (t > ts - 5e-6) & (t < ts + 25e-6)
        ax.plot(us(t[w]), v["inn"][w] * 1e3, color=col, ls=ls, lw=1.1, label=lab)
    ax.axvline(0, color=HAIR, lw=0.8, zorder=0)
    ax.set_xlabel("time from the step's tick (µs)")
    ax.set_ylabel("INN (mV)")
    ax.set_title(f"(b) INN: the off-going units pull it down\nfor a moment; no stage saturates\n(first stage "
                 f"{stage[0]:.2f}–{stage[1]:.2f} V)", loc="left")

    ax = fig.add_subplot(gs[1, 0])
    w = (tk > ts - 8 * T) & (tk < ts + 40 * T)
    x = (tk[w] - ts) * 1e6 + T * 1e6 / 2
    for (mm, col, ls, lab) in CASES:
        _t, m_ = pm[mm]
        ax.plot(x, (m_[w] - m_[post].mean()) * 1e3, color=col, ls=ls, lw=1.1, marker="o", ms=2.2, label=lab)
    ax.axvline(0, color=HAIR, lw=0.8, zorder=0)
    ax.set_xlabel("time from the step's tick (µs)")
    ax.set_ylabel("period mean − final level (mV)")
    ax.set_title(f"(c) Chopper-period means: at the final level\nfrom the first period (the carry's own\n"
                 f"transient ≤ {emax * 1e3:.0f} µV)", loc="left")
    ax.legend(loc="upper right", fontsize=7.5)

    ax = fig.add_subplot(gs[1, 1])
    codes = sorted(level)
    for c in codes:
        ax.plot([c] * len(level[c]), level[c], ls="none", marker="o", ms=5, color=ACCENT, mfc="white", mew=1.2)
    ax.plot(codes, [np.mean(level[510]) - step1 * (c - 510) for c in codes], color=MUTED, lw=0.9, ls=(0, (3, 2)),
            label="one bit-0 step per code (510 -> 511)")
    ax.set_xticks(codes)
    ax.set_xlabel("offset-DAC code M (range 4)")
    ax.set_ylabel("period mean (mV)")
    mn = lambda x: f"{x:+.2f}".replace("-", "−")
    ax.set_title(f"(d) The static output: the carry step is\n{d512 / step1:.2f} of the bit-0 step ({mn(-d512)[:-1]} against\n"
                 f"{mn(-step1)[:-1]} mV at the output): DNL ≈ {mn(d512 / step1 - 1)} LSB", loc="left")
    ax.legend(loc="upper right")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_49_nr_carry.png")
    fig.savefig(path)
    print("wrote", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()

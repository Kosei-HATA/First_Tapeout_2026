#!/usr/bin/env python3
"""Figure 52 (r13 analog, r14 digital; 11/23): VER-07 diagnostic, CHOP1's edge on the ss post-blanking spike.

Digital-control audit round 34, auditor A: CHOP1 (OTA1's chopper) changes at e16 of the frames at 0 mod 32, the start
of chopper phase A, 1 MCLK after the forced 15-MCLK blanking ends, where the ss start deck's ADC input peaks (+632 mV,
figure 51). Two runs of figure 51's extracted ss loop (deck_spike.py --chop1-td) put CHOP1's edge on that spike and on
e16 of a frame without a CHOP_OUT edge; chop1_spike.py fits the O1 difference to the deck's own run before and after
each edge (gf180/tapeout/pex/runs/ver07_r14/adc_spike/chop1_spike.json).
  (a) the ADC input around the two edges, against the frame's MCLK;
  (b) the spike edge: O1 (run - reference), the two fitted lines and the step (the charge left in C1);
  (c) the control edge: the same;
  (d) the DC error at the input if every CHOP1 edge carried the spike's extra charge, by CHOP1's rate.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/ver07_chop1_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import HAIR, INK2, MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r13", "20261119"
V.CHIP_LABEL = "Chip r13 · r14 control"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RES = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "pex", "adc_spike"))
import chop1_spike as C  # noqa: E402

OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL, PLUM, AMBER = "#0d9488", "#a21caf", "#b45309"
MCLK = 1 / 32.768e6
EDGE_FRAME = 9.7993597656e-6      # the CHOP_OUT edge (e0) whose spike CHOP1 meets in the spike run (frame 8 of the deck)


def mv(x, nd=1):
    return f"{x:.{nd}f}".replace("-", "−")


def main():
    V.apply()
    js = json.load(open(os.path.join(RES, "chop1_spike.json")))
    ref = C.load("xrun_A_actual_ss_30u")
    runs = {t: C.load(f"xrun_A_actual_ss_30u_{t}") for t in ("c1spike", "c1ctrl")}
    sp, ct = js["runs"]["c1spike"], js["runs"]["c1ctrl"]
    fig = V.figure(10.6, 8.2, "VER-07 diagnostic: CHOP1's edge on the ss post-blanking spike",
                   "CHOP1 changes at e16, 1 MCLK after the forced 15-MCLK blanking ends, where the ss start deck's ADC "
                   "input peaks. Figure 51's extracted ss loop with CHOP1's edge moved onto the spike and onto a frame "
                   "without a CHOP_OUT edge: the charge each commutation leaves in C1.",
                   note="O1: the first integrator's differential output, the run minus the deck's own run (CHOP1's only "
                        "edge at 2.475 µs); lines fitted 300–5 ns before and 30–500 ns after the edge (the first 20 ns "
                        "are the commutation's own transient, which returns). q per side = step × C1 / 2 (C1 "
                        f"{mv(js['c1_pf_per_side'])} pF per side, typical MIM). DC bound: 2 RIN × Δq × 2 f_ch (RIN 18.75 kΩ "
                        f"per side), input-referred at the AFE gain {js['afe_gain']:.0f} (offset DAC on); one commutation "
                        "direction measured, the same sign assumed for both (the bound).")
    gs = fig.add_gridspec(2, 2)

    ax = fig.add_subplot(gs[0, 0])                       # (a) the ADC input around the edges
    for tag, col, lab, t0 in (("c1spike", TEAL, "spike run: CHOP_OUT edge at frame 8", EDGE_FRAME),
                              ("c1ctrl", PLUM, "control run: frame 10 (no CHOP_OUT edge)", EDGE_FRAME + 2 * 32 * MCLK)):
        v = runs[tag]
        t = t0 + np.arange(-4, 32, 0.05) * MCLK
        ax.plot((t - t0) / MCLK, C.at(v, "sig", t) * 1e3, color=col, lw=1.3, label=lab)
    ax.axvspan(0, 15, color=HAIR, alpha=0.6, lw=0, label="blanking (15 MCLK)")
    ax.axvline(16, color=AMBER, lw=1.2, ls="--", label="CHOP1's edge (e16)")
    ax.axhline(484, color=MUTED, lw=0.8, ls=":")
    ax.text(31, 484, "DAC1 full scale", color=MUTED, fontsize=7.5, ha="right", va="bottom")
    ax.set_xlabel("MCLK after the frame's e0")
    ax.set_ylabel("ADC input (mV, differential)")
    ax.set_title(f"(a) The ADC input at CHOP1's edge: {mv(sp['sig_mv'], 0)} mV on the spike,\n"
                 f"{mv(ct['sig_mv'], 0)} mV in the control frame", loc="left")
    ax.legend(loc="upper left", fontsize=7.5)

    for k, (tag, col, d) in enumerate((("c1spike", TEAL, sp), ("c1ctrl", PLUM, ct))):
        ax = fig.add_subplot(gs[(0, 1) if k == 0 else (1, 0)])
        v = runs[tag]
        te = d["edge_us"] * 1e-6
        t = te + np.arange(-320, 560, 1.0) * 1e-9
        diff = (C.at(v, "o1", t) - C.at(ref, "o1", t)) * 1e3
        ax.plot((t - te) * 1e9, diff, color=col, lw=1.2, label="O1, run − reference")
        tb = np.array([-300, -5]) * 1e-9
        ta = np.array([30, 500]) * 1e-9
        db = C.at(v, "o1", te + np.linspace(-300e-9, -5e-9, 60)) - C.at(ref, "o1", te + np.linspace(-300e-9, -5e-9, 60))
        da = C.at(v, "o1", te + np.linspace(30e-9, 500e-9, 95)) - C.at(ref, "o1", te + np.linspace(30e-9, 500e-9, 95))
        pb = np.polyfit(np.linspace(-300e-9, -5e-9, 60), db, 1)
        pa = np.polyfit(np.linspace(30e-9, 500e-9, 95), da, 1)
        for p, rng in ((pb, (-300e-9, 0.0)), (pa, (0.0, 500e-9))):
            xx = np.array(rng)
            ax.plot(xx * 1e9, np.polyval(p, xx) * 1e3, color=INK2, lw=0.9, ls="--")
        ax.axvline(0, color=AMBER, lw=1.0, ls="--")
        lo, hi = np.percentile(diff[(t - te) > 20e-9], [1, 99])
        lo2, hi2 = np.percentile(diff[(t - te) < -5e-9], [1, 99])
        span = max(hi, hi2) - min(lo, lo2)
        ax.set_ylim(min(lo, lo2) - 0.6 * span - 0.05, max(hi, hi2) + 0.6 * span + 0.05)
        ax.set_xlabel("ns after CHOP1's edge")
        ax.set_ylabel("O1 difference (mV)")
        name = "(b) On the spike" if k == 0 else "(c) Control frame"
        ax.set_title(f"{name}: step {mv(d['o1_step_mv'], 3)} mV, q {mv(d['q_fc_per_side'], 1)} fC per side\n"
                     f"(C1 current {mv(d['i_c1_ua_per_side'], 2)} µA per side, β {d['beta_eff_ns']:.2f} ns; "
                     f"10 ns transient {mv(d['transient_10ns_mv'], 2)} mV, off scale)", loc="left")
        ax.legend(loc="lower left", fontsize=7.5)

    ax = fig.add_subplot(gs[1, 1])                       # (d) the DC bound by CHOP1's rate
    rates = [1, 2, 4, 8, 16]
    nv = [abs(js[f"dc_if_same_sign_{r}k"]["input_referred_nv"]) for r in rates]
    uv = [abs(js[f"dc_if_same_sign_{r}k"]["adc_input_uv"]) for r in rates]
    ax.bar([str(r) for r in rates], nv, color=TEAL, width=0.6)
    for i, (a, b) in enumerate(zip(nv, uv)):
        ax.text(i, a, f"{a:.0f} nV\n({b:.1f} µV at the ADC)", ha="center", va="bottom", fontsize=7.5, color=INK2)
    ax.set_xlabel("CHOP1's rate (kHz)")
    ax.set_ylabel("input-referred DC, |bound| (nV)")
    ax.set_ylim(0, max(nv) * 1.35)
    ax.set_title(f"(d) DC bound if every edge carried the spike's extra\n{mv(js['extra_q_fc_per_side'], 1)} fC per side "
                 "(all CHOP1 edges sit on a spike of one sign)", loc="left")
    ax.grid(axis="x", visible=False)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_52_ver07_chop1.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

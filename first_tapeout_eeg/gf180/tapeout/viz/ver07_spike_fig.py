#!/usr/bin/env python3
"""Figure 51 (r13 analog, r14 digital; 11/22): VER-07 diagnostic, the ADC with the ss start deck's post-blanking spike.

Figure 50's ss run with its own code (300 mV, M 991; afe_saturation.py --seq, ver07_r14/run_ver07_r14_c.sh) has an ADC
input whose chopper-period mean is in range (-34 mV) but which steps to +0.64 V for ~90 ns at the end of every output
blanking window (15 MCLK after each CHOP_OUT edge), beyond DAC1's full scale (+-0.484 V at the ADC input). The start
deck models the ADC only as its input resistors, so the ADC input of the last millisecond was run through the ADC loop
(gf180/tapeout/pex/adc_spike/, results in gf180/tapeout/pex/runs/ver07_r14/adc_spike/; 11/22):
  - wave.py: the deck's 100 ns samples of all 256 CHOP_OUT edges of the millisecond overlaid (16 phases, 6.25 ns
    apart), each segment's charge from the exact integral qo; run B (typical, M 997) as the control;
  - beh_spike.py: adc_beh_mc.py's per-clock loop (the extracted ADC's block dies, ELD 0.22 of a clock, clipped at
    figure 40's rails) with the input integrated exactly inside each clock, the strobes on the CHOP_OUT edges as
    eeg_clkgen, the millisecond repeated x10 for the RTL's sinc^3 CIC; 41 dies; also beh_seq.py (the whole start
    sequence, and 300 overloaded states per die as figure 40);
  - deck_spike.py / xan.py: figure 40's extracted loop with the ss models and run A's input, 30 us.
  (a) the ADC input around a CHOP_OUT edge, samples and reconstruction;
  (b) the behavioral loop's integrator outputs between the strobes, ss die, run A against a DC input of its mean;
  (c) the extracted loop with run A's input: O1, O2, OTA1's virtual ground, and the behavioral loop restarted from the
      extracted state at each CHOP_OUT edge;
  (d) the integrators' peaks over the 41 dies against the quantizer's range, the 1-bit test and the rails, and DATA.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/ver07_spike_fig.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, HAIR, INK, INK2, MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r13", "20261119"
V.CHIP_LABEL = "Chip r13 · r14 control"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RES = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")
XRUN = os.path.join(RES, "xrun_A_actual_ss_30u")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL, PLUM, AMBER, BLUE = "#0d9488", "#a21caf", "#b45309", "#1f5aa8"   # as figure 50 (run A: TEAL, run B: PLUM)
ADC_FS = 0.484                                      # DAC1's full scale at the ADC's input (V, differential)
QTOP = 46.875                                       # the quantizer's outermost thresholds (mV, O2 differential)
MCLK = 1 / 32.768e6
NAMES = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]


def mv(x, nd=1):
    return f"{x:.{nd}f}".replace("-", "−")


def main():
    V.apply()
    wt = np.load(os.path.join(RES, "wave_templates.npz"))
    tr = np.load(os.path.join(RES, "beh_traj.npz"))
    bs = json.load(open(os.path.join(RES, "beh_spike.json")))
    sm = json.load(open(os.path.join(RES, "summary.json")))
    xa = json.load(open(os.path.join(XRUN, "xan.json")))
    x = pd.read_csv(os.path.join(XRUN, "raw.csv"), sep=r"\s+", header=None, engine="c").to_numpy()
    raw = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    raw["t"] = x[:, 0]
    iA, iB = sm["input_A"], sm["input_B"]
    xs = sm["xrun_A_actual_ss_30u"]
    ba, bc, bd = sm["beh_A_actual"], sm["beh_A_clip"], sm["beh_A_dc"]
    sq, sw = sm["seq"], sm["sweep"]
    seq_ss = sq["A / MOS ss (res_ss, mimcap_ss)"]

    fig = V.figure(10.6, 8.6, "VER-07 diagnostic: the ADC with the ss start deck's post-blanking spike",
                   "The ADC input of figure 50's runs in their last millisecond (6.618–7.618 ms) through the ADC loop: "
                   "run A (ss, 300 mV, M 991), a step to +0.64 V for ~90 ns after every blanking window, and run B "
                   "(typical, M 997) as the control · no overload: in 41 dies O1 ≤ "
                   f"{mv(ba['all']['o1_mv'], 0)} mV and O2 ≤ {mv(ba['all']['o2_mv'], 0)} mV, no rail code, no 1-bit mode, "
                   "and DATA equals the waveform's mean",
                   note="The 1 ms result is a behavioral diagnostic: adc_beh_mc.py's per-clock loop (DWA, excess loop delay "
                        "0.22 of a clock, integrator outputs clipped at figure 40's rails O1 ±2.27 V and O2 ±3.25 V) with the "
                        "input integrated exactly on 1000 sub-steps per clock, the strobes on the CHOP_OUT edges (eeg_clkgen), "
                        "the millisecond repeated ×10 for the RTL's sinc³ CIC, 41 dies (5 block corners, 6 resistor / MIM "
                        "corners, 30 Monte Carlo). The 30 µs run is figure 40's extracted loop (eeg_adc, eeg_bias and "
                        "eeg_ref extracted, the chip's reference wiring, the RTL frame timing, the DWA controller, AVDD "
                        "3.245 V) with the ss models (53 min; a millisecond would take ~15 h). Input: the deck's 100 ns "
                        "samples of the 256 edges overlaid (6.25 ns), each segment's charge from the exact integral qo. "
                        "Also behavioral: through the whole start sequence the ss die is back "
                        f"{mv(seq_ss['back_after_release_us'])} µs after the release; from {sw['A_actual']['states']:,} "
                        f"overloaded states (figure 40) all are back within {sw['A_actual']['slowest_us']:.0f} µs, as with "
                        f"the DC input ({sw['A_dc']['slowest_us']:.0f} µs). Not covered: the spike's common-mode part "
                        "(+50 mV on 1.66 V; both decks apply the input differentially), ADC noise, the start deck's ideal "
                        "18.75 kΩ load (RIN +20 % at ss). gf180/tapeout/pex/adc_spike/, runs/ver07_r14/adc_spike/.")
    gs = fig.add_gridspec(2, 2)

    # (a) the input around a CHOP_OUT edge
    ax = fig.add_subplot(gs[0, 0])
    ax.axvspan(-MCLK * 1e9, 15 * MCLK * 1e9 + 0.25, color=HAIR, alpha=0.6, lw=0, zorder=0)
    for lim in (-ADC_FS, ADC_FS):
        ax.axhline(lim * 1e3, color=MUTED, lw=0.8, ls=(0, (3, 2)))
    for tag, col, lab in (("A", TEAL, "run A, ss"), ("B", PLUM, "run B, typical")):
        for p in (0, 1):
            ax.plot(wt[f"{tag}{p}_samples_t"] * 1e9, wt[f"{tag}{p}_samples_u"] * 1e3, "o", ms=2.2, color=col, alpha=0.35,
                    mew=0, zorder=4)
        ax.plot(wt[f"{tag}0_tmpl_t"] * 1e9, wt[f"{tag}0_tmpl_u"] * 1e3, "-", color=col, lw=0.9, label=lab, zorder=3)
        ax.plot(wt[f"{tag}1_tmpl_t"] * 1e9, wt[f"{tag}1_tmpl_u"] * 1e3, "-", color=col, lw=0.7, alpha=0.7, zorder=3)
    ax.text(-260, ADC_FS * 1e3 + 18, "DAC1 full scale ±0.484 V", fontsize=7.5, color=MUTED, va="bottom")
    ax.text(8, -275, "blanking (1 MCLK before\nto 15 MCLK after the edge)", fontsize=7.5, color=INK2, va="top")
    ax.annotate(f"+{mv(iA['peak_mv'], 0)} mV; above +0.484 V for {mv(iA['above_fs_ns'], 0)} ns\n"
                f"{mv(iA['spike_area_mvus'], 0)} mV·µs above the {mv(iA['pre_step_mv'], 0)} mV before it\n"
                f"(O1 +{mv(iA['spike_area_mvus'] / ba['ss']['tau1_us'])} mV in the ss die)",
                xy=(500, 630), xytext=(640, 420), fontsize=7.5, color=INK, va="top",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    ax.set_xlim(-300, 1500)
    ax.set_ylim(-420, 720)
    ax.set_xlabel("time after the CHOP_OUT edge (ns)")
    ax.set_ylabel("ADC input, differential (mV)")
    ax.set_title("(a) The ADC input around a CHOP_OUT edge (dots: the deck's\n100 ns samples of all edges; lines: "
                 "the two chopper phases)", loc="left")
    ax.legend(loc="center right", fontsize=7.5)

    # (b) behavioral, ss die, between the strobes
    ax = fig.add_subplot(gs[0, 1])
    t = tr["t"] * 1e6
    for e in tr["edges"]:
        ax.axvline(e * 1e6, color=HAIR, lw=0.9, zorder=0)
    for lim in (-QTOP, QTOP):
        ax.axhline(lim, color=INK2, lw=0.8, ls=(0, (1, 1.5)))
    ax.plot(t, tr["o1_actual"] * 1e3, color=TEAL, lw=1.1, label="O1, run A")
    ax.plot(t, tr["o2_actual"] * 1e3, color=TEAL, lw=1.0, ls=(0, (4, 2)), label="O2, run A")
    ax.plot(t, tr["o1_dc"] * 1e3, color=MUTED, lw=1.0, label="O1, DC at A's mean")
    ax.plot(t, tr["o2_dc"] * 1e3, color=MUTED, lw=0.9, ls=(0, (4, 2)), label="O2, DC at A's mean")
    ax.text(t[-1], QTOP - 2, "quantizer's outermost thresholds (O2)", fontsize=7.5, color=INK2, ha="right", va="top")
    ax.set_xlim(0, t[-1])
    ax.set_ylim(-55, 55)
    ax.set_xlabel("time (µs; vertical lines: the CHOP_OUT edges)")
    ax.set_ylabel("integrator output, differential (mV)")
    ax.set_title(f"(b) Behavioral, ss die: O1 steps by ~{mv(iA['spike_area_mvus'] / ba['ss']['tau1_us'], 0)} mV at each "
                 "spike;\nthe rails (±2.27 V, ±3.25 V) are far off the scale", loc="left")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 0.1), ncol=2, fontsize=7.5)

    # (c) the extracted loop
    ax = fig.add_subplot(gs[1, 0])
    tt = raw["t"] * 1e6
    o1 = (raw["o1p"] - raw["o1n"]) * 1e3
    o2 = (raw["o2p"] - raw["o2n"]) * 1e3
    vg1 = (raw["i1p"] - raw["i1n"]) * 1e3
    ax.plot(tt, vg1 * 10, color=INK2, lw=0.6, label="OTA1 virtual ground × 10")
    ax.plot(tt, o2, color=BLUE, lw=1.0, label="O2")
    ax.plot(tt, o1, color=TEAL, lw=1.1, label="O1")
    first = True
    for b in xa["beh"]:
        ax.plot(b["t_us"], b["o1_beh_mv"], "o", ms=2.6, color=AMBER, mew=0,
                label="O1 behavioral, restarted at each edge" if first else None)
        first = False
    ax.set_xlim(5, 30)
    ax.set_ylim(-50, 31)
    ax.text(29.6, -48, f"per spike: O1 +{mv(xs['o1_step_mv'][0])}…+{mv(xs['o1_step_mv'][1])} mV, OTA1 virtual ground ≤ "
            f"{mv(xs['vg1_mv'], 2)} mV\n({mv(xs['vg1_outside_spikes_mv'], 2)} mV at the other DAC updates); after the "
            f"deck's reset:\n|O1| ≤ {mv(xs['o1_mv'])} mV, |O2| ≤ {mv(xs['o2_mv'])} mV, DAC codes "
            f"{xs['codes_dac_elements'][0]}–{xs['codes_dac_elements'][1]}, no rail code",
            fontsize=7.5, color=INK, ha="right", va="bottom")
    ax.set_xlabel("deck time (µs)")
    ax.set_ylabel("mV")
    ax.set_title("(c) Extracted loop (figure 40, ss models), run A's input", loc="left")
    ax.legend(loc="upper left", ncol=2, fontsize=7.5)

    # (d) the peaks over the 41 dies against the limits
    ax = fig.add_subplot(gs[1, 1])
    R = {(r["tag"], r["variant"]): r for r in bs["results"]}
    cases = [(("A", "actual"), "run A"), (("A", "clip"), "run A, clipped to ±0.484 V"), (("A", "dc"), "DC at A's mean"),
             (("B", "actual"), "run B"), (("B", "dc"), "DC at B's mean")]
    y = np.arange(len(cases))[::-1]
    o1m = [max(q["o1_peak_mv"] for q in R[k]["dies"]) for k, _ in cases]
    o2m = [max(q["o2_peak_mv"] for q in R[k]["dies"]) for k, _ in cases]
    ax.barh(y + 0.19, o1m, 0.36, color=TEAL, label="max |O1|")
    ax.barh(y - 0.19, o2m, 0.36, color=BLUE, label="max |O2|")
    for xv, lab, col, ls in ((QTOP, "quantizer\n±46.9 mV (O2)", INK2, (0, (1, 1.5))),
                             (500, "1-bit test\n|O1| 0.5 V", ACCENT, (0, (5, 2, 1, 2))),
                             (2270, "rail\nO1", MUTED, (0, (3, 2))), (3250, "rail\nO2", MUTED, (0, (3, 2)))):
        ax.axvline(xv, color=col, lw=0.9, ls=ls)
        ax.text(xv * (0.92 if xv == 2270 else 1.08), len(cases) + 0.5, lab, fontsize=7, color=col,
                ha="right" if xv == 2270 else "left", va="top")
    ax.set_xscale("log")
    ax.set_xlim(4, 8000)
    ax.set_ylim(-0.6, len(cases) + 0.6)
    ax.set_yticks(y, [lab for _, lab in cases])
    ax.set_xlabel("mV (all 41 dies, the millisecond ×10)")
    lo, hi = sm["beh_A_actual_minus_dc_uv"]
    cl = sm["beh_A_clip"]["data_change_minus_input_uv"]
    ax.set_title("(d) Behavioral, 41 dies: the peaks against the limits;\n"
                 f"DATA − DC run {mv(lo, 2)}…+{mv(hi, 2)} µV; clipped: {mv(-sm['beh_A_clip']['input_change_mv'], 2)} mV "
                 f"± {mv(abs(min(cl)), 1)} µV", loc="left")
    ax.legend(loc="upper left", fontsize=7.5)
    ax.grid(axis="y", visible=False)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_51_ver07_spike.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

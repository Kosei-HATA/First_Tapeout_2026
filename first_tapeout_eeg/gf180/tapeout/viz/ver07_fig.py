#!/usr/bin/env python3
"""Figure 50 (r13 analog, r14 digital; 11/21): VER-07, the analog decks at the r14 sequencer's tick phase with r14's
reset trims (audit of 11/21, round 16, A1).

Runs (gf180/tapeout/pex/runs/ver07_r14/run_ver07_r14.sh and run_ver07_r14_b.sh, 11/21): afe_startup.py's start deck
(power-on; the extracted afe_top of r13 with eeg_bias and eeg_ref on the chip wiring with the pads, bond wires and the
board; 27 C; legs of 100 ohm unless noted) with r14's reset trims (AFE_IBIAS 3 from reset, BTRIM_P 1, BTRIM_N 0; REG-05):
  - the start-up with no electrode offset: AFE_RST released at its tick (5.005 ms);
  - afe_saturation.py --seq: an electrode offset present from power-on, the AFE released at 5.005 ms with the offset
    DAC off (it saturates), the host's APPLY at the tick of 5.997 ms (range and M), AFE_RST 6.0205-6.1221 ms (T_PRE
    23.4 us, T_RST 101.6 us), each edge 1739.5 ns after a phase-A edge: 300 mV with M 997 (typical and ss), 30 mV with
    M 100, and 300 mV through 51k||47n on ELP with M 100 (to 20 ms).
Drawn thin: the 11/20 runs of runs/ver07_seq (M from the nominal step, 964 and 96; r13's reset trims; the 51k run with
M 100), which the audit found beyond the ADC's range.
  (a) the ADC input OUTP - OUTN in chopper-period means after the last release (from the exact integral qo, on a grid
      a quarter period after the chopper's edges);
  (b) the instantaneous ADC input after the last release (min and max per half period), the ADC's range marked;
  (c) the residual in chopper-period means referred to the electrode (/ 297.75, the 100-ohm gain), log scale;
  (d) the numbers.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/ver07_fig.py
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
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TCH = 1 / 128e3                                     # the chopper period at 128 kHz
ADC_FS = 0.484                                      # DAC1's full scale at the ADC's input (V, differential)
G_AFE = 297.75                                      # electrode -> ADC input, 100-ohm legs (gf180_input_output_20261112.md)
TEAL, PLUM, AMBER, BLUE = "#0d9488", "#a21caf", "#b45309", "#1f5aa8"
COLS = ["qo", "outp_adc", "outn_adc"]
S14 = "_ib3_ibr3_bt10"
# key, label, colour, the 11/21 run (r14's trims), the 11/20 run (runs/ver07_seq)
CASES = [("start", "start-up, 0 mV", INK2,
          f"start_c1e-08_v3.3_typical_+0mV_afe5.00486ms{S14}_seq_chip_r13",
          "start_c1e-08_v3.3_typical_+0mV_afe5.00486ms_ib3_seq_chip_r13"),
         ("30", "30 mV, M 100", BLUE,
          f"start_c1e-08_v3.3_typical_+30mV_m100_afe5.00486ms{S14}_sat6ms_rst101.563us_seq_chip_r13",
          "start_c1e-08_v3.3_typical_+30mV_afe5.00486ms_ib3_sat6ms_rst101.563us_seq_chip_r13"),
         ("300", "300 mV, M 997", PLUM,
          f"start_c1e-08_v3.3_typical_+300mV_m997_afe5.00486ms{S14}_sat6ms_rst101.563us_seq_chip_r13",
          "start_c1e-08_v3.3_typical_+300mV_afe5.00486ms_ib3_sat6ms_rst101.563us_seq_chip_r13"),
         ("300ss", "300 mV, M 997, ss", ACCENT,
          f"start_c1e-08_v3.3_ss_+300mV_m997_afe5.00486ms{S14}_sat6ms_rst101.563us_seq_chip_r13",
          "start_c1e-08_v3.3_ss_+300mV_afe5.00486ms_ib3_sat6ms_rst101.563us_seq_chip_r13"),
         ("51k", "300 mV, 51k||47n, M 100", AMBER,
          f"start_c1e-08_v3.3_typical_+300mV_m100_afe5.00486ms{S14}_zp100+51k_47n_sat6ms_rst101.563us_seq_chip_r13",
          "start_c1e-08_v3.3_typical_+300mV_m100_afe5.00486ms_ib3_zp100+51k_47n_sat6ms_rst101.563us_seq_chip_r13")]


def load(run):
    d = os.path.join(SU, run)
    if not os.path.exists(os.path.join(d, "tr.csv")):
        return None
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    keep = [0] + [2 * meta["vectors"].index(c) + 1 for c in COLS]
    x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)[keep].to_numpy()
    v = {c: x[:, i + 1] for i, c in enumerate(COLS)}
    v["t"] = x[:, 0]
    v["vo"] = v["outp_adc"] - v["outn_adc"]
    t_rel = meta["afe_rst_again"][1] if meta.get("afe_rst_again") else meta["t_afe"]
    return dict(v=v, m=meta, t_rel=t_rel)


def analyse(r):
    """chopper-period means after the last release, when the instantaneous input is back in range for good, the means at
    0.5, 1.0 and 1.5 ms after the release (8 periods ending there) and at the end (the last 16 periods)"""
    v, m, t_rel = r["v"], r["m"], r["t_rel"]
    t0 = m["t_reset"] + TCH / 4
    e = t0 + TCH * np.arange(int((v["t"][-1] - t0) / TCH) + 1)
    e = e[e >= t_rel - 2 * TCH]
    mm = np.diff(np.interp(e, v["t"], v["qo"])) / TCH
    tc = 0.5 * (e[1:] + e[:-1]) - t_rel
    a = v["t"] > t_rel
    bad = np.nonzero(a & (np.abs(v["vo"]) > ADC_FS))[0]
    if not len(bad):
        back = 0.0
    elif v["t"][-1] - v["t"][bad[-1]] < 2 * TCH:
        back = None
    else:
        back = v["t"][bad[-1] + 1] - t_rel
    at = {}
    for s in (0.5e-3, 1.0e-3, 1.5e-3):
        k = np.nonzero(tc <= s)[0][-8:]               # the 8 periods ending there (the runs end 1.5 ms after it)
        at[s] = mm[k].mean() if len(k) == 8 and tc[k[-1]] > s - TCH else None
    r.update(tc=tc, mm=mm, back=back, at=at, end=mm[-16:].mean(), t_end=v["t"][-1] - t_rel)
    return r


def envelope(v, t0, t1, w=TCH / 2):
    edges = t0 + w * np.arange(int((t1 - t0) / w) + 1)
    i = np.searchsorted(v["t"], edges)
    lo = np.array([v["vo"][a:b].min() if b > a else np.nan for a, b in zip(i[:-1], i[1:])])
    hi = np.array([v["vo"][a:b].max() if b > a else np.nan for a, b in zip(i[:-1], i[1:])])
    return 0.5 * (edges[1:] + edges[:-1]), lo, hi


def fmt(x, unit="mV", scale=1e3, nd=2):
    return "–" if x is None else f"{x * scale:+.{nd}f} {unit}".replace("-", "−")


def main():
    V.apply()
    new = {k: load(n) for k, _l, _c, n, _o in CASES}
    old = {k: load(o) for k, _l, _c, _n, o in CASES}
    for d in (new, old):
        for k in d:
            if d[k] is not None:
                analyse(d[k])
    for tag, d in (("11/21 (r14 trims)", new), ("11/20 (nominal M, r13 trims)", old)):
        for k, lab, *_ in CASES:
            r = d[k]
            if r is None:
                print(f"{tag:30s} {lab:26s} running")
                continue
            b = "never" if r["back"] is None else f"{r['back'] * 1e6:.1f} us"
            print(f"{tag:30s} {lab:26s} back in range {b:>9s}; at 0.5/1.0/1.5 ms {fmt(r['at'][0.5e-3])} / "
                  f"{fmt(r['at'][1.0e-3])} / {fmt(r['at'][1.5e-3])}; end ({r['t_end'] * 1e3:.2f} ms) {fmt(r['end'])}, "
                  f"input-referred {fmt(r['end'] / G_AFE, 'µV', 1e6, 1)}")

    done = [k for k, *_ in CASES if new[k] is not None]
    fig = V.figure(7.6, 7.0, "VER-07: the analog decks at the r14 tick phase, with r14's reset trims",
                   "afe_startup.py / afe_saturation.py --seq: power-on start deck, extracted afe_top r13 with eeg_bias and "
                   "eeg_ref on the chip wiring; AFE_IBIAS 3 from reset, BTRIM_P 1, BTRIM_N 0; the first release at its "
                   "tick (5.005 ms); with an electrode offset the host's APPLY at the tick of 5.997 ms and AFE_RST "
                   "6.0205–6.1221 ms (T_PRE 23.4 µs, T_RST 101.6 µs)",
                   note="Runs: gf180/tapeout/pex/runs/startup/start_…_ib3_ibr3_bt10_…_seq_chip_r13 (ver07_r14/run_ver07_r14.sh "
                        "and run_ver07_r14_b.sh, 11/21). Thin lines: the 11/20 runs (ver07_seq: M from the nominal step "
                        "0.3113 mV, 964 at 300 mV and 96 at 30 mV, and r13's reset trims), beyond the ADC's range. "
                        "Chopper-period means from the exact integral of OUTP − OUTN, on a grid a quarter period after the "
                        "chopper's edges. Electrode-referred values divide by 297.75 (the gain with 100 Ω legs)."
                        + ("" if len(done) == len(CASES) else
                           " Still running: " + ", ".join(lab for k, lab, *_ in CASES if new[k] is None) + "."))
    gs = fig.add_gridspec(2, 2)

    ax = fig.add_subplot(gs[0, 0])
    ax.axhspan(-ADC_FS, ADC_FS, color=HAIR, alpha=0.35, lw=0, zorder=0)
    for k, lab, col, *_ in CASES:
        for d, lw, ls, lb in ((old, 0.8, (0, (2, 1.5)), None), (new, 1.3, "-", lab)):
            r = d[k]
            if r is None:
                continue
            w = r["tc"] <= 2e-3
            ax.plot(r["tc"][w] * 1e3, r["mm"][w], color=col, lw=lw, ls=ls, label=lb)
    ax.set_xlim(-0.02, 2.0)
    ax.set_xlabel("time after the last release (ms)")
    ax.set_ylabel("ADC input, chopper-period mean (V)")
    ax.set_title("(a) The ADC input after the last release\n(shaded: the ADC's range ±0.484 V; thin: 11/20)", loc="left")
    ax.legend(loc="upper right", fontsize=7.5)

    ax = fig.add_subplot(gs[0, 1])
    for lim in (-ADC_FS, ADC_FS):
        ax.axhline(lim, color=MUTED, lw=0.8, ls=(0, (3, 2)))
    for k, lab, col, *_ in CASES:
        r = new[k]
        if r is None:
            continue
        x, lo, hi = envelope(r["v"], r["t_rel"], r["t_rel"] + 300e-6)
        ax.fill_between((x - r["t_rel"]) * 1e6, lo, hi, color=col, alpha=0.25, lw=0)
        ax.plot((x - r["t_rel"]) * 1e6, hi, color=col, lw=0.8)
        ax.plot((x - r["t_rel"]) * 1e6, lo, color=col, lw=0.8)
    ax.set_xlim(0, 300)
    ax.set_xlabel("time after the last release (µs)")
    ax.set_ylabel("ADC input, instantaneous (V)")
    ax.set_title("(b) The instantaneous ADC input (min and max per half\nperiod); dashed: the ADC's range", loc="left")

    ax = fig.add_subplot(gs[1, 0])
    for k, lab, col, *_ in CASES:
        r = new[k]
        if r is None:
            continue
        w = r["tc"] > 0
        ax.semilogy(r["tc"][w] * 1e3, np.abs(r["mm"][w]) / G_AFE * 1e6, color=col, lw=1.1, label=lab)
    ax.set_xlabel("time after the last release (ms)")
    ax.set_ylabel("|ADC input| / 297.75 (µV, electrode-referred)")
    ax.set_title("(c) The residual referred to the electrode", loc="left")

    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    lines = ["After the last release (11/21, r14's trims):"]
    for k, lab, col, *_ in CASES:
        r = new[k]
        if r is None:
            lines.append(f"  {lab}: running")
            continue
        b = "not within the run" if r["back"] is None else f"{r['back'] * 1e6:.1f} µs"
        lines.append(f"  {lab}: in range from {b};")
        lines.append(f"    0.5 / 1.0 / 1.5 ms: {fmt(r['at'][0.5e-3])} / {fmt(r['at'][1.0e-3])} / {fmt(r['at'][1.5e-3])};")
        lines.append(f"    at {r['t_end'] * 1e3:.2f} ms {fmt(r['end'])} ({fmt(r['end'] / G_AFE, 'µV', 1e6, 1)} at the electrode)")
    lines.append("")
    lines.append("11/20 (nominal M, r13's trims), 1.5 ms after the release:")
    lines.append("  " + ", ".join(f"{lab.split(',')[0]} {fmt(old[k]['at'][1.5e-3], 'V', 1, 2)}" for k, lab, *_ in CASES
                                  if old[k] is not None and old[k]["at"][1.5e-3] is not None))
    ax.text(0.0, 1.0, "\n".join(lines), transform=ax.transAxes, va="top", fontsize=8.2, color=INK, linespacing=1.5)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_50_ver07.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

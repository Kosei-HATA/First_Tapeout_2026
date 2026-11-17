#!/usr/bin/env python3
"""Figure 45 (r12, 11/18-): the first power-on with a 300 mV electrode offset behind a real electrode, 51 kohm || 47 nF
in ELP's leg (100 ohm on ELN), against figure 39's 100 ohm legs.

afe_saturation.py's runs (the extracted afe_top, eeg_bias and eeg_ref on the chip's wiring with the pads, bond wires
and the board; power-on, typical, 27 C, AFE_IBIAS 3): AFE_RST released at 5 ms with the offset DAC off, so the AFE
saturates; the host writes range 4 and M with BLANK 15 MCLK at 6.0012 ms, then sets AFE_RST again for 100 us or 1 ms
(--rst-pulse); with --chop-hold, CHOP_EN is low whenever AFE_RST is high (the first reset, 4.8-5.0 ms, included).
  M 983: the whole offset, as the 11/16 procedure would set it if the electrode saw megaohms once released;
  M 94:  the pins' level with the AFE in range. A DAC-cancelled offset sees about 5.4 kohm (the switched capacitor
         of Cin, figure 27's runs: 5.36-5.44 kohm), in reset with the chopper running and after the release alike,
         so the pins sit at 300 mV x 5.4 k / (5.4 k + 51.2 k) = 28.6 mV.
  (a) the pins' differential v(ELP) - v(ELN), chopper-period means;
  (b) the ADC's input OUTP - OUTN, chopper-period means, against its range;
  (c) the electrode current into ELP (from the saved charge qip; the 100 ohm runs: (300 mV - pins) / 200 ohm);
  (d) the pulse and the release, closer;
  (e) the runs.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/electrode_start_fig.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, BAD, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TCH = 256 / 32.768e6                 # the chopper period
TEAL, PLUM, AMBER = "#0d9488", "#a21caf", "#b45309"
ADC_FS = 0.484                       # DAC1's full scale at the ADC's input (V, differential)
VSRC = 0.300                         # the electrode offset
R_SC = 5.40e3                        # what a DAC-cancelled offset sees at the pins (figure 27's runs: 5.36-5.44 kohm)
R_EL = 51.2e3                        # 51 kohm + 100 ohm in ELP's leg, 100 ohm in ELN's
R_LEGS = 200.0                       # the 100 ohm legs
I_LIMIT = 10e-6                      # IEC 60601-1, patient auxiliary current, DC, normal condition
STEP = 300.0 / 997                   # mV per step of M at range 4 (figure 27's 300 mV run)
T_WRITE = 6.0012e-3
ZP = "_zp100+51k_47n"
# key, the run's name between the offset and the chip, label, colour, line style, line width
RUNS = [
    ("E", f"_m94_afe5ms_ib3{ZP}_sat6ms_rst1000us", "51 k || 47 n, M 94, AFE_RST 1 ms", TEAL, "-", 1.4),
    ("F", f"_m94_afe5ms_ib3{ZP}_sat6ms_rst100us", "51 k || 47 n, M 94, AFE_RST 100 µs", AMBER, "-", 1.4),
    ("B", f"_m983_afe5ms_ib3{ZP}_sat6ms_rst100us_chophold", "51 k || 47 n, M 983, 100 µs, CHOP_EN low", PLUM, "-", 1.4),
    ("P", "_m997_afe5ms_ib3_sat6ms_rst100us", "100 Ω legs, M 997, 100 µs (figure 39)", INK2, "-", 0.9),
    ("D", "_m997_afe5ms_ib3_sat6ms_rst100us_chophold", "100 Ω legs, M 997, 100 µs, CHOP_EN low", INK2, (0, (1, 1.4)), 1.1),
]
COLS = ["elp", "eln", "outp_adc", "outn_adc", "qip"]


def name(tail):
    return f"start_c1e-08_v3.3_typical_+300mV{tail}_chip_{V.CHIP}"


def load(run):
    d = os.path.join(SU, run)
    if not os.path.exists(os.path.join(d, "tr.csv")):
        return None, None
    m = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    names = m["vectors"]
    cols = [c for c in COLS if c in names]
    keep = [0] + [2 * names.index(c) + 1 for c in cols]
    x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)[keep].to_numpy()
    v = {c: x[:, i + 1] for i, c in enumerate(cols)}
    v["t"] = x[:, 0]
    v["pins"] = v["elp"] - v["eln"]
    v["vo"] = v["outp_adc"] - v["outn_adc"]
    return v, m


def cum(t, y):
    return np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])


def periods(v, m, t1=None):
    """chopper periods from a quarter period after RESET_N's edges (the means stay off the chopper's edges)"""
    t0 = m["t_reset"] + TCH / 4
    t1 = v["t"][-1] if t1 is None else t1
    return t0 + TCH * np.arange(int((t1 - t0) / TCH + 1e-9) + 1)


def series(v, m, n=8):
    """means over n chopper periods, sliding by one: centres, pins (V), ADC input (V), electrode current into ELP (A).
    Eight periods are 62.5 us, 625 points of the 100 ns grid: the chopper's spikes at the pins (about 0.4 us) fall on
    the grid with a phase that repeats every 8 periods, so one-period means of the pins carry a 62.5 us pattern."""
    e = periods(v, m)
    c = 0.5 * (e[1:] + e[:-1])
    pins = np.diff(np.interp(e, v["t"], cum(v["t"], v["pins"]))) / TCH
    vo = np.diff(np.interp(e, v["t"], cum(v["t"], v["vo"]))) / TCH
    cur = np.diff(np.interp(e, v["t"], v["qip"])) / TCH if "qip" in v else (VSRC - pins) / R_LEGS
    k = np.ones(n) / n
    return tuple(np.convolve(y, k, "valid") for y in (c, pins, vo, cur))


def back_in_range(v, t0):
    """from when on (after t0) the instantaneous ADC input stays inside its range; None if not by the run's end"""
    bad = np.nonzero((v["t"] > t0) & (np.abs(v["vo"]) > ADC_FS))[0]
    if not len(bad):
        return 0.0
    return None if v["t"][-1] - v["t"][bad[-1]] < 2 * TCH else v["t"][bad[-1] + 1] - t0


def facts(v, m, s):
    c, pins, vo, cur = s
    t1, t2 = m["afe_rst_again"]
    end = c > c[-1] - 0.5e-3

    def ending(t):                                       # the 8-period window that ends at t (or just before)
        return pins[np.nonzero(c <= t - 4 * TCH + 1e-9)[0][-1]]
    return dict(t1=t1, t2=t2, tend=v["t"][-1], pw=ending(T_WRITE), prel=ending(t2), pend=pins[end].mean(),
                voend=vo[end].mean(), iend=cur[end].mean(), back=back_in_range(v, t2),
                imax=np.abs(cur[c > 5.0e-3]).max())


def main():
    runs = {k: load(name(tail)) for k, tail, *_ in RUNS}
    have = [k for k in runs if runs[k][0] is not None]
    S = {k: series(*runs[k]) for k in have}
    F = {k: facts(*runs[k], S[k]) for k in have}
    interim = len(have) < len(RUNS)
    for k in have:
        f = F[k]
        bk = "never" if f["back"] is None else f"{f['back'] * 1e3:.3f} ms"
        print(f"{k}: to {f['tend'] * 1e3:.3f} ms; pins at the write {f['pw'] * 1e3:.2f} mV, at the release {f['prel'] * 1e3:.2f} mV, "
              f"end {f['pend'] * 1e3:.2f} mV; ADC input at the end {f['voend']:+.3f} V; back in range {bk} after the release; "
              f"current at the end {f['iend'] * 1e6:.2f} uA (largest period {f['imax'] * 1e6:.1f} uA)")
    p_in = VSRC * R_SC / (R_SC + R_EL)

    fig = V.figure(12.8, 12.6, "First power-on with a real electrode: a 300 mV offset behind 51 kΩ || 47 nF" +
                   (" (interim)" if interim else ""),
                   "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires, power-on · "
                   "typical, 27 °C · AFE_RST released at 5 ms with the offset DAC off · the host writes range 4 and M "
                   "(BLANK 15 MCLK) at 6.0012 ms, then sets AFE_RST again · ELP 100 Ω + 51 kΩ || 47 nF, ELN 100 Ω",
                   note="A DAC-cancelled offset sees about 5.4 kΩ at the pins (figure 27's runs, 5.36–5.44 kΩ): the switched "
                        "capacitor of Cin (about 730 pF at 128 kHz). Cpf's positive feedback supplies only the charge for "
                        "what the amplifier's output carries, and the DAC cancels at the virtual ground. The load is the "
                        "same in reset with the chopper running, so with 51 kΩ in the leg the pins settle at "
                        f"300 mV × 5.4 k / (5.4 k + 51.2 k) = {p_in * 1e3:.1f} mV, where M 94 cancels "
                        f"{94 * STEP:.1f} mV; M 983 ({983 * STEP:.1f} mV) is the whole offset, as with megaohms at the pins. "
                        "CHOP_EN low ('--chop-hold'): whenever AFE_RST is high, the first reset (4.8–5.0 ms) included. "
                        "Electrode current: into ELP from the offset's source, from the leg's saved charge; the 100 Ω runs "
                        "(no saved charge) as (300 mV − pins) / 200 Ω. 10 µA: IEC 60601-1's patient auxiliary current, DC, "
                        "normal condition (10/23's requirement for the chip: 1 nA per electrode). Means over 8 chopper periods "
                        "(62.5 µs, sliding by one period): one-period means of the pins carry a 62.5 µs pattern "
                        "of the 100 ns output grid against the chopper's 0.4 µs spikes.")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.62])

    def mark(ax):
        ax.axvline(T_WRITE * 1e3, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.text(T_WRITE * 1e3 + 0.04, 0.985, "the write", transform=ax.get_xaxis_transform(), fontsize=7.4,
                color=MUTED, va="top")

    def lines(ax, idx, scale, x0=4.5e-3, x1=10.0e-3):
        for k, tail, lab, col, ls, lw in RUNS:
            if k not in S:
                ax.plot([], [], color=col, ls=ls, lw=lw, alpha=0.35, label=f"{lab} (running)")
                continue
            c = S[k][0]
            a = (c > x0) & (c < x1)
            ax.plot(c[a] * 1e3, S[k][idx][a] * scale, color=col, ls=ls, lw=lw, label=lab)

    # (a) the pins
    ax = fig.add_subplot(gs[0, 0])
    lines(ax, 1, 1e3)
    ax.axhline(VSRC * 1e3, color=LIGHT, lw=0.8, ls=(0, (4, 2)))
    ax.text(4.55, VSRC * 1e3 + 6, "the offset, 300 mV", fontsize=7.4, color=MUTED, va="bottom")
    ax.axhline(p_in * 1e3, color=TEAL, lw=0.8, ls=(0, (4, 2)))
    ax.text(4.55, p_in * 1e3 + 6, f"in range with 51 kΩ: {p_in * 1e3:.1f} mV", fontsize=7.4, color=TEAL, va="bottom")
    ax.axhline(0, color=LIGHT, lw=0.7)
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("v(ELP) − v(ELN), 8-period mean (mV)")
    b = F.get("B")
    ax.set_title("The pins" + (f": with M 983 the AFE saturates the other way at the release\nand pulls ELP to "
                               f"{b['pend'] * 1e3:.0f} mV, against the offset's +300 mV" if b else ""), loc="left")
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.905), fontsize=7.2)

    # (b) the ADC's input
    ax = fig.add_subplot(gs[0, 1])
    ax.axhspan(-ADC_FS, ADC_FS, color=ACCENT, alpha=0.07, lw=0)
    ax.text(9.95, ADC_FS + 0.04, "the ADC's range", fontsize=7.4, color=ACCENT, va="bottom", ha="right")
    lines(ax, 2, 1.0)
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_ylim(-2.2, 2.2)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("OUTP − OUTN at the ADC, 8-period mean (V)")
    ax.set_title("The ADC's input" + (f": M 983 holds it at {b['voend']:+.2f} V, out of range,\nto the end of the run "
                                      f"({b['tend'] * 1e3:.0f} ms); the host reads −full scale" if b else ""), loc="left")

    # (c) the electrode current
    ax = fig.add_subplot(gs[1, 0])
    lines(ax, 3, 1e6)
    ax.axhline(I_LIMIT * 1e6, color=BAD, lw=0.9, ls=(0, (4, 2)))
    ax.text(6.25, I_LIMIT * 1e6 - 0.8, "10 µA: patient auxiliary current, DC limit", fontsize=7.4, color=BAD, va="top")
    i_in = VSRC / (R_SC + R_EL)
    ax.axhline(i_in * 1e6, color=TEAL, lw=0.8, ls=(0, (4, 2)))
    ax.text(9.95, i_in * 1e6 - 0.8, f"in range with 51 kΩ: {i_in * 1e6:.1f} µA", fontsize=7.4, color=TEAL, va="top",
            ha="right")
    ax.axhline(0, color=LIGHT, lw=0.7)
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("Current into ELP, 8-period mean (µA)")
    p = F.get("P")
    ax.set_title("The electrode current" + (f": {b['iend'] * 1e6:.1f} µA at {b['tend'] * 1e3:.0f} ms with M 983" if b else "") +
                 (f";\n{p['iend'] * 1e6:.0f} µA with 100 Ω legs once the DAC cancels the offset" if p else ""), loc="left")

    # (d) the pulse and the release, closer
    ax = fig.add_subplot(gs[1, 1])
    lines(ax, 1, 1e3, 5.85e-3, 7.6e-3)
    for k in have:
        if k in ("B", "F", "E"):
            t1, t2 = F[k]["t1"], F[k]["t2"]
            col = next(r[3] for r in RUNS if r[0] == k)
            ax.axvspan(t1 * 1e3, t2 * 1e3, color=col, alpha=0.06, lw=0)
    ax.axhline(p_in * 1e3, color=TEAL, lw=0.8, ls=(0, (4, 2)))
    ax.axhline(0, color=LIGHT, lw=0.7)
    mark(ax)
    ax.set_xlim(5.85, 7.6)
    ax.set_ylim(-400, 330)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("v(ELP) − v(ELN), 8-period mean (mV)")
    tau = (R_EL * R_SC / (R_EL + R_SC)) * 47e-9
    ax.set_title("The pulse (shaded) and the release: with CHOP_EN low the electrode drifts\nback to 300 mV; with the "
                 f"chopper on it settles to {p_in * 1e3:.1f} mV (τ = (51.2 k || 5.4 k) × 47 nF = {tau * 1e3:.2f} ms)",
                 loc="left")

    # (e) the runs
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    head = ["", "M", "AFE_RST again", "CHOP_EN in resets", "Pins at the write", "Pins at the release",
            "ADC input in range", "At the end: pins", "ADC input", "Current into ELP"]
    rows, colours = [], []
    for k, tail, lab, col, ls, lw in RUNS:
        mag = tail.split("_m")[1].split("_")[0]
        pulse = "1 ms" if "rst1000us" in tail else "100 µs"
        hold = "low" if "chophold" in tail else "running"
        leg = "100 Ω legs" if ZP not in tail else "51 k || 47 n"
        if k not in F:
            rows.append([f"{k}: {leg}", mag, pulse, hold, "running", "", "", "", "", ""])
        else:
            f = F[k]
            bk = "never (to the end)" if f["back"] is None else ("at once" if f["back"] < 1e-6 else f"{f['back'] * 1e3:.2f} ms after")
            rows.append([f"{k}: {leg}", mag, pulse, hold, f"{f['pw'] * 1e3:.1f} mV", f"{f['prel'] * 1e3:.1f} mV", bk,
                         f"{f['pend'] * 1e3:.1f} mV ({f['tend'] * 1e3:.1f} ms)", f"{f['voend']:+.3f} V", f"{f['iend'] * 1e6:.1f} µA"])
        colours.append(col)
    tb = ax.table(cellText=rows, colLabels=head, loc="center", cellLoc="center", colLoc="center",
                  colWidths=[0.13, 0.05, 0.08, 0.1, 0.1, 0.11, 0.12, 0.13, 0.08, 0.1])
    tb.auto_set_font_size(False)
    tb.set_fontsize(7.8)
    tb.scale(1, 1.32)
    for (r, cc), cell in tb.get_celld().items():
        cell.set_edgecolor("#e2e8f0")
        if r == 0:
            cell.set_text_props(color=INK2, fontweight="medium")
        elif cc == 0:
            cell.set_text_props(color=colours[r - 1], fontweight="medium")
        else:
            cell.set_text_props(color=INK)
    ax.set_title("The runs (300 mV at the offset's source, typical)", loc="left")

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_45_electrode_start.png")
    fig.savefig(path)
    print(path)


if __name__ == "__main__":
    main()

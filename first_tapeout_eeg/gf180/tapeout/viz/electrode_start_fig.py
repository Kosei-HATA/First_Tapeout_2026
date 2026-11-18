#!/usr/bin/env python3
"""Figure 45 (r12, 11/18-): the first power-on with a 300 mV electrode offset behind a real electrode, 51 kohm || 47 nF
in ELP's leg (100 ohm on ELN), against figure 39's 100 ohm legs.

afe_saturation.py's runs (the extracted afe_top, eeg_bias and eeg_ref on the chip's wiring with the pads, bond wires
and the board; power-on, typical, 27 C, AFE_IBIAS 3): AFE_RST released at 5 ms with the offset DAC off, so the AFE
saturates; the host writes range 4 and M with BLANK 15 MCLK at 6.0012 ms, then sets AFE_RST again for 100 us or 1 ms
(--rst-pulse); with --chop-hold, CHOP_EN is low whenever AFE_RST is high (the first reset, 4.8-5.0 ms, included).

What the AFE amplifies is the pins' voltage when the input chopper switches: the chopper's spikes (Cin recharged
through the legs, about 0.4 us) are over by then, so the pins are sampled 0.3 us before each chopper edge ("settled
pins"); their plain mean is lower by the spikes' drop in the legs (about 1.4 mV here). The AFE's input is the
settled pins less what the DAC cancels, M x 300/997 mV (figure 27's 300 mV run); the ADC's range is +-0.484 V at its
input, +-1.63 mV at the AFE's input (gain 297.5).

After the release, Cpf's positive feedback supplies the charge for what the amplifier's output carries, so the
electrode current is the DAC-cancelled part's, M step / R_sc (R_sc 5.67 kohm at these pins, 5.56 kohm at 300 mV: the
switched capacitor of Cin), the chip is a current sink to the electrode (it relaxes with R_e C_e = 2.4 ms), and the
electrode's drop moves with M: each step of M moves the AFE's input by step x (1 + R_e / R_sc), 3.0 mV behind
51 kohm, nearly the ADC's whole range (G, 11/18 afternoon). Near the range's edge the AFE compresses and Cpf no longer
supplies the whole residual, so the chip draws a little more current and the electrode's drop pulls the pins back
(M 98 and M 94 settle with tau 0.4 ms). In reset with the chopper running the whole pin voltage sees about 5.7 kohm,
so the pulse charges the electrode to about 30 mV whatever M is.
  E, F: M 94, from the pins' plain mean (28.4 mV), 1 ms and 100 us pulses;
  G98, G99, G100: M 98-100, 1 ms pulses, to find the code that lands in range (M 100);
  B: M 983, the whole offset, as the 11/16 procedure would set it if the electrode saw megaohms, CHOP_EN low.
  (a) the settled pins; (b) the ADC's input; (c) the electrode current into ELP (from the saved charge qip; the
  100 ohm runs: (300 mV - pins) / 200 ohm), all as 8-period means; (d) the ADC's input / 297.5 after the 1 ms pulse
  (the AFE's input as the host reads it, the chip's own offset included), M 94-100, with exponential fits carried on;
  (e) the runs.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/electrode_start_fig.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, BAD, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TCH = 256 / 32.768e6                 # the chopper period
LEAD = 0.3e-6                        # settled pins: sampled this long before each chopper edge
TEAL, PLUM, AMBER = "#0d9488", "#a21caf", "#b45309"
ORANGE, BLUE, ROSE = "#ea580c", "#2563eb", "#be185d"   # M 98, 99, 100 (validated with M 94's teal, adjacent pairs)
ADC_FS = 0.484                       # DAC1's full scale at the ADC's input (V, differential)
GAIN = 297.5                         # the AFE's gain to the ADC's input
VSRC = 0.300                         # the electrode offset
R_E, C_E = 51e3, 47e-9               # the electrode, 51 kohm || 47 nF
I_LIMIT = 10e-6                      # IEC 60601-1, patient auxiliary current, DC, normal condition
STEP = 0.300 / 997                   # V per step of M at range 4 (figure 27's 300 mV run)
VG_SAT = 1e-3                        # the amplifier's virtual-ground error above which it is saturated (V)
T_WRITE = 6.0012e-3
FIT_FROM = 1.0e-3                    # fits start this long after the release (the first ms carries VCM_AFE's return)
ZP = "_zp100+51k_47n"
# key, the run's name between the offset and the chip, label, colour, line style, line width, panels
RUNS = [
    ("E", f"_m94_afe5ms_ib3{ZP}_sat6ms_rst1000us", "51 k || 47 n, M 94, AFE_RST 1 ms", TEAL, "-", 1.4, "abcd"),
    ("F", f"_m94_afe5ms_ib3{ZP}_sat6ms_rst100us", "51 k || 47 n, M 94, AFE_RST 100 µs", AMBER, "-", 1.4, "abc"),
    ("B", f"_m983_afe5ms_ib3{ZP}_sat6ms_rst100us_chophold", "51 k || 47 n, M 983, 100 µs, CHOP_EN low", PLUM, "-",
     1.4, "abc"),
    ("P", "_m997_afe5ms_ib3_sat6ms_rst100us", "100 Ω legs, M 997, 100 µs (figure 39)", INK2, "-", 0.9, "abc"),
    ("D", "_m997_afe5ms_ib3_sat6ms_rst100us_chophold", "100 Ω legs, M 997, 100 µs, CHOP_EN low", INK2,
     (0, (1, 1.4)), 1.1, "abc"),
    ("G98", f"_m98_afe5ms_ib3{ZP}_sat6ms_rst1000us", "51 k || 47 n, M 98, AFE_RST 1 ms", ORANGE, "-", 1.4, "d"),
    ("G99", f"_m99_afe5ms_ib3{ZP}_sat6ms_rst1000us", "51 k || 47 n, M 99, AFE_RST 1 ms", BLUE, "-", 1.4, "d"),
    ("G100", f"_m100_afe5ms_ib3{ZP}_sat6ms_rst1000us", "51 k || 47 n, M 100, AFE_RST 1 ms", ROSE, "-", 1.4, "d"),
]
COLS = ["elp", "eln", "outp_adc", "outn_adc", "qip", "inp", "inn"]


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
    v["vg"] = v["inp"] - v["inn"]
    return v, m


def cum(t, y):
    return np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])


def periods(v, m, t1=None):
    """chopper periods from a quarter period after RESET_N's edges (the means stay off the chopper's edges)"""
    t0 = m["t_reset"] + TCH / 4
    t1 = v["t"][-1] if t1 is None else t1
    return t0 + TCH * np.arange(int((t1 - t0) / TCH + 1e-9) + 1)


def series(v, m, n=8):
    """means over n chopper periods, sliding by one. Returns a dict: c (centres), pins (plain mean), set (the settled
    pins, sampled LEAD before each of the period's two chopper edges), vo (ADC input), cur (electrode current into
    ELP), vg (the amplifier's virtual-ground error, |inp - inn| at the same instants). Eight periods are 62.5 us, 625
    points of the 100 ns grid: the chopper's spikes at the pins fall on the grid with a phase that repeats every
    8 periods, so one-period means of the pins carry a 62.5 us pattern."""
    e = periods(v, m)
    t = v["t"]
    s = {"c": 0.5 * (e[1:] + e[:-1])}
    s["pins"] = np.diff(np.interp(e, t, cum(t, v["pins"]))) / TCH
    s["vo"] = np.diff(np.interp(e, t, cum(t, v["vo"]))) / TCH
    s["cur"] = (np.diff(np.interp(e, t, v["qip"])) / TCH if "qip" in v else (VSRC - s["pins"]) / 200.0)
    edges = [e[:-1] + TCH / 4 - LEAD, e[:-1] + 3 * TCH / 4 - LEAD]   # the edges at t_reset + k TCH / 2
    s["set"] = 0.5 * sum(np.interp(x, t, v["pins"]) for x in edges)
    s["vg"] = 0.5 * sum(np.abs(np.interp(x, t, v["vg"])) for x in edges)
    k = np.ones(n) / n
    s["c"] = np.convolve(s["c"], k, "valid")
    for key in ("pins", "vo", "cur", "set", "vg"):
        s[key] = np.convolve(s[key], k, "valid")
    return s


def vdac(m, t):
    """what the DAC cancels at time(s) t (V): M step from the write on"""
    return np.where(np.asarray(t) > m["t_dac"], m["dac_mag"] * STEP, 0.0)


def in_range(s):
    return (np.abs(s["vo"]) < ADC_FS) & (s["vg"] < VG_SAT)


def back_in_range(s, t0):
    """from when on (after t0) the ADC input stays in its range with the amplifier unsaturated; None if not at the end"""
    a = s["c"] > t0 + 4 * TCH
    ok = in_range(s)[a]
    if not ok[-1]:
        return None
    bad = np.nonzero(~ok)[0]
    return 0.0 if not len(bad) else s["c"][a][bad[-1] + 1] - 4 * TCH - t0


def fit_tail(s, m, t0, host=False):
    """the AFE's input after t0 (settled pins - M step, or with host=True the ADC's input / GAIN, what the host reads),
    fitted with r_inf + A exp(-(t - t0) / tau): (r_inf, tau, rms, f, p)"""
    a = s["c"] > t0
    tt = s["c"][a] - t0
    r = s["vo"][a] / GAIN if host else s["set"][a] - vdac(m, s["c"][a])
    f = lambda x, rinf, amp, tau: rinf + amp * np.exp(-x / tau)   # noqa: E731
    best = None
    for tau0 in (0.4e-3, R_E * C_E):                     # out of range the chip loads the residual (tau about 0.4 ms)
        p, _ = curve_fit(f, tt, r, p0=(r[-1], r[0] - r[-1], tau0), bounds=([-1, -1, 1e-5], [1, 1, 0.1]),
                         maxfev=20000)
        rms = float(np.sqrt(np.mean((f(tt, *p) - r) ** 2)))
        if best is None or rms < best[2]:
            best = (p[0], p[2], rms, f, p)
    return best


def facts(v, m, s):
    t1, t2 = m["afe_rst_again"]
    c = s["c"]
    end = c > c[-1] - 0.5e-3

    def ending(key, t):                                  # the 8-period window that ends at t (or just before)
        return s[key][np.nonzero(c <= t - 4 * TCH + 1e-9)[0][-1]]
    f = dict(t1=t1, t2=t2, tend=v["t"][-1], M=m["dac_mag"], pw=ending("set", T_WRITE), prel=ending("set", t2),
             pend=s["set"][end].mean(), voend=s["vo"][end].mean(), iend=s["cur"][end].mean(),
             vgend=s["vg"][end].mean(), back=back_in_range(s, t2), imax=np.abs(s["cur"][c > 5.0e-3]).max())
    f["rrel"] = f["prel"] - m["dac_mag"] * STEP
    f["rend"] = f["pend"] - m["dac_mag"] * STEP
    long = t2 - t1 > 0.5e-3                              # the 1 ms pulses: fitted from 1 ms after the release
    f["fit"] = fit_tail(s, m, t2 + FIT_FROM) if long else None
    f["fith"] = fit_tail(s, m, t2 + FIT_FROM, host=True) if long else None
    return f


def main():
    runs = {r[0]: load(name(r[1])) for r in RUNS}
    have = [k for k in runs if runs[k][0] is not None]
    S = {k: series(*runs[k]) for k in have}
    F = {k: facts(*runs[k], S[k]) for k in have}
    interim = len(have) < len(RUNS)
    for k in have:
        f = F[k]
        bk = "never" if f["back"] is None else f"{f['back'] * 1e3:.3f} ms"
        ft = "" if f["fit"] is None else (f"; fit after the release: AFE input -> {f['fit'][0] * 1e3:+.3f} mV, "
                                          f"tau {f['fit'][1] * 1e3:.3f} ms (rms {f['fit'][2] * 1e6:.1f} uV); "
                                          f"ADC input / {GAIN} -> {f['fith'][0] * 1e3:+.3f} mV "
                                          f"({f['fith'][0] * GAIN:+.4f} V), tau {f['fith'][1] * 1e3:.3f} ms "
                                          f"(rms {f['fith'][2] * 1e6:.1f} uV)")
        print(f"{k}: to {f['tend'] * 1e3:.3f} ms; settled pins at the write {f['pw'] * 1e3:.2f} mV, at the release "
              f"{f['prel'] * 1e3:.2f} mV (AFE input {f['rrel'] * 1e3:+.3f} mV), end {f['pend'] * 1e3:.3f} mV (AFE input "
              f"{f['rend'] * 1e3:+.3f} mV); ADC input at the end {f['voend']:+.3f} V (/{GAIN} = "
              f"{f['voend'] / GAIN * 1e3:+.3f} mV), virtual ground {f['vgend'] * 1e3:.3f} mV; in range {bk} after "
              f"the release; current at the end {f['iend'] * 1e6:.3f} uA (largest period {f['imax'] * 1e6:.1f} uA){ft}")
    win = ADC_FS / GAIN

    fig = V.figure(12.8, 12.9, "First power-on with a real electrode: a 300 mV offset behind 51 kΩ || 47 nF" +
                   (" (interim)" if interim else ""),
                   "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires, power-on · "
                   "typical, 27 °C · AFE_RST released at 5 ms with the offset DAC off · the host writes range 4 and M "
                   "(BLANK 15 MCLK) at 6.0012 ms, then sets AFE_RST again · ELP 100 Ω + 51 kΩ || 47 nF, ELN 100 Ω",
                   note="Settled pins: v(ELP) − v(ELN) 0.3 µs before each chopper edge, what the input chopper hands "
                        "to Cin; the plain mean is lower by the chopper's spikes in the legs (about 1.4 mV behind "
                        "51 kΩ, 11 mV with the 100 Ω legs at 300 mV). The AFE's input: settled pins − M × 300/997 mV. "
                        "After the release Cpf's positive feedback supplies the charge for what the amplifier's output "
                        "carries, so the electrode current is the DAC-cancelled part's, M × step / R_sc (R_sc 5.67 kΩ "
                        "at these pins, 5.56 kΩ at 300 mV: the switched capacitor of Cin): the chip is a current sink "
                        "to the electrode, which relaxes with 51 k × 47 n = 2.4 ms, and each step of M moves the AFE's "
                        "input by step × (1 + 51 k / R_sc) = 3.0 mV, against the ADC's ±1.63 mV. Near the range's edge "
                        "the AFE compresses and Cpf no longer supplies the whole residual: the chip draws a little more "
                        "current, the electrode's drop pulls the pins back, and M 98 and M 94 settle with τ about "
                        "0.4 ms. In reset with the chopper running the whole pin voltage sees about 5.7 kΩ, so the "
                        "pulse charges the electrode to about 30 mV whatever M is; with CHOP_EN low the pins see "
                        "capacitance only and the electrode drifts back towards 300 mV. In range: ADC input inside "
                        "±0.484 V with the amplifier's virtual-ground error under 1 mV (F's mean dips into range at "
                        "6.6 ms while the amplifier is still saturated, 14 mV). Fits in (d) and the table: "
                        "r∞ + A·exp(−t/τ) from 1 ms after the release, carried on dashed. 10 µA: IEC 60601-1's patient "
                        "auxiliary current, DC, normal condition (10/23's requirement for the chip: 1 nA per "
                        "electrode). Means over 8 chopper periods (62.5 µs, sliding by one period).")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.78])

    def mark(ax):
        ax.axvline(T_WRITE * 1e3, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.text(T_WRITE * 1e3 + 0.04, 0.985, "the write", transform=ax.get_xaxis_transform(), fontsize=7.4,
                color=MUTED, va="top")

    def lines(ax, key, scale, panel, x0=4.5e-3, x1=10.0e-3):
        for k, tail, lab, col, ls, lw, panels in RUNS:
            if panel not in panels:
                continue
            if k not in S:
                ax.plot([], [], color=col, ls=ls, lw=lw, alpha=0.35, label=f"{lab} (running)")
                continue
            c = S[k]["c"]
            a = (c > x0) & (c < x1)
            ax.plot(c[a] * 1e3, S[k][key][a] * scale, color=col, ls=ls, lw=lw, label=lab)

    e, f_, b, p = (F.get(k) for k in ("E", "F", "B", "P"))

    # (a) the settled pins
    ax = fig.add_subplot(gs[0, 0])
    lines(ax, "set", 1e3, "a")
    ax.axhline(VSRC * 1e3, color=LIGHT, lw=0.8, ls=(0, (4, 2)))
    ax.text(9.95, VSRC * 1e3 - 8, "the offset, 300 mV", fontsize=7.4, color=MUTED, va="top", ha="right")
    ax.axhline(0, color=LIGHT, lw=0.7)
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("Settled pins, v(ELP) − v(ELN), 8-period mean (mV)")
    ax.set_title("The pins as the chopper hands them to Cin: the pulse with the chopper running\n"
                 + (f"charges the electrode to {e['prel'] * 1e3:.1f} mV; CHOP_EN low lets it drift back (B)"
                    if e else "charges the electrode; CHOP_EN low lets it drift back (B)"), loc="left")
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.93), fontsize=7.2)

    # (b) the ADC's input
    ax = fig.add_subplot(gs[0, 1])
    ax.axhspan(-ADC_FS, ADC_FS, color=ACCENT, alpha=0.07, lw=0)
    ax.text(9.95, ADC_FS + 0.04, "the ADC's range", fontsize=7.4, color=ACCENT, va="bottom", ha="right")
    lines(ax, "vo", 1.0, "b")
    if f_:
        c = S["F"]["c"]
        dip = (c > 6.3e-3) & (c < 7.0e-3)
        i = np.argmin(S["F"]["vo"][dip])
        ax.annotate(f"F: amplifier still saturated\n(virtual ground {S['F']['vg'][dip][i] * 1e3:.0f} mV)",
                    xy=(c[dip][i] * 1e3, S["F"]["vo"][dip][i]), xytext=(7.3, -0.75), fontsize=7.2, color=INK2,
                    arrowprops=dict(arrowstyle="-", color=AMBER, lw=0.7))
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_ylim(-2.2, 2.2)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("OUTP − OUTN at the ADC, 8-period mean (V)")
    ax.set_title("The ADC's input" + (f": M 94 leaves E and F at {e['voend']:+.2f} V and {f_['voend']:+.2f} V,\nout of "
                                      f"range, to the end ({e['tend'] * 1e3:.0f} ms); M 983 holds B at {b['voend']:+.2f} V"
                                      if e and f_ and b else ""), loc="left")

    # (c) the electrode current
    ax = fig.add_subplot(gs[1, 0])
    lines(ax, "cur", 1e6, "c")
    ax.axhline(I_LIMIT * 1e6, color=BAD, lw=0.9, ls=(0, (4, 2)))
    ax.text(6.25, I_LIMIT * 1e6 + 0.8, "10 µA: patient auxiliary current, DC limit", fontsize=7.4, color=BAD,
            va="bottom")
    ax.axhline(0, color=LIGHT, lw=0.7)
    mark(ax)
    ax.set_xlim(4.5, 10.0)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("Current into ELP, 8-period mean (µA)")
    ax.set_title("The electrode current" + (f": {e['iend'] * 1e6:.1f} µA behind 51 kΩ (M 94), {b['iend'] * 1e6:.1f} µA "
                                            f"with M 983\nlatched the other way, {p['iend'] * 1e6:.0f} µA with 100 Ω legs"
                                            if e and b and p else ""), loc="left")

    # (d) the AFE's input as the host reads it (ADC input / GAIN) after the 1 ms pulse, M 94-100
    ax = fig.add_subplot(gs[1, 1])
    ax.axhspan(-win * 1e3, win * 1e3, color=ACCENT, alpha=0.07, lw=0)
    ax.text(15.9, -win * 1e3 - 0.12, f"the ADC's range at the AFE's input, ±{win * 1e3:.2f} mV", fontsize=7.4,
            color=ACCENT, va="top", ha="right")
    X1 = 16.0e-3
    for k, tail, lab, col, ls, lw, panels in RUNS:
        if "d" not in panels:
            continue
        if k not in S:
            ax.plot([], [], color=col, ls=ls, lw=lw, alpha=0.35, label=f"M {tail.split('_m')[1].split('_')[0]} (running)")
            continue
        s, m, f = S[k], runs[k][1], F[k]
        a = s["c"] > f["t2"] + 2 * TCH
        ax.plot(s["c"][a] * 1e3, s["vo"][a] / GAIN * 1e3, color=col, lw=lw, label=f"M {f['M']}")
        if f["fith"]:
            rinf, tau, rms, fn, par = f["fith"]
            t0 = f["t2"] + FIT_FROM
            x = np.linspace(s["c"][-1], X1, 200)
            ax.plot(x * 1e3, fn(x - t0, *par) * 1e3, color=col, lw=1.0, ls=(0, (3, 2)))
            ax.text(X1 * 1e3 + 0.1, rinf * 1e3, f"M {f['M']}: {rinf * 1e3:+.2f} mV", fontsize=7.4, color=INK2,
                    va="center")
    g99, g100 = F.get("G99"), F.get("G100")
    if g99 and g100:                                     # one step of M, as the host reads it after settling
        y0, y1 = g100["fith"][0] * 1e3, g99["fith"][0] * 1e3
        xs = 14.6
        ax.annotate("", xy=(xs, y1), xytext=(xs, y0), arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.8))
        ax.text(xs - 0.12, 0.5 * (y0 + y1), f"one step of M:\n{y1 - y0:.2f} mV\n(0.30 mV with\n100 Ω legs)",
                fontsize=7.2, color=INK2, ha="right", va="center")
    ax.axhline(0, color=LIGHT, lw=0.7)
    ax.axvline(10.0, color=LIGHT, lw=0.7, ls=(0, (1, 2)))
    ax.text(10.05, 0.02, "the runs end;\nfits carried on", transform=ax.get_xaxis_transform(), fontsize=7.2,
            color=MUTED, va="bottom")
    ax.set_xlim(6.9, X1 * 1e3)
    ax.set_ylim(-2.1, 3.6)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("ADC input / 297.5: the AFE's input as the host reads it (mV)")
    ax.legend(loc="lower left", bbox_to_anchor=(0.01, 0.1), fontsize=7.2)
    ax.set_title("After the 1 ms pulse: only M 100 settles inside the range, M 99 at its edge;\nin range the electrode "
                 f"relaxes with 51 k × 47 n = {R_E * C_E * 1e3:.1f} ms" + (" (M 98–100 running)" if interim else ""),
                 loc="left")

    # (e) the runs
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    head = ["", "M", "AFE_RST\nagain", "CHOP_EN\nin resets", "Settled pins\nat the write", "Settled pins\nat the release",
            "AFE input\nat the release", "In range", "At the end:\nAFE input", "ADC input\nat the end",
            "ADC input\nsettles at (fit)", "Current\ninto ELP"]
    rows, colours = [], []
    for k, tail, lab, col, ls, lw, panels in RUNS:
        mag = tail.split("_m")[1].split("_")[0]
        pulse = "1 ms" if "rst1000us" in tail else "100 µs"
        hold = "low" if "chophold" in tail else "running"
        leg = "100 Ω legs" if ZP not in tail else "51 k || 47 n"
        if k not in F:
            rows.append([f"{k}: {leg}", mag, pulse, hold, "running", "", "", "", "", "", "", ""])
        else:
            f = F[k]
            bk = ("not by the end" if f["back"] is None else
                  ("at the release" if f["back"] < 1e-6 else f"{f['back'] * 1e3:.2f} ms after the release"))
            settle = "" if f["fith"] is None else f"{f['fith'][0] * GAIN:+.3f} V (τ {f['fith'][1] * 1e3:.2f} ms)"
            if f["fith"] is not None and f["back"] is not None and abs(f["fith"][0] * GAIN) > 0.98 * ADC_FS:
                bk += "; ends at edge"
            rows.append([f"{k}: {leg}", mag, pulse, hold, f"{f['pw'] * 1e3:.1f} mV", f"{f['prel'] * 1e3:.1f} mV",
                         f"{f['rrel'] * 1e3:+.2f} mV", bk, f"{f['rend'] * 1e3:+.2f} mV ({f['tend'] * 1e3:.1f} ms)",
                         f"{f['voend']:+.3f} V", settle, f"{f['iend'] * 1e6:.2f} µA"])
        colours.append(col)
    tb = ax.table(cellText=rows, colLabels=head, loc="center", cellLoc="center", colLoc="center",
                  colWidths=[0.11, 0.035, 0.06, 0.07, 0.08, 0.08, 0.08, 0.15, 0.1, 0.07, 0.11, 0.065])
    tb.auto_set_font_size(False)
    tb.set_fontsize(7.6)
    tb.scale(1, 1.28)
    for (r, cc), cell in tb.get_celld().items():
        cell.set_edgecolor("#e2e8f0")
        if r == 0:
            cell.set_height(cell.get_height() * 1.8)
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

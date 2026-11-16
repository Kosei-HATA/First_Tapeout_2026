#!/usr/bin/env python3
"""Figure 39 (r12, 11/16): the first power-on with an electrode DC offset, as the host procedure runs it
(gf180_electrode_dc_20261022.md, "使い方"): AFE_RST released at 5 ms with the offset DAC off, so the AFE saturates; the
host writes the DAC's range and M with BLANK 15 at 6.0 ms (afe_saturation.py). Against figure 27's runs (the DAC
written before the release), and with the host re-asserting AFE_RST for 20 us or 100 us after the write
(afe_saturation.py --rst-pulse), where those runs exist; the 100 us restart also at ss.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/saturation_fig.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
FCH = 32.768e6 / 256
TCH = 1 / FCH
TEAL, PLUM, AMBER, BLUE = "#0d9488", "#a21caf", "#b45309", "#1f5aa8"
ADC_FS = 0.484                                   # DAC1 full scale at the ADC's input (V, differential)
COLS = ["qo", "outp_adc", "outn_adc", "inp", "inn", "opi", "oni", "vcm_afe"]
CASES = [(30, 100, BLUE), (300, 997, PLUM)]
MAG = {vin: mag for vin, mag, _ in CASES}
KINDS = {"sat": "_sat6ms", "rst": "_sat6ms_rst20us", "rst100": "_sat6ms_rst100us", "long": "_sat6ms_to11ms", "ref": ""}
RCOL = {"rst": TEAL, "rst100": AMBER}
# the restarts (AFE_RST again after the write): offset (mV), kind, corner, colour, line style, label
RESTARTS = [(30, "rst", "typical", TEAL, (0, (1, 1.2)), "30 mV, 20 µs"),
            (300, "rst", "typical", TEAL, "-", "300 mV, 20 µs"),
            (300, "rst100", "typical", AMBER, "-", "300 mV, 100 µs"),
            (300, "rst100", "ss", ACCENT, "-", "300 mV, 100 µs, ss")]


def name(vin, kind, corner="typical"):
    return f"start_c1e-08_v3.3_{corner}_+{vin}mV_m{MAG[vin]}_afe5ms_ib3" + KINDS[kind] + f"_chip_{V.CHIP}"


def load(run):
    d = os.path.join(SU, run)
    if not os.path.exists(os.path.join(d, "tr.csv")):
        return None, None
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    names = meta["vectors"]
    keep = [0] + [2 * names.index(c) + 1 for c in COLS]
    df = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)
    x = df[keep].to_numpy()
    v = {c: x[:, i + 1] for i, c in enumerate(COLS)}
    v["t"] = x[:, 0]
    v["vo"] = v["outp_adc"] - v["outn_adc"]
    return v, meta


def chop_means(v, t0, t1):
    edges = t0 + TCH * np.arange(int((t1 - t0) / TCH) + 1)
    return 0.5 * (edges[1:] + edges[:-1]), np.diff(np.interp(edges, v["t"], v["qo"])) / TCH


def envelope(v, t0, t1, w=TCH / 2):
    """per half chopper period: (centres, min, max) of the instantaneous ADC input"""
    edges = t0 + w * np.arange(int((t1 - t0) / w) + 1)
    i = np.searchsorted(v["t"], edges)
    lo = np.array([v["vo"][a:b].min() if b > a else np.nan for a, b in zip(i[:-1], i[1:])])
    hi = np.array([v["vo"][a:b].max() if b > a else np.nan for a, b in zip(i[:-1], i[1:])])
    return 0.5 * (edges[1:] + edges[:-1]), lo, hi


def wmean(t, y, t0, t1):
    a = (t >= t0) & (t <= t1)
    return float(np.trapz(y[a], t[a]) / (t[a][-1] - t[a][0]))


def half_means(v, y, m, t0, t1):
    """means over the chopper's half periods, between its edges (RESET_N's release + k TCH/2): (centres, means)"""
    e0 = m["t_reset"] + TCH / 2 * np.ceil((t0 - m["t_reset"]) / (TCH / 2))
    e = e0 + TCH / 2 * np.arange(int((t1 - e0) / (TCH / 2)) + 1)
    return 0.5 * (e[1:] + e[:-1]), np.array([wmean(v["t"], y, a, b) for a, b in zip(e[:-1], e[1:])])


def after_release(v, m, t_rel):
    """chopper-period means of OUTP - OUTN after the (last) release: (time after it, mean)"""
    tc, mm = chop_means(v, m["t_reset"] + TCH / 4, v["t"][-1])
    a = tc > t_rel
    return tc[a] - t_rel, mm[a]


def reset_climb(v, t1, t2):
    """the input common mode during the pulse: (half-period centres from t1, half-period means, the level of the pulse's
    last 30 us, the time constant fitted while the gap to that level is 2 mV..0.25 V; None when the pulse is too short)"""
    cm = 0.5 * (v["inp"] + v["inn"])
    e = t1 + TCH / 2 * np.arange(int(round((t2 - t1) / (TCH / 2))) + 1)
    x = 0.5 * (e[1:] + e[:-1]) - t1
    h = np.array([wmean(v["t"], cm, a, b) for a, b in zip(e[:-1], e[1:])])
    if t2 - t1 < 60e-6:
        return x, h, None, None
    lvl = h[x > t2 - t1 - 30e-6].mean()
    gap = (lvl - h) * np.sign(lvl - h[0])
    k = (gap > 2e-3) & (gap < 0.25)
    tau = -1 / np.polyfit(x[k], np.log(gap[k]), 1)[0] if k.sum() >= 3 else None
    return x, h, lvl, tau


def back_in_range(v, t0):
    """from when on the instantaneous ADC input stays inside the ADC's range (None if not for the last two chopper
    periods of the run)"""
    a = v["t"] > t0
    bad = np.nonzero(a & (np.abs(v["vo"]) > ADC_FS))[0]
    if not len(bad):
        return 0.0
    return None if v["t"][-1] - v["t"][bad[-1]] < 2 * TCH else v["t"][bad[-1] + 1] - t0


def main():
    runs = {(vin, kind, "typical"): load(name(vin, kind)) for vin, _, _ in CASES for kind in KINDS if kind != "rst100" or vin == 300}
    runs[300, "rst100", "ss"] = load(name(300, "rst100", "ss"))
    have = {k for k, (v, m) in runs.items() if v is not None}
    interim = any((vin, kind, c) not in have for vin, kind, c, *_ in RESTARTS) or (300, "long", "typical") not in have

    def R(vin, kind, corner="typical"):
        return runs.get((vin, kind, corner), (None, None))

    fig = V.figure(12.8, 14.0, "First power-on with an electrode offset: saturated, then the DAC written" +
                   (" (interim)" if interim else ""),
                   "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires, power-on · "
                   "typical (one restart also at ss), 27 °C · RESET_N at 4.8 ms, AFE_IBIAS = 3 at 4.82 ms, AFE_RST released "
                   "at 5 ms with the offset DAC off (BLANK 7 MCLK) · electrodes 100 Ω per leg",
                   note="The host's write at 6.0012 ms (the middle of a chopper half period): the DAC's range and M "
                        "(30 mV: range 1, M 100; 300 mV: range 4, M 997) with BLANK 15 MCLK. Figure 27's runs write the same "
                        "code before the release. 'AFE_RST again': the host then sets CONTROL[4] for 20 µs (6.027–6.047 ms) "
                        "or 100 µs (6.025–6.125 ms) and clears it at the chopper phase of the first release. The ADC is its "
                        "input resistors into a virtual ground here; its range is DAC1's full scale, ±0.484 V differential "
                        "(figure 40 for the ADC itself). Chopper-period means are what the CIC sees once the ADC is in range. "
                        "With the DAC off, the chopped electrode offset steps INP and INN every half period even in reset "
                        "(1.08–1.52 V at 300 mV, against 1.59–1.67 V with the DAC on), and their common mode settles low; "
                        "once the AFE is released, only the DC path (two switched capacitors, about 72 MΩ to the outputs) "
                        "moves it. VCM_AFE has 10 nF on the board.")
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 0.5])

    # (a) chopper-period means
    ax = fig.add_subplot(gs[0, 0])
    for vin, mag, col in CASES:
        for kind, ls, lw in (("sat", "-", 1.3), ("long", "-", 1.3), ("ref", (0, (4, 2)), 1.0), ("rst", "-", 0.9),
                             ("rst100", "-", 0.9)):
            v, m = R(vin, kind)
            if v is None or (kind == "sat" and (vin, "long", "typical") in have):
                continue
            tc, mm = chop_means(v, m["t_reset"] + TCH / 4, v["t"][-1])
            a = tc > (m["afe_rst_again"][0] if kind in RCOL else 4.9e-3)   # a restart run: from the re-assertion
            ax.plot(tc[a] * 1e3, mm[a], color=RCOL.get(kind, col), ls=ls, lw=lw)
    ax.axvline(6.0012, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(6.02, 0.97, "the host's write", transform=ax.get_xaxis_transform(), fontsize=7.6, color=MUTED, va="top")
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("OUTP − OUTN, chopper-period mean (V)")
    ax.set_title("What the CIC would see: the mean falls to about 0 V at the write", loc="left")
    for vin, mag, col in CASES:
        ax.plot([], [], color=col, lw=1.3, label=f"{vin} mV, saturated first")
    ax.plot([], [], color=INK2, ls=(0, (4, 2)), lw=1.0, label="figure 27 (DAC before the release)")
    for kind, lab in (("rst", "AFE_RST again after the write, 20 µs"), ("rst100", "AFE_RST again, 100 µs (300 mV)")):
        if any(k[1] == kind and k[2] == "typical" for k in have):
            ax.plot([], [], color=RCOL[kind], lw=0.9, label=lab)
    ax.legend(loc="upper right", fontsize=7.4)

    # (b) the instantaneous ADC input: envelope per half chopper period
    ax = fig.add_subplot(gs[0, 1])
    ax.axhspan(-ADC_FS, ADC_FS, color=ACCENT, alpha=0.07, lw=0)
    ax.text(4.92, ADC_FS * 1.05, "the ADC's range", fontsize=7.4, color=ACCENT, va="bottom")
    for vin, mag, col in CASES:
        v, m = R(vin, "long") if (vin, "long", "typical") in have else R(vin, "sat")
        tc, lo, hi = envelope(v, 4.9e-3, v["t"][-1])
        ax.fill_between(tc * 1e3, lo, hi, color=col, alpha=0.35, lw=0)
        ax.plot([], [], color=col, lw=6, alpha=0.35, label=f"{vin} mV: per half chopper period, lowest to highest")
    ax.axvline(6.0012, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("OUTP − OUTN at the ADC, instantaneous (V)")
    ax.legend(loc="lower right", fontsize=7.4)
    ax.set_title("What the ADC sees: the amplifier stays saturated\nbehind the output chopper (±1.2–1.5 V square wave)",
                 loc="left")

    # (c) the amplifier's input nodes
    ax = fig.add_subplot(gs[1, 0])
    for vin, mag, col in CASES:
        v, m = R(vin, "long") if (vin, "long", "typical") in have else R(vin, "sat")
        d = v["inp"] - v["inn"]
        tc, mm = chop_means(dict(t=v["t"], qo=np.concatenate([[0.0], np.cumsum(0.5 * (d[1:] + d[:-1]) * np.diff(v["t"]))])),
                            4.9e-3, v["t"][-1])
        ax.plot(tc * 1e3, mm * 1e3, color=col, lw=1.3, label=f"{vin} mV")
    ax.axvline(6.0012, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.axhline(0, color=LIGHT, lw=0.8)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("INP − INN, chopper-period mean (mV)")
    ax.legend(loc="lower right", fontsize=7.6)
    ax.set_title("The amplifier's inputs, unregulated while it is saturated:\nthe charge leaves only through the DC path",
                 loc="left")

    # (d) the input common mode from power-on
    ax = fig.add_subplot(gs[1, 1])
    drop = {}
    for vin, mag, col in CASES:
        v, m = R(vin, "long") if (vin, "long", "typical") in have else R(vin, "sat")
        a = v["t"] > 4.9e-3
        cm = 0.5 * (v["inp"] + v["inn"])
        ax.plot(v["t"][a][::20] * 1e3, cm[a][::20], color=col, lw=1.1, label=f"{vin} mV, saturated first")
        vr, mr = R(vin, "ref")
        if vr is not None:
            cmr = 0.5 * (vr["inp"] + vr["inn"])
            ar = vr["t"] > 4.9e-3
            ax.plot(vr["t"][ar][::20] * 1e3, cmr[ar][::20], color=col, lw=0.9, ls=(0, (4, 2)))
            ref = cmr[vr["t"] > vr["t"][-1] - 0.1e-3].mean()
            sat = cm[(v["t"] > 5.5e-3) & (v["t"] < m["t_dac"])].mean()
            end = cm[(v["t"] > 7.9e-3) & (v["t"] < 8.0e-3)].mean()
            drop[vin] = (ref - sat, ref - end)
        for kind in RCOL:
            rv, rm = R(vin, kind)
            if rv is not None:
                ar = rv["t"] > rm["afe_rst_again"][0]
                ax.plot(rv["t"][ar][::20] * 1e3, (0.5 * (rv["inp"] + rv["inn"]))[ar][::20], color=RCOL[kind], lw=0.9)
    ax.plot([], [], color=INK2, lw=0.9, ls=(0, (4, 2)), label="figure 27 (DAC before the release)")
    for kind, lab in (("rst", "AFE_RST again, 20 µs"), ("rst100", "AFE_RST again, 100 µs")):
        if any(k[1] == kind and k[2] == "typical" for k in have):
            ax.plot([], [], color=RCOL[kind], lw=0.9, label=lab)
    ax.axvline(6.0012, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("(INP + INN) / 2 (V)")
    ax.legend(loc="lower right", fontsize=7.4)
    d3 = drop.get(300)
    ax.set_title("The amplifier's input common mode against figure 27:\n" +
                 (f"{d3[0]:.2f} V low already in reset at 300 mV, still {d3[1]:.2f} V low at 8 ms" if d3 else ""), loc="left")

    # (e) the pulse itself: the input common mode climbs to its reset level
    ax = fig.add_subplot(gs[2, 0])
    climb = {}
    for vin, kind, c, col, ls, lab in RESTARTS:
        v, m = R(vin, kind, c)
        if v is None:
            continue
        t1, t2 = m["afe_rst_again"]
        xc, hc = half_means(v, 0.5 * (v["inp"] + v["inn"]), m, t1 - 15e-6, t1 + 335e-6)
        ax.plot((xc - t1) * 1e6, hc, color=col, ls=ls, lw=1.3, label=lab)
        if vin == 300:
            xv, hv = half_means(v, v["vcm_afe"], m, t1 - 15e-6, t1 + 335e-6)
            ax.plot((xv - t1) * 1e6, hv, color=col, ls=(0, (3, 1.6)), lw=0.8)
        ax.axvline((t2 - t1) * 1e6, color=col, lw=0.7, ls=(0, (1, 2.5)))
        xh, h, lvl, tau = reset_climb(v, t1, t2)
        climb[(vin, kind, c)] = dict(end=h[-1], lvl=lvl, tau=tau)
    vr, mr = R(300, "ref")
    if vr is not None:
        cr = wmean(vr["t"], 0.5 * (vr["inp"] + vr["inn"]), mr["t_afe"] - 8 * TCH, mr["t_afe"])
        vc = wmean(vr["t"], vr["vcm_afe"], mr["t_afe"] - 8 * TCH, mr["t_afe"])
        for y in (cr, vc):
            ax.axhline(y, color=INK2, lw=0.8, ls=(0, (6, 3)), alpha=0.8)
    ax.plot([], [], color=INK2, lw=0.8, ls=(0, (3, 1.6)), label="VCM_AFE (300 mV runs)")
    if vr is not None:
        ax.plot([], [], color=INK2, lw=0.8, ls=(0, (6, 3)), alpha=0.8,
                label=f"figure 27 at its release (300 mV):\ninput CM {cr:.3f} V, VCM_AFE {vc:.3f} V")
    ax.set_xlim(-15, 330)
    ax.set_ylim(1.27, 1.71)
    ax.set_xlabel("Time from AFE_RST going high again (µs); dotted: its release")
    ax.set_ylabel("(INP + INN) / 2, solid, and VCM_AFE, dashed:\nhalf-chopper-period means (V)")
    ax.legend(loc="lower right", fontsize=7.2)
    t100 = climb.get((300, "rst100", "typical"), {})
    t20 = climb.get((300, "rst", "typical"), {})
    tss = climb.get((300, "rst100", "ss"), {})
    if t100.get("tau"):
        ttl = (f"In reset the input common mode climbs to {t100['lvl']:.3f} V (300 mV; τ {t100['tau'] * 1e6:.0f} µs" +
               (f", ss {tss['tau'] * 1e6:.0f} µs" if tss.get("tau") else "") + ")")
        if t20:
            ttl += f":\n20 µs leaves it {1e3 * (t100['lvl'] - t20['end']):.0f} mV short, and after the release only the DC path moves it"
    else:
        ttl = "The pulse: the input common mode in reset"
    ax.set_title(ttl, loc="left")

    # (f) the output after the release against figure 27 at the same time after its release
    ax = fig.add_subplot(gs[2, 1])
    dlt = {}
    for vin, kind, c, col, ls, lab in RESTARTS:
        v, m = R(vin, kind, c)
        vr, mr = R(vin, "ref")
        if c != "typical" or v is None or vr is None:
            continue
        x, mm = after_release(v, m, m["afe_rst_again"][1])
        xr, mmr = after_release(vr, mr, mr["t_afe"])
        a = x <= xr[-1]
        d = (mm[a] - np.interp(x[a], xr, mmr)) * 1e3
        ax.plot(x[a] * 1e3, d, color=col, ls=ls, lw=1.3, label=lab)
        xa = x[a]
        ax.annotate(f"{d[-8:].mean():+.2f} mV".replace("-", "−"), (xa[-1] * 1e3, d[-8:].mean()), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=7.4, color=col)
        dlt[lab] = dict(t_end=xa[-1], d_end=d[-8:].mean(), d15=d[(xa > 1.5e-3 - 8 * TCH) & (xa <= 1.5e-3)].mean(),
                        slope=(d[-8:].mean() - d[(xa > xa[-1] - 0.5e-3 - 8 * TCH) & (xa <= xa[-1] - 0.5e-3)].mean()) / 0.5)
    ax.axhline(0, color=LIGHT, lw=0.9)
    ax.set_ylim(-2.4, 1.4)
    ax.set_xlim(-0.05, 2.85)
    ax.text(0.03, 0.97, "the first points after the release, up to about 15 mV, are off the axis", transform=ax.transAxes,
            fontsize=7, color=MUTED, va="top")
    ax.set_xlabel("Time from the (last) release (ms)")
    ax.set_ylabel("OUTP − OUTN, chopper-period mean,\nminus figure 27's (mV)")
    ax.legend(loc="lower right", fontsize=7.4)
    q20, q100 = dlt.get("300 mV, 20 µs"), dlt.get("300 mV, 100 µs")
    ttl = "The output minus figure 27's, at the same time after the release"
    if q20 and q100:
        def how(q):
            return "and moving away" if q["slope"] * q["d_end"] > 0 else "and closing"
        ttl += (f":\n300 mV: 20 µs leaves {q20['d_end']:+.1f} mV {how(q20)}, 100 µs {q100['d_end']:+.1f} mV {how(q100)}"
                ).replace("-", "−")
    ax.set_title(ttl, loc="left")

    # (g) the numbers
    ax = fig.add_subplot(gs[3, :])
    ax.set_axis_off()
    left = ["Back inside the ADC's range (instantaneous, for good), from the write:"]
    for vin, mag, col in CASES:
        for kind, c, lab in (("sat", "typical", "no restart"), ("long", "typical", "no restart, to 11 ms"),
                             ("rst", "typical", "AFE_RST again, 20 µs"), ("rst100", "typical", "AFE_RST again, 100 µs"),
                             ("rst100", "ss", "AFE_RST again, 100 µs, ss")):
            v, m = R(vin, kind, c)
            if v is None or (kind == "sat" and (vin, "long", "typical") in have):
                continue
            tb = back_in_range(v, m["t_dac"])
            extra = ""
            if tb is not None and m.get("afe_rst_again"):
                extra = f" ({(m['t_dac'] + tb - m['afe_rst_again'][0]) * 1e6:.1f} µs after AFE_RST went high)"
            left.append(f"  {vin} mV, {lab}: " + (f"{tb * 1e3:.3f} ms{extra}" if tb is not None else
                                                    f"not by {(v['t'][-1] - m['t_dac']) * 1e3:.1f} ms"))
    right = ["After AFE_RST again, 1.5 ms after the release (figure 27 at the same time):"]
    gain = {}
    for vin, kind, c, col, ls, lab in RESTARTS:
        v, m = R(vin, kind, c)
        vr, mr = R(vin, "ref")
        if v is None or c != "typical" or vr is None:
            continue
        t2 = m["afe_rst_again"][1]
        cm = wmean(v["t"], 0.5 * (v["inp"] + v["inn"]), t2 + 1.5e-3 - 8 * TCH, t2 + 1.5e-3)
        cmr = wmean(vr["t"], 0.5 * (vr["inp"] + vr["inn"]), mr["t_afe"] + 1.5e-3 - 8 * TCH, mr["t_afe"] + 1.5e-3)
        q = dlt.get(lab)
        right.append(f"  {lab}: input CM {cm:.3f} V ({cmr:.3f} V), output {q['d15']:+.2f} mV"
                     .replace("-", "−") if q else f"  {lab}: input CM {cm:.3f} V ({cmr:.3f} V)")
        if q and abs(cm - cmr) > 2e-3:
            gain.setdefault(vin, []).append(q["d15"] * 1e-3 / (cm - cmr))
    if gain:
        right.append("  The output follows the input CM through the DAC's charge, in proportion to M:")
        right.append("  " + ", ".join(f"{np.mean(g) * 1e3:.0f} mV/V at {vin} mV (M {MAG[vin]})" for vin, g in sorted(gain.items())) +
                     " at the AFE output")
    vs, ms_ = R(300, "rst100", "ss")
    if vs is not None:
        x, mm = after_release(vs, ms_, ms_["afe_rst_again"][1])
        fin = mm[-16:].mean()
        bad = np.nonzero(np.abs(mm - fin) >= 1e-4)[0]
        t01 = x[bad[-1] + 1] if len(bad) and bad[-1] + 1 < len(x) else None
        right.append((f"  300 mV, 100 µs, ss (no figure 27 at ss): output {fin * 1e3:.2f} mV at {x[-1] * 1e3:.1f} ms, within "
                      f"0.1 mV of it from " + (f"{t01 * 1e3:.2f} ms" if t01 is not None else "–")).replace("-", "−"))
        right.append(f"    M {MAG[300]} is typical's: at ss it leaves about {abs(fin) / (0.99 * 287.0) * 1e3:.1f} mV at the input "
                     "(−0.50 V between the blanks), so the host's\n    search moves M (step 2 of the procedure), "
                     "each write with the 100 µs pulse")
    else:
        right.append("  300 mV, 100 µs at ss: running")
    ax.text(0.0, 0.98, "\n".join(left), transform=ax.transAxes, va="top", fontsize=8.6, color=INK, linespacing=1.55)
    ax.text(0.44, 0.98, "\n".join(right), transform=ax.transAxes, va="top", fontsize=8.6, color=INK, linespacing=1.55)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_39_saturated_start.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

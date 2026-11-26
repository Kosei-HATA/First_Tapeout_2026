#!/usr/bin/env python3
"""Figure 57 (r14, 11/25): the digital side of the 14th chip against the 13th in the chip-level supply-noise deck
(gf180/tapeout/pex/digital_noise.py, case S). One deck holds three copies of chunk 14 of the 12th chip's chain (AFE and
ADC running, electrode 0.3 mV DC + 0.5 mV 16 kHz): A without the digital side, r13 and r14 with their macros' charge
per MCLK edge (gf180/tapeout/digital/power/current_profile.py), their own VDD-VSS capacitance (cell_decap.py) and
their chip-level DVDD / DVSS (supply_check.py), all solved on the same time points.
  (a) the charge per MCLK edge over a modulator frame: eeg_digital_top of r13 and r14 (rising edges by frame cycle,
      falling edges), eeg_adc_dig (the same macro in both chips)
  (b) the pad ring's DVDD over a frame
  (c) the macros' own supply (DVDD - DVSS at each macro)
  (d) the common mode at the AFE's input, copy - A
  (e) the AFE output per chopper period, copy - A, r14 - r13 and A - the chain's own chunk (the same circuit in another
      deck: the floor of comparing separate decks), electrode-referred, with offset + 16 kHz tone fitted (± its standard
      error), only once the window holds four periods or more
Data: gf180/tapeout/pex/runs/digital_noise_r12/S/ (out.raw, compare.json from `digital_noise.py --chain r12 compare
S`; git-ignored), gf180/tapeout/digital/power/build/current_profile.json, build/r14/current_profile.json,
build/cell_decap_r13.json, build/cell_decap_r14.json (git-ignored). While the run is going the figure is labelled
interim with the simulated length.
Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_digital_noise_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import HAIR, LIGHT, MUTED  # noqa: E402

V.CHIP, V.CHIP_DATE = "r14", "20261124"
V.CHIP_LABEL = "Chip r14 (fourteenth assembly, 24 Nov 2026)"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "pex"))
import digital_noise as dn  # noqa: E402

dn.use_chain("r12")
SDIR = os.path.join(dn.RUNS, "S")
POWER = os.path.join(REPO, "gf180", "tapeout", "digital", "power", "build")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
COL = {"A": LIGHT, "r13": "#64748b", "r14": "#0d9488", "d": "#4f46e5", "adc": "#cbd5e1", "num": "#a1a1aa"}
LAB = {"A": "A: no digital side", "r13": "13th chip (r13 macro, 4.36 mA)", "r14": "14th chip (r14 macro, 6.99 mA)"}
LW = {"A": 0.9, "r13": 1.0, "r14": 1.5}  # r14 the widest and lowest, so r13 (smaller swings) shows on top of it
Z = {"A": 4, "r13": 3, "r14": 2}
LSB_DATA = 1 / (306.6 * 2 ** 24)       # V at the electrode per LSB of DATA (figs_perf.LSB_DATA)


def minus(s):
    return s.replace("-", "−")


def nv(x, d=2):
    """a signed value with d decimals, a zero without its sign"""
    s = f"{x:+.{d}f}"
    return minus(s if float(s) else f"{0:.{d}f}")


def main():
    V.apply()
    res = json.load(open(os.path.join(SDIR, "compare.json")))
    copies = res["copies"]
    R = dn.load_same(copies)
    t = R["A"]["time"]
    status = open(os.path.join(SDIR, "status.txt")).read() if os.path.exists(os.path.join(SDIR, "status.txt")) else ""
    done = "exit 0" in status and res["tend_us"] > 47.2
    text = open(os.path.join(dn.BASE, "tb.spice")).read()
    e0, TF = dn.frame_e0(text), dn.TF
    prof = {"r13": json.load(open(os.path.join(POWER, "current_profile.json"))),
            "r14": json.load(open(os.path.join(POWER, "r14", "current_profile.json")))}
    dec = {"r13": json.load(open(os.path.join(POWER, "cell_decap_r13.json"))),
           "r14": json.load(open(os.path.join(POWER, "cell_decap_r14.json")))}
    ca, df = res["cases"], res["diff"]
    # a frame 20 us into the window (or the last whole one so far): its first cycles are where the ADC's digital draws most
    fs = e0 + np.floor((min(20e-6, t[-1] - 0.5e-6) - e0) / TF) * TF
    w0, w1 = fs - 30e-9, fs + 280e-9
    tg = np.arange(w0, w1, 2e-12)
    x = (tg - fs) * 1e9

    def on(c, name):
        r = R[c]
        m = (r["time"] > w0 - 1e-8) & (r["time"] < w1 + 1e-8)
        return np.interp(tg, r["time"][m], r[name][m])

    nP = len(res["periods_us"])
    fitted = nP >= 4                     # offset + tone (3 unknowns) only with a period to spare
    off = {k: nv(df[k]["fit"]["offset_nV"]) + (f" ± {df[k]['fit']['offset_se_nV']:.2f}" if fitted else "")
           for k in ("r13-A", "r14-A", "r14-r13")}
    state = ("" if done else f" — interim, {res['tend_us']:.1f} of 47.3 µs")
    if fitted:
        say = (f"The coupling leaves a constant offset of {off['r13-A']} nV (r13) and {off['r14-A']} nV (r14) at the "
               f"electrode, locked to MCLK; r14 − r13 {off['r14-r13']} nV, about "
               f"{df['r14-r13']['fit']['offset_nV'] / (LSB_DATA * 1e9):.1f} LSB of DATA ({LSB_DATA * 1e9:.2f} nV)."
               + (f" The same circuit in another deck (A against the chain's own chunk) differs by "
                  f"{nv(df['A-chain']['fit']['offset_nV'])} nV, hence one deck." if "A-chain" in df else ""))
    else:
        per = {k: ", ".join(minus(f"{v * 1e3:+.2f}") for v in df[k]["electrode_uV"]) for k in ("r13-A", "r14-A")}
        say = (f"So far {nP} whole chopper period{'s' if nP > 1 else ''}: r13 − A {per['r13-A']} nV, r14 − A "
               f"{per['r14-A']} nV at the electrode per period (DATA's LSB {LSB_DATA * 1e9:.2f} nV); offset and tone are "
               "fitted once the window holds its five periods.")
    fig = V.figure(
        13.4, 12.6, "The digital side of the 14th chip against the 13th: supply current, rails and the AFE" + state,
        "Three copies of chunk 14 of the 12th chip's chain in one deck, on the same time points: A without the digital "
        "side, r13 and r14 with their macros' charge per MCLK edge, own VDD–VSS capacitance and chip-level DVDD / DVSS. "
        + say,
        note="Chain: power-on to CIC of the 12th chip (afe_top and eeg_adc of r12's extraction on its chip nets; the 13th "
             "and 14th chips' AFE differs only in INN's Metal4 blankets), chunk 14 = 6.17 ms from power-on, typical, "
             "27 °C, 47.3 µs. Current per edge: OpenSTA with the gate-level activity of 1 ms of RUN (10/29 r13, 11/24 "
             "r14), split over the edges by the liberty's clock energy, the clock tree's polarity and the data nets' "
             "switching; each a 2 ns triangle. Own capacitance: the cells (PDK netlists, ngspice AC) + the n-well from "
             "the GDS. Chip-level DVDD / DVSS from each chip's supply check. Nine bi_24t pads, bond wires, board; the "
             "electrodes 100 Ω. Electrode-referred = AFE output / "
             f"{dn.GAIN:g}; periods start a quarter period after each CHOP falling edge; the fit takes the 16 kHz tone "
             f"({res['tone']['out_uV'] / 1e3:.1f} mV at the AFE output) out of each difference. Not in it: the ring's "
             "resistance (one node, so the coupling is on the large side), the substrate between DVSS and AVSS, "
             "glitches (zero-delay activity). digital_noise.py --chain r12 S, r14_digital_noise_fig.py.")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.2])
    # (a) the charge per edge
    ax = fig.add_subplot(gs[0, 0])
    cyc = np.arange(32)
    qa = np.array(prof["r13"]["eeg_adc_dig"]["q_rise_pC"])
    ax.bar(cyc, qa, 0.8, color=COL["adc"], label=f"eeg_adc_dig, rising (the same macro in both; falling "
                                                  f"{prof['r13']['eeg_adc_dig']['q_fall_pC']:.0f} pC)")
    for v in ("r13", "r14"):
        p = prof[v]["eeg_digital_top"]
        ax.step(np.r_[cyc, 32] - 0.5, np.r_[p["q_rise_pC"], p["q_rise_pC"][-1]], where="post", color=COL[v], lw=1.6,
                label=f"eeg_digital_top {v}, rising (mean {np.mean(p['q_rise_pC']):.1f} pC)")
        ax.axhline(p["q_fall_pC"], color=COL[v], lw=1.1, ls=(0, (4, 2)),
                   label=f"eeg_digital_top {v}, falling ({p['q_fall_pC']:.1f} pC)")
    ax.set_xlim(-0.6, 31.6)
    ax.set_ylim(0, 205)
    ax.set_xlabel("Frame cycle (0 = CMP_STROBE high)")
    ax.set_ylabel("Charge per MCLK edge (pC)")
    i13, i14 = (prof[v]["eeg_digital_top"]["I_avg_mA"] for v in ("r13", "r14"))
    ax.set_title(f"(a) Charge per MCLK edge: eeg_digital_top {i13:.2f} mA (r13), {i14:.2f} mA (r14); clock tree "
                 f"{prof['r13']['eeg_digital_top']['C_clock_pF']['rise']:.1f} and "
                 f"{prof['r14']['eeg_digital_top']['C_clock_pF']['rise']:.1f} pF", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=6.9, ncol=1)
    # (b) the pad ring
    ax = fig.add_subplot(gs[0, 1])
    big = 0.0
    for c in copies:
        y = (on(c, "v(dvddc)") - 3.3) * 1e3
        big = max(big, np.max(np.abs(y)))
        ax.plot(x, y, color=COL[c], lw=LW[c], zorder=Z[c],
                label=f"{LAB[c]}: {ca[c]['ring_vdd_pp_mV']:.0f} mV p-p (DVSS {ca[c]['ring_vss_pp_mV']:.0f})")
    ax.set_ylim(-1.75 * big, 1.15 * big)
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel("Time from a frame start (ns)")
    ax.set_ylabel("Ring DVDD − 3.3 V (mV)")
    ax.set_title("(b) Pad ring DVDD over a frame", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.2)
    # (c) the macros' own supply
    ax = fig.add_subplot(gs[1, 0])
    for v in ("r13", "r14"):
        if v not in ca:
            continue
        b = ca[v]
        cdig = dec[v]["eeg_digital_top"]["C_total_pF"]
        ax.plot(x, (on(v, "v(dvdd_add)") - on(v, "v(dvss_add)") - 3.3) * 1e3, color=COL[v], lw=1.0, ls=(0, (3, 1.5)),
                zorder=Z[v], label=f"{v} ADC's digital: {b['add_pp_mV']:.0f} mV p-p, mean "
                                   + minus(f"{b['add_mean_mV'] - 3300:+.1f} mV"))
        ax.plot(x, (on(v, "v(dvdd_dig)") - on(v, "v(dvss_dig)") - 3.3) * 1e3, color=COL[v], lw=LW[v], zorder=Z[v],
                label=f"{v} digital block ({cdig:.0f} pF own): {b['dig_pp_mV']:.0f} mV p-p, mean "
                      + minus(f"{b['dig_mean_mV'] - 3300:+.1f} mV"))
    ax.set_xlim(x[0], x[-1])
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo - 0.55 * (hi - lo), hi)
    ax.set_xlabel("Time from a frame start (ns)")
    ax.set_ylabel("DVDD − DVSS − 3.3 V at the macro (mV)")
    ax.set_title("(c) The macros' own supply (chip-level DVDD / DVSS: r13 0.192 / 1.118 Ω, r14 0.184 / 1.081 Ω)",
                 fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.0)
    # (d) the AFE's input common mode, copy - A
    ax = fig.add_subplot(gs[1, 1])
    ax.axhline(0, color=HAIR, lw=0.9, zorder=0)
    cm = {c: (on(c, "v(elp)") + on(c, "v(eln)")) / 2 for c in copies}
    big = 0.0
    for v in ("r13", "r14"):
        y = (cm[v] - cm["A"]) * 1e3
        big = max(big, np.max(np.abs(y)))
        inp = df[f"{v}-A"].get("input", {})
        ax.plot(x, y, color=COL[v], lw=LW[v], zorder=Z[v],
                label=f"{v} − A: {inp.get('cm_pp_mV', np.nan):.2f} mV p-p over the window; differential "
                      f"{inp.get('diff_pp_uV', np.nan):.2f} µV p-p away from the CHOP edges")
    ax.set_ylim(-1.15 * big, 1.8 * big)
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel("Time from a frame start (ns)")
    ax.set_ylabel("mV")
    ax.set_title("(d) Common mode at the AFE's input, copy − A", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=7.0)
    # (e) the AFE output per chopper period
    ax = fig.add_subplot(gs[2, :])
    P = np.array(res["periods_us"]) * 1e-6
    mid = P.mean(axis=1) * 1e6
    ax.axhline(0, color=HAIR, lw=0.9)
    pairs = (("r13-A", "13th chip − A: the coupling of r13", COL["r13"], "o"),
             ("r14-A", "14th chip − A: the coupling of r14", COL["r14"], "D"),
             ("r14-r13", "14th − 13th chip", COL["d"], "s"),
             ("A-chain", "A − the chain's own chunk 14: the same circuit in another deck (numerical)", COL["num"], "x"))
    pairs = tuple(p for p in pairs if p[0] in df)
    pts = np.concatenate([np.array(df[p]["electrode_uV"]) * 1e3 for p, *_ in pairs])
    lo, hi = min(-0.6, 1.2 * pts.min()), max(0.8, 1.2 * pts.max())
    hi += 0.45 * (hi - lo)                      # room over the points for the legend
    for s in range(int(np.ceil(lo / (LSB_DATA * 1e9))), int(np.floor(hi / (LSB_DATA * 1e9))) + 1):
        if s:
            ax.axhline(s * LSB_DATA * 1e9, color=HAIR, lw=0.6, ls=(0, (1, 2)), zorder=0)
    f, td = res["tone"]["f_Hz"], res["tone"]["td_s"]
    wt = 2 * np.pi * f
    tt = np.linspace(P[0, 0], P[-1, 1], 400)
    Sm = (np.cos(wt * (tt - dn.TCH / 2 - td)) - np.cos(wt * (tt + dn.TCH / 2 - td))) / wt / dn.TCH
    Cm = (np.sin(wt * (tt + dn.TCH / 2 - td)) - np.sin(wt * (tt - dn.TCH / 2 - td))) / wt / dn.TCH
    for pair, lab, colr, mk in pairs:
        d = df[pair]
        fz = d["fit"]
        if fitted:
            lab += (": offset " + nv(fz["offset_nV"], 3) + f" ± {fz['offset_se_nV']:.3f} nV, 16 kHz tone "
                    f"{fz['tone_ppm']:.2f} ppm, rest {fz['rest_nV_rms']:.3f} nV rms")
        else:
            lab += ": " + ", ".join(nv(v * 1e3, 3) for v in d["electrode_uV"]) + " nV (not yet fitted)"
        ax.plot(mid, np.array(d["electrode_uV"]) * 1e3, ls="none", marker=mk, ms=6.5, mfc="white", mew=1.5, color=colr,
                label=lab + f" (codes differ {d['codes_differ']}/{d['frames']})", zorder=3)
        if fitted:
            k1, k2 = fz["tone_uV"]
            ax.plot(tt * 1e6, fz["offset_nV"] + (k1 * Sm + k2 * Cm) / dn.GAIN * 1e3, color=colr, lw=1.0, alpha=0.8,
                    ls="-" if pair != "A-chain" else (0, (4, 2)))
    ax.set_xlim(0, 47.3)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Chopper period centre (µs into the window)")
    ax.set_ylabel("Electrode-referred (nV)")
    ax.set_title("(e) AFE output per chopper period, the difference (points) and offset + 16 kHz tone fitted (lines); "
                 f"dotted: steps of 1 LSB of DATA ({LSB_DATA * 1e9:.2f} nV)", fontsize=9.5)
    ax.legend(loc="upper left", fontsize=7.3)
    ax.text(0.995, 0.03, "Separate decks before (b1 − b1iso, r13's macro): +0.21 nV (r7 ADC), +0.30 (r10), +0.02 (r12 "
            "chain), each within the floor of comparing separate decks (grey)", transform=ax.transAxes, ha="right",
            va="bottom", fontsize=7.0, color=MUTED)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_57_digital_noise.png")
    fig.savefig(p)
    print("wrote", p, "" if done else f"(interim, {res['tend_us']:.1f} us)")


if __name__ == "__main__":
    main()

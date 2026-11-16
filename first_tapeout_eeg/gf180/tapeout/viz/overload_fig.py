#!/usr/bin/env python3
"""Figure 40 (r12, 11/16): the ADC driven out of range and back. The extracted loop on the chip's operating point
(adc_overload.py: +-2.5 V at the ADC's input for 50 us each, a full-scale 20 kHz sine between; and +2.5 V for 150 us,
then the -39 mV DC that the AFE settles to at 30 mV of electrode offset), and the behavioral loop from the same
states (adc_overload_beh.py: validated clock by clock against the extracted run, then 2 ms runs and the dies of the
block corners and Monte Carlo from random states at the end of an overload).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/overload_fig.py
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
RUNS = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", f"adc_overload_{V.CHIP}")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TWO = "typical_ov2.5V_50u_rec60u_f20k_a0.28"
ONE = "typical_ov2.5V_150u_then_dc-39mV_300u"
TEAL, PLUM = "#0d9488", "#a21caf"
NAMES = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]
Q = 46.9                                       # the quantizer's outermost thresholds (mV, O2 differential)


def load(name):
    d = os.path.join(RUNS, name)
    if not os.path.exists(os.path.join(d, "out.csv")):
        return None, None
    x = pd.read_csv(os.path.join(d, "out.csv"), sep=r"\s+", header=None, engine="c").to_numpy()
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    v["t"] = x[:, 0]
    v["o1"], v["o2"] = v["o1p"] - v["o1n"], v["o2p"] - v["o2n"]
    v["vg1"], v["vg2"] = v["i1p"] - v["i1n"], v["i2p"] - v["i2n"]
    v["code"] = np.round((v["norm1"] + 0.5) * 31)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    rep = os.path.join(d, "report.json")
    meta["report"] = json.load(open(rep, encoding="utf-8")) if os.path.exists(rep) else None
    return v, meta


def shade(ax, segs, ymax=None):
    for name, a, b in segs:
        if "overload" in name:
            ax.axvspan(a * 1e6, b * 1e6, color=LIGHT, alpha=0.18, lw=0)


def main():
    v2, m2 = load(TWO)
    v1, m1 = load(ONE)
    val = json.load(open(os.path.join(RUNS, "beh_validate.json")))["result"]
    lng = json.load(open(os.path.join(RUNS, "beh_long.json")))["result"]
    sw = json.load(open(os.path.join(RUNS, "beh_sweep.json")))
    rows = sw["result"]["rows"]
    segs = m2["overload"]["segments"]
    rec = {r["segment"]: r for r in m2["report"]}

    fig = V.figure(12.8, 13.2, "The ADC driven out of range: how the loop gets back" +
                   ("" if v1 is not None else " (interim: the overload-then-DC run is still running)"),
                   "eeg_adc extracted in its loop (eeg_bias and eeg_ref extracted, the chip's reference wiring, the RTL frame "
                   "timing, the DWA controller), typical, 27 °C, AVDD 3.245 V at the ADC · the input is differential at the "
                   "ADC's pins (DAC1 full scale ±0.484 V)",
                   note="Behavioral: adc_beh_mc.py's exact per-clock loop (DWA on both DACs, excess loop delay 0.22 of a clock, "
                        "which reproduces the transistor-level loop) started from given states, the integrator outputs clipped at "
                        "the extracted rails (O1 ±2.27 V, O2 ±3.25 V); it does not model an OTA's own recovery once it has lost "
                        "its virtual ground (36 µs for OTA2 in the extracted run). Dies: the typical model, the block "
                        "corners and resistor / MIM corners, and the 30 Monte Carlo dies of the block benches (thresholds, DAC1 "
                        f"elements, OTA gains, sheet and MIM draws). Random states: {sw['result']['states']} per die and input, "
                        "O1 uniform in ±2.27 V and O2 in ±3.25 V, random input phase; back = from when on O1 and O2 stay "
                        "within 1.5 × the swings of the same die and input started from zero (at least ±0.2 V and ±46.9 mV); "
                        "the 1-bit mode = |O1| above 0.5 V in the last 0.1 ms of 2 ms. No start from zero ended in it.")
    gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 1], width_ratios=[1.0, 1.0, 1.0])

    # (a) the extracted two-sided run: O1, O2 and the codes
    ax = fig.add_subplot(gs[0, 0:2])
    t = v2["t"] * 1e6
    k = slice(None, None, 4)
    shade(ax, segs)
    ax.plot(t[k], v2["o1"][k], color=ACCENT, lw=1.1, label="O1 (stage 1)")
    ax.plot(t[k], v2["o2"][k], color=TEAL, lw=1.1, label="O2 (stage 2, the quantizer's input)")
    ax.axhspan(-Q / 1e3, Q / 1e3, color=INK2, alpha=0.25, lw=0)
    for name, a, b in segs:
        lab = {"before": "0 V", "+overload": "+2.5 V", "recovery 1": "sine 0.28 V pk, 20 kHz", "-overload": "−2.5 V",
               "recovery 2": "sine again"}[name]
        ax.text((a + b) / 2 * 1e6, 3.55, lab, ha="center", va="bottom", fontsize=7.6, color=INK2)
    ax.set_xlim(0, 230)
    ax.set_ylim(-3.6, 3.9)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Differential output (V)")
    ax.legend(loc="lower left", fontsize=7.8, ncol=2)
    r1, r2 = rec["recovery 1"], rec["recovery 2"]
    ax.set_title("Extracted: both integrators hit their rails, and 60 µs of a full-scale 20 kHz sine do not bring the "
                 f"loop back (O2 down to {r1['o2_mv'][0] / 1e3:.1f} V)".replace("-", "−"), loc="left")

    # (b) the virtual grounds
    ax = fig.add_subplot(gs[0, 2])
    shade(ax, segs)
    ax.plot(t[k], v2["vg1"][k], color=ACCENT, lw=1.1, label="OTA1: I1P − I1N")
    ax.plot(t[k], v2["vg2"][k], color=TEAL, lw=1.1, label="OTA2: I2P − I2N")
    tbs = []
    for s0 in (60e-6, 170e-6):
        w = (v2["t"] > s0) & (v2["t"] < s0 + 60e-6)
        ok = np.nonzero(w & (np.abs(v2["vg2"]) > 0.05))[0]
        if len(ok):
            tb = v2["t"][ok[-1]] - s0
            tbs.append(tb)
            ax.annotate(f"{tb * 1e6:.0f} µs", xy=(v2["t"][ok[-1]] * 1e6, 0.05 * np.sign(v2["vg2"][ok[-1]])),
                        xytext=(v2["t"][ok[-1]] * 1e6 + 8, 1.0 * np.sign(v2["vg2"][ok[-1]] + 1e-9)),
                        fontsize=7.6, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    ax.set_xlim(0, 230)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Virtual ground, differential (V)")
    ax.legend(loc="lower left", fontsize=7.8)
    span = (f"{min(tbs) * 1e6:.0f}" if round(min(tbs) * 1e6) == round(max(tbs) * 1e6) else
            f"{min(tbs) * 1e6:.0f}–{max(tbs) * 1e6:.0f}")
    ax.set_title(f"The OTAs lose their virtual grounds; OTA2's is\nback (within 50 mV) {span} µs after each overload", loc="left")

    # (c) validation: the model from the extracted state against the extracted run
    ax = fig.add_subplot(gs[1, 0])
    c0 = val[0]
    tt = np.array(c0["t_us"])
    ax.plot(t[(t > 94) & (t < 120)], v2["o2"][(t > 94) & (t < 120)], color=TEAL, lw=1.2, label="extracted")
    ax.plot(tt, c0["o2_beh"], "o", color=INK, ms=3.2, mfc="white", mew=0.9, label="behavioral, from the state at the dot")
    ax.plot([c0["t0_us"]], [c0["x2_0"]], "o", color=INK, ms=5)
    ax.axhspan(-Q / 1e3, Q / 1e3, color=INK2, alpha=0.25, lw=0)
    ax.set_xlim(94, 120)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("O2 (V)")
    ax.legend(loc="upper right", fontsize=7.6)
    ax.set_title(f"The model against the extracted run: the\nsame code at {c0['same']} of {c0['clocks']} clocks "
                 f"({val[1]['same']} of {val[1]['clocks']} from 2 µs later)", loc="left")

    # (d) behavioral from the same state for 2 ms
    ax = fig.add_subplot(gs[1, 1])
    cols = {"sine 0.28 V 20 kHz (continued)": PLUM, "DC -300 mV": "#86b6ef", "DC -39 mV": ACCENT, "DC +0 mV": "#1f5aa8",
            "DC +300 mV": "#0d366b", "sine 0.28 V 2 kHz": TEAL}
    for c in lng["cases"]:
        te = np.array(c["t_env_us"])
        y = np.maximum(np.array(c["x2_env"]), 1e-4)
        lab = c["case"].replace("-", "−").replace(" (continued)", ", continued")
        lab += ": not back in 2 ms" if c["back_clock"] >= 2048 - 100 else f": back at {c['back_us']:.0f} µs"
        ax.semilogy(te / 1e3, y, color=cols.get(c["case"], INK2), lw=1.4 if "20 kHz" in c["case"] else 1.1, label=lab)
    ax.axhline(Q / 1e3, color=MUTED, lw=0.8, ls=(0, (2, 2)), label="the quantizer's range (46.9 mV)")
    ax.set_xlim(0, 2.0)
    ax.set_ylim(1e-3, 6)
    ax.set_xlabel("Time from the state of (c) (ms)")
    ax.set_ylabel("|O2|, largest per 31 µs (V, log)")
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.86), fontsize=7.0, labelspacing=0.35)
    ax.set_title("Behavioral, 2 ms from that state: only the\n20 kHz full-scale sine keeps the 1-bit mode", loc="left")

    # (e) the extracted overload, then DC
    ax = fig.add_subplot(gs[1, 2])
    if v1 is not None:
        t1 = v1["t"] * 1e6
        shade(ax, m1["overload"]["segments"])
        kk = slice(None, None, 4)
        ax.plot(t1[kk], v1["o1"][kk], color=ACCENT, lw=1.0, label="O1")
        ax.plot(t1[kk], v1["o2"][kk], color=TEAL, lw=1.0, label="O2")
        ax.axhspan(-Q / 1e3, Q / 1e3, color=INK2, alpha=0.25, lw=0)
        rr = {r["segment"]: r for r in (m1["report"] or [])}.get("recovery")
        ax.set_xlim(0, t1[-1])
        ax.set_ylim(-1.3, 3.9)
        ax.set_xlabel("Time (µs)")
        ax.set_ylabel("Differential output (V)")
        ax.legend(loc="upper right", fontsize=7.6)
        if rr:
            te = [b for name, a, b in m1["overload"]["segments"] if "overload" in name][0]
            tb = te * 1e6 + rr["back_after_us"]
            ax.axvline(tb, color=MUTED, lw=0.8, ls=(0, (2, 2)))
            after = v1["t"] > te

            def vg_back(x):                                    # last time the virtual ground is off by > 50 mV
                i = np.nonzero(after & (np.abs(x) > 0.05))[0]
                return (v1["t"][i[-1]] - te) * 1e6 if len(i) else 0.0

            # from when on the codes stay on the two adjacent codes of the last 100 us
            tail = v1["t"] > v1["t"][-1] - 100e-6
            lo, hi = v1["code"][tail].min(), v1["code"][tail].max()
            off = np.nonzero(after & ((v1["code"] < lo) | (v1["code"] > hi)))[0]
            t2 = v1["t"][off[-1]] if len(off) else te
            late = v1["t"] > t2
            code = v1["code"][late]
            vin = m1["overload"]["rec_dc"]
            expect = 15.5 - vin / 0.484 * 15.5                # the code of a DC input (the loop inverts: −V → above 15.5)
            ax.text(tb + 5, 2.6,
                    f"back {rr['back_after_us']:.0f} µs after the overload\n"
                    f"virtual grounds within 50 mV:\nOTA1 at {vg_back(v1['vg1']):.0f} µs, OTA2 at {vg_back(v1['vg2']):.0f} µs\n"
                    f"from {(t2 - te) * 1e6:.0f} µs only codes {lo:.0f} and {hi:.0f},\n"
                    f"mean {code.mean():.2f} (−39 mV: {expect:.2f})\n"
                    f"|O2| ≤ {np.abs(v1['o2'][late]).max() * 1e3:.0f} mV, |O1| ≤ {np.abs(v1['o1'][late]).max() * 1e3:.0f} mV",
                    ha="left", va="top", fontsize=7.2, color=INK2, linespacing=1.35)
        ax.set_title("Extracted: +2.5 V for 150 µs, then −39 mV DC\n" +
                     (f"(the AFE's residual at 30 mV of offset): back in {rr['back_after_us']:.0f} µs" if rr else ""),
                     loc="left")
    else:
        ax.set_axis_off()
        ax.text(0.0, 0.95, "Extracted: +2.5 V for 150 µs, then −39 mV DC\n(the AFE's residual at 30 mV of offset)\n\n"
                "running (adc_overload.py --one-sided)", transform=ax.transAxes, va="top", fontsize=9, color=INK2)

    # (f) statistics: the slowest recovery per die and input, (g) the share left in the 1-bit mode
    cases = []
    for r in rows:
        key = (r["f"], r["a"])
        if key not in cases:
            cases.append(key)

    def lab(f, a):
        return (f"DC ±{a:g}" if f == 0 else f"{f / 1e3:g} kHz\n{a:g}" if f >= 1e3 else f"{f:g} Hz\n{a:g}")

    ax = fig.add_subplot(gs[2, 0:2])
    xs = np.arange(len(cases))
    rng = np.random.default_rng(5)
    kinds = [("typ", INK, "typical model"), ("corner", ACCENT, "block / R / MIM corners"), ("mc", LIGHT, "Monte Carlo dies")]
    for i, (f, a) in enumerate(cases):
        rs = [r for r in rows if r["f"] == f and r["a"] == a]
        for kind, col, _ in kinds:
            sel = [r for r in rs if (r["die"] == "typ") == (kind == "typ") and r["die"].startswith("mc") == (kind == "mc")]
            y = np.array([r["t_max_us"] if r["t_max_us"] is not None else np.nan for r in sel])
            ax.plot(i + rng.uniform(-0.22, 0.22, y.size) * (kind != "typ"), y, "o", color=col, ms=4.6 if kind != "mc" else 4.0,
                    mec="white", mew=0.5, zorder=3 if kind != "mc" else 2)
    for kind, col, l in kinds:
        ax.plot([], [], "o", color=col, ms=5, label=l)
    ax.set_xticks(xs, [lab(f, a) for f, a in cases], fontsize=7.8)
    ax.set_xlim(-0.6, len(cases) - 0.4)
    ax.set_ylim(0, 1100)
    ax.set_xlabel("Input after the overload (V pk at the ADC's pins)")
    ax.set_ylabel("Slowest of the states that got back (µs)")
    inb = [r for r in rows if r["f"] <= 2e3]
    worst = max(r["t_max_us"] for r in inb)
    worst28 = max(r["t_max_us"] for r in inb if r["a"] <= 0.28)
    ax.axvspan(-0.6, 6.5, color=ACCENT, alpha=0.04, lw=0)
    ax.text(3.0, 1060, "in band and up to 2 kHz: every state of every die got back", ha="center", fontsize=7.8, color=INK2)
    ax.legend(loc="upper right", fontsize=7.6)
    ax.set_title(f"Behavioral, {len(set(r['die'] for r in rows))} dies: the slowest recovery is {worst:.0f} µs in band "
                 f"({worst28:.0f} µs up to 0.28 V; OTA2's own 36 µs not included)", loc="left")
    ax.grid(axis="x", visible=False)

    ax = fig.add_subplot(gs[2, 2])
    share = [max(r["onebit_share"] for r in rows if r["f"] == f and r["a"] == a) * 100 for f, a in cases]
    med = [np.median([r["onebit_share"] for r in rows if r["f"] == f and r["a"] == a]) * 100 for f, a in cases]
    ax.bar(xs - 0.18, med, width=0.36, color=ACCENT, label="median over the dies")
    ax.bar(xs + 0.18, share, width=0.36, color=LIGHT, label="the worst die")
    ax.set_xticks(xs, [lab(f, a).replace("\n", " ") for f, a in cases], rotation=60, ha="right", fontsize=7.2)
    ax.set_ylim(0, 100)
    ax.set_ylabel("States still in the 1-bit mode at 2 ms (%)")
    ax.legend(loc="upper left", fontsize=7.6)
    ax.set_title("Where the 1-bit mode stays: large\ninputs at 10–20 kHz only", loc="left")
    ax.grid(axis="x", visible=False)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_40_adc_overload.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

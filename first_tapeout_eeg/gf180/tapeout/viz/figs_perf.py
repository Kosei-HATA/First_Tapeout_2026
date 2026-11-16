#!/usr/bin/env python3
"""Performance figures of the final GF180 EEG chip from the simulation records, in the look of
figs.py: the end-to-end transient with parasitics (pex/pex_e2e.py, read through
pex/plot_e2e.py), Bode plots of the AFE amplifier, the AFE baseband transfer with chopping, the
ADC OTAs and the modulator's NTF/STF, the AFE input impedance (pex/viz_data.py), and the AFE's
start-up from power-on on the chip's own wiring (pex/afe_startup.py: pads, board and bond wires,
eeg_bias and eeg_ref extracted, the RTL's reset sequence with the firmware writing AFE_IBIAS = 3,
Monte Carlo and AVDD ±5 %; the counterparts of the SKY130 figures of 12 Sep): power-on, the release
with the electrodes at 0 V, an electrode DC offset with the offset DAC at the firmware's code, and a
full-scale sine, schematic against extracted, with the extraction's capacitors
(runs/afe_top_c/afe_top_pex.spice).

usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r10_20261109/viz [names]
       (the chip version is set in vizstyle.py; SRC below says which runs each figure reads for it)"""
import csv
import functools
import glob
import importlib.util
import json
import os
import re
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vizstyle  # noqa: E402
from vizstyle import ACCENT, BAD, HAIR, INK, INK2, LIGHT, MUTED, figure  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

PEX, OUT = sys.argv[1], sys.argv[2]
# Which runs a chip's figures read. The runs of a later chip than r6 sit in <folder>_<rev> (EEG_PEX_REV, pex.py),
# r6's in the plain folders. A block that a later chip left unchanged keeps the runs of the chip it last changed in
# (checked by XOR, gf180_chip_assembly_20261023.md): afe_top since r6, adc_top since r7 (C1 and C2 x1.25), so the
# AFE's runs (viz) are r6's and the ADC's (viz: ota and ntf, the E2E with both blocks, the ADC's loop model and
# transistor loop) r7's for r9. The runs on the chip wiring (afe_startup.py) are each chip's own, tagged _chip<_rev>
# in runs/startup/ (r9: the DVDD straps of r8 and the Metal3 under the AFE's AVSS jumpers). The blocks' own Monte
# Carlo (adc_mc) is shared: comparator, OTA and DAC1 did not change.
# r10 (11/9): adc_top changed (the quantizer's latch ground, a Metal5 strap), so the ADC's runs are r10's on its
# own extraction (the user's decision; the analog nets are within 0.03 fF of r7's); afe_top is r6's, and the chip
# wiring (top-level shapes identical to r9's by XOR) keeps r9's runs.
# r11 (11/13): RIN, DAC1 and R21 on ppolyf_u (adc_top's cells adc_rdac, rdac_r, adc_r21 and its top changed), and
# the router's wires to the ADC's moved west ports (OUTP / OUTN, VREFP / VREFN and the ADC's bias lines): the ADC's
# runs, the blocks' Monte Carlo (mc: runs/adc_mc_r11, DAC1 and the OTAs' loads), the flicker study and the runs on
# the chip wiring (chipnets_r11) are r11's own; afe_top stays r6's.
# r12 (11/13): no switching line under the sensitive nets (adc_top: the SEL1 / DAC_CLK tunnel under the I1N / O1P
# straps, afe_top: the corridor's shield and the WN sheet off the clock rows): the AFE's and the ADC's runs and the
# runs on the chip wiring (chipnets_r12) are r12's own; the blocks' Monte Carlo and the flicker study stay r11's
# (adc_rdac, the OTAs and the comparator did not change), and so does the per-die loop model (beh: adc_beh_mc.py
# reads only the blocks' Monte Carlo).
SRC = {"r6": dict(afe="", adc="", startup="_chip"),
       "r9": dict(afe="", adc="_r7", startup="_chip_r9"),
       "r10": dict(afe="", adc="_r10", startup="_chip_r9"),
       "r11": dict(afe="", adc="_r11", startup="_chip_r11", mc="_r11", flicker="_r11"),
       "r12": dict(afe="_r12", adc="_r12", startup="_chip_r12", mc="_r11", flicker="_r11", beh="_r11")}[vizstyle.CHIP]
VIZ = os.path.join(PEX, "runs", "viz" + SRC["afe"])
VIZ_ADC = os.path.join(PEX, "runs", "viz" + SRC["adc"])
E2E = os.path.join(PEX, "runs", "e2e" + SRC["adc"])
DATA_DIR = "data" if vizstyle.CHIP == "r6" else f"data_{vizstyle.CHIP}"   # figs.py's CSVs of this chip
os.makedirs(OUT, exist_ok=True)
PREFIX = f"gf180_viz_{vizstyle.CHIP}_"
TEAL = "#0d9488"
GRID2 = "#cbd5e1"
BAND = (0.5, 100.0)                      # band of the 16.5-bit residual budget
FCH, FS = 128e3, 1.024e6
NET = {"sch": dict(color=INK2, label="Schematic"), "pex": dict(color=ACCENT, label="Extracted final chip")}
RUN = {
    "d4": dict(color=LIGHT, ls=(0, (1, 1.5)), label="Schematic, D4 deck"),
    "sch": dict(color=INK2, ls=(0, (5, 2.5)), label="Schematic, cut as the extraction"),
    "pex": dict(color=ACCENT, ls="-", label="Extracted final chip"),
    "pexchip": dict(color=TEAL, ls=(0, (6, 2, 1.5, 2)), label="Extracted + chip-level OUTP/OUTN wiring"),
}


def save(fig, name):
    path = os.path.join(OUT, PREFIX + name + ".png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", os.path.basename(path))


def rcsv(name, base=None):
    with open(os.path.join(base or VIZ, name + ".csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def col(rows, name):
    return np.array([float(r[name]) for r in rows])


def afe_ripple():
    """The AFE alone: output ripple outside the blanking (mV p-p), the final column of figs.py's afe_metrics.csv."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_DIR, "afe_metrics.csv"), encoding="utf-8") as f:
        return float(next(r for r in csv.DictReader(f) if r["metric"].startswith("Output ripple"))["final"])


def summary(name, base=None):
    with open(os.path.join(base or VIZ, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def logf(ax, lo, hi):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(mticker.LogLocator(base=10, numticks=12))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(hz))
    ax.xaxis.set_minor_locator(mticker.LogLocator(base=10, subs=np.arange(2, 10), numticks=12))
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())


def hz(v, _=None):
    for s, k in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if v >= k:
            return f"{v / k:g} {s}"
    return f"{v:g}"


def band(ax, label=False):
    ax.axvspan(*BAND, color="#f1f5f9", zorder=0, lw=0)
    if label:
        ax.text(np.sqrt(BAND[0] * BAND[1]), 1.0, "EEG band", transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                fontsize=7.5, color=MUTED)


def vmark(ax, f, text, y=1.0):
    ax.axvline(f, color=MUTED, lw=0.8, ls=(0, (1, 2)), zorder=1)
    ax.text(f, y, " " + text, transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, ha="left", va="top")


def minus(s):
    return s.replace("-", "−")


# ---------------------------------------------------------------- end-to-end transient

def e2e_runs():
    spec = importlib.util.spec_from_file_location("plot_e2e", os.path.join(PEX, "plot_e2e.py"))
    pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pe)
    vizstyle.apply()                     # plot_e2e sets its own fonts on import
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = {r: pe.load(os.path.join(E2E, r), 16e3, 20e-6, 7) for r in RUN}
        for r in d:
            co, _ = pe.fit(d[r]["tp"], d[r]["per"], 16e3)
            d[r]["co"] = co
            d[r]["ch"], d[r]["rh"] = pe.fit(d[r]["ht"], d[r]["hv"], 16e3)
    return pe, d


def run_handles(runs):
    return [Line2D([], [], color=RUN[r]["color"], ls=RUN[r]["ls"], lw=1.6, label=RUN[r]["label"]) for r in runs]


def fig_e2e():
    pe, d = e2e_runs()
    fig = figure(12.4, 13.4, "End-to-end transient, electrode to ADC",
                 "16 kHz full-scale sine (0.943 mV pk, 100 Ω per leg) · typical, 27 °C · AFE reset released at 10 µs · "
                 "the shaded start is outside the evaluation window",
                 note="Panels 3–6 show the schematic and the extracted chip; the D4 deck and the chip-level wiring run lie on them "
                      "(differences in the next figure). The ADC integrates its input, so the instantaneous chopping\nspikes in panel 3 "
                      "matter only through the integrator swings in panels 4 and 5.")
    axs = fig.subplots(6, 1, sharex=True, gridspec_kw=dict(height_ratios=[0.75, 1.25, 1.25, 1, 1, 1.05]))
    t = lambda r: d[r]["t"] * 1e6  # noqa: E731
    for ax in axs:
        ax.axvspan(0, 20, color="#f8fafc", zorder=0, lw=0)
        ax.axvline(20, color=GRID2, lw=0.8, zorder=1)
    ax = axs[0]
    ax.plot(t("pex"), d["pex"]["sig"] * 1e3, color=INK2, lw=1.3)
    ax.set_ylim(-1.3, 1.75)
    ax.set_ylabel("mV")
    ax.set_title("Electrode input (differential)", fontsize=9.5)
    ax.axvline(10, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(10.3, 1.68, "AFE reset released", fontsize=7.5, color=MUTED, va="top")
    ax.text(20.4, 1.68, "evaluation window", fontsize=7.5, color=MUTED, va="top")
    ax = axs[1]
    for r in RUN:
        tt, av = pe.sliding(d[r])
        ax.plot(tt * 1e6, av * 1e3, color=RUN[r]["color"], ls=RUN[r]["ls"], lw=1.5)
    ax.set_ylabel("mV")
    ax.set_ylim(-330, 330)
    ax.set_title("AFE output OUTP − OUTN, averaged over each chopper period (7.8 µs)", fontsize=9.5)
    ax.legend(handles=run_handles(RUN), loc="lower left", ncols=2, fontsize=8)
    ax = axs[2]
    for r in ("sch", "pex"):
        ax.plot(t(r), d[r]["vo"] * 1e3, color=RUN[r]["color"], lw=0.7, alpha=0.95 if r == "pex" else 0.8)
    for y, ls in ((300, (0, (4, 3))), (260, (0, (1, 2)))):
        for s in (1, -1):
            ax.axhline(s * y, color=BAD if y == 300 else MUTED, ls=ls, lw=0.9)
    ax.annotate("dashed: full scale ±300 mV", (70, 300), textcoords="offset points", xytext=(0, 3), ha="right", va="bottom",
                fontsize=7.5, color=BAD)
    ax.annotate("dotted: signal range ±260 mV", (0.4, 300), textcoords="offset points", xytext=(0, 3), ha="left", va="bottom",
                fontsize=7.5, color=MUTED)
    ax.set_ylim(-345, 375)
    ax.set_ylabel("mV")
    ax.set_title("ADC input OUTP − OUTN, instantaneous", fontsize=9.5)
    ax = axs[3]
    for r in ("sch", "pex"):
        ax.plot(t(r), d[r]["o1"] * 1e3, color=RUN[r]["color"], ls=RUN[r]["ls"], lw=1.0)
    ax.set_ylabel("mV")
    ax.set_ylim(-120, 120)
    ax.set_title("First integrator O1", fontsize=9.5)
    ax = axs[4]
    for r in ("sch", "pex"):
        ax.plot(t(r), d[r]["o2"] * 1e3, color=RUN[r]["color"], ls=RUN[r]["ls"], lw=1.0)
    for s in (1, -1):
        ax.axhline(s * 46.9, color=BAD, ls=(0, (4, 3)), lw=0.9)
    ax.annotate("quantizer range ±46.9 mV", (70, 46.9), textcoords="offset points", xytext=(0, 2), ha="right", va="bottom",
                fontsize=7.5, color=BAD)
    ax.set_ylim(-62, 62)
    ax.set_ylabel("mV")
    ax.set_title("Second integrator O2", fontsize=9.5)
    ax = axs[5]
    # DAC1 level at mid-frame, in volts at the ADC input (x 0.96875 V); sign set to follow the input
    ph = lambda c: np.angle(c[0] - 1j * c[1])  # noqa: E731
    flip = -1.0 if np.cos(ph(d["pex"]["cn"]) - ph(d["pex"]["co"])) < 0 else 1.0
    for r in ("sch", "pex"):
        ax.step(d[r]["tk"] * 1e6, flip * d[r]["n1"] * 968.75, where="mid", color=RUN[r]["color"], ls=RUN[r]["ls"], lw=1.0)
    tk = np.linspace(20e-6, d["pex"]["t"][-1], 400)
    cn = d["pex"]["cn"]
    ax.plot(tk * 1e6, flip * 968.75 * (cn[0] * np.cos(2 * np.pi * 16e3 * tk) + cn[1] * np.sin(2 * np.pi * 16e3 * tk) + cn[2]),
            color=MUTED, lw=0.9, ls=(0, (1, 1.5)))
    ax.text(69.5, 300, "dotted: sine fit (extracted)", fontsize=7.5, color=MUTED, ha="right", va="top")
    ax.set_ylim(-345, 345)
    ax.set_ylabel("mV")
    ax.set_title("DAC1 level at mid-frame, in input volts (one element = 31.25 mV)" + (", sign inverted" if flip < 0 else ""),
                 fontsize=9.5)
    ax.set_xlim(0, 70)
    ax.set_xlabel("Time (µs)")
    save(fig, "16_e2e_transient")


def fig_e2e_effects():
    pe, d = e2e_runs()
    # decay of the extracted A - B: adjacent held levels, log-linear fit over the window
    rh, ht = d["pex"]["rh"], d["pex"]["ht"]
    ab = (rh[:-1] - rh[1:]) * (-1.0) ** np.arange(len(rh) - 1)
    tau = -1 / np.polyfit(0.5 * (ht[:-1] + ht[1:]), np.log(np.abs(ab)), 1)[0]
    fig = figure(12.4, 9.0, "End-to-end run: what the parasitics change",
                 "Evaluation window 20–70 µs · the same 16 kHz full-scale sine as the previous figure",
                 note=f"Middle: the A/B square wave is the P/N imbalance left when the AFE reset is released; it decays (fit {tau * 1e6:.0f} µs "
                      "in this window, DC path 138 µs). Before the 25 Oct fix of the input chopper's clock coupling (WP against WN) "
                      f"it was 18.8 mV.\nThe AFE alone shows {afe_ripple():.2f} mV p-p (0.1–0.2 ms). "
                      "Bottom: the residual is noise-shaped quantization error, mostly above the band; one DAC1 element is "
                      "1/31 = 0.032 of the range.")
    axs = fig.subplots(3, 1, sharex=True)
    ax = axs[0]
    tp = d["sch"]["tp"] * 1e6
    for (a, b), c, ls, lab in ((("pex", "sch"), ACCENT, "-", "Extracted − schematic"),
                               (("pexchip", "pex"), TEAL, (0, (6, 2, 1.5, 2)), "Chip-level wiring: (extracted + wiring) − extracted")):
        ax.plot(tp, (d[a]["per"] - d[b]["per"]) * 1e3, color=c, ls=ls, lw=1.4, marker="o", ms=4, label=lab)
    ax.axhline(0, color=GRID2, lw=0.9)
    ax.set_ylabel("mV")
    ax.set_title("Difference of the AFE output, averaged over each chopper period (signal amplitude 275 mV)", fontsize=9.5)
    ax.legend(loc="upper left", fontsize=8)
    ax = axs[1]
    for r, mk in (("sch", "s"), ("pex", "o")):
        ab = d[r]["met"]["ab_mv"]
        ax.plot(d[r]["ht"] * 1e6, d[r]["rh"] * 1e3, color=RUN[r]["color"], lw=0.8, marker=mk, ms=3.6,
                label=f"{RUN[r]['label']}: A − B {minus(f'{ab:.2f}')} mV")
    ax.axhline(0, color=GRID2, lw=0.9)
    ax.set_ylabel("mV")
    ax.set_title("AFE output held in each chopper half period, minus the sine fit (phases A and B alternate)", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    ax = axs[2]
    for r, mk in (("sch", "s"), ("pex", "o")):
        ax.plot(d[r]["tk"] * 1e6, d[r]["rn"], color=RUN[r]["color"], lw=0.8, marker=mk, ms=3.6,
                label=f"{RUN[r]['label']}: {d[r]['met']['residual']:.4f} rms")
    for s in (1, -1):
        ax.axhline(s / 31, color=MUTED, ls=(0, (1, 2)), lw=0.9)
    ax.axhline(0, color=GRID2, lw=0.9)
    ax.set_ylim(-0.1, 0.1)
    ax.set_ylabel("DAC1 range = 1")
    ax.set_title("DAC1 level minus its sine fit, per frame", fontsize=9.5)
    h, _ = ax.get_legend_handles_labels()
    ax.legend(handles=h + [Line2D([], [], color=MUTED, ls=(0, (1, 2)), lw=0.9, label="± one DAC1 element (1/31)")],
              loc="lower right", fontsize=8, ncols=3)
    ax.set_xlim(19, 70.5)
    ax.set_xlabel("Time (µs)")
    save(fig, "17_e2e_effects")


def fig_e2e_metrics():
    with open(os.path.join(E2E, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    runs = list(RUN)
    fig = figure(13.2, 6.6, "End-to-end metrics, four netlists",
                 "Fits over 20–70 µs (0.8 period of the 16 kHz sine): gains are good to a few per cent in this window",
                 note="A − B: square-wave difference of the AFE output's held levels between chopper phases. ADC input peak: "
                      "largest |OUTP − OUTN|, chopping spikes included.")
    axs = fig.subplots(2, 4)
    x = np.arange(len(runs))
    names = ["D4", "Sch.", "Ext.", "Ext. +\nwiring"]

    def dots(ax, key, title, unit, ylim, fmt, ref=None, ref_lab=None, scale=1.0, side=False, ref_right=False):
        v = [s[r][key] * scale for r in runs]
        for xi, vi, r in zip(x, v, runs):
            ax.scatter([xi], [vi], s=55, color=RUN[r]["color"], zorder=3, edgecolor="white", linewidth=0.8)
            ax.annotate(minus(fmt.format(vi)), (xi, vi), textcoords="offset points", xytext=(8, 0) if side else (0, 8),
                        ha="left" if side else "center", va="center" if side else "baseline", fontsize=8)
        if ref is not None:
            ax.axhline(ref, color=MUTED, ls=(0, (1, 2)), lw=0.9)
            ax.annotate(ref_lab, (len(runs) - 0.45 if ref_right else -0.5, ref), textcoords="offset points", xytext=(-2 if ref_right else 2, 3),
                        ha="right" if ref_right else "left", fontsize=7.5, color=MUTED, va="bottom")
        ax.set_ylim(*ylim)
        finish(ax, title, unit)

    def finish(ax, title, unit):
        ax.set_xticks(x, names, fontsize=8)
        ax.set_xlim(-0.6, len(runs) - 0.4)
        ax.set_title(title, fontsize=9.2)
        ax.set_ylabel(unit, fontsize=8.5)
        ax.grid(axis="x", visible=False)

    dots(axs[0, 0], "gain_afe", "AFE gain (period averages)", "V/V", (282, 300), "{:.1f}")
    dots(axs[0, 1], "gain_all", "Overall gain, electrode to DAC1", "V/V", (292, 310), "{:.1f}")
    dots(axs[0, 2], "residual", "DAC1 residual after the sine fit", "rms (DAC1 range = 1)", (0, 0.045), "{:.4f}",
         ref=1 / 31, ref_lab="one element")
    dots(axs[0, 3], "avdd_ma", "AVDD current", "mA", (26.0, 28.5), "{:.2f}")
    dots(axs[1, 0], "ab_mv", "AFE output, phase A − B", "mV", (-6, 6), "{:+.2f}", ref=afe_ripple(), ref_lab=f"AFE alone: {afe_ripple():.2f} p-p",
         side=True, ref_right=True)
    axs[1, 0].axhline(0, color=HAIR, lw=1)
    ax = axs[1, 1]
    v = [max(-s[r]["adc_in_min_mv"], s[r]["adc_in_max_mv"]) for r in runs]
    for xi, vi, r in zip(x, v, runs):
        ax.scatter([xi], [vi], s=55, color=RUN[r]["color"], zorder=3, edgecolor="white", linewidth=0.8)
        ax.annotate(f"{vi:.1f}", (xi, vi), textcoords="offset points", xytext=(0, -13), ha="center", fontsize=8)
    ax.axhline(300, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate("full scale 300", (-0.5, 300), textcoords="offset points", xytext=(2, 3), fontsize=7.5, color=BAD, va="bottom")
    ax.axhline(260, color=MUTED, ls=(0, (1, 2)), lw=0.9)
    ax.annotate("signal range 260", (-0.5, 260), textcoords="offset points", xytext=(2, 3), fontsize=7.5, color=MUTED, va="bottom")
    ax.set_ylim(240, 315)
    finish(ax, "ADC input peak", "mV")
    for ax, k, title, lim, lab in ((axs[1, 2], "o1", "First integrator O1, range", 120, None),
                                   (axs[1, 3], "o2", "Second integrator O2, range", 60, 46.9)):
        for xi, r in zip(x, runs):
            lo, hi = s[r][k + "_min_mv"], s[r][k + "_max_mv"]
            ax.plot([xi, xi], [lo, hi], color=RUN[r]["color"], lw=6, solid_capstyle="butt")
            ax.text(xi + 0.16, hi, f"{hi:.1f}", fontsize=7.4, va="center", color=INK2)
            ax.text(xi + 0.16, lo, minus(f"{lo:.1f}"), fontsize=7.4, va="center", color=INK2)
        if lab:
            for sg in (1, -1):
                ax.axhline(sg * lab, color=BAD, ls=(0, (4, 3)), lw=1)
            ax.annotate("quantizer ±46.9", (3.55, lab), textcoords="offset points", xytext=(0, 3), ha="right", fontsize=7.5,
                        color=BAD, va="bottom")
        ax.axhline(0, color=GRID2, lw=0.8)
        ax.set_ylim(-lim, lim)
        finish(ax, title, "mV")
    save(fig, "18_e2e_metrics")


# ---------------------------------------------------------------- Bode plots

def loop_panel(axm, axp, data, qty, ann):
    """Magnitude and phase of one quantity (A or T) for the schematic and the extraction."""
    for net, (f, mag, ph) in data.items():
        axm.plot(f, mag, color=NET[net]["color"], lw=1.6 if net == "pex" else 1.3, ls="-" if net == "pex" else (0, (5, 2.5)),
                 label=NET[net]["label"])
        axp.plot(f, ph, color=NET[net]["color"], lw=1.6 if net == "pex" else 1.3, ls="-" if net == "pex" else (0, (5, 2.5)))
    for ax in (axm, axp):
        logf(ax, 1, 1e9)
    axm.axhline(0, color=GRID2, lw=0.9)
    axp.axhline(-180, color=BAD, ls=(0, (4, 3)), lw=0.9)
    axm.set_ylabel(f"|{qty}| (dB)")
    axp.set_ylabel(f"Phase of {qty} (°)")
    axp.set_xlabel("Frequency (Hz)")
    axp.yaxis.set_major_locator(mticker.MultipleLocator(45))
    for net, text, xy, off in ann:
        axm.annotate(text, xy, textcoords="offset points", xytext=off, fontsize=7.8, color=NET[net]["color"],
                     arrowprops=dict(arrowstyle="-", color=NET[net]["color"], lw=0.6))


def fig_afe_bode():
    sm = summary("afe_loop_summary")
    data_a, data_t = {}, {}
    for net in ("sch", "pex"):
        r = rcsv(f"afe_loop_{net}_A")
        f = col(r, "f_hz")
        data_a[net] = (f, col(r, "A_db"), col(r, "A_deg"))
        data_t[net] = (f, col(r, "T_db"), col(r, "T_deg"))
    fig = figure(13.0, 8.0, "AFE amplifier: open-loop gain and loop gain",
                 "Chopper stopped in phase A (an LTI circuit) · typical, 27 °C · Cpf trim 8 · loaded by the ADC input (18.75 kΩ per side)",
                 note="A = (OPI − ONI)/(INPG − INNG) with the loop opened at the input-pair gates; T by Middlebrook's double injection at "
                      "the same break. Phase B gives the same curves (T within 0.3 dB, PM within 0.1°).")
    axs = fig.subplots(2, 2, sharex="col", gridspec_kw=dict(height_ratios=[1.35, 1]))
    sa, ss = sm["pex_A"], sm["sch_A"]
    loop_panel(axs[0, 0], axs[1, 0], data_a, "A",
               [("pex", f"DC {sa['A_dc_db']:.1f} dB", (10, sa["A_dc_db"]), (10, -24)),
                ("pex", f"unity gain {sa['A_ugf_hz'] / 1e6:.0f} MHz", (sa["A_ugf_hz"], 0), (-120, -26))])
    axs[0, 0].set_title("Open-loop gain A(f)", fontsize=10)
    loop_panel(axs[0, 1], axs[1, 1], data_t, "T", [("pex", f"DC {sa['T_dc_db']:.1f} dB", (10, sa["T_dc_db"]), (10, -24))])
    for net, sv in (("sch", ss), ("pex", sa)):
        axs[0, 1].scatter([sv["T_ugf_hz"]], [0], s=34, facecolor="white", edgecolor=NET[net]["color"], linewidth=1.4, zorder=4)
        ph = np.interp(np.log(sv["T_ugf_hz"]), np.log(data_t[net][0]), data_t[net][2])
        axs[1, 1].scatter([sv["T_ugf_hz"]], [ph], s=34, facecolor="white", edgecolor=NET[net]["color"], linewidth=1.4, zorder=4)
    axs[0, 1].text(0.03, 0.05, f"Crossover (open marks)\nextracted {sa['T_ugf_hz'] / 1e6:.2f} MHz, PM {sa['PM_deg']:.1f}°\n"
                   f"  (its phase stays above −180° up to 1 GHz)\nschematic {ss['T_ugf_hz'] / 1e6:.2f} MHz, PM {ss['PM_deg']:.1f}°, "
                   f"GM {ss['GM_db']:.1f} dB at {ss['f180_hz'] / 1e6:.0f} MHz", transform=axs[0, 1].transAxes, fontsize=7.8,
                   color=INK2, linespacing=1.5, va="bottom")
    axs[0, 1].set_title("Loop gain T(f)", fontsize=10)
    axs[0, 0].legend(loc="lower left")
    for ax in axs[0]:
        vmark(ax, FCH, "chopper 128 kHz", 0.98)
        band(ax)
    for ax in axs[1]:
        band(ax)
        ax.set_ylim(-240, 30)
    axs[0, 0].set_ylim(-60, 95)
    axs[0, 1].set_ylim(-90, 45)
    axs[1, 1].annotate("−180°", (2, -180), textcoords="offset points", xytext=(0, 3), fontsize=7.5, color=BAD, va="bottom")
    save(fig, "19_afe_bode")


def fig_afe_baseband():
    # transient (lowest frequency) against the harmonic sum at that frequency
    above = {}
    if os.path.exists(os.path.join(VIZ, "afe_baseband_transient.csv")):
        for net in ("sch", "pex"):
            rr = [x for x in rcsv("afe_baseband_transient") if x.get("netlist", net) == net]
            r = rcsv(f"afe_baseband_{net}_A")
            if rr:
                f0, g0 = float(rr[0]["f_hz"]), float(rr[0]["gain_db"])
                above[net] = 10 ** ((g0 - np.interp(f0, col(r, "f_hz"), col(r, "gain_db"))) / 20) - 1
    pct = " and ".join(f"{100 * above[n]:.1f} % ({w})" for n, w in (("sch", "schematic"), ("pex", "extracted")) if n in above)
    fig = figure(12.6, 8.6, "AFE baseband transfer with chopping",
                 "Electrode (differential, 100 Ω per leg) to OUTP − OUTN · harmonic sum over the odd chopper harmonics of the "
                 "frozen-phase transfer · typical, 27 °C",
                 note="G(f) = Σ_k odd 4/(πk)² · [H(k·fch + f) + H*(k·fch − f)], fch = 128 kHz, k ≤ 7811. Dashed: with the chopper-period "
                      "average that the end-to-end checks apply (adds sinc(f/fch)).\nBlanking is not modelled: the sum counts the "
                      "settling after each chopper edge, which the 7-MCLK blanking hides. Diamonds: chopped transient runs with the "
                      f"blanking, {pct} above the sum, at the frozen-phase in-band gain.")
    axs = fig.subplots(3, 1, sharex=True, gridspec_kw=dict(height_ratios=[1.1, 1.1, 0.9]))
    for net in ("sch", "pex"):
        r = rcsv(f"afe_baseband_{net}_A")
        f, g, ph, ga, pa = (col(r, c) for c in ("f_hz", "gain_db", "phase_deg", "gain_avg_db", "phase_avg_deg"))
        st = dict(color=NET[net]["color"], lw=1.6 if net == "pex" else 1.3)
        axs[0].plot(f, 10 ** (g / 20), label=f"{NET[net]['label']}: {10 ** (g[0] / 20):.1f} V/V at 0.1 Hz", **st)
        axs[0].plot(f, 10 ** (ga / 20), ls=(0, (5, 2.5)), **st)
        axs[1].plot(f, g - g[0], **st)
        axs[1].plot(f, ga - g[0], ls=(0, (5, 2.5)), **st)
        axs[2].plot(f, ph, **st)
        axs[2].plot(f, pa, ls=(0, (5, 2.5)), **st)
    tr = os.path.join(VIZ, "afe_baseband_transient.csv")
    if os.path.exists(tr):
        r = rcsv("afe_baseband_transient")
        for net in ("sch", "pex"):
            rr = [x for x in r if x.get("netlist", net) == net]
            if rr:
                dia = dict(s=40, marker="D", facecolor="white", edgecolor=NET[net]["color"], linewidth=1.4, zorder=4)
                gt = col(rr, "gain_db")
                axs[0].scatter(col(rr, "f_hz"), 10 ** (gt / 20), label=f"{NET[net]['label']}: chopped transient with blanking", **dia)
                axs[1].scatter(col(rr, "f_hz"), gt - gt[0], **dia)
                axs[2].scatter(col(rr, "f_hz"), col(rr, "phase_deg"), **dia)
    for ax in axs:
        logf(ax, 0.1, 64e3)
        band(ax, label=ax is axs[0])
    axs[0].set_ylim(0, 340)
    axs[0].set_ylabel("|G| (V/V)")
    axs[0].legend(loc="lower left", fontsize=8)
    axs[1].set_ylim(-4.5, 0.5)
    axs[1].set_ylabel("|G| relative to 0.1 Hz (dB)")
    axs[1].text(0.15, -3.9, "solid: harmonic sum · dashed: with the chopper-period average · diamonds: transient, relative to its "
                "lowest frequency", fontsize=7.8, color=MUTED)
    axs[2].set_ylim(-32, 3)
    axs[2].set_ylabel("Phase of G (°)")
    axs[2].set_xlabel("Frequency (Hz)")
    save(fig, "20_afe_baseband")


def fig_ota_bode():
    sm = summary("ota_summary", VIZ_ADC)
    fig = figure(13.0, 8.0, "ADC integrator OTAs: open-loop gain and loop gain",
                 "With their stage loads (RIN, DAC1 resistors, C1 / R21, C2, quantizer inputs, wiring) · OTA1 chopper stopped in "
                 "phase A · typical, 27 °C",
                 note="Solid: loaded open-loop gain A = −T/β; dashed: loop gain T by double injection at the summing node. "
                      "OTA1 phase B: the same within 0.01 dB and 0.1°.")
    axs = fig.subplots(2, 2, sharex=True, gridspec_kw=dict(height_ratios=[1.35, 1]))
    for j, (ota, files) in enumerate((("OTA1 (first integrator)", {"sch": "ota1_sch_A", "pex": "ota1_pex_A"}),
                                      ("OTA2 (second integrator)", {"sch": "ota2_sch", "pex": "ota2_pex"}))):
        axm, axp = axs[0, j], axs[1, j]
        for net, fn in files.items():
            r = rcsv(fn, VIZ_ADC)
            f = col(r, "f_hz")
            st = dict(color=NET[net]["color"], lw=1.6 if net == "pex" else 1.3)
            axm.plot(f, col(r, "A_db"), **st, label=f"{NET[net]['label']}, A")
            axm.plot(f, col(r, "T_db"), ls=(0, (5, 2.5)), **st, label=f"{NET[net]['label']}, T")
            axp.plot(f, col(r, "A_deg"), **st)
            axp.plot(f, col(r, "T_deg"), ls=(0, (5, 2.5)), **st)
        for ax in (axm, axp):
            logf(ax, 1, 1e9)
            vmark(ax, FS, "fs 1.024 MHz", 0.98) if ax is axm else ax.axvline(FS, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        axm.axhline(0, color=GRID2, lw=0.9)
        axp.axhline(-180, color=BAD, ls=(0, (4, 3)), lw=0.9)
        axm.set_title(ota, fontsize=10)
        axm.set_ylabel("dB")
        axp.set_ylabel("Phase (°)")
        axp.set_xlabel("Frequency (Hz)")
        axp.yaxis.set_major_locator(mticker.MultipleLocator(90))
        axp.set_ylim(-300, 100)
        axm.set_ylim(-60, 120)
        k = "ota1" if j == 0 else "ota2"
        p, s = sm[f"{k}_pex_A" if j == 0 else f"{k}_pex"], sm[f"{k}_sch_A" if j == 0 else f"{k}_sch"]
        lines = [f"A at DC {p['A_dc_db']:.1f} dB, unity gain {p['A_ugf_hz'] / 1e6:.3g} MHz",
                 f"T crossover {p['T_ugf_hz'] / 1e6:.3g} MHz, PM {p['PM_deg']:.1f}°, GM {p['GM_db']:.1f} dB",
                 f"(schematic: PM {s['PM_deg']:.1f}°, GM {s['GM_db']:.1f} dB)"]
        axm.text(0.98, 0.80, "Extracted\n" + "\n".join(lines), transform=axm.transAxes, ha="right", va="top", fontsize=7.8,
                 color=INK2, linespacing=1.5, bbox=dict(fc="white", ec="none", alpha=0.9))
    axs[0, 0].legend(loc="lower left", fontsize=7.8, ncols=2)
    save(fig, "21_ota_bode")


def fig_ntf():
    r = rcsv("adc_ntf_stf", VIZ_ADC)
    f = col(r, "f_hz")
    nt, ni = col(r, "ntf_db"), col(r, "ntf_ideal_db")
    lift = f[np.argmax(nt - ni < 1.0)]
    fig = figure(12.6, 6.6, "Modulator noise and signal transfer",
                 "Continuous-time 2nd-order loop as implemented: fs 1.024 MHz, 5-bit quantizer (linearized), NRZ DACs with their "
                 "delays, integrator leakage from the OTA DC gains",
                 note=minus(f"Ideal: infinite OTA gain. The integrators' leakage (OTA DC gains 70.2 and 104.2 dB) lifts the NTF by more "
                            f"than 1 dB only below {lift:.0f} Hz, where it is already under {np.interp(lift, f, nt):.0f} dB. "
                            "STF normalized to its DC value."))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.6, 1], height_ratios=[1, 1])
    ax = fig.add_subplot(gs[:, 0])
    ax.plot(f, col(r, "ntf_db"), color=ACCENT, lw=1.7, label="NTF")
    ax.plot(f, col(r, "ntf_ideal_db"), color=INK2, lw=1.2, ls=(0, (5, 2.5)), label="NTF, ideal integrators")
    ax.plot(f, col(r, "stf_db"), color=TEAL, lw=1.7, label="STF")
    logf(ax, 0.1, FS / 2)
    band(ax, label=True)
    i = np.argmin(abs(f - 100))
    ax.annotate(minus(f"NTF {col(r, 'ntf_db')[i]:.1f} dB at 100 Hz"), (f[i], col(r, "ntf_db")[i]), textcoords="offset points",
                xytext=(18, -16), fontsize=7.8, color=ACCENT, arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.6))
    ax.set_ylim(-260, 20)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("dB")
    ax.legend(loc="center right")
    ax.set_title("Magnitude", fontsize=10)
    a2 = fig.add_subplot(gs[0, 1])
    a2.plot(f, col(r, "stf_db"), color=TEAL, lw=1.6)
    logf(a2, 1e3, FS / 2)
    a2.set_ylim(-16, 1)
    a2.set_ylabel("dB")
    a2.set_title("STF near fs/2", fontsize=10)
    a3 = fig.add_subplot(gs[1, 1], sharex=a2)
    a3.plot(f, col(r, "stf_deg"), color=TEAL, lw=1.6)
    logf(a3, 1e3, FS / 2)
    a3.set_ylim(-190, 10)
    a3.yaxis.set_major_locator(mticker.MultipleLocator(45))
    a3.set_ylabel("Phase (°)")
    a3.set_xlabel("Frequency (Hz)")
    save(fig, "22_ntf_stf")


# ---------------------------------------------------------------- input impedance

def zin_data():
    r = rcsv("afe_zin_frozen_ac")
    out = {}
    for x in r:
        mode = "dm" if "-dm" in x["method"] else "cm"
        out.setdefault((x["netlist"], mode), []).append((float(x["f_hz"]), complex(float(x["re_ohm"]), float(x["im_ohm"]))))
    out = {k: (np.array([a for a, _ in v]), np.array([b for _, b in v])) for k, v in out.items()}
    tr = []
    if os.path.exists(os.path.join(VIZ, "afe_zin.csv")):
        for x in rcsv("afe_zin"):
            if "transient" in x["method"]:
                tr.append((x["netlist"], "dm" if "dm" in x["method"] else "cm", float(x["f_hz"]),
                           complex(float(x["re_ohm"]), float(x["im_ohm"]))))
    return out, tr


ZSTY = {("sch", "dm"): dict(color=INK2, ls=(0, (5, 2.5))), ("pex", "dm"): dict(color=ACCENT, ls="-"),
        ("sch", "cm"): dict(color="#94a3b8", ls=(0, (5, 2.5))), ("pex", "cm"): dict(color=TEAL, ls="-")}
ZLAB = {("sch", "dm"): "Schematic, differential", ("pex", "dm"): "Extracted, differential",
        ("sch", "cm"): "Schematic, common mode (per side)", ("pex", "cm"): "Extracted, common mode (per side)"}


def smith_grid(ax, lim=1.12):
    ax.set_aspect("equal")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.axis("off")
    rim = Circle((0, 0), 1, transform=ax.transData, fc="none", ec="none")
    ax.add_patch(rim)
    for rr in (0.2, 0.5, 1, 2, 5):
        ax.add_patch(Circle((rr / (1 + rr), 0), 1 / (1 + rr), fc="none", ec=HAIR, lw=0.8, zorder=1))
        ax.text((rr - 1) / (rr + 1) + 0.012, 0.012, f"{rr:g}", fontsize=6.8, color=MUTED, ha="left", va="bottom")
    for xx in (0.2, 0.5, 1, 2, 5):
        for sg in (1, -1):
            c = Circle((1, sg / xx), 1 / xx, fc="none", ec=HAIR, lw=0.8, zorder=1)
            ax.add_patch(c)
            c.set_clip_path(rim)
            g = (1j * sg * xx - 1) / (1j * sg * xx + 1)
            ax.text(1.07 * g.real, 1.07 * g.imag, minus(f"{sg * xx:+g}j"), fontsize=6.8, color=MUTED, ha="center", va="center")
    ax.plot([-1, 1], [0, 0], color=HAIR, lw=0.8, zorder=1)
    ax.add_patch(Circle((0, 0), 1, fc="none", ec=INK2, lw=1.0, zorder=2))
    ax.text(-1.03, 0, "0", fontsize=7.5, color=MUTED, ha="right", va="center")
    ax.text(1.03, 0.02, "∞", fontsize=9, color=MUTED, ha="left", va="bottom")
    ax.text(0, 1.1, "inductive", fontsize=7.5, color=MUTED, ha="center")
    ax.text(0, -1.13, "capacitive", fontsize=7.5, color=MUTED, ha="center", va="top")


def gamma(z, z0):
    zn = z / z0
    return (zn - 1) / (zn + 1)


def neg_re(zd, net):
    """Frequencies where the frozen differential input has Re Z < 0 (first and last)."""
    f, z = zd[(net, "dm")]
    m = z.real < 0
    return f[m][0], f[m][-1]


def fig_zin_smith():
    zd, tr = zin_data()
    lo, hi = neg_re(zd, "pex")
    lo_s = f"{lo:.0f} Hz" if lo < 1e3 else f"{lo / 1e3:.1f} kHz"
    fig = figure(13.0, 7.6, "AFE input impedance on Smith charts",
                 "Electrode-side impedance: lines frozen-phase AC (chopper stopped in phase A, an LTI reference), diamonds chopped "
                 "transient · typical, 27 °C, 100 Ω per leg · Γ = (Z − Z0)/(Z + Z0)",
                 note="Z0 is a chart normalization, not a line impedance: 100 MΩ puts the EEG band mid-chart; 50 Ω is the usual RF reference. "
                      f"Markers at decades of frequency; diamonds in each chart's range (DC on the left).\nFrom {lo_s} to {hi / 1e6:.0f} MHz "
                      "the frozen differential input has Re Z < 0, so its trace runs just outside |Γ| = 1 there.")
    axs = fig.subplots(1, 2)
    views = ((axs[0], 100e6, "Z0 = 100 MΩ, 1 Hz – 10 kHz", (1, 1e4), (1, 10, 100, 1e3, 1e4)),
             (axs[1], 50.0, "Z0 = 50 Ω, 1 MHz – 1 GHz", (1e6, 1e9), (1e6, 1e7, 1e8, 1e9)))
    for ax, z0, title, (f0, f1), marks in views:
        smith_grid(ax)
        ax.set_title(title, fontsize=10, loc="center")
        for key in (("sch", "cm"), ("pex", "cm"), ("sch", "dm"), ("pex", "dm")):
            f, z = zd[key]
            m = (f >= f0 * 0.999) & (f <= f1 * 1.001)
            g = gamma(z[m], z0)
            ax.plot(g.real, g.imag, lw=1.5 if key[0] == "pex" else 1.2, zorder=3, label=ZLAB[key], **ZSTY[key])
            for fm in marks:
                i = np.argmin(abs(np.log(f / fm)))
                gm = gamma(z[i], z0)
                ax.scatter([gm.real], [gm.imag], s=18, facecolor="white", edgecolor=ZSTY[key]["color"], linewidth=1.1, zorder=4)
                if key == ("pex", "dm"):
                    ax.annotate(hz(fm) + ("Hz" if fm >= 1e3 else " Hz"), (gm.real, gm.imag), textcoords="offset points", xytext=(7, -2), fontsize=7.4,
                                color=ACCENT, zorder=6, bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))
        dm = []
        for net, mode, f, z in tr:
            if (f0 * 0.999 <= f <= f1 * 1.001) or (f == 0 and f0 <= 1):
                g = gamma(z, z0)
                ax.scatter([g.real], [g.imag], s=46, marker="D", color=ZSTY[(net, mode)]["color"], zorder=5)
                if mode == "dm":
                    dm.append((abs(z), g))
        if dm and z0 > 1e6:
            za, zb = min(a for a, _ in dm), max(a for a, _ in dm)
            ax.annotate(f"chopped differential:\n|Z| {za / 1e6:.1f}–{zb / 1e6:.1f} MΩ, far below Z0", xy=(-0.97, 0.0), xytext=(-0.78, 0.34),
                        fontsize=7.4, color=INK2, zorder=6, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8),
                        bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))
    axs[0].legend(loc="upper left", bbox_to_anchor=(-0.02, 1.02), fontsize=7.8)
    save(fig, "23_zin_smith")


def fig_zin_bode():
    zd, tr = zin_data()
    zdc = {net: z.real for net, mode, f, z in tr if mode == "dm" and f == 0}   # chopped differential at DC
    rs, rp = minus(f"{zdc['sch'] / 1e3:.0f}"), minus(f"{zdc['pex'] / 1e6:+.1f}")
    fig = figure(12.6, 7.8, "AFE input impedance against frequency",
                 "Electrode side: lines frozen-phase AC (chopper stopped in phase A, an LTI reference), diamonds chopped transient · "
                 "typical, 27 °C, 100 Ω per leg",
                 note="Differential: Z = (V_ELP − V_ELN)/I_ELP with a differential drive; common mode: V_ELP/I_ELP per side with both "
                      "electrodes driven. The chopped input's switched-capacitor\naction is missing from the frozen-phase circuit; "
                      "chopped values come from transient runs (diamonds; DC drawn at the left edge). The schematic's differential phase "
                      f"near −180° is a negative resistance ({rs} kΩ: the Cpf trim 8\ncancels the "
                      f"switched-capacitor current 1 % too much); the extracted chip is {rp} MΩ (DC).")
    axs = fig.subplots(2, 1, sharex=True, gridspec_kw=dict(height_ratios=[1.4, 1]))
    for key in (("sch", "dm"), ("pex", "dm"), ("sch", "cm"), ("pex", "cm")):
        f, z = zd[key]
        axs[0].plot(f, abs(z), lw=1.6 if key[0] == "pex" else 1.2, label=ZLAB[key], **ZSTY[key])
        axs[1].plot(f, np.degrees(np.angle(z)), lw=1.6 if key[0] == "pex" else 1.2, **ZSTY[key])
    for net, mode, f, z in tr:
        axs[0].scatter([max(f, 0.3)], [abs(z)], s=46, marker="D", color=ZSTY[(net, mode)]["color"], zorder=5)
        axs[1].scatter([max(f, 0.3)], [np.degrees(np.angle(z))], s=46, marker="D", color=ZSTY[(net, mode)]["color"], zorder=5)
    for ax in axs:
        logf(ax, 0.2 if tr else 1, 1e9)
        band(ax, label=ax is axs[0])
        vmark(ax, FCH, "chopper 128 kHz", 0.98) if ax is axs[0] else ax.axvline(FCH, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    axs[0].set_yscale("log")
    axs[0].set_ylim(0.5, 2e10)
    axs[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: (hz(v) if v >= 1e3 else f"{v:g} ") + "Ω"))
    axs[0].set_ylabel("|Z|")
    h, _ = axs[0].get_legend_handles_labels()
    if tr:
        h.append(Line2D([], [], marker="D", ls="", color=MUTED, label="Chopped transient"))
        axs[0].text(0.3, 2.2e8, "DC", fontsize=7.5, color=MUTED, ha="center", va="bottom")
    axs[0].legend(handles=h, loc="lower left", fontsize=8)
    axs[1].set_ylim(-190, 10)
    axs[1].yaxis.set_major_locator(mticker.MultipleLocator(45))
    axs[1].axhline(-90, color=GRID2, lw=0.9)
    axs[1].set_ylabel("Phase of Z (°)")
    axs[1].set_xlabel("Frequency (Hz)")
    save(fig, "24_zin_bode")


# ---------------------------------------------------------------- start-up of the AFE, from power-on

SU = os.path.join(PEX, "runs", "startup")              # afe_startup.py runs (power-on, pads, board, real bias)
AFE_C = os.path.join(PEX, "runs", "afe_top_c", "afe_top_pex.spice")
TCH = 1 / FCH
UNIT_MV = 60e-15 * 3.3 / 636e-12 * 1e3   # offset-DAC step, electrode-referred (pex_afe.py)
NBITS = {1: 7, 2: 8, 3: 9, 4: 10}
SUPPLIES = {"AVDD", "AVSS", "AVDD_CLK"}
SETTLE_MV = 1.0                          # settled: within 1 mV of the final output (3.6 µV at the electrodes)
SU_SAVE = ("vdd avssc dvddc dvssc cm vrefp vrefn vbn vbcm bln blp gp afe_rst outp outn opi oni inp inn elp eln "
           "iavdd idvdd").split()
CVCM = [(10e-9, "10 nF"), (100e-9, "100 nF"), (1e-6, "1 µF")]
RAMP3 = ["#86b6ef", "#2a78d6", "#0d366b"]   # one-hue ordinal steps (validated, light surface)


SU_ALIAS = {"vdd": "avdd_afei", "avssc": "avss_afei", "cm": "vcm_afe", "vrefp": "vrefp_adc", "vrefn": "vrefn_adc",
            "vbn": "vbn_afe", "vbcm": "vbcm_afe", "bln": "bln_afe", "blp": "blp_afe", "outp": "outp_adc", "outn": "outn_adc"}


@functools.lru_cache(maxsize=4)
def su_load(run):
    """An afe_startup.py run: its vectors by name (time t; qo, the running integral of OUTP - OUTN) and meta.json.
    Runs on the chip wiring (meta.json lists its vectors) also answer to the names of the earlier bench (SU_ALIAS:
    the AFE's own supply after its rails, VBN at the AFE, OUTP / OUTN at the ADC)."""
    d = os.path.join(SU, run)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    names = meta.get("vectors") or ((["qo", "qa"] if x.shape[1] // 2 == len(SU_SAVE) + 2 else []) + SU_SAVE)
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(names)}
    v["t"] = x[:, 0]
    for old, new in SU_ALIAS.items():
        if old not in v and new in v:
            v[old] = v[new]
    if "qo" not in v:
        vo = v["outp"] - v["outn"]
        v["qo"] = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(v["t"]))])
    return v, meta


def chop_means(v, t0, t1):
    """OUTP - OUTN averaged over each chopper period from t0 to t1: (centres, means)."""
    edges = t0 + TCH * np.arange(int((t1 - t0) / TCH) + 1)
    return 0.5 * (edges[1:] + edges[:-1]), np.diff(np.interp(edges, v["t"], v["qo"])) / TCH


def period_mean(t, y, tg):
    """y averaged over the chopper period that ends at each time of tg (from its running integral)"""
    q = np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])
    return (np.interp(tg, t, q) - np.interp(tg - TCH, t, q)) / TCH


def read_raw(path):
    """ngspice binary raw file (real) -> dict name -> array (as e2e_startup.read_raw)"""
    blob = open(path, "rb").read()
    i = blob.index(b"Binary:\n")
    head = blob[:i].decode().splitlines()
    nv = int(next(h for h in head if h.startswith("No. Variables:")).split(":")[1])
    k = head.index("Variables:")
    names = [h.split()[1].lower() for h in head[k + 1:k + 1 + nv]]
    data = np.frombuffer(blob[i + 8:], dtype="<f8")
    data = data[:data.size // nv * nv].reshape(-1, nv)
    return {n: data[:, j] for j, n in enumerate(names)}


def su_probe(run):
    """The probe rerun of a start run (runs/startup/<run>/probe/: the same deck to 5.1 or 5.4 ms with the simulator's own
    time points kept, probe.raw), for exact chopper-period averages of VBN and the AVDD current. Averaged from tr.csv's
    100 ns samples they carry a pattern that repeats every 8 periods (62.5 µs, where the grid's phase against the
    chopper edges repeats: 0.11 mV and 0.05 mA p-p), which is not in the circuit. None if there is no probe."""
    p = os.path.join(SU, run, "probe", "probe.raw")
    if not os.path.exists(p):
        return None
    r = read_raw(p)
    return {"t": r["time"], "vbn": r["v(vbn_afe)"] - r["v(avss_afei)"], "iavdd": -r["i(vavdd)"]}


def settle_time(t, x, final, tol):
    """first time after which |x - final| stays below tol (t[0] if it always does)"""
    late = np.nonzero(np.abs(x - final) >= tol)[0]
    return t[late[-1] + 1] if len(late) and late[-1] + 1 < len(t) else (t[0] if not len(late) else np.nan)


def fig_power_on():
    runs = {c: su_load(f"power_c{c:g}_v3.3_typical_+0mV{SRC['startup']}") for c, _ in CVCM}
    v10, meta = runs[10e-9]
    tramp = meta["tramp"]
    afe = v10["avdd_afei"] - v10["avss_afei"]
    bias = v10["avdd_bias"] - v10["avss_bias"]
    vbn_b = v10["vbn_bias"] - v10["avss_bias"]
    vbn_a = v10["vbn_afe"] - v10["avss_afei"]
    fig = figure(12.8, 13.6, "Power-on: supplies, bias and VCM, the AFE held in reset",
                 "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring (pad cells, grid, decoupling, routes), every pad "
                 f"of the ring, the board (assumed) and bond wires · typical, 27 °C · supplies ramp in {tramp * 1e3:g} ms",
                 note="VCM is the midpoint of the reference divider in eeg_bias (2 × 100 kΩ) and charges the capacitor on the VCM pad "
                      "(a board choice): τ ≈ 50 kΩ × C. RESET_N is held low throughout, so the choppers\nare idle and the AFE "
                      f"and the ADC stay in reset; the ADC is its supply current ({meta['iadc'] * 1e3:g} mA), reference load and input "
                      f"resistors. afe_top's own rails to its tails are a lumped estimate ({meta['rafe'][0]:g} / {meta['rafe'][1]:g} Ω AVSS / AVDD).")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1])
    ax = fig.add_subplot(gs[0, 0])
    t = v10["t"] * 1e3
    for y, lab, c, ls in ((afe, "AVDD − AVSS at the AFE's tails", INK2, "-"),
                          (v10["dvddc"] - v10["dvssc"], "DVDD − DVSS (pad ring)", LIGHT, (0, (4, 2))),
                          (v10["vrefp_adc"] - v10["vrefn_adc"], "VREFP − VREFN at the ADC", TEAL, "-"),
                          (vbn_a, "VBN at the AFE (AFE tail bias)", ACCENT, "-"),
                          (v10["bln_afe"] - v10["avss_afei"], "BLN at the AFE (booster bias)", ACCENT, (0, (5, 2)))):
        ax.plot(t, y, color=c, ls=ls, lw=1.5, label=lab)
    ax.axvline(tramp * 1e3, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(tramp * 1e3, 1.0, " supplies at full scale", transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, va="top")
    tf = np.arange(0, 2e-3, 1e-7)                      # the run keeps 10 µs points: on them this would round up to the next one
    tb = settle_time(tf, np.interp(tf, v10["t"], vbn_a), vbn_a[-1], 0.01 * vbn_a[-1])
    ax.annotate(f"VBN within 1 % at {tb * 1e3:.2f} ms", (tb * 1e3, vbn_a[-1]), textcoords="offset points", xytext=(20, -12),
                fontsize=7.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    ax.set_xlim(0, 2.0)
    ax.set_ylim(-0.1, 3.6)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("V")
    ax.set_title("Supplies and bias during the ramp (VCM capacitor 10 nF)", fontsize=9.5)
    ax.legend(loc="center right", fontsize=7.5)
    ax = fig.add_subplot(gs[0, 1])
    for (c, lab), col in zip(CVCM, RAMP3):
        v, _ = runs[c]
        fin = v["cm"][-1]
        ts = settle_time(v["t"], v["cm"], fin, 1e-3)
        ax.plot(v["t"] * 1e3, v["cm"], color=col, lw=1.6, label=f"{lab}: within 1 mV at {ts * 1e3:.3g} ms")
        ax.plot([ts * 1e3], [v["cm"][np.searchsorted(v["t"], ts)]], "o", color=col, ms=5)
    ax.set_xscale("log")
    ax.set_xlim(0.05, runs[1e-6][0]["t"][-1] * 1e3)
    ax.set_ylim(0, 1.8)
    ax.set_xlabel("Time from power-on (ms, log scale)")
    ax.set_ylabel("VCM (V)")
    ax.set_title(f"VCM for the three VCM capacitors (final {fin:.3f} V)", fontsize=9.5)
    ax.legend(loc="upper left", fontsize=8)
    ax = fig.add_subplot(gs[1, 0])
    ax.plot(t, vbn_b * 1e3, color=INK2, lw=1.5, label="VBN − AVSS at the bias block (what it makes)")
    ax.plot(t, vbn_a * 1e3, color=ACCENT, lw=1.5, label="VBN − AVSS at the AFE's tails (what they get)")
    ax.annotate(f"{(vbn_b[-1] - vbn_a[-1]) * 1e3:.1f} mV less", (t[-1], vbn_a[-1] * 1e3), textcoords="offset points",
                xytext=(-4, -14), ha="right", fontsize=8, color=ACCENT)
    ax.set_xlim(0, v10["t"][-1] * 1e3)
    ax.set_ylim(780, 870)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("mV")
    ax.set_title("The AFE's tail bias: the bias block's VBN against its own AVSS, seen from the AFE's", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[1, 1])
    up = v10["t"] >= 1.2 * tramp                       # after the ramp: the drops, not the ramp itself
    for y, lab, c, ls in ((v10["avss_afei"], "AVSS at the AFE's tails, above the board's ground", ACCENT, "-"),
                          (v10["avss_bias"], "AVSS at the bias block, above the board's ground", INK2, "-"),
                          (meta["vdd"] - v10["avdd_afei"], "AVDD at the AFE's tails, below the regulator", ACCENT, (0, (4, 2))),
                          (meta["vdd"] - v10["avdd_bias"], "AVDD at the bias block, below the regulator", INK2, (0, (4, 2)))):
        ax.plot(t[up], y[up] * 1e3, color=c, ls=ls, lw=1.4, label=lab)
    ax.set_xlim(0, v10["t"][-1] * 1e3)
    ax.set_ylim(0, 75)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("mV")
    ax.set_title(f"Where the supply goes (AFE {afe[-1]:.3f} V, bias block {bias[-1]:.3f} V at the end)", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    ax = fig.add_subplot(gs[2, 0])
    ax.plot(t, (v10["outp"] - v10["outn"]) * 1e3, color=ACCENT, lw=1.4, label="OUTP − OUTN at the ADC (AFE in reset)")
    ax.plot(t, (v10["opi"] - v10["oni"]) * 1e3, color=TEAL, lw=1.2, ls=(0, (5, 2)), label="OPI − ONI (amplifier output)")
    ax.axhline(0, color=GRID2, lw=0.9)
    ax.set_xlim(0, v10["t"][-1] * 1e3)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("mV")
    ax.set_title("AFE outputs during power-on (differential)", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[2, 1])
    ax.plot(t, -v10["iavdd"] * 1e3, color=INK2, lw=1.4, label="AVDD regulator (board capacitors included)")
    ax.plot(t, -v10["idvdd"] * 1e3, color=LIGHT, lw=1.2, ls=(0, (4, 2)), label="DVDD regulator (pad ring; no digital load)")
    ax.set_xlim(0, 2.0)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("mA")
    ax.set_title(f"Supply currents (AVDD settles at {-v10['iavdd'][-1] * 1e3:.1f} mA, ADC included)", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    save(fig, "25_power_on")


def su_gain():
    """The AFE's chopped gain at 1 kHz, extracted (viz_data.py's transient check)."""
    rows = [r for r in csv.DictReader(open(os.path.join(VIZ, "afe_baseband_transient.csv"), encoding="utf-8"))
            if r["netlist"] == "pex" and float(r["f_hz"]) == 1000]
    return 10 ** (float(rows[0]["gain_db"]) / 20)


def su_release(name):
    """A start run: chopper-period means of OUTP - OUTN from RESET_N to the end, the time axis from the AFE
    release; the final value (mean of the last 16 periods), its drift over them, the settling times to
    1 mV and 0.1 mV, the bias start-up time (VBN within 1 %), the largest |OPI - ONI|, the AFE's own
    supply at the end and whether ngspice reached tstop (None if the run is not there)."""
    d = os.path.join(SU, name)
    if not os.path.exists(os.path.join(d, "tr.csv")):
        return None
    log = open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()
    v, meta = su_load(name)
    done = "timestep too small" not in log.lower() and v["t"][-1] >= meta["tstop"] * (1 - 1e-6)
    # periods from a quarter period after the chopper's first edge: qo is on a 100 ns grid (78.125 points per period),
    # and a boundary on an edge cuts through the edge's transient at a phase that repeats every 8 periods (62.5 µs:
    # 1.4 µV p-p per period at 0 mV, up to 0.6 mV with the offset DAC on, none of it in the circuit)
    tc, m = chop_means(v, meta["t_reset"] + TCH / 4, v["t"][-1])
    x = tc - meta["t_afe"]
    tail = m[-16:]
    fin = tail.mean()
    after = x > 0
    pre = v["t"] < meta["t_reset"]                     # the bias start-up: power-on to RESET_N
    vb = (v["vbn"] - v["avssc"])[pre]
    vamax = float(log.split("vamax =")[1].split()[0]) if "vamax =" in log else np.nan
    return dict(name=name, meta=meta, done=done, x=x, m=m, final=fin, drift=tail[-1] - tail[0],
                t1=settle_time(x[after], m[after], fin, 1e-3), t01=settle_time(x[after], m[after], fin, 1e-4),
                tbias=settle_time(v["t"][pre], vb, vb[-1], 0.01 * vb[-1]), vamax=vamax,
                peak=np.max(np.abs(m[after] - fin)), iavdd=-v["iavdd"][-1], vafe=(v["vdd"] - v["avssc"])[-1])


SU_IB = "_ib3" + SRC["startup"]         # the firmware writes AFE_IBIAS = 3 (afe_startup.py --ibias 3)


def su_spike(v, meta):
    """The largest |VBN - its chopper-period mean| of a probe rerun with the choppers running: the transient at the edges."""
    a = v["t"] > meta["t_reset"] + 2 * TCH
    return np.max(np.abs(v["vbn"][a] - period_mean(v["t"], v["vbn"], v["t"][a])))


def fig_startup():
    gain = su_gain()
    typ = {vdd: su_release(f"start_c1e-08_v{vdd:g}_typical_+0mV_afe5ms{SU_IB}") for vdd in (3.3, 3.135, 3.465)}
    mc = [su_release(f"start_c1e-08_v3.3_mc{s}_+0mV_afe5ms{SU_IB}") for s in range(1, 31)]
    ran = [r for r in mc if r is not None]
    ok = [r for r in ran if r["done"]]
    if not ok:
        print("fig_startup: no Monte Carlo runs yet")
    t0 = typ[3.3]
    # the trim write: the AFE's tail bias and the AVDD current from RESET_N to the release (typical)
    seq = [("code 3, written by the firmware", f"start_c1e-08_v3.3_typical_+0mV_afe5ms{SU_IB}", ACCENT, "-"),
           ("code 3 from power-on (for comparison)", f"start_c1e-08_v3.3_typical_+0mV_afe5ms_ib3static{SRC['startup']}", INK2, (0, (5, 2.5))),
           ("code 2 (the reset value) kept", f"start_c1e-08_v3.3_typical_+0mV_afe5ms{SRC['startup']}", LIGHT, (0, (1, 1.5)))]
    runs = []
    for lab, n, c, ls in seq:
        p = su_probe(n)
        if p is None:
            print(f"fig_startup: no probe rerun of {n} (the bottom row needs its exact averages)")
            continue
        with open(os.path.join(SU, n, "meta.json"), encoding="utf-8") as f:
            runs.append((lab, p, json.load(f), c, ls))
    spike = max((su_spike(v, meta) for lab, v, meta, _, _ in runs if lab != seq[0][0]), default=np.nan)   # not across the write's own step
    ends = "–".join(sorted({f"{v['t'][-1] * 1e3:.1f}" for _, v, *_ in runs}))
    fig = figure(12.8, 14.6, "Start-up from power-on: the AFE released with the electrodes at 0 V",
                 "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, every pad of the ring, the board (assumed), bond wires · "
                 "27 °C · supplies ramp in 1 ms · RESET_N at 4.8 ms, AFE_IBIAS = 3 written 20 µs later, AFE_RST released at 5 ms · "
                 "VCM capacitor 10 nF",
                 note=f"Monte Carlo: {len(ok)} of 30 seeds reached the end ({len(ran) - len(ok)} stopped, {30 - len(ran)} not run); "
                      "each draws the PDK's global process and per-device mismatch, with stand-ins for the MIM and poly-resistor "
                      "mismatch (1.41 and 3 %·µm),\nand releases AFE_RST at a random phase of the chopper. The Monte Carlo and "
                      "±5 % runs end 1 ms after the release. Output values are chopper-period means; electrode-referred = output / "
                      f"{gain:.1f} (the AFE's chopped gain). Bottom row: averages over the\npreceding chopper period (the "
                      f"instantaneous VBN and AVDD current carry transients at every chopper edge, VBN up to {spike * 1e3:.0f} mV), from the "
                      f"simulator's own time points (each deck rerun to {ends} ms).")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1])
    ax = fig.add_subplot(gs[0, 0])
    for r in ok:
        ax.plot(r["x"] * 1e3, r["m"] * 1e3, color=LIGHT, lw=0.6, alpha=0.7)
    for vdd, ls in ((3.135, (0, (4, 2))), (3.465, (0, (1, 1.5))), (3.3, "-")):
        r = typ[vdd]
        if r and r["done"]:
            ax.plot(r["x"] * 1e3, r["m"] * 1e3, color=ACCENT if vdd == 3.3 else INK2, ls=ls, lw=1.6 if vdd == 3.3 else 1.2,
                    label=f"typical, AVDD {vdd:g} V")
    ax.plot([], [], color=LIGHT, lw=0.8, label="Monte Carlo seeds")
    ax.axvline(0, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(0, 1.0, " AFE_RST released", transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, va="top")
    ax.set_xlim(-0.2, 3.0)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    ax.set_title("AFE output, chopper-period means", fontsize=9.5)
    ax.legend(loc="center right", fontsize=8)              # the curves sit near the bottom of the axis
    ax = fig.add_subplot(gs[0, 1])
    for r in ok:
        a = r["x"] > 0
        ax.semilogy(r["x"][a] * 1e3, np.abs(r["m"][a] - r["final"]) * 1e3, color=LIGHT, lw=0.6, alpha=0.7)
    if t0 and t0["done"]:
        a = t0["x"] > 0
        ax.semilogy(t0["x"][a] * 1e3, np.abs(t0["m"][a] - t0["final"]) * 1e3, color=ACCENT, lw=1.5)
    for y, lab in ((1.0, f"1 mV ({1e3 / gain:.1f} µV at the electrodes)"), (0.1, f"0.1 mV ({1e2 / gain:.2f} µV)")):
        ax.axhline(y, color=MUTED, lw=0.9, ls=(0, (4, 3)))
        ax.annotate(lab, (2.98, y), xytext=(0, 1.5), textcoords="offset points", fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax.set_xlim(0, 3.0)
    ax.set_ylim(1e-5, 10)                              # 10 nV at the output: above the simulator's scatter (about 3 nV)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("|output − final| (mV)")
    ax.set_title("Settling to the final value (mean of the last 16 periods)", fontsize=9.5)
    ax = fig.add_subplot(gs[1, 0])
    fin = np.array([r["final"] for r in ok]) * 1e3
    if len(fin):
        ax.plot(np.sort(fin), (np.arange(len(fin)) + 0.5) / len(fin), "o", color=LIGHT, ms=4.5, label="Monte Carlo seeds")
    for vdd, mk in ((3.3, "D"), (3.135, "v"), (3.465, "^")):
        r = typ[vdd]
        if r and r["done"]:
            ax.plot([r["final"] * 1e3], [0.5], mk, color=ACCENT if vdd == 3.3 else INK2, ms=6, label=f"typical, {vdd:g} V")
    ax.set_xlabel("Final OUTP − OUTN (mV)")
    ax.set_ylabel("Fraction of seeds")
    ax.set_ylim(0, 1)
    if len(fin):
        sd = fin.std(ddof=1) if len(fin) > 1 else 0.0
        ax.set_title(f"Residual output offset: mean {fin.mean():+.3f} mV ({fin.mean() / gain * 1e3:+.2f} µV at the electrodes), "
                     f"σ {sd:.3f} mV ({sd / gain * 1e3:.2f} µV)".replace("-", "−"), fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[1, 1])
    for r in ok:
        a = r["x"] < 0.1e-3
        ax.plot(r["x"][a] * 1e6, r["m"][a] * 1e3, "-", color=LIGHT, lw=0.7, alpha=0.8)
    for vdd, ls in ((3.135, (0, (4, 2))), (3.465, (0, (1, 1.5))), (3.3, "-")):
        r = typ[vdd]
        if r and r["done"]:
            a = r["x"] < 0.1e-3
            ax.plot(r["x"][a] * 1e6, r["m"][a] * 1e3, ls=ls, color=ACCENT if vdd == 3.3 else INK2, lw=1.5 if vdd == 3.3 else 1.1,
                    marker="o", ms=2.5)
    ax.axvline(0, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.set_xlim(-30, 100)
    ax.set_xlabel("Time from the AFE release (µs)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    t1 = np.array([r["t1"] for r in ok]) * 1e6
    t01 = np.array([r["t01"] for r in ok]) * 1e6
    ax.set_title("The release, one chopper period (7.8 µs) per point", fontsize=9.5)
    if len(ok) and t0 and t0["done"]:
        sb = np.array([r["tbias"] for r in ok]) * 1e3
        va = np.array([r["vamax"] for r in ok]) * 1e3
        ax.text(0.99, 0.45, f"Settled to 1 mV: Monte Carlo {np.nanmax(t1):.0f} µs at most, to 0.1 mV {np.nanmax(t01):.0f} µs at most\n"
                f"Bias (VBN within 1 %): typical {t0['tbias'] * 1e3:.2f} ms, Monte Carlo {sb.min():.2f}–{sb.max():.2f} ms from power-on\n"
                f"Largest |OPI − ONI|: typical {t0['vamax'] * 1e3:.1f} mV, Monte Carlo up to {va.max():.1f} mV",
                transform=ax.transAxes, fontsize=7.5, color=MUTED, ha="right", va="center")
    ax_b, ax_i = fig.add_subplot(gs[2, 0]), fig.add_subplot(gs[2, 1])
    avg = {}
    for lab, v, meta, c, ls in runs:
        tr = meta["t_reset"]
        tg = np.arange(tr - 60e-6, meta["t_afe"] + 60e-6, 0.25e-6)
        vb, ia = period_mean(v["t"], v["vbn"], tg), period_mean(v["t"], v["iavdd"], tg)
        avg[lab] = (tg, vb, meta)
        ax_b.plot((tg - tr) * 1e6, vb * 1e3, color=c, ls=ls, lw=1.6, label=lab)
        ax_i.plot((tg - tr) * 1e6, ia * 1e3, color=c, ls=ls, lw=1.6,
                  label=f"{lab}: {np.interp(meta['t_afe'], tg, ia) * 1e3:.1f} mA")
    for ax in (ax_b, ax_i):
        for xv, lab, y in ((0, "RESET_N: choppers start", 1.0), (20, "AFE_IBIAS = 3 written", 0.93), (200, "AFE_RST released", 1.0)):
            ax.axvline(xv, ymax=y, color=MUTED, lw=0.8, ls=(0, (1, 2)))
            ax.text(xv, y, " " + lab, transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, va="top")
        ax.set_xlim(-60, 260)
        ax.set_xlabel("Time from RESET_N (µs)")
    if runs and runs[0][2].get("t_write"):
        tg, vb, meta = avg[runs[0][0]]
        tw = meta["t_reset"] + meta["t_write"]
        a = (tg > tw) & (tg < meta["t_afe"])
        rel = np.interp(meta["t_afe"], tg, vb)
        ts = settle_time(tg[a], vb[a], rel, 1e-3 * rel) - tw
        ax_b.annotate(f"within 0.1 % of its value at the release\n{ts * 1e6:.1f} µs after the write (one averaging period)",
                      ((tw + ts - meta["t_reset"]) * 1e6, rel * 1e3), textcoords="offset points", xytext=(14, -30),
                      fontsize=7.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
        if len(runs) > 1:
            tg2, vb2, m2 = avg[runs[1][0]]
            ref = np.interp(m2["t_afe"], tg2, vb2)
            ax_b.set_title(f"Tail bias VBN − AVSS: {rel * 1e3:.2f} mV at the release, {ref * 1e3:.2f} mV with code 3 from power-on",
                           fontsize=9.5)
    mid = (110 + 60) / 320                             # the middle of the write and the release: no dotted line through the text
    ax_b.set_ylim(814, 848)
    ax_b.set_ylabel("Chopper-period average (mV)")
    ax_b.legend(loc="center", bbox_to_anchor=(mid, 0.5), fontsize=8)
    ax_i.set_ylim(23, 29.5)
    ax_i.set_ylabel("Chopper-period average (mA)")
    ax_i.set_title("AVDD current from the regulator (the ADC's 4.7 mA included); values at the release", fontsize=9.5)
    ax_i.legend(loc="center", bbox_to_anchor=(mid, 0.5), fontsize=8)
    save(fig, "26_startup")


VIN_DC = [10, 20, 30, 40, 50, 300]                     # electrode DC offsets of the DC-input runs (mV)
RAMP6 = ["#c7dbf7", "#9cc0ef", "#6d9fe3", "#3f7bd0", "#1f5aa8", "#0d366b"]   # one-hue ordinal steps


def dac_range(vin):
    return next(r for r, full in ((1, 39), (2, 79), (3, 159), (4, 318)) if abs(vin) <= full)


def su_dc_alts(vin):
    """The finished DC-input runs for vin with a code of their own (_m<M>): {M: su_release}."""
    base = f"start_c1e-08_v3.3_typical_{vin:+g}mV"
    alt = [n for n in os.listdir(SU) if n.startswith(base + "_m") and n.endswith("_afe5ms" + SU_IB)]
    rel = ((int(n[len(base) + 2:].split("_")[0]), su_release(n)) for n in alt)
    return {m: r for m, r in rel if r and r["done"]}


def su_dc_run(vin):
    """The DC-input run for vin with the code the firmware's search settles on: of the runs of
    su_dc_alts, the one that leaves the smallest output; else the nominal code round(vin / step);
    (name, M)."""
    alts = su_dc_alts(vin)
    if alts:
        m = min(alts, key=lambda k: abs(alts[k]["final"]))
        return alts[m]["name"], m
    base = f"start_c1e-08_v3.3_typical_{vin:+g}mV"
    return base + "_afe5ms" + SU_IB, min(int(round(abs(vin) / UNIT_MV)), 2 ** NBITS[dac_range(vin)] - 1)


def dac_weights():
    """The offset DAC's bit weights in the extraction, fF, the mean of its two halves: {(bit, range): weight}. A bit weighs its
    MIM (area and perimeter, PDK cap_mim_2f0ff) plus the wiring from what moves with its plate (the driver's side, the ppoly
    segments, the plate) to the input and to the top plates its range connects: a parked top plate does not reach the input."""
    cap, res, mim = {}, {}, {}
    for t in (ln.split() for ln in open(AFE_C, encoding="utf-8")):
        if t and t[0].startswith("C") and len(t) >= 4:
            cap[frozenset(t[1:3])] = cap.get(frozenset(t[1:3]), 0.0) + float(t[3]) * 1e15
        elif "ppolyf_u_1k" in t:
            res.setdefault(t[1], set()).add(t[2])
            res.setdefault(t[2], set()).add(t[1])
        elif "cap_mim_2f0ff" in t:
            w, l = (float(re.search(k + r"=([\d.]+)u", " ".join(t)).group(1)) for k in ("c_width", "c_length"))
            mim[t[2]] = mim.get(t[2], 0.0) + 1.99 * w * l + 0.2383 * 2 * (w + l)
    weights = {}
    for bit in range(10):
        for rng in range(1, 5):
            parts = []
            for side, top in (("P", "INP"), ("N", "INN")):
                nodes, todo = {f"OD{side}.H.D{side}{bit}", f"OD{side}.H.B{side}{bit}"}, [f"OD{side}.H.D{side}{bit}"]
                while todo:
                    for n in res.get(todo.pop(), ()):
                        if n not in nodes:
                            nodes.add(n)
                            todo.append(n)
                tops = [top] + [f"OD{side}.H.T{side}{g}" for g in range(rng)]
                parts.append(mim[f"OD{side}.H.B{side}{bit}"] + sum(c for pair, c in cap.items() for n in tops
                                                                   if n in pair and (pair - {n}) & nodes))
            weights[bit, rng] = np.mean(parts)
    return weights


def dac_fit():
    """The DC runs against the bit weights: output = g × (offset − Σ weights × supply / Cin), by least squares over every finished
    run. g is the gain with the DAC on: 15 MCLK of blanking, where su_gain() has 7. (g, Cin in pF, the largest misfit at the
    electrodes in µV, the number of runs)"""
    w = dac_weights()
    rows = []
    for vin in VIN_DC:
        alts = su_dc_alts(vin)
        if not alts:
            name, m = su_dc_run(vin)
            alts = {m: su_release(name)}
        rows += [(vin, sum(w[k, dac_range(vin)] for k in range(10) if (m >> k) & 1) * r["vafe"], r["final"] * 1e3)
                 for m, r in alts.items() if r and r["done"]]
    vin, q, y = np.array(rows).T
    g, h = np.linalg.lstsq(np.column_stack([vin, -q]), y, rcond=None)[0]
    return g, g / h, np.max(np.abs(y - (g * vin - h * q))) / g * 1e3, len(rows)


def fig_dc_input():
    gain, cin, misfit, nruns = dac_fit()
    runs = {}
    for vin in VIN_DC:
        name, m = su_dc_run(vin)
        r = su_release(name)
        if r and r["done"]:
            runs[vin] = (r, m)
    vafe = np.mean([r["vafe"] for r, _ in runs.values()]) if runs else 3.3
    step = UNIT_MV * vafe / 3.3                        # the DAC's unit swings the AFE's own supply
    dac = [100 * ((vin - r["final"] / gain * 1e3) / (m * UNIT_MV * r["vafe"] / 3.3) - 1) for vin, (r, m) in runs.items()]
    est = ""
    if 300 in runs:
        left = su_dc_alts(300)                         # what each code tried leaves, the evidence for the one the search takes
        vals = ", ".join(minus(f"{left[k]['final'] / gain * 1e6:+.0f}") for k in sorted(left))
        est = (f", so at 300 mV the search settles on {runs[300][1]}, where the estimate would take {round(300 / step)} "
               f"({', '.join(map(str, sorted(left)))} leave {vals} µV)")
    weights = (f" The extraction's bit weights (each MIM plus its wiring to the top plates the range connects) and an input of "
               f"{cin:.1f} pF reproduce all {nruns} runs within {max(1, np.ceil(misfit)):.0f} µV.")
    fig = figure(12.8, 9.8, "Electrode DC offset from power-on, the offset DAC set as the firmware leaves it",
                 "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires · typical, 27 °C, AVDD 3.3 V · "
                 "the offset present from power-on · RESET_N at 4.8 ms, AFE_IBIAS = 3 written 20 µs later, AFE_RST released at 5 ms · "
                 "VCM capacitor 10 nF",
                 note=f"The DAC is static: its range and magnitude M are written before the release (range 1 to ±39 mV, 2 to ±79, "
                      f"3 to ±159, 4 to ±318 mV). One step is a 60 fF unit swung across the AFE's supply into the 636 pF input\n"
                      f"capacitor: {UNIT_MV:.3f} mV at 3.3 V, {step:.3f} mV at the {vafe:.3f} V the AFE has on the chip; M is the code "
                      f"the firmware's search settles on (the code that leaves the least). The DAC differs from M × one step by "
                      f"{minus(f'{min(dac):+.2f}')} to {minus(f'{max(dac):+.2f}')} %{est}.{weights} Output values are chopper-period means, and 9 µs "
                      f"is the middle of the first whole period after the release; electrode-referred = output / {gain:.1f}, the gain "
                      f"with the DAC's 15 MCLK of blanking ({su_gain():.1f} with 7), from that same fit.")
    gs = fig.add_gridspec(2, 2)
    ax = fig.add_subplot(gs[0, 0])
    for (vin, (r, m)), c in zip(runs.items(), RAMP6):
        ax.plot(r["x"] * 1e3, r["m"] * 1e3, color=c, lw=1.4, label=f"{vin} mV (range {dac_range(vin)}, M {m})")
    ax.axvline(0, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(0, 1.0, " AFE_RST released", transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, va="top")
    ax.set_xlim(-0.2, 3.0)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    ax.set_title("AFE output, chopper-period means", fontsize=9.5)
    y0, y1 = ax.get_ylim()
    ys = sorted(r["final"] * 1e3 for r, _ in runs.values())
    lo, hi = max(zip(ys, ys[1:]), key=lambda g: g[1] - g[0])   # the widest gap between the settled outputs
    ax.legend(loc="center right", bbox_to_anchor=(1.0, ((lo + hi) / 2 - y0) / (y1 - y0)), fontsize=7.5, ncol=2)
    ax = fig.add_subplot(gs[0, 1])
    for (vin, (r, m)), c in zip(runs.items(), RAMP6):
        a = r["x"] > 0
        ax.semilogy(r["x"][a] * 1e3, np.abs(r["m"][a] - r["final"]) * 1e3, color=c, lw=1.2)
    if 300 in runs:                                    # the one visible tail: it moves with VCM's last settling
        r = runs[300][0]
        v, meta = su_load(r["name"])
        dv = (v["cm"][-1] - np.interp(meta["t_afe"] + 0.5e-3, v["t"], v["cm"])) * 1e3
        tail = np.interp(0.5e-3, r["x"], r["m"]) - r["final"]
        ax.text(1.25, 0.16, f"300 mV: a slow tail, {abs(tail) / gain * 1e6:.2f} µV at the electrodes at 0.5 ms,\n"
                f"that moves with VCM's last {dv:.1f} mV of settling", fontsize=7.5, color=INK2, va="bottom")
    for y, lab in ((1.0, f"1 mV ({1e3 / gain:.1f} µV at the electrodes)"), (0.1, f"0.1 mV ({1e2 / gain:.2f} µV)")):
        ax.axhline(y, color=MUTED, lw=0.9, ls=(0, (4, 3)))
        ax.annotate(lab, (2.98, y), xytext=(0, 1.5), textcoords="offset points", fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax.set_xlim(0, 3.0)
    ax.set_ylim(1e-3, 10)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("|output − final| (mV)")
    ax.set_title("Settling to the final value (mean of the last 16 periods)", fontsize=9.5)
    ax = fig.add_subplot(gs[1, 0])
    half = step / 2 * 1e3
    ax.axhspan(-half, half, color="#f1f5f9", lw=0, zorder=0)
    ax.text(0.01, half, f" ±½ step ({half:.0f} µV): the most a code leaves if all steps are equal", transform=ax.get_yaxis_transform(),
            fontsize=7.5, color=MUTED, va="bottom")
    lim = 1.4 * max([half] + [abs(r["final"] / gain * 1e6) for r, _ in runs.values()])
    for k, (vin, (r, m)) in enumerate(runs.items()):
        q = (vin - m * UNIT_MV * r["vafe"] / 3.3) * 1e3
        ax.plot([k], [r["final"] / gain * 1e6], "o", color=RAMP6[k], ms=7, zorder=3)
        if abs(q) <= lim:
            ax.plot([k], [q], "_", color=INK2, ms=14, mew=1.6, zorder=2)
        else:                                          # the estimate off the axis: an arrow at the edge, its value
            y = np.sign(q) * lim * 0.97
            ax.annotate(f"expected {q:+.0f} µV".replace("-", "−"), (k, y), xytext=(k, y * 0.62), ha="center",
                        fontsize=7.5, color=INK2, arrowprops=dict(arrowstyle="->", color=INK2, lw=0.9))
    ax.plot([], [], "o", color=ACCENT, label="Simulated (final output / gain)")
    ax.plot([], [], "_", color=INK2, ms=12, mew=1.6, label="Expected: offset − M × step at the AFE's supply")
    ax.set_ylim(-lim, lim)
    ax.set_xticks(range(len(runs)), [f"{v} mV" for v in runs])
    ax.set_xlabel("Electrode DC offset")
    ax.set_ylabel("Residual at the electrodes (µV)")
    ax.set_title("What the DAC leaves", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    ax = fig.add_subplot(gs[1, 1])
    for k, (r, _) in enumerate(runs.values()):
        ax.plot([k - 0.1], [r["t1"] * 1e6], "o", color=RAMP6[k], ms=7)
        ax.plot([k + 0.1], [r["t01"] * 1e6], "s", color=RAMP6[k], ms=5, mfc="white", mew=1.4)
    ax.plot([], [], "o", color=ACCENT, label="to 1 mV")
    ax.plot([], [], "s", color=ACCENT, mfc="white", mew=1.4, label="to 0.1 mV")
    ax.set_xticks(range(len(runs)), [f"{v} mV" for v in runs])
    ax.set_yscale("log")
    ax.set_ylim(1, 1000)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))
    ax.set_xlabel("Electrode DC offset")
    ax.set_ylabel("Settled after the release (µs)")
    va = [r["vamax"] * 1e3 for r, _ in runs.values()]
    ax.set_title("Settling time" + (f" · |OPI − ONI| up to {max(va):.0f} mV in spikes at the chopper "
                                                    "edges, inside the blanking" if va else ""), fontsize=9.5)
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "27_dc_input")


SINE_RUN = "start_c1e-08_v3.3_typical_+0mV_sine0.943mV2000Hz_afe5ms"


def sine_amp(r, f0):
    """A start run's amplitude at f0, period by period: a sine, an offset and a drift fitted to the chopper-period means
    over each signal period, the period average's sinc taken out. (period centres after the release, amplitudes)"""
    a = r["x"] > 0
    x, m = r["x"][a], r["m"][a]
    win = int(round(1 / f0 / TCH))                    # one signal period of chopper means
    tc, av = [], []
    for i in range(0, len(x) - win, win // 8):
        tc.append(x[i + win // 2])
        av.append(sine_fit(x[i:i + win], m[i:i + win], f0))
    return np.array(tc), np.array(av) / np.sinc(f0 * TCH)   # undo the chopper-period average


def fig_pex_sine():
    """The full-scale sine from power-on on the chip (against the schematic where that run exists), its
    amplitude settling, and the extraction's capacitors."""
    gain = su_gain()
    nm = SINE_RUN + SU_IB
    d = {k: su_release(p + nm) for k, p in (("pex", ""), ("sch", "sch_"))}
    d = {k: r for k, r in d.items() if r and r["done"]}
    if "pex" not in d:
        print("fig_pex_sine: the extracted run is missing")
        return
    sch = "sch" in d
    f0 = 2000.0
    amp = {k: sine_amp(r, f0) for k, r in d.items()}
    caps = pex_caps()
    tot = {}
    for a_, b_, c in caps:
        for n in (a_, b_):
            tot[n] = tot.get(n, 0.0) + c
    top = sorted(((c, n) for n, c in tot.items() if n not in SUPPLIES), reverse=True)[:14]
    stop = ""                                          # where this chip's schematic run stopped (its run.log)
    log = os.path.join(SU, "sch_" + nm, "run.log")
    if not sch and os.path.exists(log):
        hit = re.search(r"time = ([0-9.eE+-]+), timestep = ([0-9.eE+-]+)", open(log, encoding="utf-8", errors="replace").read())
        if hit:
            stop = f", its step down to {float(hit[2]):.3g} s at {float(hit[1]) * 1e3:.2f} ms"
    note_sch = ("The schematic run has neither afe_top's signal-path nor its rail resistance, and needs 1 fF from every node "
                "to ground, gear integration and reltol 1e-4 (1e-5 extracted) in ngspice." if sch else
                "The schematic blocks on this bench do not run through in ngspice (with 1 fF per node, gear and reltol 1e-4"
                f"{stop}; without them at the end of the supply ramp);\nschematic against extracted: figure 20 (the "
                "chopped baseband transfer) and gf180_pex_20261023.md.")
    fig = figure(12.8, 10.2, ("Extracted against schematic: a" if sch else "The extracted chip:") + " full-scale sine from power-on",
                 f"0.943 mV pk at {f0 / 1e3:g} kHz from 20 µs after the AFE release, electrodes 100 Ω per leg · pads, board, "
                 "power-on, the chip's extracted wiring, afe_top, eeg_bias and eeg_ref extracted" + (", or as drawn" if sch else "") +
                 " · AFE_IBIAS = 3 · typical, 27 °C",
                 note="Amplitude: a sine, an offset and a drift fitted to the chopper-period means over each signal period "
                      "(500 µs), the period average's sinc taken out. Capacitors: every capacitor of the extraction "
                      f"({len(caps)}),\nAVDD, AVSS and AVDD_CLK left out of the per-net totals. " + note_sch)
    gs = fig.add_gridspec(2, 2)
    ax = fig.add_subplot(gs[0, 0])
    for k in [k for k in ("sch", "pex") if k in d]:
        r = d[k]
        ax.plot(r["x"] * 1e3, r["m"] * 1e3, color=NET[k]["color"], lw=1.1 if k == "pex" else 1.6,
                ls="-" if k == "pex" else (0, (5, 2.5)), label=NET[k]["label"])
    ax.set_xlim(-0.1, 3.0)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("OUTP − OUTN (mV)")
    ax.set_title("AFE output, chopper-period means", fontsize=9.5)
    if len(d) > 1:                                     # one run: the figure's title names it (a legend sat on a trough)
        ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[0, 1])
    for k in [k for k in ("sch", "pex") if k in d]:
        tc, av = amp[k]
        fin = av[-4:].mean()
        ax.plot(tc * 1e3, av * 1e3, "o-", color=NET[k]["color"], ms=3, lw=1.1,
                label=f"{NET[k]['label']}: {fin * 1e3:.2f} mV pk, gain {fin / 0.943e-3:.1f}")
    ax.set_xlim(0, 3.0)
    ax.set_xlabel("Centre of the fitted period (ms after the release)")
    ax.set_ylabel("Output amplitude (mV pk)")
    ax.set_title("Amplitude settling", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[1, 0])
    y = np.arange(len(top))[::-1]
    ax.barh(y, [c * 1e12 for c, _ in top], color=ACCENT, height=0.6)
    ax.set_yticks(y, [n for _, n in top], fontsize=7.5)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))     # 3, 4, … 20 rather than 3×10⁰
    ax.xaxis.set_minor_formatter(mticker.FormatStrFormatter("%g"))
    ax.set_xlabel("Total extracted capacitance on the net (pF, log scale)")
    ax.set_title("Largest node capacitances", fontsize=9.5)
    ax = fig.add_subplot(gs[1, 1])
    vals = np.array([c for _, _, c in caps]) * 1e15
    sup = np.array([a_ in SUPPLIES or b_ in SUPPLIES for a_, b_, _ in caps])
    bins = np.logspace(np.log10(max(vals.min(), 1e-3)), np.log10(vals.max()), 40)
    ax.hist(vals[~sup], bins=bins, color=ACCENT, alpha=0.85, label=f"between signal nets ({(~sup).sum()})")
    ax.hist(vals[sup], bins=bins, color=LIGHT, alpha=0.85, label=f"to AVDD / AVSS / AVDD_CLK ({sup.sum()})")
    ax.set_xscale("log")
    ax.set_xlabel("Capacitance (fF, log scale)")
    ax.set_ylabel("Count")
    ax.set_title("Distribution of the extracted capacitors", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    save(fig, "28_pex_sine")


# ---------------------------------------------------------------- the ADC with manufacturing variation

ADC_MC = os.path.join(PEX, "runs", "adc_mc" + SRC.get("mc", ""), "adc_block_mc.json")    # adc_block_mc.py (blocks)
ADC_BEH = os.path.join(PEX, "runs", "adc_beh_mc" + SRC.get("beh", SRC["adc"]))  # adc_beh_mc.py (per-die loop model)
ADC_LOOP_MC = os.path.join(PEX, "runs", "adc_mc_loop" + SRC["adc"])         # adc_loop_mc.py (transistor-level loop)
LSB_Q = 3.125                                                        # quantizer LSB at O2 (mV)
SNDR_165 = 6.02 * 16.5 + 1.76                                        # 16.5 bits (101.1 dB)
# r6: adc_beh_mc.py's defaults (the RTL's excess loop delay 3/32); r7: the delay that reproduces the transistor-level
# loop (0.22 of a clock)
BEH_TAG = "ain0.3_eld0.0938" if vizstyle.CHIP == "r6" else "ain0.3_eld0.2200"
BEH_ELD = "ELD 3/32 MCLK" if vizstyle.CHIP == "r6" else "ELD 0.22 of a clock, which reproduces the transistor-level loop"


BEH_KEY = {"even": "DAC1 even charge swept", "corners": "corners", "mc": "Monte Carlo"}   # adc_beh_mc.py's result keys


def beh(kind):
    """adc_beh_mc.py's dies of one case ('even', 'corners', 'mc'): [dict], empty if not run. Read from the case's own
    run (<kind>_<tag>.json, r6 and r7) or from a run of several cases at once (even_corners_mc_<tag>.json, r10)."""
    if not os.path.isdir(ADC_BEH):
        return []
    names = [f"{kind}_{BEH_TAG}.json"] + sorted(n for n in os.listdir(ADC_BEH) if n.endswith(f"_{BEH_TAG}.json"))
    for n in names:
        p = os.path.join(ADC_BEH, n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                res = json.load(f)["results"]
            if BEH_KEY[kind] in res:
                return res[BEH_KEY[kind]]
    return []


def fig_adc_mc():
    with open(ADC_MC, encoding="utf-8") as f:
        j = json.load(f)
    typ = j["corners"]["typical"]
    ps = {int(s): d for s, d in j["per_seed"].items()}
    thr = {s: np.array(d["quant_threshold_error_mv"]) for s, d in ps.items() if d.get("quant_threshold_error_mv")}
    dac = {s: d for s, d in ps.items() if d.get("even_all_fc") is not None and d.get("even_one_fc") is not None}
    stat = {s: d for s, d in ps.items() if d.get("elem_err")}
    ota = {s: d for s, d in ps.items() if d.get("ota1") and d.get("ota2")}
    corners = {c: j["corners"].get(c) or {} for c in ("ss", "ff", "fs", "sf")}
    fig = figure(12.8, 14.6, "The ADC with manufacturing variation: its blocks, and the SNDR they give",
                 "Extracted blocks (eeg_quantizer, adc_rdac, the two integrator OTAs, eeg_bias, eeg_ref), each on its own bench · "
                 "Monte Carlo of the PDK's global process and per-device mismatch, seeds 1–30 · corners without mismatch · 27 °C",
                 note=f"Seeds done: quantizer {len(thr)}, DAC1 even charge {len(dac)}, DAC1 elements {len(stat)}, OTAs {len(ota)} of 30. "
                      "Resistor and MIM mismatch are stand-ins (3 and 1.41 %·µm; the PDK has none). SNDR: the per-clock loop "
                      f"model (DWA, {BEH_ELD}) with each die's blocks (adc_beh_mc.py), a 0.3 V pk 32 Hz sine at the ADC input "
                      "(the full-scale 0.943 mV pk at the electrodes gives 0.28 V), 0.5–100 Hz after the CIC and FIR of the RTL; "
                      "the budget allotments are those of the 16.5-bit residual budget (tracker A6).")
    gs = fig.add_gridspec(3, 2)
    # quantizer thresholds
    ax = fig.add_subplot(gs[0, 0])
    lv = (np.arange(31) - 15) * LSB_Q
    ax.axhspan(-LSB_Q / 2, LSB_Q / 2, color="#f1f5f9", lw=0, zorder=0, label=f"±½ LSB ({LSB_Q / 2:.2f} mV)")
    for e in thr.values():
        ax.plot(lv, e, "o", color=LIGHT, ms=3.2, alpha=0.9)
    ax.plot([], [], "o", color=LIGHT, ms=3.2, label=f"Monte Carlo seeds ({len(thr)}), one dot per comparator")
    ax.plot(lv, typ["quant"]["err_mv"], "-D", color=ACCENT, lw=1.3, ms=3, label="typical")
    ax.axhline(0, color=GRID2, lw=0.9)
    ax.set_xlabel("Ideal threshold at the quantizer input O2 (mV)")
    ax.set_ylabel("Threshold error (mV)")
    if thr:
        sd = np.mean([np.std(e, ddof=1) for e in thr.values()])
        mx = max(np.abs(e).max() for e in thr.values())
        ax.set_title(f"Quantizer: 31 thresholds, σ {sd:.2f} mV ({sd / LSB_Q:.2f} LSB) within a seed, largest |error| "
                     f"{mx:.1f} mV", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    # DAC1 even-order charge
    ax = fig.add_subplot(gs[0, 1])
    for y in (0.008, -0.008):
        ax.axhline(y, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate("requirement on the common part (all 31 together) ±0.008 fC", (30.4, 0.008), textcoords="offset points",
                xytext=(0, 2), fontsize=7.5, color=BAD, ha="right", va="bottom")
    ax.axhline(typ["dac1"]["even_one_fc"], color=INK2, lw=0.9, ls=(0, (1, 1.5)),
               label=f"typical, one cell ({typ['dac1']['even_one_fc']:+.5f} fC)".replace("-", "−"))
    ax.axhline(typ["dac1"]["even_all_fc"], color=INK2, lw=0.9, ls=(0, (5, 2)),
               label=f"typical, all 31 together ({typ['dac1']['even_all_fc']:+.5f} fC)".replace("-", "−"))
    if dac:
        s = sorted(dac)
        ax.plot(s, [dac[k]["even_one_fc"] for k in s], "o", color=LIGHT, ms=5,
                label="Monte Carlo, one cell (cell 0): the scatter between elements, shaped by DWA")
        ax.plot(s, [dac[k]["even_all_fc"] for k in s], "s", color=ACCENT, ms=4.5, mfc="white", mew=1.3,
                label="Monte Carlo, all 31 together: the common part, per element")
    ax.set_xlim(0.5, 30.5)
    ax.set_ylim(-0.016, 0.016)
    ax.set_xlabel("Monte Carlo seed")
    ax.set_ylabel("Charge per toggle that does not\ndepend on its direction (fC)")
    if len(dac) > 1:
        al = np.array([d["even_all_fc"] for d in dac.values()])
        one = np.array([d["even_one_fc"] for d in dac.values()])
        mn = lambda x: f"{x:+.4f}".replace("-", "−")
        ax.set_title(f"DAC1, even-order charge per toggle ({len(dac)} of 30 seeds):\ncommon part {mn(al.mean())} ± "
                     f"{al.std(ddof=1):.4f} fC (worst {mn(al[np.abs(al).argmax()])}), one cell σ {one.std(ddof=1):.4f} fC",
                     fontsize=9.5)
    else:
        ax.set_title("DAC1, even-order charge per toggle", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.5)
    # the integrator OTAs
    for k, (blk, ph, lab, model_db) in enumerate((("ota1", "A", "OTA1, stage 1 (chopper phase A)", 68.7),
                                                   ("ota2", "-", "OTA2, stage 2", 69.5))):
        ax = fig.add_subplot(gs[1, k])
        g = np.array([d[blk][ph]["A_dc_db"] for d in ota.values()])
        pm = np.array([d[blk][ph]["PM_deg"] for d in ota.values()])
        fu = np.array([d[blk][ph]["T_ugf_hz"] for d in ota.values()])
        ax.plot(g, pm, "o", color=LIGHT, ms=4.5, label=f"Monte Carlo seeds ({len(ota)})")
        for c, d in corners.items():
            if d.get(blk):
                ax.plot(d[blk][ph]["A_dc_db"], d[blk][ph]["PM_deg"], "s", color=INK2, ms=5)
                ax.annotate(c, (d[blk][ph]["A_dc_db"], d[blk][ph]["PM_deg"]), textcoords="offset points", xytext=(5, 3),
                            fontsize=7.5, color=INK2)
        ax.plot([], [], "s", color=INK2, ms=5, label="corners (ss, ff with res / MIM ss, ff)")
        t = typ[blk][ph]
        ax.plot(t["A_dc_db"], t["PM_deg"], "D", color=ACCENT, ms=6.5, label="typical")
        ax.set_xlabel("DC gain with the integrator load (dB)")
        ax.set_ylabel("Phase margin of the integrator loop (°)")
        if len(g) > 1:
            ax.set_title(f"{lab}: gain {g.mean():.2f} ± {g.std(ddof=1):.2f} dB, PM {pm.mean():.1f} ± {pm.std(ddof=1):.1f}° "
                         f"(worst {pm.min():.1f}°)\nintegrator loop unity gain {fu.mean() / 1e6:.1f} MHz; the loop model "
                         f"assumed {model_db} dB", fontsize=9.5)
        ax.legend(loc="lower left" if k == 0 else "upper left", fontsize=8)
    # SNDR against DAC1's even-order charge
    ax = fig.add_subplot(gs[2, 0])
    u = typ["dac1"]["u_mean_fc"]
    sw = [(d["e1_mean"] * u, d["sndr_db"]) for d in beh("even")]
    for sign, kw, lab in ((1, dict(marker="o", color=ACCENT, ms=7, mfc="white", mew=1.4, lw=2.2), "even charge > 0"),
                          (-1, dict(marker="s", color=TEAL, ms=3.5, lw=1.0), "even charge < 0 (the same SNDR)")):
        p = sorted((abs(q), s) for q, s in sw if q * sign > 0)
        if p:
            ax.semilogx(*zip(*p), label=lab, **kw)
    zero = [s for q, s in sw if q == 0]
    if zero:
        ax.axhline(zero[0], color=MUTED, lw=0.9, ls=(0, (1, 2)))
        ax.annotate(f"none: {zero[0]:.0f} dB (quantization, mismatch)", (1.05e-4, zero[0]), textcoords="offset points",
                    xytext=(0, 2), fontsize=7.5, color=MUTED, va="bottom")
    ax.axhline(SNDR_165, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate(f"16.5 bits ({SNDR_165:.1f} dB)", (1.05e-4, SNDR_165), textcoords="offset points", xytext=(0, 2), fontsize=7.5,
                color=BAD, va="bottom")
    ax.axvline(0.008, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.text(0.008, 0.55, " requirement\n 0.008 fC", transform=ax.get_xaxis_transform(), fontsize=7.5, color=BAD)
    cor = beh("corners")
    td = next((d for d in cor if d["label"] == "MOS typical"), None)
    if td:
        q = abs(typ["dac1"]["even_all_fc"])
        ax.plot(q, td["sndr_db"], "D", color=INK, ms=6.5, label=f"typical die, extracted ({q:.5f} fC): {td['sndr_db']:.1f} dB")
    mc = beh("mc")
    if mc:
        ax.plot([abs(d["e1_mean"]) * u for d in mc], [d["sndr_db"] for d in mc], "o", color=LIGHT, ms=4,
                label=f"Monte Carlo dies ({len(mc)})")
    ax.set_xscale("log")
    ax.set_xlim(1e-4, 0.03)
    ax.set_ylim(95, 200)
    ax.set_xlabel("|Even-order charge per toggle|, the same on all 31 elements (fC)")
    ax.set_ylabel("SNDR, 0.5–100 Hz (dB)")
    ax.set_title("SNDR against DAC1's even-order charge (typical blocks otherwise)", fontsize=9.5)
    ax.legend(loc="upper left", bbox_to_anchor=(0.01, 0.83), fontsize=8)
    # each die's error against the residual budget: HD2 (distortion) and the rest (noise floor)
    ax = fig.add_subplot(gs[2, 1])
    labels = [d["label"].replace("MOS ", "").replace(" (res_ss, mimcap_ss)", "*").replace(" (res_ff, mimcap_ff)", "*")
              .replace("res_", "R ").replace("mimcap_", "C ") for d in cor]
    fs = 0.943e-3 / np.sqrt(2)                                # the full-scale sine at the electrodes (rms)
    eq = lambda db: fs * 10 ** (np.asarray(db, dtype=float) / 20) * 1e9
    xs = np.arange(len(cor), dtype=float)
    if mc:
        labels.append("Monte Carlo")
        xs = np.concatenate([xs, len(cor) + 0.5 + 0.6 * (np.random.RandomState(0).rand(len(mc)) - 0.5)])
    allv = cor + mc
    hd2 = eq([d.get("hd2_dbc", np.nan) for d in allv])
    nz = eq([-d.get("snr_db", np.nan) for d in allv])
    col = [INK2] * len(cor) + [LIGHT] * len(mc)
    ax.scatter(xs, hd2, c=col, marker="o", s=26, zorder=3)
    ax.scatter(xs, nz, facecolors="white", edgecolors=col, marker="s", s=22, linewidths=1.2, zorder=3)
    ax.plot([], [], "o", color=MUTED, ms=5, label="HD2 (dark: corners, light: Monte Carlo dies)")
    ax.plot([], [], "s", color=MUTED, mfc="white", mew=1.2, ms=5, label="everything else: the noise floor")
    for y, lab in ((2.0, "distortion, AFE + ADC: 2.0 nVrms allotted (the AFE 0.50)"),
                   (0.1, "DAC2, quantization, ELD: 0.1 nVrms allotted")):
        ax.axhline(y, color=BAD, ls=(0, (4, 3)), lw=1)
        ax.annotate(lab, (len(labels) - 0.3, y), textcoords="offset points", xytext=(0, 2), fontsize=7.5, color=BAD,
                    ha="right", va="bottom")
    ax.set_yscale("log")
    ax.set_ylim(1e-4, 10)
    ax.set_xticks(list(range(len(cor))) + ([len(cor) + 0.5] if mc else []), labels, rotation=30, ha="right", fontsize=8)
    ax.set_xlim(-0.6, len(labels) - 0.2)
    ax.set_ylabel("At the electrodes (nVrms, 0.5–100 Hz)")
    ok = np.isfinite(hd2)
    if ok.any():
        ax.set_title(f"Each die's ADC error at full scale (0.943 mV pk): HD2 up to {np.nanmax(hd2):.2f} nVrms,\n"
                     f"the rest up to {np.nanmax(nz):.3f} nVrms (* with R / MIM ss, ff)", fontsize=9.5)
    ax.legend(loc="center left", fontsize=8)        # between the HD2 row and the noise floor
    save(fig, "29_adc_mc")


def loop_runs(suffix="_f20k_a0.28_t100u"):
    """adc_loop_mc.py's runs: [(kind, label, metrics)], typical first, then the seeds, then the R / MIM corners, then the
    runs with no input (kind "z", no loop gain)."""
    out = []
    if not os.path.isdir(ADC_LOOP_MC):
        return out
    for n in sorted(os.listdir(ADC_LOOP_MC)):
        p = os.path.join(ADC_LOOP_MC, n, "result.json")
        zero = n.endswith("_f20k_a0_t100u")
        if not (n.endswith(suffix) or zero) or not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        w = r["tr_window"]
        num = lambda pat: [float(x) for x in re.search(pat, w).groups()]
        mt = dict(gain=np.nan if zero else num(r"loop gain ([\d.]+)")[0], resid=num(r"residual ([\d.]+) rms")[0],
                  o1=num(r"O1 (-?[\d.]+)\.\.(-?[\d.]+) mV"), o2=num(r"O2 (-?[\d.]+)\.\.(-?[\d.]+) mV"),
                  cm=num(r"O1 CM ([\d.]+) V, O2 CM ([\d.]+) V"), iavdd=num(r"AVDD ([\d.]+) mA")[0],
                  agree=r["agree"], o2s=(r["o2min"] * 1e3, r["o2max"] * 1e3))
        kind = n.split("_")[0]
        lab = {"typical": "typical"}.get(kind, kind if kind.startswith("mc") else
                                         "R " + n.split("_")[1] + ", C " + n.split("_")[2])
        out.append(("z" if zero else "typ" if kind == "typical" else "mc" if kind.startswith("mc") else "rc",
                    lab + (", no input" if zero else ""), mt))
    order = {"typ": 0, "mc": 1, "rc": 2, "z": 3}
    return sorted(out, key=lambda x: (order[x[0]], int(x[1][2:]) if x[0] == "mc" else 0, x[1]))


def fig_adc_loop_mc():
    runs = loop_runs()
    if not runs:
        print("fig_adc_loop_mc: no runs")
        return
    nmc = sum(k == "mc" for k, _, _ in runs)
    fine = ""                                   # the R ff, C ff run again with a 1 ns largest step, if there is one
    p = os.path.join(ADC_LOOP_MC, "rc_ff_ff_f20k_a0.28_t100u_tmax1n", "result.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        res = float(re.search(r"residual ([\d.]+) rms", r["tr_window"]).group(1))
        fine = (f" R ff, C ff rerun with a 1 ns largest step (instead of 10 µs): O2 {r['o2min'] * 1e3:.0f}..{r['o2max'] * 1e3:+.0f} mV, "
                f"residual {res:.3f}.")
    fig = figure(12.8, 9.8, "The ADC loop at transistor level with manufacturing variation",
                 "eeg_adc, eeg_bias and eeg_ref extracted, the XSPICE DWA controller, the RTL's frame timing · the chip's operating "
                 "point (AVDD 3.245 V at the ADC, the reference through the chip wiring) · 0.28 V pk 20 kHz at the ADC input "
                 "(none where marked), frames 20–100 µs · 27 °C",
                 note=f"Monte Carlo: {nmc} seeds of the PDK's global process and per-device mismatch (stand-ins for resistor and MIM "
                      "mismatch); R / MIM corners: ppolyf_u_1k res_ss / res_ff with mimcap_ss / mimcap_ff, typical transistors.\n"
                      "Loop gain: DAC1's level against the input (none without input); residual: the quantization residual in DAC1 "
                      "levels (adc_loop_mc.py, tr_window.py)." + fine)
    gs = fig.add_gridspec(2, 2)
    x = np.arange(len(runs))
    col = {"typ": ACCENT, "mc": LIGHT, "rc": INK2, "z": TEAL}       # a category, not a status
    mk = {"typ": "D", "mc": "o", "rc": "s", "z": "s"}
    labels = [lab for _, lab, _ in runs]

    def strip(ax, key, ylab, title):
        for i, (k, _, mt) in enumerate(runs):
            ax.plot(i, mt[key], mk[k], color=col[k], ms=6)
        ax.set_xticks(x, labels, rotation=40, ha="right", fontsize=7.5)
        ax.set_ylabel(ylab)
        ax.set_title(title, fontsize=9.5)

    ax = fig.add_subplot(gs[0, 0])
    strip(ax, "gain", "Loop gain", "Loop gain (DAC1's level against the input)")
    ax = fig.add_subplot(gs[0, 1])
    strip(ax, "resid", "Residual (DAC1 levels, rms)", "Residual of DAC1's level about the fitted sine (the shaped "
          "quantization noise, all frequencies)")
    ax.axhline(0.1, color=MUTED, ls=(0, (4, 3)), lw=0.9)
    ax.annotate("a working loop stays below about 0.1", (len(runs) - 0.5, 0.1), textcoords="offset points", xytext=(0, 2),
                fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax.set_ylim(0, max(0.12, 1.15 * max(mt["resid"] for _, _, mt in runs)))
    ax = fig.add_subplot(gs[1, 0])
    for i, (k, _, mt) in enumerate(runs):
        ax.plot([i, i], mt["o2s"], "-", color=col[k], lw=3, solid_capstyle="butt")
    for s in (1, -1):
        ax.axhline(s * 46.875, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate("quantizer range ±46.9 mV", (len(runs) - 0.5, 46.875), textcoords="offset points", xytext=(0, 2), fontsize=7.5,
                color=BAD, ha="right", va="bottom")
    ax.set_xticks(x, labels, rotation=40, ha="right", fontsize=7.5)
    lo, hi = min(mt["o2s"][0] for _, _, mt in runs), max(mt["o2s"][1] for _, _, mt in runs)
    ax.set_ylim(min(-55, 1.1 * lo), max(60, 1.15 * hi))
    ax.set_ylabel("O2 at the strobes (mV)")
    ax.set_title("The quantizer input at its strobes (range over the frames)", fontsize=9.5)
    ax = fig.add_subplot(gs[1, 1])
    for i, (k, _, mt) in enumerate(runs):
        ax.plot(i, mt["agree"] * 100, mk[k], color=col[k], ms=6)
    ax.set_xticks(x, labels, rotation=40, ha="right", fontsize=7.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Frames (%)")
    ax.set_title("Decisions that agree with the ideal thresholds (comparator offsets differ per seed)", fontsize=9.5)
    save(fig, "30_adc_loop_mc")


# ---------------------------------------------------------------- the digital side on the chip wiring

AMBER = "#d97706"
LSB_DATA = 1 / (306.6 * 2 ** 24)          # V at the electrode per LSB of DATA (the chain's gain from the electrode)


def fig_digital_noise():
    """digital_noise.py's cases on chunk 14 of the r9 chain: the pad ring, the blocks' rails, the AFE's input and the
    AFE output per chopper period (runs/digital_noise/compare.json and the cases' raw files). r10: the same cases with
    r10's eeg_adc and their own A (digital_noise.py --adc r10, runs/digital_noise_r10/). r12: the same cases on r12's
    own chain, A = that chain's chunk 14 (digital_noise.py --chain r12, runs/digital_noise_r12/)."""
    if vizstyle.CHIP not in ("r9", "r10", "r12"):
        print("fig_digital_noise: its runs are on the r9, r10 and r12 chains")
        return
    spec = importlib.util.spec_from_file_location("digital_noise", os.path.join(PEX, "digital_noise.py"))
    dn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dn)
    own = vizstyle.CHIP == "r10"            # its own runs: chunk 14 with r10's eeg_adc, A = that deck alone
    if own:
        dn.use_adc("r10")
    chain = "r12" if vizstyle.CHIP == "r12" else "r9"     # whose chain's chunk 14 the cases are on
    if chain != "r9":
        dn.use_chain(chain)
    ref = "A" if own else "the chain"
    p = os.path.join(dn.RUNS, "compare.json")
    if not os.path.exists(p):
        print("fig_digital_noise: no compare.json (digital_noise.py compare)")
        return
    with open(p, encoding="utf-8") as f:
        res = json.load(f)
    if not all(k in res["diff"] for k in ("b1iso-A", "b1-b1iso", "b2-b1", "b3-b1")):
        print("fig_digital_noise: compare.json lacks a case")
        return
    R = {c: dn.load_case(c) for c in ("A", "b1", "b1iso", "b3")}
    with open(os.path.join(dn.BASE, "tb.spice"), encoding="utf-8") as f:
        text = f.read()
    e0, TF = dn.frame_e0(text), dn.TF
    # a frame start 20 us into the window: the frame's first cycles are where the ADC's digital draws most
    fs = e0 + np.ceil((20e-6 - e0) / TF) * TF
    w0, w1 = fs - 30e-9, fs + 280e-9
    tg = np.arange(w0, w1, 2e-12)
    x = (tg - fs) * 1e9

    def on(c, name):
        r = R[c]
        m = (r["time"] > w0 - 1e-8) & (r["time"] < w1 + 1e-8)
        return np.interp(tg, r["time"][m], r[name][m])

    ca, df = res["cases"], res["diff"]
    fig = figure(
        12.8, 12.8, "The digital side on the chip wiring: what the pads and the digital current do to the AFE and the ADC",
        "The nine bi_24t pads, the two digital macros' supply current (gate-level activity, typical) and the chip-level "
        f"DVDD / DVSS added to chunk 14 of the {chain} chain (6.17–6.22 ms from power-on, AFE and ADC running, electrode "
        "0.3 mV DC + 0.5 mV 16 kHz; " + ("its ADC: r10's extraction" if own else
                                         "afe_top and eeg_adc of r12's extraction on its own chip nets" if chain == "r12"
                                         else "its ADC is r7's extraction, whose analog nets r10's matches within 0.03 fF")
        + ") · 47.3 µs · typical, 27 °C",
        note=("A: the chunk's deck alone over the same window. " if own else "")
             + "b1: MCLK running, host idle, raw stream off. b1iso: the same sources and pads on a separate copy of the ring "
             "(the simulator's extra events without the coupling). b2: b1 with an SPI read (2 MHz, 48 bits, 8–34 µs"
             + ("; MISO and DRDY_N 0.125 ns after the chip's clock grid" if own or chain == "r12" else "") + "). "
             "b3: b1 with the raw debug stream on (RAW_CLK = MCLK / 4, RAW_DATA random; its edges 0.125 ns after the chip's "
             "clock grid). b2 − b1 and b3 − b1 hold the numerical difference of their extra events too. Periods start a "
             "quarter period after each CHOP falling edge; electrode-referred = AFE output / "
             f"{dn.GAIN:g}; the fit takes the 16 kHz tone ({res['tone']['out_uV'] / 1e3:.1f} mV at the AFE output) out "
             "of each difference. In the 50 ns after each CHOP edge the differential differs by up to "
             f"±{df['b1-b1iso']['input']['diff_pp_all_uV'] / 2:.0f} µV, of either sign from edge to edge: the two runs' "
             "points on the switching transient. Not in it: the ring's resistance between the MCLK pad and the electrode "
             "pads (the ring is one node, so the coupling is on the large side), the substrate between DVSS and AVSS, "
             "glitches (zero-delay activity). digital_noise.py.")
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.15])
    # (a) the pad ring
    ax = fig.add_subplot(gs[0, 0])
    big = 0.0
    for c, lab, lw in (("A", ("A, the chunk alone" if own else "chain") + " (no digital current, no digital pads)", 0.9),
                       ("b1", "b1", 1.2),
                       ("b3", "b3 (raw stream on)", 1.0)):
        y = (on(c, "v(dvddc)") - 3.3) * 1e3
        big = max(big, np.max(np.abs(y)))
        ax.plot(x, y, color={"A": LIGHT, "b1": ACCENT, "b3": AMBER}[c], lw=lw, label=lab)
    ax.set_ylim(-1.75 * big, 1.15 * big)                  # room under the traces for the legend
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel("Time from a frame start (ns)")
    ax.set_ylabel("DVDD − 3.3 V (mV)")
    ax.set_title(f"Pad ring DVDD: {ca['A']['ring_vdd_pp_mV']:.0f} mV p-p in {ref}, {ca['b1']['ring_vdd_pp_mV']:.0f} "
                 f"in b1, {ca['b3']['ring_vdd_pp_mV']:.0f} in b3 (DVSS {ca['A']['ring_vss_pp_mV']:.0f} / "
                 f"{ca['b1']['ring_vss_pp_mV']:.0f} / {ca['b3']['ring_vss_pp_mV']:.0f})", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.5)
    # (b) the blocks' own rails
    ax = fig.add_subplot(gs[0, 1])
    b = ca["b1"]
    ax.plot(x, (on("b1", "v(dvdd_add)") - on("b1", "v(dvss_add)") - 3.3) * 1e3, color=INK2, lw=1.2,
            label=f"ADC's digital (4.32 / 1.41 Ω from the ring): {b['add_pp_mV']:.0f} mV p-p, mean "
                  + minus(f"{b['add_mean_mV'] - 3300:+.1f} mV"))
    ax.plot(x, (on("b1", "v(dvdd_dig)") - on("b1", "v(dvss_dig)") - 3.3) * 1e3, color=MUTED, lw=0.9,
            label=f"digital block (0.19 / 1.12 Ω): {b['dig_pp_mV']:.0f} mV p-p, mean "
                  + minus(f"{b['dig_mean_mV'] - 3300:+.1f} mV"))
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel("Time from a frame start (ns)")
    ax.set_ylabel("DVDD − DVSS − 3.3 V (mV)")
    ax.set_title(f"The blocks' own supply (b1; b3 within {abs(ca['b3']['add_pp_mV'] - b['add_pp_mV']):.0f} mV p-p)",
                 fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.5)
    # (c), (d) the AFE's input: the coupling (b1 - b1iso) and what the raw stream adds (b3 - b1)
    nm = ("v(elp)", "v(eln)")
    w = {c: {n: on(c, n) for n in nm} for c in ("b1", "b1iso", "b3")}
    cmf = lambda r: (r["v(elp)"] + r["v(eln)"]) / 2      # noqa: E731
    dff = lambda r: r["v(elp)"] - r["v(eln)"]            # noqa: E731
    for k, (fn, lab, unit, sc, key, extra) in enumerate((
            (cmf, "Common mode", "mV", 1e3, "cm_pp_mV", ""),
            (dff, "Differential", "µV", 1e6, "diff_pp_uV", " away from the CHOP edges"))):
        ax = fig.add_subplot(gs[1, k])
        ax.axhline(0, color=HAIR, lw=0.9, zorder=0)
        big = 0.0
        for (pc, qc, colr, lw) in (("b3", "b1", AMBER, 0.9), ("b1", "b1iso", ACCENT, 1.1)):
            v = df[f"{pc}-{qc}"]["input"][key]
            y = (fn(w[pc]) - fn(w[qc])) * sc
            big = max(big, np.max(np.abs(y)))
            ax.plot(x, y, color=colr, lw=lw, label=f"{pc} − {qc}: {v:.3g} {unit} p-p over the window" + extra)
        ax.set_ylim(-1.15 * big, 1.75 * big)              # room over the traces for the legend
        ax.set_xlim(x[0], x[-1])
        ax.set_xlabel("Time from a frame start (ns)")
        ax.set_ylabel(unit)
        ax.set_title(f"{lab} at the AFE's input: the coupling (b1 − b1iso) and the raw stream (b3 − b1)", fontsize=9.5)
        ax.legend(loc="upper right", fontsize=7.5)
    # (e) the AFE output per chopper period
    ax = fig.add_subplot(gs[2, :])
    P = np.array(res["periods_us"]) * 1e-6
    mid = P.mean(axis=1) * 1e6
    ax.axvspan(8.0, 34.0, color="#f1f5f9", lw=0, zorder=0)
    ax.text(21.0, 0.03, "SPI read (b2)", transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, ha="center",
            va="bottom")
    ax.axhline(0, color=HAIR, lw=0.9)
    pairs = ("b1iso-A", "b1-b1iso", "b2-b1", "b3-b1")
    pts = np.concatenate([np.array(df[p]["electrode_uV"]) * 1e3 for p in pairs])
    lo, hi = min(-1.0, 1.15 * pts.min()), max(1.6, 1.15 * pts.max() + 0.6)     # room over the points for the legend
    for s in range(int(np.ceil(lo / (LSB_DATA * 1e9))), int(np.floor(hi / (LSB_DATA * 1e9))) + 1):
        if s:
            ax.axhline(s * LSB_DATA * 1e9, color=HAIR, lw=0.6, ls=(0, (1, 2)), zorder=0)
    f, td = res["tone"]["f_Hz"], res["tone"]["td_s"]
    wt = 2 * np.pi * f
    tt = np.linspace(P[0, 0], P[-1, 1], 400)
    # the fit as a curve: offset + the tone's running mean over one chopper period around t
    Sm = (np.cos(wt * (tt - dn.TCH / 2 - td)) - np.cos(wt * (tt + dn.TCH / 2 - td))) / wt / dn.TCH
    Cm = (np.sin(wt * (tt + dn.TCH / 2 - td)) - np.sin(wt * (tt - dn.TCH / 2 - td))) / wt / dn.TCH
    for pair, lab, colr, mk in (("b1iso-A", f"b1iso − {'A' if own else 'chain'}: the simulator's extra events", LIGHT, "s"),
                                ("b1-b1iso", "b1 − b1iso: the coupling (MCLK pad, core current, pads)", ACCENT, "o"),
                                ("b2-b1", "b2 − b1: an SPI read", TEAL, "D"),
                                ("b3-b1", "b3 − b1: the raw stream", AMBER, "^")):
        d = df[pair]
        fz = d["fit"]
        ax.plot(mid, np.array(d["electrode_uV"]) * 1e3, ls="none", marker=mk, ms=6.5, mfc="white", mew=1.5, color=colr,
                label=f"{lab}: offset " + minus(f"{fz['offset_nV']:+.2f}") + f" nV, 16 kHz tone {fz['tone_ppm']:.1f} ppm, "
                      f"rest {fz['rest_nV_rms']:.2f} nV rms (codes differ {d['codes_differ']}/{d['frames']})")
        k1, k2 = fz["tone_uV"]
        ax.plot(tt * 1e6, fz["offset_nV"] + (k1 * Sm + k2 * Cm) / dn.GAIN * 1e3, color=colr, lw=1.0, alpha=0.8)
    ax.set_xlim(0, res["tend_us"])
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Chopper period centre (µs into the window)")
    ax.set_ylabel("Electrode-referred (nV)")
    ax.set_title("AFE output per chopper period, the difference (points) and offset + 16 kHz tone fitted (lines); "
                 f"dotted: steps of 1 LSB of DATA ({LSB_DATA * 1e9:.2f} nV)", fontsize=9.5)
    ax.legend(loc="upper left", fontsize=7.3)
    save(fig, "31_digital_noise")


# ---------------------------------------------------------------- input to output

CHAIN_BASE = "c1e-08_v3.3_typical_+0mV_dc+0.3mV_ib3_sine0.5mV16000Hz_rst4.8_afe5_to10.002ms"
# the power-on-to-CIC chains (e2e_startup.py) a chip's figure reads, the first one that has finished: r10's own ADC
# extraction, else r9's chain (r7's ADC extraction, the same chip wiring) until r10's ends; r11 only its own (its ADC
# resistors and chip wiring differ from r10's)
CHAIN_TAGS = {"r6": ["_chain"], "r9": ["_r9_chain"], "r10": ["_r10_chain", "_r9_chain"], "r11": ["_r11_chain"],
              "r12": ["_r12_chain"]}[vizstyle.CHIP]
FS_SPEC = 0.943e-3          # V pk at the electrodes: the full scale of the ENOB budget (budget.csv's target row)
ADC_LOOP_PK = 0.30          # V pk at the ADC input: what the transistor ADC loop was run at (B2, adc_loop_mc.py)
ADC_SAT_PK = 0.44           # V pk (period means): the behavioral loop's quantizer starts to saturate (adc_headroom.py, 10/24)
DATA_CEIL = 31 * 2 ** 18    # every code 31: the largest DATA the CIC can give
RES_MAX = {1: 153.4e-6, 2: 166.2e-6, 3: 166.2e-6, 4: 166.2e-6}   # V: the most the offset DAC leaves (half its largest step, 10/31)
RANGE_MV = {1: 39, 2: 79, 3: 159, 4: 318}


def sinc3(f):
    """|eeg_cic3| at f: sinc^3 with R = 1024 at the modulator's 1.024 MHz, DATA at 1 kHz."""
    x = np.pi * np.asarray(f, dtype=float) / FS
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(x == 0, 1.0, np.sin(1024 * x) / (1024 * np.sin(x)))
    return np.abs(r) ** 3


def chain_io():
    """The chip's power-on-to-CIC chain: its valid samples, and at its last strobe the sinc³-weighted electrode
    signal s_w and ADC input u_w (e2e_startup.expect): the ADC's DATA / (2^24 u_w). (rev, folder, samples, s_w, u_w, adc)"""
    import contextlib
    import io
    sys.path.insert(0, PEX)
    import e2e_startup as E
    root = os.path.join(PEX, "runs", "e2e_startup")
    tag = next(t for t in CHAIN_TAGS if os.path.exists(os.path.join(root, CHAIN_BASE + t, "e2e.gold")))
    d = os.path.join(root, CHAIN_BASE + tag)
    with contextlib.redirect_stdout(io.StringIO()):
        x = E.expect(d)
    h = E.cic_weights()
    j = len(x["outs"]) - 1
    nn = 1024 * (j + 1) - 1
    lo = max(0, nn - len(h) + 1)
    w = h[nn - np.arange(lo, nn + 1)]
    uw, sw = (float(np.dot(w, x[k][lo:nn + 1]) / w.sum()) for k in ("u", "s"))
    rev = "r6" if tag == "_chain" else tag.split("_")[1]
    # VREF at the ADC: the mean over 9-10 ms from the chunks' saved vectors (None if they are not here)
    num = den = 0.0
    for cdir in sorted(glob.glob(os.path.join(d, "chunk_*"))):
        try:
            cm = json.load(open(os.path.join(cdir, "chunk.json"), encoding="utf-8"))
            if cm["t1"] < 9e-3 or cm["t0"] > 10e-3:
                continue
            z = np.load(os.path.join(cdir, "lean.npz"))
        except (OSError, KeyError, ValueError):
            continue
        t = z["time"]
        k = (t >= 9e-3) & (t <= 10e-3)
        if k.sum() > 1:
            num += np.trapz((z["v(vrefp_adc)"] - z["v(vrefn_adc)"])[k], t[k])
            den += t[k][-1] - t[k][0]
    return dict(rev=rev, folder=d, samples=[a for a, v in x["outs"] if v], sw=sw, uw=uw, adc=x["outs"][j][0] / (2 ** 24 * uw),
                vref=num / den if den > 0.9e-3 else None)


def fig_input_output():
    c = chain_io()
    zero = su_release("start_c1e-08_v3.3_typical_+0mV_afe5ms" + SU_IB)["final"]   # the AFE's output with the electrodes at 0 V
    rs_ = su_release(SINE_RUN + SU_IB)                                               # figure 28's full-scale sine
    g28 = sine_amp(rs_, 2000.0)[1][-4:].mean() / 0.943e-3 if rs_ and rs_["done"] else None
    cnt = c["adc"] * 2 ** 24                       # DATA per volt at the ADC input
    afe = (c["uw"] - zero) / c["sw"]               # the AFE's gain once its own offset is taken out
    k7 = cnt * afe * 1e-6                          # DATA per µV at the electrodes, DAC off (7 MCLK of blanking)
    d0 = cnt * zero                                # DATA with the electrodes at 0 V
    g15 = dac_fit()[0]
    k15 = cnt * g15 * 1e-6                         # DAC on: 15 MCLK of blanking
    fit = d0 + k7 * c["sw"] * 1e6
    # frequency response: the AFE (extracted, chopped harmonic sum) x the modulator's STF x the CIC, each relative to DC
    ra, rs = rcsv("afe_baseband_pex_A"), rcsv("adc_ntf_stf", VIZ_ADC)
    fa, ga, fsr, gsr = col(ra, "f_hz"), col(ra, "gain_db"), col(rs, "f_hz"), col(rs, "stf_db")

    def resp(f, parts=False):
        lf = np.log10(f)
        a = 10 ** ((np.interp(lf, np.log10(fa), ga) - ga[0]) / 20)
        s = 10 ** ((np.interp(lf, np.log10(fsr), gsr) - gsr[0]) / 20)
        return (a, s) if parts else a * s * sinc3(f)

    db = lambda f: 20 * np.log10(resp(np.atleast_1d(float(f)))[0])   # noqa: E731
    fl = np.linspace(0.01, 64e3, 1_000_001)
    enbw = np.trapz(resp(fl) ** 2, fl)
    a1k, s1k = resp(np.array([1e3]), True)
    a16, s16 = resp(np.array([16e3]), True)
    f3 = fl[np.argmax(resp(fl) < 10 ** (-3 / 20))]
    # noise: the residual budget (0.5-100 Hz) and, if it were white, a raw 1 kHz sample through the CIC
    bud = list(csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_DIR, "budget.csv"),
                                   encoding="utf-8")))
    nb = np.sqrt(sum(float(r["nvrms"]) ** 2 for r in bud if r["kind"] == "component")) * 1e-9
    ns = nb / np.sqrt(BAND[1] - BAND[0]) * np.sqrt(enbw)
    dc_runs = {}
    for vin in VIN_DC:
        name, m = su_dc_run(vin)
        r = su_release(name)
        if r and r["done"]:
            dc_runs[vin] = (r["final"], m)
    lim_chk, lim_sat = ADC_LOOP_PK / afe * 1e3, ADC_SAT_PK / afe * 1e3       # mV at the electrodes
    fmt = lambda v: minus(f"{v:+,.0f}")                                        # noqa: E731

    fig = figure(13.6, 10.4, "What DATA shows for a given input at the electrodes",
                 f"Electrode differential input (ELP − ELN) to the 24-bit DATA read over SPI, 1000 samples/s · typical, 27 °C, "
                 f"AFE_IBIAS = 3 · the slope from the power-on-to-CIC chain ({c['rev']}'s, transistor level on the chip's wiring), "
                 f"the frequency response from the RTL's CIC with the extracted AFE and the modulator's STF, the offset DAC from the "
                 f"extracted start-up runs",
                 note=f"Slope: the chain's last valid sample at +0.3 mV DC gives the ADC {c['adc']:.5f} × 2^24 counts per volt at its "
                      f"input (VREF from the board's 0.5 V" + (f", {c['vref'] * 1e3:.1f} mV at the ADC over 9–10 ms" if c["vref"] else "") +
                      f"); the AFE's gain {afe:.2f} is the chain's "
                      f"{c['uw'] / c['sw']:.2f} with the start-up run's own offset at 0 V ({minus(f'{zero * 1e3:.4f}')} mV at its output) "
                      f"taken out" + (f"; the full-scale sine (figure 28) gives {g28:.1f}" if g28 else "") +
                      f". So DATA ≈ {minus(f'{d0:,.0f}')} + {k7:,.1f} × V (µV), "
                      f"which puts the chain's 0.3 mV at {fit:,.0f} against its samples {', '.join(f'{v:,d}' for v in c['samples'])}. "
                      f"The slope scales with 1 / VREF at the ADC and with the AFE's capacitor ratio, so a real chip wants one "
                      f"calibration with a known input. Noise: the budget's {nb * 1e9:.2f} nVrms in 0.5–100 Hz ({nb * 1e6 * k7:.0f} "
                      f"counts rms); a raw sample sees the CIC's noise bandwidth of {enbw:.0f} Hz, {ns * 1e9:.1f} nVrms "
                      f"({ns * 1e6 * k7:.0f} counts rms) if every part of the budget were white.")
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.22])

    # (a) the static transfer, DAC off
    ax = fig.add_subplot(gs[0, 0])
    xmax = 1.75
    ax.axvspan(lim_sat, xmax, color="#fef2f2", lw=0, zorder=0)
    ax.axvspan(-xmax, -lim_sat, color="#fef2f2", lw=0, zorder=0)
    ax.text(lim_sat + 0.02, -7.9, "the modulator\noverloads\n(codes stick\nat 0 and 31)", fontsize=7.3, color=BAD, va="bottom")
    v = np.linspace(-lim_chk, lim_chk, 3)
    ax.plot(v, (d0 + k7 * v * 1e3) / 1e6, color=ACCENT, lw=1.8, zorder=3, label="Transistor ADC loop run to here (±0.30 V at its input)")
    for sgn in (-1, 1):
        v = np.linspace(sgn * lim_chk, sgn * lim_sat, 3)
        ax.plot(v, (d0 + k7 * v * 1e3) / 1e6, color=ACCENT, lw=1.6, ls=(0, (4, 2.5)), zorder=3,
                label="Behavioral loop: still linear (to ±0.44 V)" if sgn > 0 else None)
    for sgn in (-1, 1):
        ax.axhline(sgn * DATA_CEIL / 1e6, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.axvline(sgn * FS_SPEC * 1e3, color=MUTED, lw=0.8, ls=(0, (4, 3)))
    ax.text(0, DATA_CEIL / 1e6, f"every code 31, DATA's largest: {DATA_CEIL:,d}", fontsize=7.3, color=MUTED, va="bottom", ha="center")
    ax.text(FS_SPEC * 1e3 + 0.03, -5.2, f"full scale of\nthe ENOB budget,\n±{FS_SPEC * 1e3:.3f} mV pk\n(DATA ±{k7 * FS_SPEC * 1e6 / 1e6:.2f} M)",
            fontsize=7.3, color=MUTED, va="center")
    ax.plot([c["sw"] * 1e3], [np.mean(c["samples"]) / 1e6], "o", color=ACCENT, ms=7, mec="white", mew=1.2, zorder=4)
    ax.annotate(f"+0.3 mV DC: {fmt(c['samples'][0])},\n{', '.join(fmt(s) for s in c['samples'][1:])}\n(the {c['rev']} chain, transistor\n"
                f"level; bit-exact with the RTL)", (c["sw"] * 1e3, np.mean(c["samples"]) / 1e6), xytext=(0.18, -0.9), textcoords="data",
                fontsize=7.3, color=INK2, va="top", arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.8))
    ax.text(-1.68, 7.0, minus(f"1 µV = {k7:,.0f} counts · 1 count = {1e3 / k7:.3f} nV\n0 V reads {d0:,.0f} (the AFE's {zero / afe * 1e6:.2f} µV)"),
            fontsize=8, color=INK, va="top", linespacing=1.4, bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    ax.set_xlim(-xmax, xmax)
    ax.set_ylim(-9.2, 9.2)
    ax.set_xlabel("Electrode input, ELP − ELN (mV)")
    ax.set_ylabel("DATA (millions of counts)")
    top = ax.secondary_xaxis("top", functions=(lambda m: m * afe / 1e3, lambda u: u / afe * 1e3))
    top.set_xlabel("ADC input, chopper-period mean (V)", fontsize=8, color=MUTED)
    top.tick_params(labelsize=7.5)
    ax.set_title(minus(f"DC and slow signals, offset DAC off: {k7:,.0f} counts per µV"), fontsize=9.5)
    ax.legend(loc="upper left", fontsize=7.3, bbox_to_anchor=(0.0, 0.72), frameon=True, facecolor="white", edgecolor="none",
              framealpha=1.0)

    # (b) frequency response
    ax = fig.add_subplot(gs[0, 1])
    f = np.logspace(-1, np.log10(64e3), 6000)
    ax.semilogx(f, 20 * np.log10(np.maximum(resp(f), 1e-9)), color=ACCENT, lw=1.5, label="Electrode to DATA, relative to DC")
    logf(ax, 0.1, 64e3)
    band(ax)
    ax.text(np.sqrt(BAND[0] * BAND[1]), -78, "EEG band", fontsize=7.5, color=MUTED, ha="center", va="bottom")
    for f0, dx, dy in ((10, -6, -26), (50, -10, -40), (100, 12, 9), (f3, 12, 8), (500, 12, 6)):
        y0 = db(f0)
        ax.plot([f0], [y0], "o", color=ACCENT, ms=4.5, zorder=4)
        ax.annotate(minus(f"{f0:.0f} Hz: {y0:+.3f} dB" if f0 < 200 else f"{f0:.0f} Hz: {y0:+.1f} dB"), (f0, y0), xytext=(dx, dy),
                    textcoords="offset points", fontsize=7.5, color=INK2, ha="right" if dx < 0 else "left",
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
    for fa_, fo, dy in ((1250, 250, -11), (1500, 500, 11)):
        y0 = db(fa_)
        ax.plot([fa_], [y0], "s", color=INK2, ms=4.5, mfc="white", mew=1.1, zorder=4)
        ax.annotate(minus(f"{fa_:,} Hz shows at {fo} Hz, {y0:+.1f} dB"), (fa_, y0), xytext=(-10, dy), textcoords="offset points",
                    fontsize=7.5, color=INK2, ha="right", va="center", arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
    ax.annotate("zero at every 1 kHz (DATA's rate):\nthe chain's 16 kHz tone\ndoes not show", (16e3, -79), xytext=(2.2e3, -27),
                textcoords="data", fontsize=7.5, color=INK2, ha="left", arrowprops=dict(arrowstyle="->", color=LIGHT, lw=0.8))
    ax.set_ylim(-80, 4)
    ax.set_xlabel("Input frequency (Hz)")
    ax.set_ylabel("Amplitude in DATA, relative to DC (dB)")
    ax.set_title(minus(f"Frequency: the CIC's sinc³ sets it (−3 dB at {f3:.0f} Hz); above 500 Hz an input shows at "
                       f"|f − n·1 kHz|"), fontsize=9.5)
    ax.text(0.13, -66, minus(f"The extracted AFE and the modulator's STF stay within {max(abs(20 * np.log10(a1k[0])), abs(20 * np.log10(s1k[0]))):.4f} dB "
                             f"of DC to 1 kHz\n({20 * np.log10(a16[0] * s16[0]):+.2f} dB at 16 kHz); only the CIC shapes the band."),
            fontsize=7.5, color=MUTED)

    # (c) electrode DC offset and the offset DAC
    ax = fig.add_subplot(gs[1, 0])
    lo_mv = 0.1
    v = np.logspace(np.log10(lo_mv), np.log10(lim_sat), 200)
    ax.plot(v, (d0 + k7 * v * 1e3) / 1e6, color=INK2, lw=1.4, label=f"DAC off: {k7:,.0f} counts per µV of offset")
    prev = 1.0
    for rg, top_mv in RANGE_MV.items():
        y = RES_MAX[rg] * 1e6 * k15 / 1e6
        ax.fill_between([prev, top_mv], [-y, -y], [y, y], color="#e0e7ff", lw=0, zorder=0,
                        label=f"DAC on: what the best code can leave (±{RES_MAX[1] * 1e6:.0f} / ±{RES_MAX[2] * 1e6:.0f} µV)" if rg == 1 else None)
        ax.axvline(top_mv, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.text(np.sqrt(prev * top_mv), 1.12, f"range {rg}", fontsize=7.3, color=MUTED, ha="center")
        prev = top_mv
    ax.axvspan(RANGE_MV[4], 450, color="#fef2f2", lw=0, zorder=0)
    ax.text(330, -1.05, "beyond\nrange 4", fontsize=7.3, color=BAD, va="bottom")
    place = {10: ((0, 8), "center", "bottom"), 20: ((0, 8), "center", "bottom"), 30: ((0, -8), "center", "top"),
             40: ((0, -8), "center", "top"), 50: ((8, 0), "left", "center"), 300: ((-8, 0), "right", "center")}
    for vin, (fin, m) in dc_runs.items():
        y = cnt * fin / 1e6
        ax.plot([vin], [y], "o", color=ACCENT, ms=6.5, mec="white", mew=1.0, zorder=4)
        off, ha, va = place.get(vin, ((0, 8), "center", "bottom"))
        ax.annotate(minus(f"{cnt * fin:+,.0f}\nM {m}"), (vin, y), xytext=off, textcoords="offset points", fontsize=7, color=INK2,
                    ha=ha, va=va, linespacing=1.1)
    ax.plot([], [], "o", color=ACCENT, ms=6.5, label="Extracted start-up runs, the code the firmware settles on")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xscale("log")
    ax.set_xlim(lo_mv, 450)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x_, _: f"{x_:g}"))
    ax.set_ylim(-1.2, 1.25)
    ax.set_xlabel("Electrode DC offset (mV)")
    ax.set_ylabel("DATA with no signal (millions of counts)")
    ax.set_title(minus(f"Electrode offsets: the DAC takes them out; a signal on top then reads {k15:,.0f} counts per µV"), fontsize=9.5)
    ax.legend(loc="lower left", fontsize=7.3)

    # (d) the table
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    pk = lambda a, f_: k7 * a * 10 ** (db(f_) / 20)                            # noqa: E731
    fin30, m30 = dc_runs.get(30, (np.nan, 0))
    fin300, m300 = dc_runs.get(300, (np.nan, 0))
    rows = [("Electrodes shorted (0 V)", "DAC off (default)", minus(f"{d0:,.0f}"), "start-up runs"),
            ("   its noise", "", f"≈ {ns * 1e6 * k7:.0f} rms a sample ({nb * 1e6 * k7:.0f} in 0.5–100 Hz)", "noise budget"),
            ("A change of 1 µV", "", f"{k7:,.0f}", f"{c['rev']} chain"),
            ("+0.3 mV DC, 0.5 mV at 16 kHz", "", " / ".join([fmt(c["samples"][0])] + [f"{s % 1000:03d}" for s in c["samples"][1:]]),
             f"{c['rev']} chain"),
            ("0.943 mV pk at 10 Hz (full scale)", "", f"±{pk(FS_SPEC * 1e6, 10):,.0f} pk", "slope × CIC"),
            ("100 µV pk at 100 Hz", "", f"±{pk(100, 100):,.0f} pk", "slope × CIC"),
            ("10 µV pk at 50 Hz", "", f"±{pk(10, 50):,.0f} pk", "slope × CIC"),
            ("100 µV pk at 1,250 Hz", "", f"±{pk(100, 1250):,.0f} pk at 250 Hz", "slope × CIC"),
            ("Any multiple of 1 kHz", "", "0", "CIC zeros"),
            ("+30 mV DC", f"range 1, M {m30}, BLANK 15", minus(f"{cnt * fin30:+,.0f}"), "extracted start-up"),
            ("+300 mV DC", f"range 4, M {m300}, BLANK 15", minus(f"{cnt * fin300:+,.0f}"), "extracted start-up"),
            (f"Beyond ±{lim_sat:.2f} mV", "DAC off", "not proportional", "behavioral loop"),
            (f"Beyond ±{RANGE_MV[4]} mV DC", "", "cannot be taken out", "DAC range 4")]
    xs = (0.0, 0.335, 0.555, 0.86)
    for xc, h_ in zip(xs, ("Input at the electrodes", "Setting", "DATA (counts)", "From")):
        ax.text(xc, 1.0, h_, fontsize=8.2, fontweight="semibold", color=INK, va="top", transform=ax.transAxes)
    ax.plot([0, 1], [0.955, 0.955], color=HAIR, lw=1.0, transform=ax.transAxes, clip_on=False)
    step = 0.94 / len(rows)
    for i, row in enumerate(rows):
        y = 0.93 - i * step
        for xc, txt in zip(xs, row):
            ax.text(xc, y, txt, fontsize=7.6, color=INK2 if xc else INK, va="top", transform=ax.transAxes)
    ax.set_title(minus(f"Examples (DAC off: {k7:,.0f} counts per µV; with the DAC and BLANK 15: {k15:,.0f})"), fontsize=9.5)
    save(fig, "32_input_output")


# ---------------------------------------------------------------- the ADC's poly-resistor flicker noise (11/12)

def logbin(f, p, lo, hi, nb=56):
    """power-averaged PSD in log-spaced bins (for a readable single-record spectrum)"""
    edges = np.logspace(np.log10(lo), np.log10(hi), nb + 1)
    fc, pc = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (f >= a) & (f < b)
        if m.any():
            fc.append(np.sqrt(a * b))
            pc.append(p[m].mean())
    return np.array(fc), np.array(pc)


def fig_adc_flicker():
    # r11 on (SRC "flicker"): RIN, DAC1 and R21 in ppolyf_u, each 300 kohm unit two strips of 320.48 x 0.8 um in series
    # (adc_flicker.py --unit); the figure then also shows r10's ppolyf_u_1k unit (runs/adc_flicker) for comparison
    src = SRC.get("flicker", "")
    d = json.load(open(os.path.join(PEX, "runs", "adc_flicker" + src, "adc_flicker.json")))
    lp, sm = d["loop"], d["summary"]
    fs, p10, dcr, z0, zt = lp["sine_fs"], lp["sine_10pct"], lp["dc_res153"], lp["zero"], lp["zero_therm"]
    g = d["g_afe"]
    i0 = d["i0"] * 1e6
    amp_fs = fs["amp_v"] / g * 1e6                 # µV pk at the electrodes
    # closed forms through the full-scale runs (the 10 Hz runs leave out sidebands beyond 100 Hz and within 0.5 Hz
    # of the tone, about 10 % below the closed forms)
    kb, kd, ka = fs["rin_b_nv"] / amp_fs, fs["dac_nv"] / amp_fs, fs["rin_a_nv"] / np.sqrt(amp_fs)
    pu = "unit" in sm
    utype, ul, uw, un = sm["unit"] if pu else ("ppolyf_u_1k", 291.28, 1.0, 1)
    unit = next(r for r in d["ngspice"] if r["type"] == utype and r["l_um"] == ul and abs(r["i_ua"] - 0.4064) < 1e-6)
    worst_ng = max(abs(r["ratio"] - 1) for r in d["ngspice"] if r["type"] == utype and (not pu or r["l_um"] == ul))
    if pu:
        prev = json.load(open(os.path.join(PEX, "runs", "adc_flicker", "adc_flicker.json")))
        pfs = prev["loop"]["sine_fs"]
        prev_unit = next(r for r in d["ngspice"] if r["type"] == "ppolyf_u_1k")
        what = (f"RIN (16 units per side, each {({2: 'two', 3: 'three'}).get(un, un)} ppolyf_u strips of {ul:g} × {uw:g} µm "
                f"in series) and DAC1 (31 cells, two "
                f"600 kΩ strings each, the same units)")
        model = (f"The PDK gives the body of ppolyf_u S_I = KF·|I|^AF / (f·L·W), KF {d['kf']:.2g}, AF {d['af']:.2f} (ngspice "
                 f".noise on afe_startup.res_mm agrees within {worst_ng * 100:.2f} %: one unit at {unit['i_ua']:.2f} µA gives "
                 f"{unit['sim_nv']:.0f} nV/√Hz at 10 Hz, against 70 nV/√Hz of 4kTR; r10's unit, one ppolyf_u_1k strip of "
                 f"291.28 × 1 µm, gave {prev_unit['sim_nv']:.0f}). ")
        level = (f"with AF {d['af']:.2f} its level KF·I^(AF−2) grows only as I^{d['af'] - 2:.2f} as the current falls "
                 f"(r10's ppolyf_u_1k, AF 1: as 1/I), so (b) sweeps I_cal for both. ")
    else:
        what = "RIN (16 ppolyf_u_1k units of 291.28 × 1 µm per side) and DAC1 (31 cells, two 600 kΩ strings each)"
        model = (f"The PDK gives the body of ppolyf_u_1k S_I = KF·|I|^AF / (f·L·W), KF 2.62e-26, AF 1 (ngspice .noise on "
                 f"afe_startup.res_mm agrees within {worst_ng * 100:.2f} %: one unit at {unit['i_ua']:.2f} µA gives "
                 f"{unit['sim_nv']:.0f} nV/√Hz at 10 Hz, against 70 nV/√Hz of 4kTR). ")
        level = "with AF = 1 its level KF/I grows as the current falls, so (b) sweeps I_cal. "
    fig = figure(13.6, 10.4, "Flicker noise of the ADC's poly resistors",
                 f"{what} with the PDK's 1/f model, through the behavioral CT loop and the RTL's DWA · 0.5–100 Hz, "
                 f"electrode-referred (AFE gain {g:.2f}) · typical, 27 °C",
                 note=minus(f"{model}A resistor's 1/f noise is a fluctuation "
                            f"of its resistance, noise current −I(t)·δR/R (Coram, McAndrew, Gullapalli, Kundert, IEEE TCAD 2020). "
                            f"Model B, used for the budget, takes δR/R at the PDK's level at a current I_cal and applies it to each "
                            f"resistor's own current: a DAC1 string carries a constant {i0:.2f} µA whatever the code, and the steering "
                            f"switches multiply its noise by the cell's ±1; with the DWA every cell's selection averages to the code, so "
                            f"only the part that follows the signal stays in the band. Model A applies KF·|I|^AF at RIN's instantaneous "
                            f"current, as a periodic-noise analysis with the PDK's model would; the paper shows that form is wrong when "
                            f"the current reverses. The PDK documents 1/f measurement conditions only for MOSFETs, and {level}"
                            f"Code streams: rtl/model/ct2_codes.py with "
                            f"{d['noise'] * 1e6:.0f} µVrms of white noise at its input, {d['n'] / FS:.1f} s at 1.024 MHz, tone "
                            f"{d['f0']:.2f} Hz (bins within 0.5 Hz of it count as the signal). Run: pex/adc_flicker.py."))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.12, 1])

    # (a) against the signal
    ax = fig.add_subplot(gs[0, 0])
    x = np.logspace(np.log10(3), np.log10(2000), 200)
    ax.loglog(x, kb * x, color=ACCENT, lw=1.6, label=f"RIN, model B (the PDK's level at {i0:.2f} µA)")
    ax.loglog(x, kd * x, color=TEAL, lw=1.6, label="DAC1 with the DWA (the same with A or B)")
    ax.loglog(x, np.hypot(kb, kd) * x, color=INK, lw=2.0, label="RIN + DAC1, model B")
    ax.loglog(x, ka * np.sqrt(x), color=LIGHT, lw=1.4, ls=(0, (5, 2.5)), label="RIN, model A (the PDK's |I| form, for reference)")
    if pu:
        tot_p = np.hypot(pfs["rin_b_nv"], pfs["dac_nv"])
        ax.loglog(x, tot_p / amp_fs * x, color=MUTED, lw=1.3, ls=(0, (2, 2)),
                  label="r10 (one ppolyf_u_1k strip per unit): RIN + DAC1, model B")
        ax.annotate(f"r10: {tot_p:.2f} nVrms", (amp_fs, tot_p), xytext=(-12, 8), textcoords="offset points", fontsize=7.5,
                    color=MUTED, ha="right", arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
    for r, mk in ((p10, "o"), (fs, "o"), (dcr, "s")):
        xv = (r["amp_v"] or r["dc_v"]) / g * 1e6
        ax.plot([xv], [r["rin_b_nv"]], mk, color=ACCENT, ms=6, mec="white", mew=1.0, zorder=4)
        ax.plot([xv], [r["dac_nv"]], mk, color=TEAL, ms=6, mec="white", mew=1.0, zorder=4)
        ax.plot([xv], [np.hypot(r["rin_b_nv"], r["dac_nv"])], mk, color=INK, ms=6.5, mec="white", mew=1.0, zorder=4)
        ax.plot([xv], [r["rin_a_nv"]], mk, color=LIGHT, ms=6, mfc="white", mew=1.2, zorder=4)
    ax.plot([], [], "o", color=INK2, ms=6, label="Loop runs, sine (10 % and full scale)")
    ax.plot([], [], "s", color=INK2, ms=6, label="Loop run, DC 153 µV (the offset DAC's largest residual)")
    ax.axhline(sm["room_nv"], color=BAD, lw=1.0, ls=(0, (4, 2.5)))
    ax.text(3.3, sm["room_nv"] * 1.12, f"room left for 16.5 bit at full scale: {sm['room_nv']:.2f} nVrms", fontsize=7.5, color=BAD)
    ax.axvline(amp_fs, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(amp_fs * 1.06, 0.0115 if pu else 0.25, f"full\nscale\n{amp_fs:.0f}\nµV pk", fontsize=7.5, color=MUTED, ha="left",
            va="bottom")
    tot = np.hypot(fs["rin_b_nv"], fs["dac_nv"])
    ax.annotate(f"{tot:.2f} nVrms\n(RIN {fs['rin_b_nv']:.2f}, DAC1 {fs['dac_nv']:.2f})", (amp_fs, tot), xytext=(-12, 22),
                textcoords="offset points", fontsize=7.5, color=INK, ha="right", arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
    ax.text(3.3, 7.5 if pu else 9.5, f"No input: DAC1 {z0['dac_nv']:.{3 if pu else 2}f} nVrms with the DWA,\n"
                      f"{zt['dac_nv']:.{2 if pu else 1}f} nVrms with the thermometer "
                      f"(DWA_EN = 0); RIN none", fontsize=7.6, color=INK2, va="top", linespacing=1.35,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    ax.set_xlim(3, 2000)
    ax.set_ylim(0.01, 60 if pu else 20)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("Signal at the electrodes, sine peak or DC (µV)")
    ax.set_ylabel("Flicker noise in 0.5–100 Hz (nVrms)")
    ax.set_title("It follows the signal: a gain noise of the ADC (the RIN / DAC1 ratio)", fontsize=9.5)
    if pu:
        ax.legend(loc="upper left", fontsize=6.9, ncol=2, columnspacing=1.2, handlelength=2.2)
    else:
        ax.legend(loc="lower right", fontsize=7.2)

    # (b) full-scale ENOB against where the PDK's level holds
    ax = fig.add_subplot(gs[0, 1])
    ic = np.array([s["i_cal"] for s in d["sweep"]]) * 1e6
    en = np.array([s["enob"] for s in d["sweep"]])
    if pu:
        icp = np.array([s["i_cal"] for s in prev["sweep"]]) * 1e6
        enp = np.array([s["enob"] for s in prev["sweep"]])
        ax.semilogx(icp, enp, color=MUTED, lw=1.4, ls=(0, (2, 2)), label="r10: one ppolyf_u_1k strip per unit (AF 1)")
        ax.plot([i0], [sm["enob_prev"]], "o", color=MUTED, ms=6, mec="white", mew=1.0, zorder=4)
        ax.annotate(f"r10 at {i0:.2f} µA: {sm['fs_b_prev_nv']:.2f} nVrms, {sm['enob_prev']:.2f} bit", (i0, sm["enob_prev"]),
                    xytext=(14, -8), textcoords="offset points", fontsize=7.5, color=MUTED, va="top",
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
    ax.semilogx(ic, en, color=ACCENT, lw=1.8,
                label=f"RIN + DAC1, model B ({({2: 'two', 3: 'three'}).get(un, un)} ppolyf_u strips per unit, AF {d['af']:.2f})" if pu else "RIN + DAC1, model B")
    ax.axhline(16.5, color=BAD, lw=1.0, ls=(0, (4, 2.5)))
    ax.text(0.105, 16.503, "target 16.5 bit", fontsize=7.5, color=BAD, va="bottom")
    ax.axhline(sm["base_enob"], color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(0.105, sm["base_enob"] + 0.003, f"without these terms: {sm['base_enob']:.2f} bit ({sm['base_nv']:.2f} nVrms)",
            fontsize=7.5, color=MUTED, va="bottom")
    ax.plot([i0], [sm["enob_b"]], "o", color=ACCENT, ms=7, mec="white", mew=1.2, zorder=4)
    if pu:          # A and B fall on one point: one label, and the crossing far left of the axis as text
        ax.plot([i0], [sm["enob_a"]], "o", color=LIGHT, ms=4.5, mfc="white", mew=1.1, zorder=5)
        ax.annotate(f"the PDK's level at our {i0:.2f} µA:\n{sm['fs_b_nv']:.2f} nVrms, {sm['enob_b']:.2f} bit\n"
                    f"(model A, open: {sm['fs_a_nv']:.2f} nVrms, {sm['enob_a']:.2f} bit)", (i0, sm["enob_b"]),
                    xytext=(3.2, 16.475), textcoords="data", fontsize=7.5, color=INK, va="top", linespacing=1.35,
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
        ax.text(95, 16.03, minus(f"At {i0:.2f} µA the flicker is ×{1 / sm['prev_ratio']:.3f} of r10's\n"
                                  f"({sm['fs_b_prev_nv']:.2f} nVrms in r10, {sm['fs_b_nv']:.2f} now). 16.5 bit\n"
                                  f"for any I_cal above {sm['i_cross'] * 1e6:.0e} µA (r10: above "
                                  f"{prev['summary']['i_cross'] * 1e6:.2f} µA)."),
                fontsize=7.5, color=INK2, ha="right", va="bottom", linespacing=1.4,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    else:
        ax.annotate(f"the PDK's level at our {i0:.2f} µA:\n{sm['fs_b_nv']:.2f} nVrms, {sm['enob_b']:.2f} bit", (i0, sm["enob_b"]),
                    xytext=(14, -6), textcoords="offset points", fontsize=7.5, color=INK, va="top",
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.7))
        ax.plot([i0], [sm["enob_a"]], "o", color=LIGHT, ms=6.5, mfc="white", mew=1.3, zorder=4)
        ax.annotate(f"model A: {sm['fs_a_nv']:.2f} nVrms, {sm['enob_a']:.2f} bit", (i0, sm["enob_a"]), xytext=(12, -2),
                    textcoords="offset points", fontsize=7.5, color=MUTED, va="center")
        ax.axvline(sm["i_cross"] * 1e6, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.text(sm["i_cross"] * 1e6 * 1.12, 16.33, f"16.5 bit if the PDK's level\nholds only above {sm['i_cross'] * 1e6:.2f} µA",
                fontsize=7.5, color=INK2, va="center")
        ax.text(0.105, 16.04, minus(f"At the PDK's level at {i0:.2f} µA:\n"
                                     f"· RIN and DAC1 in ppolyf_u (857 × 1 µm, AF 1.79): ×{sm['alt_ratio']:.3f}, {sm['enob_alt']:.2f} bit\n"
                                     f"· ppolyf_u_1k at 4× the area (582.56 × 2 µm): ×{sm['big_ratio']:.2f}, {sm['enob_big']:.2f} bit"),
                fontsize=7.5, color=INK2, va="bottom", linespacing=1.4, bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    ax.set_xlim(0.1, 100)
    ax.set_ylim(16.0, 16.62)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("I_cal: the current at which the PDK's level KF·I^(AF−2) is taken (µA)" if pu else
                  "I_cal: the current at which the PDK's level KF / I is taken (µA)")
    ax.set_ylabel("ENOB at full scale (bit)")
    ax.set_title("Full-scale ENOB against I_cal: nearly flat with ppolyf_u's AF 1.79" if pu else
                 "Full-scale ENOB: decided by where the PDK's AF = 1 fit holds", fontsize=9.5)
    if pu:
        ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.43), fontsize=7.2)

    # (c) DAC1's spectrum: the DWA moves the cells' noise out of the band
    ax = fig.add_subplot(gs[1, 0])
    for name, key, color, lw, lab in (("zero_therm", "dac", BAD, 1.4, "DAC1, no input, thermometer (DWA_EN = 0)"),
                                      ("sine_fs", "rin_b", ACCENT, 1.3, "RIN, model B, full-scale sine"),
                                      ("sine_fs", "dac", TEAL, 1.5, "DAC1, full-scale sine, DWA"),
                                      ("zero", "dac", INK2, 1.5, "DAC1, no input, DWA")):
        z = np.load(os.path.join(PEX, "runs", "adc_flicker" + src, f"psd_{name}.npz"))
        fc, pc = logbin(z["f"], z[key], 0.3, 400)
        ax.loglog(fc, np.sqrt(pc) * 1e9, color=color, lw=lw, label=lab)
    band(ax, label=True)
    ax.axvline(d["f0"], color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(d["f0"] * 1.06, 0.7 if pu else 3.5, f"tone {d['f0']:.1f} Hz", fontsize=7.3, color=MUTED, va="top")
    logf(ax, 0.3, 400)
    ax.set_ylim(*((1e-5, 1) if pu else (1e-4, 5)))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Electrode-referred noise (nV/√Hz)")
    ax.set_title("Spectra: with the DWA, DAC1 reaches the band only through the signal (one 4.1 s record, log bins)",
                 fontsize=9.5)
    ax.legend(loc="lower right", fontsize=7.2)

    # (d) the table
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    f2 = lambda v: f"{v:.3f}" if pu and 0 < v < 0.01 else f"{v:.2f}"                 # noqa: E731
    rows = [("No input (electrodes shorted)", f2(z0["rin_b_nv"]), f2(z0["dac_nv"]), f2(np.hypot(z0["rin_b_nv"], z0["dac_nv"])),
             f2(z0["rin_a_nv"])),
            ("   the same, DWA_EN = 0", "0.00", f"{zt['dac_nv']:.2f}", f"{zt['dac_nv']:.2f}", "0.00"),
            ("DC 153 µV (offset DAC's residual)", f2(dcr["rin_b_nv"]), f2(dcr["dac_nv"]),
             f2(np.hypot(dcr["rin_b_nv"], dcr["dac_nv"])), f2(dcr["rin_a_nv"])),
            (f"Sine {p10['amp_v'] / g * 1e6:.0f} µV pk (10 % of full scale)", f2(p10["rin_b_nv"]), f2(p10["dac_nv"]),
             f2(np.hypot(p10["rin_b_nv"], p10["dac_nv"])), f2(p10["rin_a_nv"])),
            (f"Sine {amp_fs:.0f} µV pk (full scale)", f2(fs["rin_b_nv"]), f2(fs["dac_nv"]), f2(tot), f2(fs["rin_a_nv"])),
            ("ENOB at full scale (bit)", "", "", f"{sm['enob_b']:.2f}", f"{sm['enob_a']:.2f}"),
            ("", "", "", "", ""),
            ("Reference filter R_f (ppolyf_u 2 × 7 µm, 30 µA)", "", "", f"{sm['rf_fs_nv']:.3f}", ""),
            (f"   {sm['rf_nv']:.0f} nVrms on VREFP − VREFN, against the 375 nVrms asked of the external reference", "", "", "", ""),
            ("Bias, VCM divider, ladder, R21", "", "", "≈ 0", ""),
            ("   common mode, or inside a loop, or after the first integrator", "", "", "", "")]
    xs = (0.0, 0.50, 0.62, 0.74, 0.88)
    for xc, h_ in zip(xs, ("nVrms in 0.5–100 Hz", "RIN (B)", "DAC1", "Sum (B)", "RIN (A)")):
        ax.text(xc, 1.0, h_, fontsize=8.2, fontweight="semibold", color=INK, va="top", transform=ax.transAxes)
    ax.plot([0, 1], [0.955, 0.955], color=HAIR, lw=1.0, transform=ax.transAxes, clip_on=False)
    step = 0.9 / len(rows)
    for i, row in enumerate(rows):
        y = 0.93 - i * step
        for xc, txt in zip(xs, row):
            ax.text(xc, y, minus(txt), fontsize=7.6, color=INK2 if xc else INK, va="top", transform=ax.transAxes)
    ax.set_title("Contributions (model B at the PDK's level at the strings' current; A for reference)", fontsize=9.5)
    save(fig, "33_adc_poly_flicker")


def pex_caps():
    """Every capacitor of the extracted afe_top: [(net a, net b, farad)]."""
    caps = []
    with open(AFE_C, encoding="utf-8") as f:
        for line in f:
            if line[:1] in "Cc":
                _, a, b, v = line.split()[:4]
                caps.append((a, b, float(v)))
    return caps


def sine_fit(t, v, f0):
    """Amplitude of the f0 component of v(t) with an offset and a linear drift fitted alongside."""
    w = 2 * np.pi * f0 * t
    a = np.column_stack([np.sin(w), np.cos(w), np.ones_like(t), t - t.mean()])
    c = np.linalg.lstsq(a, v, rcond=None)[0]
    return np.hypot(c[0], c[1])


ONLY = sys.argv[3:]
for fn in (fig_e2e, fig_e2e_effects, fig_e2e_metrics, fig_afe_bode, fig_afe_baseband, fig_ota_bode, fig_ntf, fig_zin_smith,
           fig_zin_bode, fig_power_on, fig_startup, fig_dc_input, fig_pex_sine, fig_adc_mc, fig_adc_loop_mc,
           fig_digital_noise, fig_input_output, fig_adc_flicker):
    if not ONLY or fn.__name__ in ONLY:
        fn()

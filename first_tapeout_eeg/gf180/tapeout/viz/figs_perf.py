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

usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r6_20261026/viz [names]
       (the chip version, r6, is set in vizstyle.py; the runs it reads must be of that chip)"""
import csv
import functools
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
# the runs of a later chip than r6 sit in <folder>_<chip> (EEG_PEX_REV, pex.py: r6's runs were still being read when
# r7 was made); r6's in the plain folders. The blocks' own runs (adc_mc, the start-up of afe_top) are shared where the
# blocks did not change.
RSFX = "" if vizstyle.CHIP == "r6" else f"_{vizstyle.CHIP}"
VIZ = os.path.join(PEX, "runs", "viz" + RSFX)
E2E = os.path.join(PEX, "runs", "e2e" + RSFX)
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


def rcsv(name):
    with open(os.path.join(VIZ, name + ".csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def col(rows, name):
    return np.array([float(r[name]) for r in rows])


def afe_ripple():
    """The AFE alone: output ripple outside the blanking (mV p-p), the final column of figs.py's afe_metrics.csv."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "afe_metrics.csv"), encoding="utf-8") as f:
        return float(next(r for r in csv.DictReader(f) if r["metric"].startswith("Output ripple"))["final"])


def summary(name):
    with open(os.path.join(VIZ, name + ".json"), encoding="utf-8") as f:
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
                label=f"{RUN[r]['label']}: A − B {ab:.2f} mV")
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
    sm = summary("ota_summary")
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
            r = rcsv(fn)
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
    r = rcsv("adc_ntf_stf")
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
    runs = {c: su_load(f"power_c{c:g}_v3.3_typical_+0mV_chip") for c, _ in CVCM}
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
    tb = settle_time(v10["t"], vbn_a, vbn_a[-1], 0.01 * vbn_a[-1])
    ax.annotate(f"VBN within 1 % at {tb * 1e3:.2f} ms", (tb * 1e3, vbn_a[-1]), textcoords="offset points", xytext=(12, -22),
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
    ax.set_title("VCM for the three VCM capacitors (final 1.650 V)", fontsize=9.5)
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
    ax.legend(loc="center right", fontsize=8)
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


SU_IB = "_ib3_chip"                     # the firmware writes AFE_IBIAS = 3 (afe_startup.py --ibias 3)


def fig_startup():
    gain = su_gain()
    typ = {vdd: su_release(f"start_c1e-08_v{vdd:g}_typical_+0mV_afe5ms{SU_IB}") for vdd in (3.3, 3.135, 3.465)}
    mc = [su_release(f"start_c1e-08_v3.3_mc{s}_+0mV_afe5ms{SU_IB}") for s in range(1, 31)]
    ran = [r for r in mc if r is not None]
    ok = [r for r in ran if r["done"]]
    if not ok:
        print("fig_startup: no Monte Carlo runs yet")
    t0 = typ[3.3]
    fig = figure(12.8, 14.6, "Start-up from power-on: the AFE released with the electrodes at 0 V",
                 "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, every pad of the ring, the board (assumed), bond wires · "
                 "27 °C · supplies ramp in 1 ms · RESET_N at 4.8 ms, AFE_IBIAS = 3 written 20 µs later, AFE_RST released at 5 ms · "
                 "VCM capacitor 10 nF",
                 note=f"Monte Carlo: {len(ok)} of 30 seeds reached the end ({len(ran) - len(ok)} stopped, {30 - len(ran)} not run); "
                      "each draws the PDK's global process and per-device mismatch, with stand-ins for the MIM and poly-resistor "
                      "mismatch (1.41 and 3 %·µm),\nand releases AFE_RST at a random phase of the chopper. The Monte Carlo and "
                      "±5 % runs end 1 ms after the release. Output values are chopper-period means; electrode-referred = output / "
                      f"{gain:.1f} (the AFE's chopped gain). Bottom row: averages over the\npreceding chopper period (the "
                      "instantaneous VBN and AVDD current carry transients at every chopper edge, VBN up to 8 mV), from the "
                      "simulator's own time points (each deck rerun to 5.1–5.4 ms).")
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
    ax.legend(loc="lower right", fontsize=8)
    ax = fig.add_subplot(gs[0, 1])
    for r in ok:
        a = r["x"] > 0
        ax.semilogy(r["x"][a] * 1e3, np.abs(r["m"][a] - r["final"]) * 1e3, color=LIGHT, lw=0.6, alpha=0.7)
    if t0 and t0["done"]:
        a = t0["x"] > 0
        ax.semilogy(t0["x"][a] * 1e3, np.abs(t0["m"][a] - t0["final"]) * 1e3, color=ACCENT, lw=1.5)
    for y, lab in ((1.0, f"1 mV ({1e3 / gain:.1f} µV at the electrodes)"), (0.1, f"0.1 mV ({1e2 / gain:.2f} µV)")):
        ax.axhline(y, color=MUTED, lw=0.9, ls=(0, (4, 3)))
        ax.text(2.98, y, lab, fontsize=7.5, color=MUTED, ha="right", va="bottom")
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
    # the trim write: the AFE's tail bias and the AVDD current from RESET_N to the release (typical)
    seq = [("code 3, written by the firmware", f"start_c1e-08_v3.3_typical_+0mV_afe5ms{SU_IB}", ACCENT, "-"),
           ("code 3 from power-on (for comparison)", "start_c1e-08_v3.3_typical_+0mV_afe5ms_ib3static_chip", INK2, (0, (5, 2.5))),
           ("code 2 (the reset value) kept", "start_c1e-08_v3.3_typical_+0mV_afe5ms_chip", LIGHT, (0, (1, 1.5)))]
    runs = []
    for lab, n, c, ls in seq:
        p = su_probe(n)
        if p is None:
            print(f"fig_startup: no probe rerun of {n} (the bottom row needs its exact averages)")
            continue
        with open(os.path.join(SU, n, "meta.json"), encoding="utf-8") as f:
            runs.append((lab, p, json.load(f), c, ls))
    ax_b, ax_i = fig.add_subplot(gs[2, 0]), fig.add_subplot(gs[2, 1])
    avg = {}
    for lab, v, meta, c, ls in runs:
        tr = meta["t_reset"]
        tg = np.arange(tr - 60e-6, meta["t_afe"] + 60e-6, 0.25e-6)
        vb, ia = period_mean(v["t"], v["vbn"], tg), period_mean(v["t"], v["iavdd"], tg)
        avg[lab] = (tg, vb, meta)
        ax_b.plot((tg - tr) * 1e6, vb * 1e3, color=c, ls=ls, lw=1.6, label=lab)
        ax_i.plot((tg - tr) * 1e6, ia * 1e3, color=c, ls=ls, lw=1.6,
                  label=f"{lab}: {np.interp(meta['t_afe'], tg, ia) * 1e3:.1f} mA at the release")
    for ax in (ax_b, ax_i):
        for xv, lab, y in ((0, "RESET_N: choppers start", 1.0), (20, "AFE_IBIAS = 3 written", 0.93), (200, "AFE_RST released", 1.0)):
            ax.axvline(xv, color=MUTED, lw=0.8, ls=(0, (1, 2)))
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
            ax_b.set_title(f"The AFE's tail bias VBN − AVSS: at the release {rel * 1e3:.2f} mV, the same as code 3 from "
                           f"power-on ({ref * 1e3:.2f} mV)", fontsize=9.5)
    ax_b.set_ylim(814, 848)
    ax_b.set_ylabel("Chopper-period average (mV)")
    ax_b.legend(loc="center right", fontsize=8)
    ax_i.set_ylim(23, 29.5)
    ax_i.set_ylabel("Chopper-period average (mA)")
    ax_i.set_title("AVDD current from the regulator (the ADC's 4.7 mA included)", fontsize=9.5)
    ax_i.legend(loc="center right", fontsize=8)
    save(fig, "26_startup")


VIN_DC = [10, 20, 30, 40, 50, 300]                     # electrode DC offsets of the DC-input runs (mV)
RAMP6 = ["#c7dbf7", "#9cc0ef", "#6d9fe3", "#3f7bd0", "#1f5aa8", "#0d366b"]   # one-hue ordinal steps


def dac_range(vin):
    return next(r for r, full in ((1, 39), (2, 79), (3, 159), (4, 318)) if abs(vin) <= full)


def su_dc_run(vin):
    """The DC-input run for vin with the code the firmware's search settles on: of the finished runs
    with a code of their own (_m<M>), the one that leaves the smallest output; else the nominal
    code round(vin / step); (name, M)."""
    base = f"start_c1e-08_v3.3_typical_{vin:+g}mV"
    alt = [n for n in os.listdir(SU) if n.startswith(base + "_m") and n.endswith("_afe5ms" + SU_IB)]
    done = [(abs(r["final"]), n) for n, r in ((n, su_release(n)) for n in alt) if r and r["done"]]
    if done:
        n = min(done)[1]
        return n, int(n[len(base) + 2:].split("_")[0])
    return base + "_afe5ms" + SU_IB, min(int(round(abs(vin) / UNIT_MV)), 2 ** NBITS[dac_range(vin)] - 1)


def fig_dc_input():
    gain = su_gain()
    runs = {}
    for vin in VIN_DC:
        name, m = su_dc_run(vin)
        r = su_release(name)
        if r and r["done"]:
            runs[vin] = (r, m)
    vafe = np.mean([r["vafe"] for r, _ in runs.values()]) if runs else 3.3
    step = UNIT_MV * vafe / 3.3                        # the DAC's unit swings the AFE's own supply
    fig = figure(12.8, 9.8, "Electrode DC offset from power-on, the offset DAC set as the firmware leaves it",
                 "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires · typical, 27 °C, AVDD 3.3 V · "
                 "the offset present from power-on · RESET_N at 4.8 ms, AFE_IBIAS = 3 written 20 µs later, AFE_RST released at 5 ms · "
                 "VCM capacitor 10 nF",
                 note=f"The DAC is static: its range and magnitude M are written before the release (range 1 to ±39 mV, 2 to ±79, "
                      f"3 to ±159, 4 to ±318 mV). One step is a 60 fF unit swung across the AFE's supply into the 636 pF input\n"
                      f"capacitor: {UNIT_MV:.3f} mV at 3.3 V, {step:.3f} mV at the {vafe:.3f} V the AFE has on the chip; M is the code "
                      f"the firmware's search settles on (the code that leaves the least). The DAC gives 0.05–0.16 % less than M × "
                      f"one step,\nso at 300 mV the search settles on 997, where the estimate would take 995. Output values are "
                      f"chopper-period means; electrode-referred = output / {gain:.1f}. Blanking 15 MCLK.")
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
    ax.legend(loc="center right", fontsize=7.5)
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
        ax.text(2.98, y, lab, fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax.set_xlim(0, 3.0)
    ax.set_ylim(1e-3, 10)
    ax.set_xlabel("Time from the AFE release (ms)")
    ax.set_ylabel("|output − final| (mV)")
    ax.set_title("Settling to the final value (mean of the last 16 periods)", fontsize=9.5)
    ax = fig.add_subplot(gs[1, 0])
    half = step / 2 * 1e3
    ax.axhspan(-half, half, color="#f1f5f9", lw=0, zorder=0)
    ax.text(0.01, half, f" ±½ step ({half:.0f} µV): the most a code can leave", transform=ax.get_yaxis_transform(),
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
        ax.plot([k], [r["t1"] * 1e3], "o", color=RAMP6[k], ms=7)
        ax.plot([k], [r["t01"] * 1e3], "s", color=RAMP6[k], ms=5, mfc="white", mew=1.4)
    ax.plot([], [], "o", color=ACCENT, label="to 1 mV")
    ax.plot([], [], "s", color=ACCENT, mfc="white", mew=1.4, label="to 0.1 mV")
    ax.set_xticks(range(len(runs)), [f"{v} mV" for v in runs])
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Electrode DC offset")
    ax.set_ylabel("Settled after the release (ms)")
    va = [r["vamax"] * 1e3 for r, _ in runs.values()]
    ax.set_title("Settling time" + (f" · |OPI − ONI| up to {max(va):.0f} mV in spikes at the chopper "
                                                    "edges, inside the blanking" if va else ""), fontsize=9.5)
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "27_dc_input")


def fig_pex_sine():
    """The full-scale sine from power-on on the chip (against the schematic where that run exists), its
    amplitude settling, and the extraction's capacitors."""
    gain = su_gain()
    nm = "start_c1e-08_v3.3_typical_+0mV_sine0.943mV2000Hz_afe5ms" + SU_IB
    d = {k: su_release(p + nm) for k, p in (("pex", ""), ("sch", "sch_"))}
    d = {k: r for k, r in d.items() if r and r["done"]}
    if "pex" not in d:
        print("fig_pex_sine: the extracted run is missing")
        return
    sch = "sch" in d
    f0 = 2000.0
    amp = {}
    for k, r in d.items():
        a = r["x"] > 0
        x, m = r["x"][a], r["m"][a]
        win = int(round(1 / f0 / TCH))                    # one signal period of chopper means
        tc, av = [], []
        for i in range(0, len(x) - win, win // 8):
            tc.append(x[i + win // 2])
            av.append(sine_fit(x[i:i + win], m[i:i + win], f0))
        amp[k] = (np.array(tc), np.array(av) / np.sinc(f0 * TCH))   # undo the chopper-period average
    caps = pex_caps()
    tot = {}
    for a_, b_, c in caps:
        for n in (a_, b_):
            tot[n] = tot.get(n, 0.0) + c
    top = sorted(((c, n) for n, c in tot.items() if n not in SUPPLIES), reverse=True)[:14]
    note_sch = ("The schematic run has neither afe_top's signal-path nor its rail resistance, and needs 1 fF from every node "
                "to ground, gear integration and reltol 1e-4 (1e-5 extracted) in ngspice." if sch else
                "The schematic blocks on this bench do not run through in ngspice (a 1e-19 s step at the end of the supply ramp, "
                "or at 1.33 ms with 1 fF per node, gear and reltol 1e-4);\nschematic against extracted: figure 20 (the "
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

ADC_MC = os.path.join(PEX, "runs", "adc_mc", "adc_block_mc.json")    # adc_block_mc.py (blocks, extracted)
ADC_BEH = os.path.join(PEX, "runs", "adc_beh_mc" + RSFX)              # adc_beh_mc.py (per-die loop model)
ADC_LOOP_MC = os.path.join(PEX, "runs", "adc_mc_loop" + RSFX)         # adc_loop_mc.py (transistor-level loop)
LSB_Q = 3.125                                                        # quantizer LSB at O2 (mV)
SNDR_165 = 6.02 * 16.5 + 1.76                                        # 16.5 bits (101.1 dB)
# r6: adc_beh_mc.py's defaults (the RTL's excess loop delay 3/32); r7: the delay that reproduces the transistor-level
# loop (0.22 of a clock)
BEH_TAG = "ain0.3_eld0.0938" if vizstyle.CHIP == "r6" else "ain0.3_eld0.2200"
BEH_ELD = "ELD 3/32 MCLK" if vizstyle.CHIP == "r6" else "ELD 0.22 of a clock, which reproduces the transistor-level loop"


def beh(kind):
    """adc_beh_mc.py's dies of one case ('even', 'corners', 'mc'): [dict], empty if not run."""
    p = os.path.join(ADC_BEH, f"{kind}_{BEH_TAG}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        res = json.load(f)["results"]
    return next(iter(res.values())) if res else []


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
                      f"model (DWA, {BEH_ELD}) with each die's blocks\n(adc_beh_mc.py), a 0.3 V pk 32 Hz sine at the ADC input "
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
    ax.text(30.4, 0.008, "requirement on the common part (all 31 together) ±0.008 fC", fontsize=7.5, color=BAD,
            ha="right", va="bottom")
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
        ax.set_title(f"DAC1, even-order charge per toggle ({len(dac)} of 30 seeds): common part {mn(al.mean())} ± "
                     f"{al.std(ddof=1):.4f} fC (worst {mn(al[np.abs(al).argmax()])}),\none cell σ {one.std(ddof=1):.4f} fC",
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
        ax.text(1.05e-4, zero[0], f"none: {zero[0]:.0f} dB (quantization, mismatch)", fontsize=7.5, color=MUTED, va="bottom")
    ax.axhline(SNDR_165, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.text(1.05e-4, SNDR_165, f"16.5 bits ({SNDR_165:.1f} dB)", fontsize=7.5, color=BAD, va="bottom")
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
    ax.legend(loc="center left", fontsize=8)
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
        ax.text(len(labels) - 0.3, y, lab, fontsize=7.5, color=BAD, ha="right", va="bottom")
    ax.set_yscale("log")
    ax.set_ylim(1e-4, 10)
    ax.set_xticks(list(range(len(cor))) + ([len(cor) + 0.5] if mc else []), labels, rotation=30, ha="right", fontsize=8)
    ax.set_xlim(-0.6, len(labels) - 0.2)
    ax.set_ylabel("At the electrodes (nVrms, 0.5–100 Hz)")
    ok = np.isfinite(hd2)
    if ok.any():
        ax.set_title(f"Each die's ADC error at full scale (0.943 mV pk): HD2 up to {np.nanmax(hd2):.2f} nVrms, "
                     f"the rest up to {np.nanmax(nz):.3f} nVrms (* with R / MIM ss, ff)", fontsize=9.5)
    ax.legend(loc="lower left", fontsize=8)
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
    col = {"typ": ACCENT, "mc": LIGHT, "rc": INK2, "z": BAD}
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
    ax.text(len(runs) - 0.5, 0.1, "a working loop stays below about 0.1", fontsize=7.5, color=MUTED, ha="right", va="bottom")
    ax.set_ylim(0, max(0.12, 1.15 * max(mt["resid"] for _, _, mt in runs)))
    ax = fig.add_subplot(gs[1, 0])
    for i, (k, _, mt) in enumerate(runs):
        ax.plot([i, i], mt["o2s"], "-", color=col[k], lw=3, solid_capstyle="butt")
    for s in (1, -1):
        ax.axhline(s * 46.875, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.text(len(runs) - 0.5, 46.875, "quantizer range ±46.9 mV", fontsize=7.5, color=BAD, ha="right", va="bottom")
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
           fig_zin_bode, fig_power_on, fig_startup, fig_dc_input, fig_pex_sine, fig_adc_mc, fig_adc_loop_mc):
    if not ONLY or fn.__name__ in ONLY:
        fn()

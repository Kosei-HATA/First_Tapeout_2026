#!/usr/bin/env python3
"""Performance figures of the final GF180 EEG chip from the simulation records, in the look of
figs.py: the end-to-end transient with parasitics (pex/pex_e2e.py, read through
pex/plot_e2e.py), Bode plots of the AFE amplifier, the AFE baseband transfer with chopping, the
ADC OTAs and the modulator's NTF/STF, and the AFE input impedance (pex/viz_data.py).

usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r6_20261026/viz [names]
       (the chip version, r6, is set in vizstyle.py; the runs it reads must be of that chip)"""
import csv
import importlib.util
import json
import os
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
VIZ = os.path.join(PEX, "runs", "viz")
E2E = os.path.join(PEX, "runs", "e2e")
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


ONLY = sys.argv[3:]
for fn in (fig_e2e, fig_e2e_effects, fig_e2e_metrics, fig_afe_bode, fig_afe_baseband, fig_ota_bode, fig_ntf, fig_zin_smith,
           fig_zin_bode):
    if not ONLY or fn.__name__ in ONLY:
        fn()

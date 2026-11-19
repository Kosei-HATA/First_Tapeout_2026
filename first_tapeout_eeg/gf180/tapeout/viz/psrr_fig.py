#!/usr/bin/env python3
"""Figure 46 (r12, 11/19): the chip's supply rejection, ripple on the AVDD and DVDD regulators.

psrr.py's results (gf180/tapeout/pex/runs/psrr_r12/results.json) and its runs: afe_startup.py's start deck (power-on;
the extracted afe_top, eeg_bias and eeg_ref on the chip wiring with the pads, bond wires and the board; typical, 27 C,
AFE_IBIAS 3, the AFE released at 5 ms) with ripple tones of 10 mV pk each on one regulator's output (1 kHz, and next to
the chopper's harmonics 1-3, which fold them onto 1.25, 1.5 and 1.75 kHz), legs of 100 ohm each or ELP 100 ohm +
51 kohm || 47 nF.
  (a) the output in band (as the chip's CIC sees it) of the AVDD run with legs of 100 ohm, and the fitted tones;
  (b) the supply rejection at the electrodes per tone, in band, against the board's ripple;
  (c) carried into the EEG band: the legs' currents through their own impedances from each leg's admittance to the
      supply at 1 kHz (without ngspice's gmin on the switches' PMOS wells), plus the balanced run's own conversion;
  (d) the regulator noise (flat, at the board next to the chip) that adds 5 % to the AFE's own 5.341 nVrms, in band and
      next to each chopper harmonic;
  (e) the Monte Carlo dies (process + mismatch) and the MOS corners on the AVDD deck with legs of 100 ohm (no
      baselines: each fitted alone): the folded tones, and the conversion between the choppers behind them;
  (f) the numbers behind them: the conversion between the choppers, the legs' capacitance to AVDD, the board's ripple.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/psrr_fig.py     (after gf180/tapeout/pex/psrr.py)
       EEG_PEX_REV=r13 ... psrr_fig.py: r13's runs (runs/psrr_r13/results.json) into figures/gf180/r13_20261119/viz
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, HAIR, INK, INK2, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
sys.path.insert(0, PEX)
import cmrr as C  # noqa: E402
import psrr as S  # noqa: E402

if S.REV == "r13":                                    # EEG_PEX_REV=r13: the thirteenth chip's runs and figure folder
    V.CHIP, V.CHIP_DATE, V.CHIP_LABEL = "r13", "20261119", "Chip r13 (thirteenth assembly, 19 Nov 2026)"
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL = "#0d9488"
COL = {"AVDD": ACCENT, "DVDD": TEAL}                  # checked with the dataviz validator (CVD, light)
IMB, BAL = "100+51k|47n", "100"
LEGS = {BAL: "legs 100 Ω each", IMB: "ELP 100 Ω + 51 kΩ || 47 nF"}
ADD5 = S.NOISE_NV * np.sqrt(1.05 ** 2 - 1)            # nVrms that adds 5 % to the AFE's own noise
XMAX = 1e6                                            # (d)'s right edge, nV/rtHz
SEEDS = range(1, 9)                                   # (e): the Monte Carlo dies and the MOS corners run_psrr_mc.sh runs
CORNERS = ("ss", "ff", "sf", "fs")


def minus(s):
    return s.replace("-", "−")


def tone_label(x):
    if x["harmonic"] == 0:
        return f"{x['f'] / 1e3:g} kHz (direct)"
    return f"{x['f'] / 1e3:g} kHz, out at {x['f_out'] / 1e3:g} kHz\n(the chopper's harmonic {x['harmonic']})"


def mark(ax, x, y, sup, legs, **kw):
    c = COL[sup]
    ax.plot(x, y, "o", ms=kw.pop("ms", 6.5), mec=c, mew=1.4, mfc=c if legs == BAL else "white", **kw)


def trace(r):
    """the output at the electrodes (uV) in band (psrr.py's three 62.5 us boxcars) over the run's window, against its
    baseline, the drift taken out by the run's own fit, and the fitted tones; the times moved back by the boxcars'
    delay (1.5 x 62.5 us)"""
    v, _ = C.load(os.path.join(S.RUNS, r["run"]), ["qo"])
    t, q = v["t"], v["qo"]
    if r["base"]:
        vb, _ = C.load(os.path.join(S.RUNS, r["base"]), ["qo"])
        n = min(len(t), len(vb["t"]))
        t, q = t[:n], q[:n] - vb["qo"][:n]
    tt, mm = S.boxcar3(t, q)
    t0, t1 = r["window"]
    a = (tt >= t0) & (tt < t1)
    tt, mm = tt[a][::S.DEC], mm[a][::S.DEC]
    u = (tt - 0.5 * (tt[0] + tt[-1])) / (0.5 * (tt[-1] - tt[0]))
    cols = [u ** p for p in range(r["poly"] + 1)]
    for tau in (x * 1e-3 for x in r["taus_ms"]):
        x = (tt - t0) / tau
        cols += [np.exp(-x), x * np.exp(-x)]
    nb = len(cols)
    for x in r["tones"]:
        w = 2 * np.pi * x["f_out"] * tt
        cols += [np.cos(w), np.sin(w)]
    A = np.column_stack(cols)
    y = mm / r["gain"] * 1e6
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    return tt - 1.5 * S.LBOX, y - A[:, :nb] @ c[:nb], A[:, nb:] @ c[nb:]


def together(xs):
    """the flat noise that adds 5 % when it sits next to every harmonic in xs at once (powers add)"""
    return 1 / np.sqrt(sum(1 / x["allowed_nv_rthz"] ** 2 for x in xs))


def density(v):
    return f"{v:,.0f} nV/√Hz" if v < 1e3 else f"{v / 1e3:,.0f} µV/√Hz"


def main():
    allres = json.load(open(os.path.join(S.OUT, "results.json"), encoding="utf-8"))
    sw = allres["switches_avdd"]
    runs = {(r["supply"], r["zp"]): r for r in allres["runs"]
            if r["zn"] == BAL and r["corner"] == "typical" and r["seed"] is None}
    keys = [k for k in (("AVDD", BAL), ("AVDD", IMB), ("DVDD", BAL), ("DVDD", IMB)) if k in runs]
    stat = {(r["seed"] if r["seed"] is not None else r["corner"]): r for r in allres["runs"]
            if r["supply"] == "AVDD" and r["zp"] == BAL and r["zn"] == BAL
            and (r["seed"] is not None or r["corner"] != "typical")}
    nstat = len(SEEDS) + len(CORNERS)
    if S.REV == "r13":     # r13's plan (runs/psrr_r13/run_psrr_r13.sh): AVDD only (afe_top changed; DVDD as r12), no baselines
        interim = len(keys) < 2 or len(stat) < nstat
    else:
        interim = len(keys) < 4 or not all(runs[k]["base"] for k in keys) or len(stat) < nstat
    r0 = runs[keys[0]]
    tones = r0["tones"]
    based = all(runs[k]["base"] for k in keys)          # r13: no baselines were run, every run is fitted alone

    fig = V.figure(12.8, 15.4, "Supply rejection: ripple on the AVDD and DVDD regulators" + (" (interim)" if interim else ""),
                   f"Ripple tones of {r0['rip_mv']:g} mV pk each at one regulator's output (1 kHz, and next to the "
                   "chopper's harmonics 1–3, which fold them into the band at the output) in the start deck: power-on, "
                   "the extracted AFE, bias and reference on the chip wiring with the pads, bond wires and board · "
                   "typical, 27 °C, AFE_IBIAS 3, the AFE released at 5 ms · "
                   + ("minus the same deck without ripple" if based else "each run fitted alone (no baselines)") + " · the "
                   "output in band as the chip's CIC sees it (three 62.5 µs boxcars), referred to the electrodes by the "
                   f"AFE's gain ({r0['gain']:.2f}) · (e) Monte Carlo dies (process + mismatch) and MOS corners",
                   note=minus(
                       "The ripple runs are cmrr.py's common-mode baselines (the common mode at 0) plus the ripple source, "
                       "so those baselines are theirs; the window is 6–10 ms (every tone a whole number of periods; the "
                       "chopper's harmonics too). In band: the CIC (sinc³, zeros every 1 kHz) passes only what the "
                       "output chopper leaves there; the boxcars (zeros every 16 kHz) take out the tones' direct "
                       "components next to a chopper harmonic as the CIC does. "
                       + ("(e)'s dies and corners have no baselines and are fitted alone (polynomial 4): on the typical "
                          "run" if based else "No run of this chip has a baseline; all are fitted alone (polynomial 4): "
                          "on r12's typical run") +
                       " the folded tones agree with the "
                       "baseline fit to 1e−5, while the 1 kHz and 257.5 kHz tones sit near the method's floor (139 against "
                       "143 dB) and the legs' admittances keep only their mean (the split between P and N takes ±3 pF of "
                       "the start-up's drift). (c) carries the 1 kHz tone into 0.5–100 Hz: "
                       "each leg's admittance to the supply at 1 kHz (conductance and capacitance; for AVDD without the "
                       f"{sw['g_gmin_ns_leg']:.2f} nS per leg that ngspice's default gmin puts across the input switches' "
                       "PMOS wells, not in silicon) through the legs' own impedances, plus the balanced run's own "
                       "conversion at 1 kHz, taken as flat and added in magnitude; the AVDD admittance was not run at "
                       "50 Hz. (d) a flat noise S in band gives S·√(∫|T|² df) at the electrodes; next to harmonic k "
                       "both sides fold, S·h·√(2 × 99.5 Hz); 5 % on top of the AFE's own "
                       f"{S.NOISE_NV} nVrms is {ADD5:.2f} nVrms. No noise in the runs; the board's values are "
                       "assumptions (0.05 Ω regulator, 10 µF + 100 nF). AVDD's regulator at 3.3 V in every run (the "
                       "chip's AVDD is set per die near 3.4 V; not run there)."))
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 0.62, 0.5])

    # (a) the output in band: the folded tones
    ax = fig.add_subplot(gs[0, 0])
    ka = ("AVDD", BAL)
    if ka in runs:
        r = runs[ka]
        tb, y, fitted = trace(r)
        ax.plot(tb * 1e3, y, color=COL["AVDD"], lw=3.0, alpha=0.35, solid_capstyle="round",
                label="the output in band, minus the start-up's drift")
        ax.plot(tb * 1e3, fitted, color=INK, lw=0.9, ls=(0, (4, 2)), label="the fitted tones")
        x1 = next(x for x in r["tones"] if x["harmonic"] == 1)
        x3 = next(x for x in r["tones"] if x["harmonic"] == 3)
        top = x1["vdm_uv"] + x3["vdm_uv"]
        ax.set_ylim(-1.55 * top, 1.9 * top)
        ax.text(0.01, 0.97, minus(f"{x1['f'] / 1e3:g} kHz, out at {x1['f_out'] / 1e3:g} kHz: {x1['vdm_uv']:.2f} µV pk "
                                  f"({x1['psrr_board_db']:.1f} dB)\n{x3['f'] / 1e3:g} kHz, out at {x3['f_out'] / 1e3:g} "
                                  f"kHz: {x3['vdm_uv']:.2f} µV pk ({x3['psrr_board_db']:.1f} dB)\n"
                                  "1 kHz, and 257.5 kHz out at 1.5 kHz: below 0.002 µV"),
                transform=ax.transAxes, va="top", fontsize=8, color=INK2, linespacing=1.4)
        ax.legend(loc="lower left", fontsize=7.6, ncol=2)
        ax.set_xlim(tb[0] * 1e3 - 0.05, tb[-1] * 1e3 + 0.05)
    ax.set_xlabel("time (ms; moved back by the boxcars' delay)")
    ax.set_ylabel("output at the electrodes (µV)")
    ax.set_title("AVDD ripple, legs 100 Ω each: the tones next to 128 and 384 kHz\ncome back in band at 1.25 and 1.75 kHz",
                 loc="left")

    # (b) the rejection per tone
    ax = fig.add_subplot(gs[0, 1])
    off = {("AVDD", BAL): -0.24, ("AVDD", IMB): -0.08, ("DVDD", BAL): 0.08, ("DVDD", IMB): 0.24}
    for k in keys:
        r = runs[k]
        for i, x in enumerate(r["tones"]):
            yy = i + off[k]
            mark(ax, [x["psrr_board_db"]], [yy], *k, label=f"{k[0]}, {LEGS[k[1]]}" if i == 0 else None)
            ax.text(x["psrr_board_db"] + 2.5, yy, f"{x['psrr_board_db']:.0f}", fontsize=7.4, color=INK2, va="center")
    ax.set_yticks(range(len(tones)))
    ax.set_yticklabels([tone_label(x) for x in tones], fontsize=8)
    ax.set_ylim(len(tones) - 0.5, -0.5)
    ax.set_xlim(35, 215)
    ax.set_xlabel("supply rejection at the electrodes, in band (dB, against the board's ripple)")
    ax.legend(loc="lower right", fontsize=7.6)
    ax.set_title("Rejection per tone: the output in band over the ripple on the\nboard (filled: legs 100 Ω; open: 51 kΩ || 47 nF)",
                 loc="left")

    # (c) carried into the band
    ax = fig.add_subplot(gs[1, 0])
    for k in keys:
        r = runs[k]
        if "band" not in r:
            continue
        b = r["band"]
        ax.semilogx(b["f_hz"], [-20 * np.log10(v) for v in b["transfer"]], color=COL[k[0]], lw=1.4,
                    ls="-" if k[1] == IMB else (0, (4, 2)), label=f"{k[0]}, {LEGS[k[1]]}")
        x = next(x for x in r["tones"] if x["harmonic"] == 0)
        mark(ax, [x["f"]], [x["psrr_board_db"]], *k)
        if k[1] == IMB:
            ax.plot([50], [b["psrr50_db"]], "|", color=COL[k[0]], ms=9, mew=1.3)
            ax.annotate(f"{b['psrr50_db']:.1f} dB at 50 Hz", (50, b["psrr50_db"]), xytext=(5, -15),
                        textcoords="offset points", fontsize=7.6, color=INK2)
    ax.axvspan(S.BAND[0], S.BAND[1], color="#f1f5f9", zorder=0)
    ax.set_xlim(0.4, 2e3)
    ax.set_ylim(40, 210)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("supply rejection at the electrodes (dB)")
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.86), fontsize=7.6)
    ax.set_title("Carried into the EEG band (shaded): the legs' admittance to the supply\nat 1 kHz through their impedances, "
                 "plus the chip's own (dots: the 1 kHz runs)", loc="left")

    # (d) the regulator noise that adds 5 %
    ax = fig.add_subplot(gs[1, 1])
    rows = ["in band, 0.5–100 Hz", "128 kHz ± 100 Hz (k = 1)", "256 kHz ± 100 Hz (k = 2)", "384 kHz ± 100 Hz (k = 3)",
            "k = 1 and 3 together"]
    for k in keys:
        r = runs[k]
        by = {x["harmonic"]: x for x in r["tones"] if x.get("allowed_nv_rthz")}
        vals = [r.get("band", {}).get("allowed_nv_rthz"), by[1]["allowed_nv_rthz"], by[2]["allowed_nv_rthz"],
                by[3]["allowed_nv_rthz"], together([by[1], by[3]])]
        for i, v in enumerate(vals):
            if v is None:
                continue
            yy = i + off[k]
            if v > XMAX:
                ax.annotate("", (XMAX, yy), xytext=(XMAX / 5, yy),
                            arrowprops=dict(arrowstyle="->", color=COL[k[0]], lw=1.1))
                continue
            mark(ax, [v], [yy], *k)
            ax.text(v * 1.4, yy, density(v).replace("/√Hz", ""), fontsize=7.4, color=INK2, va="center")
    ax.set_xscale("log")
    ax.set_xlim(5, XMAX)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_xlabel("the regulator's noise there, flat (nV/√Hz at the board next to the chip; arrows: above 1 mV/√Hz)")
    ax.set_title(f"The regulator noise that adds 5 % to the AFE's own {S.NOISE_NV} nVrms\n(0.5–100 Hz at the electrodes; "
                 "markers as in (b))", loc="left")

    # (e) the dies and the corners
    ax = fig.add_subplot(gs[2, :])
    ref = runs.get(("AVDD", BAL))
    cols = [("typical", ref)] + [(f"mc {s_}", stat.get(s_)) for s_ in SEEDS] + [(c, stat.get(c)) for c in CORNERS]
    xs = [0.0] + [1.4 + i for i in range(len(SEEDS))] + [1.4 + len(SEEDS) + 0.4 + j for j in range(len(CORNERS))]
    lo_hi = []
    yv_all = [x["psrr_board_db"] for _, r in cols if r is not None for x in r["tones"] if x["harmonic"] in (1, 3)]
    ylo, yhi = np.floor(min(yv_all)) - 6.0, np.ceil(max(yv_all)) + 2.0
    for (name, r), xx in zip(cols, xs):
        if r is None:
            ax.text(xx, ylo + 0.62 * (yhi - ylo), "running", rotation=90, ha="center", va="center", fontsize=7.4,
                    color=MUTED)
            continue
        by = {x["harmonic"]: x for x in r["tones"]}
        big = 8 if name == "typical" else 6.5
        ax.plot([xx], [by[1]["psrr_board_db"]], "o", ms=big, mec=COL["AVDD"], mew=1.4, mfc=COL["AVDD"],
                label=minus(f"{by[1]['f'] / 1e3:g} kHz, out at {by[1]['f_out'] / 1e3:g} kHz (k = 1)") if xx == 0 else None)
        ax.plot([xx], [by[3]["psrr_board_db"]], "o", ms=big, mec=COL["AVDD"], mew=1.4, mfc="white",
                label=minus(f"{by[3]['f'] / 1e3:g} kHz, out at {by[3]['f_out'] / 1e3:g} kHz (k = 3)") if xx == 0 else None)
        ax.text(xx, by[1]["psrr_board_db"] - 1.25, f"{by[1]['between_vv']:.2f}", ha="center", va="top", fontsize=7.2,
                color=INK2)
        if name != "typical":
            lo_hi.append((name, by[1]["psrr_board_db"], by[3]["psrr_board_db"],
                          min(by[0]["psrr_board_db"], by[2]["psrr_board_db"])))
    if ref:
        for kk in (1, 3):
            yv = next(x for x in ref["tones"] if x["harmonic"] == kk)["psrr_board_db"]
            ax.axhline(yv, color=HAIR, lw=1.0, ls=(0, (4, 2)), zorder=0)
    ax.set_xticks(xs)
    ax.set_xticklabels([c[0] for c in cols], fontsize=8)
    ax.set_xlim(-0.7, xs[-1] + 0.7)
    ax.set_ylim(ylo, yhi)
    ax.set_ylabel("supply rejection (dB)")
    ax.legend(loc="lower left", bbox_to_anchor=(0.06, 0.02), fontsize=7.6)
    ax.set_title("Monte Carlo dies (process + mismatch) and MOS corners, AVDD, legs 100 Ω each, each fitted alone"
                 + (f" (interim: {len(stat)} of {nstat})" if len(stat) < nstat else "")
                 + ":\nthe fold is the same on every die and follows the conversion between the choppers "
                 "(OPI − ONI in V/V under the filled markers; dashed: typical)", loc="left")

    # (f) the numbers
    ax = fig.add_subplot(gs[3, :])
    ax.set_axis_off()
    left, right = [], []
    a, d = runs.get(("AVDD", BAL)), runs.get(("DVDD", BAL))
    if a:
        x0 = next(x for x in a["tones"] if x["harmonic"] == 0)
        x1 = next(x for x in a["tones"] if x["harmonic"] == 1)
        x2 = next(x for x in a["tones"] if x["harmonic"] == 2)
        x3 = next(x for x in a["tones"] if x["harmonic"] == 3)
        hi = [x["between_vv"] for x in a["tones"] if x["harmonic"] > 0]
        left.append("Between the choppers (the amplifier's own OPI − ONI per V of the board's ripple), legs 100 Ω:")
        span = f"{min(hi):.2f}" if f"{min(hi):.2f}" == f"{max(hi):.2f}" else f"{min(hi):.2f}–{max(hi):.2f}"
        line = f"  AVDD {x0['between_vv']:.2f} V/V at 1 kHz, {span} V/V at 129–386 kHz"
        if d:
            line += (f"; DVDD {min(x['between_vv'] for x in d['tones']) * 1e3:.1f}–"
                     f"{max(x['between_vv'] for x in d['tones']) * 1e3:.1f} mV/V")
        left.append(line)
        left.append(f"  The output chopper's harmonic k brings (2/π)/k of it into band: {x1['fold_pred_uv']:.2f} µV at "
                    f"1.25 kHz (measured {x1['vdm_uv']:.2f}),")
        left.append(f"  {x3['fold_pred_uv']:.2f} µV at 1.75 kHz (measured {x3['vdm_uv']:.2f}); none at even k "
                    f"(257.5 kHz: {x2['vdm_uv'] * 1e3:.1f} nV)")
        s = a["direct"].get("split")
        if s:
            tot = -0.5 * (a["direct"]["cp_pf"] + a["direct"]["cn_pf"])
            icm = abs(complex(a["direct"]["icm_re"], a["direct"]["icm_im"]))
            pcm = abs(complex(a["direct"]["pcm_re"], a["direct"]["pcm_im"]))
            left.append(f"Each leg's capacitance to AVDD at 1 kHz: {tot:.1f} pF = the input switches' PMOS wells "
                        f"{s['c_sw_pf']:.1f} pF")
            left.append(f"  + through Cin {s['c_cin_pf']:.1f} pF (the amplifier's input common mode moves "
                        f"{icm * 100:.1f} % of the ripple, the pins {pcm * 100:.1f} %) + {s['c_rest_pf']:.1f} pF not split")
        if d:
            left.append(f"  To DVDD: {-0.5 * (d['direct']['cp_pf'] + d['direct']['cn_pf']):.1f} pF per leg")
        if lo_hi:
            left.append(f"The dies and corners in (e), {len(lo_hi)} of {nstat}: {min(x[1] for x in lo_hi):.1f}–"
                        f"{max(x[1] for x in lo_hi):.1f} dB at 1.25 kHz, {min(x[2] for x in lo_hi):.1f}–"
                        f"{max(x[2] for x in lo_hi):.1f} dB at 1.75 kHz; 1 kHz and 257.5 kHz "
                        f"{min(x[3] for x in lo_hi):.0f} dB and above")
        cl = [-0.5 * (r["direct"]["cp_pf"] + r["direct"]["cn_pf"]) for r in stat.values() if "direct" in r]
        if cl:
            left.append(f"  each leg's capacitance to AVDD there {min(cl):.1f}–{max(cl):.1f} pF (the legs' mean)")
    rb = runs[keys[0]]
    right.append("The ripple for 10 mV pk at the regulator,")
    right.append("on the board / on the chip (AVDD, mV pk):")
    right.append("  " + ", ".join(f"{x['board_mv']:.2f} / {x['chip_mv']:.2f}" for x in rb["tones"]))
    if a:
        right.append(f"The 1 kHz ripple's square wave at the ADC's input: AVDD {a['direct']['chopped_ratio']:.2f} V/V")
        right.append(f"  (10 mV takes {a['direct']['chopped_mv']:.1f} mV of the ADC's ±484 mV)")
    right.append("Next to 128 and 384 kHz together, the noise that adds 5 %:")
    for k in keys:
        r = runs[k]
        by = {x["harmonic"]: x for x in r["tones"] if x.get("allowed_nv_rthz")}
        right.append(f"  {k[0]}, {LEGS[k[1]]}: {density(together([by[1], by[3]]))}")
    if stat:
        wv, wn = min((together([next(x for x in r["tones"] if x["harmonic"] == kk) for kk in (1, 3)]), n)
                     for n, r in stat.items())
        right.append(f"  AVDD, legs 100 Ω, the lowest of the dies and corners: {density(wv)} "
                     f"({'mc ' + str(wn) if isinstance(wn, int) else wn})")
        # the odd harmonics above 3 fold (2/pi)/k of the same conversion (taken as flat): their powers add
        a1 = next(x for x in stat[wn]["tones"] if x["harmonic"] == 1)["allowed_nv_rthz"]
        hi = 1 / np.sqrt(1 / wv ** 2 + sum(1 / k ** 2 for k in range(5, 2001, 2)) / a1 ** 2)
        right.append(f"    with the odd harmonics above 3 too ((2/π)/k each): {density(hi)}")
    ax.text(0.0, 0.98, minus("\n".join(left)), transform=ax.transAxes, va="top", fontsize=8.2, color=INK,
            linespacing=1.45)
    ax.text(0.63, 0.98, minus("\n".join(right)), transform=ax.transAxes, va="top", fontsize=8.2, color=INK,
            linespacing=1.45)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_46_psrr.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, "(interim)" if interim else "")


if __name__ == "__main__":
    main()

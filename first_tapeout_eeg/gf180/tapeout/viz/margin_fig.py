#!/usr/bin/env python3
"""Figure 43 (r12, 11/17): margins on what the PDK does not give.

  - DAC1's element mismatch: the poly resistors' per-device mismatch is a stand-in (3 %·um, the block Monte Carlo).
    enob_sine.py --margin mm: the sine test (full scale at the electrodes to DATA, ENOB from the SINAD) on the 30
    Monte Carlo dies with DAC1's element errors (static, and the random part of the even charge) times 1, 2, 4, 8;
    --margin mmlow: 6 of them without noise at -60 dBFS and without input, where DWA's idle tones would show.
  - The input resistors' voltage coefficient: the PDK's terms are 0. enob_sine.py --margin vc: typical with
    R(v) = RIN (1 + vc1 v + vc2 v^2) for the voltage across each input resistor.
  - The offset DAC's MIM mismatch: the MIM's per-device mismatch is a stand-in too (1.41 %·um, mim_mm.spice). The
    extracted bit weights (figs_perf.dac_weights: each MIM with its wiring) plus a random error per bit MIM, sigma =
    0.7071 x 1.41 %·um x scale / sqrt(area) of its capacitance on each half (the halves averaged), 20,000 dies per
    scale: the smallest step (monotonic or not) and the largest residual (half the largest step, what the search
    leaves at worst) against the firmware's window (+-54 mV at the ADC input, 0.6 of a step).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/margin_fig.py     (after enob_sine.py --margin mm, mmlow and vc)
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, BAD, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
ENOB = os.path.join(PEX, "runs", f"enob_sine_{V.CHIP}")
argv, sys.argv = sys.argv, [sys.argv[0], PEX, OUT, "-"]      # figs_perf draws only the figures named after these: none
import figs_perf as F  # noqa: E402  (the offset DAC's extracted bit weights)
sys.argv = argv
TEAL, PLUM, AMBER, BLUE = "#0d9488", "#a21caf", "#b45309", "#1f5aa8"
RCOL = {1: TEAL, 2: BLUE, 3: PLUM, 4: AMBER}
TARGET = 16.5
HD3_REQ = -111.0
A_SIDE = 0.5 * 297.75 * 0.943e-3                      # V pk across each input resistor at full scale
MIM_A = 0.0141                                         # the stand-in pair coefficient, um (1.41 %·um)
UV_PER_FF = 3.196 / 638.08e-12 * 1e-15 * 1e6           # the AFE's supply over Cin (figs_perf.dac_fit)
WIN_UV = 54.0 / 287.25 * 1e3                           # the firmware's +-54 mV at the ADC input, at the electrodes
SCALES = [1, 2, 4, 8]
N_DIES = 20000


def minus(s):
    return s.replace("-", "−")


def offset_dac():
    """per range and scale: the smallest step's 0.1 % point, the share of non-monotonic dies, the largest residual's
    99.9 % point and the share of dies whose largest residual leaves the window (uV)"""
    w = F.dac_weights()
    txt = open(F.AFE_C, encoding="utf-8").read()
    area = [sum(float(a) * float(b) for a, b in re.findall(
        rf"\sODP\.H\.BP{k}\s+cap_mim_2f0ff\s+c_width=([\d.]+)u\s+c_length=([\d.]+)u", txt)) for k in range(10)]
    rng = np.random.default_rng(7)
    res = {}
    for r in range(1, 5):
        nb = 6 + r
        codes = np.arange(2 ** nb)
        bits = ((codes[:, None] >> np.arange(nb)[None, :]) & 1).astype(float)
        w0 = np.array([w[k, r] for k in range(nb)])
        st0 = np.diff(bits @ w0) * UV_PER_FF
        res[r, 0] = dict(smin=st0.min(), smax=st0.max(), resid=st0.max() / 2, nonmono=0.0, out=0.0)
        for s in SCALES:
            sig = 0.7071 * MIM_A * s / np.sqrt(area[:nb]) * 60.0 * 2.0 ** np.arange(nb) / np.sqrt(2)
            st = np.diff((w0[None, :] + rng.standard_normal((N_DIES, nb)) * sig[None, :]) @ bits.T, axis=1) * UV_PER_FF
            smin, smax = st.min(axis=1), st.max(axis=1)
            res[r, s] = dict(smin=np.percentile(smin, 0.1), nonmono=100 * (smin <= 0).mean(),
                             resid=np.percentile(smax, 99.9) / 2, out=100 * (smax / 2 > WIN_UV).mean())
    return res


def main():
    mm = json.load(open(os.path.join(ENOB, "enob_sine_margin_mm.json"), encoding="utf-8"))["rows"]
    low = json.load(open(os.path.join(ENOB, "enob_sine_margin_mmlow.json"), encoding="utf-8"))["rows"]
    vc = json.load(open(os.path.join(ENOB, "enob_sine_margin_vc.json"), encoding="utf-8"))["rows"]
    dac = offset_dac()

    fig = V.figure(12.8, 13.6, "Margins on what the PDK does not give: poly mismatch, the resistors' voltage coefficient, "
                   "MIM mismatch",
                   "The sine test of figure 35 (full scale at the electrodes through the AFE's transfer, the extracted "
                   "ADC's loop model and the RTL's decimator to DATA; SINAD over 0.5–100 Hz) with each unknown swept, "
                   "and the offset DAC's extracted bit weights with random MIM errors · typical, 27 °C",
                   note="DAC1's element mismatch comes from the block Monte Carlo with the stand-in poly coefficient "
                        "(3 %·µm); its static errors and the random part of its even charge are scaled, DAC2, the "
                        "thresholds and the rest left as they are. The input resistors carry the signal (±0.14 V across "
                        "each at full scale); DAC1's resistors switch between two levels, so a voltage coefficient there "
                        "only scales them. One record's ENOB scatters by about 0.025 bit (1 σ). The offset DAC: 20,000 "
                        "dies per scale, each bit's MIM with σ = 0.7071 × 1.41 %·µm × scale / √area of its capacitance "
                        "on each half; the window is the firmware's ±54 mV at the ADC input (0.6 of a step), within "
                        "which M does not move in operation.")
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 0.42])

    # (a) ENOB with noise, the 30 dies per scale
    ax = fig.add_subplot(gs[0, 0])
    means = {}
    for i, s in enumerate(SCALES):
        e = np.array([r["enob"] for r in mm if r["group"] == f"mm{s}" and "enob" in r])
        x = i + np.linspace(-0.18, 0.18, len(e))
        ax.scatter(x, e, s=14, color=ACCENT, alpha=0.55, lw=0)
        ax.plot([i - 0.28, i + 0.28], [e.mean()] * 2, color=INK, lw=1.6)
        means[s] = (e.mean(), e.min(), len(e))
    ax.axhline(TARGET, color=BAD, lw=1.0, ls=(0, (4, 2)))
    ax.text(len(SCALES) - 0.55, TARGET + 0.004, "target 16.5 bit", color=BAD, fontsize=8, ha="right", va="bottom")
    ax.set_xticks(range(len(SCALES)), [f"×{s}" for s in SCALES])
    ax.set_xlabel("DAC1's element mismatch against the block Monte Carlo's")
    ax.set_ylabel("ENOB from DATA (bit)")
    ax.set_title(f"30 Monte Carlo dies per scale, with noise: mean {means[1][0]:.3f} at ×1, {means[8][0]:.3f} bit at ×8",
                 loc="left")

    # (b) the in-band error without noise, 6 dies per scale: full scale, -60 dBFS, no input (DWA's idle tones)
    ax = fig.add_subplot(gs[0, 1])
    cpu = np.mean([r["counts_per_uv"] for r in mm if r["group"] == "mm1" and "counts_per_uv" in r])
    nl = {}
    for kind, grp, col, lab in (("fs", "mm{}_nl", PLUM, "full scale"), ("low", "mmlow{}", TEAL, "−60 dBFS"),
                                ("zero", "mmzero{}", AMBER, "no input")):
        src = mm if kind == "fs" else low
        ys = []
        for i, s in enumerate(SCALES):
            rs = [r for r in src if r["group"] == grp.format(s)]
            y = np.array([r["nad_nv"] if "nad_nv" in r else r["nad_counts"] / cpu * 1e3 for r in rs])
            ax.scatter(i + np.linspace(-0.12, 0.12, len(y)) + {"fs": -0.25, "low": 0.0, "zero": 0.25}[kind], y, s=16,
                       color=col, lw=0, alpha=0.8)
            ys.append(y)
        ax.plot(np.arange(len(SCALES)) + {"fs": -0.25, "low": 0.0, "zero": 0.25}[kind], [y.max() for y in ys], color=col,
                lw=1.2, label=f"{lab} (line: the worst die)")
        nl[kind] = ys
    ax.set_yscale("log")
    ax.set_xticks(range(len(SCALES)), [f"×{s}" for s in SCALES])
    ax.set_xlabel("DAC1's element mismatch against the block Monte Carlo's")
    ax.set_ylabel("in-band error without noise (nVrms at the electrodes)")
    ax.legend(loc="lower right", fontsize=7.6)
    worst = max(float(y.max()) for ys in nl.values() for y in ys)
    ax.set_title(f"Without noise (6 dies), 0.5–100 Hz: the loop's own error, at most {worst:.2f} nVrms\n"
                 "(the budget's total is 6.14 nVrms); with no input it grows with the mismatch", loc="left")

    # (c) HD3 against the input resistors' vc2
    ax = fig.add_subplot(gs[1, 0])
    rows = sorted((r for r in vc if r["group"] == "vc2_nl"), key=lambda r: r["vc2"])
    v2 = np.array([r["vc2"] * 1e6 for r in rows])
    hd3 = np.array([r["hd"][1] for r in rows])
    base = hd3[v2 == 0][0]
    k = v2 > 0
    ax.semilogx(v2[k], hd3[k], "o-", color=ACCENT, lw=1.4, ms=5, label="the chain (AFE's transfer, loop) with it")
    xs = np.logspace(1, 4.6, 50)
    ax.semilogx(xs, 20 * np.log10(xs * 1e-6 * A_SIDE ** 2 / 4), color=MUTED, lw=1.0, ls=(0, (4, 2)),
                label="the input resistors alone: vc2 · (0.14 V)² / 4")
    ax.axhline(base, color=LIGHT, lw=0.9)
    ax.text(1500, base + 0.8, minus(f"vc2 = 0: {base:.1f} dBc (the AFE's own)"), fontsize=7.8, color=MUTED)
    ax.axhline(HD3_REQ, color=BAD, lw=1.0, ls=(0, (4, 2)))
    ax.text(12, HD3_REQ + 0.8, minus("requirement −111 dBc"), fontsize=7.8, color=BAD)
    x111 = 10 ** np.interp(HD3_REQ, hd3[k], np.log10(v2[k])) if (hd3[k] > HD3_REQ).any() else None   # hd3 rises with vc2
    ax.set_xlabel("vc2 of the input resistors (ppm/V²)")
    ax.set_ylabel("HD3 at full scale, without noise (dBc)")
    ax.set_ylim(base - 3, hd3.max() + 4)
    ax.legend(loc="upper left", fontsize=7.6)
    ax.set_title(minus(f"HD3 reaches −111 dBc at vc2 ≈ {x111:.0f} ppm/V²" if x111 else "HD3 against vc2"), loc="left")

    # (d) ENOB against vc2
    ax = fig.add_subplot(gs[1, 1])
    rn = sorted((r for r in vc if r["group"] == "vc2"), key=lambda r: r["vc2"])
    v2n = np.array([r["vc2"] * 1e6 for r in rn])
    en = np.array([r["enob"] for r in rn])
    enl = np.array([r["enob"] for r in rows])
    kk = v2n > 0
    ax.semilogx(v2n[kk], en[kk], "o-", color=ACCENT, lw=1.4, ms=5, label="with noise (one record each)")
    ax.semilogx(v2[k], enl[k], "s-", color=PLUM, lw=1.0, ms=4, label="without noise")
    ax.axhline(en[v2n == 0][0], color=LIGHT, lw=0.9)
    ax.text(5000, en[v2n == 0][0] + 0.12, f"vc2 = 0, with noise: {en[v2n == 0][0]:.3f} bit", fontsize=7.8, color=MUTED)
    ax.axhline(TARGET, color=BAD, lw=1.0, ls=(0, (4, 2)))
    ax.text(5000, TARGET - 0.12, "target 16.5 bit", fontsize=7.8, color=BAD, va="top")
    ax.set_ylim(12, 20)
    ax.set_xlim(20, 5e4)
    ax.set_xlabel("vc2 of the input resistors (ppm/V²)")
    ax.set_ylabel("ENOB from DATA (bit)")
    ax.legend(loc="lower left", fontsize=7.6)
    below = v2n[kk][en[kk] < TARGET]
    ax.set_title(f"ENOB with noise stays at 16.5 bit or above up to {v2n[kk][en[kk] >= TARGET].max():.0f} ppm/V²"
                 + (f", below it from {below.min():.0f}" if len(below) else ""), loc="left")

    # (e) the offset DAC's smallest step
    ax = fig.add_subplot(gs[2, 0])
    for r in range(1, 5):
        ax.plot(SCALES, [dac[r, s]["smin"] for s in SCALES], "o-", color=RCOL[r], lw=1.3, ms=4, label=f"range {r}")
        ax.plot([0.75], [dac[r, 0]["smin"]], "D", color=RCOL[r], ms=4)
    ax.axhline(0, color=BAD, lw=1.0, ls=(0, (4, 2)))
    ax.text(1.05, 6, "below: not monotonic", fontsize=7.8, color=BAD)
    ax.set_xscale("log", base=2)
    ax.set_xticks([0.75] + SCALES, ["none"] + [f"×{s}" for s in SCALES])
    ax.set_xlabel("MIM mismatch against the stand-in (1.41 %·µm)")
    ax.set_ylabel("smallest step, 0.1 % of dies (µV at the electrodes)")
    ax.legend(loc="lower left", fontsize=7.6, ncol=2)
    nm4 = max(dac[r, 4]["nonmono"] for r in range(1, 5))
    ax.set_title(f"The offset DAC stays monotonic to ×2; at ×4 {nm4:.1f} % of dies lose it at a carry", loc="left")

    # (f) the offset DAC's largest residual
    ax = fig.add_subplot(gs[2, 1])
    for r in range(1, 5):
        ax.plot(SCALES, [dac[r, s]["resid"] for s in SCALES], "o-", color=RCOL[r], lw=1.3, ms=4, label=f"range {r}")
        ax.plot([0.75], [dac[r, 0]["resid"]], "D", color=RCOL[r], ms=4)
    ax.axhline(WIN_UV, color=BAD, lw=1.0, ls=(0, (4, 2)))
    ax.text(0.78, WIN_UV + 1.5, f"the firmware's window, {WIN_UV:.0f} µV (±54 mV at the ADC)", fontsize=7.8, color=BAD)
    ax.set_xscale("log", base=2)
    ax.set_xticks([0.75] + SCALES, ["none"] + [f"×{s}" for s in SCALES])
    ax.set_xlabel("MIM mismatch against the stand-in (1.41 %·µm)")
    ax.set_ylabel("largest residual, 99.9 % of dies (µV)")
    ax.legend(loc="upper left", fontsize=7.6, ncol=2)
    out8 = max(dac[r, 8]["out"] for r in range(1, 5))
    ax.set_title(f"The residual stays inside the window to ×4; at ×8 {out8:.1f} % of dies leave it", loc="left")

    # (g) the numbers
    ax = fig.add_subplot(gs[3, :])
    ax.set_axis_off()
    left = ["DAC1's element mismatch (30 dies, with noise): ENOB mean / worst"]
    left += [f"  ×{s}: {means[s][0]:.3f} / {means[s][1]:.3f} bit" for s in SCALES]
    left.append("Without noise, the worst of 6 dies at −60 dBFS / with no input (nVrms):")
    left.append("  " + ", ".join(f"×{s} {lo.max():.2f} / {ze.max():.2f}" for s, lo, ze in zip(SCALES, nl['low'], nl['zero'])))
    right = ["The input resistors' voltage coefficient (typical):"]
    right += [minus(f"  vc2 {r['vc2'] * 1e6:>6.0f} ppm/V²: HD3 {r['hd'][1]:.1f} dBc, ENOB without noise {r['enob']:.2f} bit")
              for r in rows if r["vc2"] * 1e6 in (100, 300, 1000, 3000)]
    v1 = sorted((r for r in vc if r["group"] == "vc1_nl"), key=lambda r: r["vc1"])
    right.append(minus("  vc1 alone (" + ", ".join(f"{r['vc1'] * 1e6:.0f}" for r in v1) + " ppm/V): HD3 "
                       + ", ".join(f"{r['hd'][1]:.1f}" for r in v1) + " dBc (the pair cancels vc1; it enters as −vc1²)"))
    ax.text(0.0, 0.98, "\n".join(left), transform=ax.transAxes, va="top", fontsize=8.6, color=INK, linespacing=1.5)
    ax.text(0.42, 0.98, "\n".join(right), transform=ax.transAxes, va="top", fontsize=8.6, color=INK, linespacing=1.5)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_43_pdk_margins.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)
    for r in range(1, 5):
        print(f"range {r}: " + "; ".join(f"x{s}: smallest {dac[r, s]['smin']:.1f} uV, non-monotonic {dac[r, s]['nonmono']:.3f} %, "
                                         f"residual {dac[r, s]['resid']:.1f} uV, out {dac[r, s]['out']:.3f} %" for s in SCALES))
    print("DAC1 mismatch ENOB:", {s: tuple(round(v, 3) for v in means[s][:2]) for s in SCALES}, "vc2 at -111 dBc:", x111)
    for kind, ys in nl.items():
        print(f"  without noise, {kind}: worst die per scale " + ", ".join(f"x{s} {y.max():.3f}" for s, y in zip(SCALES, ys))
              + " nVrms")


if __name__ == "__main__":
    main()

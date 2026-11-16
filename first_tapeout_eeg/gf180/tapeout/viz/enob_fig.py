#!/usr/bin/env python3
"""Figure 35 (r12, 11/14): ENOB from a full-scale sine, the sine test of pex/enob_sine.py
(runs/enob_sine_<chip>/enob_sine.json and spectra.npz): DATA's spectrum on typical, ENOB per die,
SINAD against the input level.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/enob_fig.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RUN = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", f"enob_sine_{V.CHIP}")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL = "#0d9488"
TARGET = 16.5
BUDGET_SUM = 16.44           # figure 07: the noise sum with the ADC side's 10/22 allocation (2.93 nVrms)


def main():
    d = json.load(open(os.path.join(RUN, "enob_sine.json"), encoding="utf-8"))
    meta, rows = d["meta"], d["rows"]
    sp = np.load(os.path.join(RUN, "spectra.npz"))
    f, k0 = sp["f"], int(sp["k0"])
    by = {r["label"]: r for r in rows}
    typ = by["typical"]
    quiet = by["typical, no noise"]
    adc = by["typical, no noise, AFE linear"]
    mc = [r for r in rows if r["group"] == "mc" and "enob" in r]
    cor = [r for r in rows if r["group"] == "corner" and "enob" in r]
    reps = [typ] + [r for r in rows if r["group"] == "repeat" and "enob" in r]
    e_rep = np.array([r["enob"] for r in reps])
    q_rep = np.array([r["enob_eq"] for r in reps])
    idle = next((r for r in rows if r["group"] == "noinput"), None)
    sw = sorted([r for r in rows if r["group"] == "sweep"] + [typ], key=lambda r: r["amp_db"])
    f0 = meta["f0_hz"]
    fig = V.figure(12.6, 8.6, "ENOB from a full-scale sine",
                   f"{meta['fs_pk_v'] * 1e3:.3f} mV pk, {f0:.2f} Hz at the electrodes, through the AFE (r12 extraction: static "
                   f"transfer, Monte Carlo noise), the ADC loop model (dies of the extracted block Monte Carlo) and eeg_cic3 "
                   f"bit-exact to DATA · {meta['nrec']}-point FFT at 1 kS/s, SINAD over 0.5–100 Hz, "
                   f"ENOB = (SINAD − 1.76) / 6.02",
                   note="Not a transistor-level sine: the band starts at 0.5 Hz, so the record must be seconds long, and the "
                        "chip's transistor chain covers 10 ms in about 2.5 days. The noise sources go in at their extracted "
                        "levels (AFE per die on the chip wiring, AFE_IBIAS 3; output-chopper blanking; ADC resistors and OTA1; "
                        "poly-resistor 1/f as a gain noise). Not included: the OTAs' static nonlinearity (figure 36: "
                        "below −150 dBc; in the loop the ENOB moves by 0.45 mbit at most), the poly resistors' voltage "
                        "coefficient (the PDK's terms are 0), the external reference (requirement 0.5 nVrms at full "
                        "scale), clock jitter (figure 36: DAC1's edge, 0.02 nVrms per 10 ps), and the source's own "
                        "thermal noise (100 Ω per leg would add 18.2 nVrms).")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.95], width_ratios=[1.0, 1.15])
    ax = fig.add_subplot(gs[0, :])
    ax.axvspan(0.5, 100.0, color="#eef2ff", zorder=0, lw=0)
    ax.text(0.53, -12, "band 0.5–100 Hz", fontsize=8, color=ACCENT, va="top")
    lab = {"typical_no_noise": ("Without noise (loop, AFE transfer, decimator)", LIGHT, 0.9),
           "typical": ("With the extracted noise", ACCENT, 0.7)}
    for key in ("typical_no_noise", "typical"):
        p = np.maximum(sp[key], 1e-30)
        sel = f > 0
        ax.semilogx(f[sel], 10 * np.log10(p[sel]), color=lab[key][1], lw=lab[key][2], label=lab[key][0],
                    zorder=3 if key == "typical" else 2)
    ax.plot([f0], [0], "o", color=ACCENT, ms=5, zorder=4)
    for h, v, xt, yt in zip((2, 3), quiet["hd"][:2], (13.0, 36.0), (-88.0, -100.0)):
        ax.annotate(f"HD{h} {v:.1f} dBc (no noise)", (h * f0, v), xytext=(xt, yt), fontsize=7.8, color=MUTED, ha="left",
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.6))
    ax.set_xlim(f[1], 500)
    ax.set_ylim(-205, 8)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power per bin (dB re the tone)")
    ax.set_title("DATA spectrum, typical die, full-scale input", loc="left")
    ax.legend(loc="lower left", ncol=2)
    s_mean = 6.02 * e_rep.mean() + 1.76
    nad_mean = meta["fs_pk_v"] / math.sqrt(2) * 10 ** (-s_mean / 20) * 1e9
    box = (f"Typical die, mean of {len(reps)} records of 8.19 s:\n"
           f"   SINAD {s_mean:.2f} dB, ENOB {e_rep.mean():.2f} bit (one record scatters {e_rep.std(ddof=1):.3f} bit, 1σ)\n"
           f"   the sinc³ droop equalized (a flat band): {q_rep.mean():.2f} bit\n"
           f"   noise and distortion {nad_mean:.2f} nVrms at the electrodes"
           + (f"; no input, noise alone {idle['noise_nv']:.2f}" if idle else "") + "\n"
           f"Without noise: SINAD {quiet['sinad']:.1f} dB (AFE transfer and loop), ADC alone {adc['sinad']:.1f} dB\n"
           f"Shown: record 1 (SINAD {typ['sinad']:.2f} dB, THD {typ['thd']:.1f} dBc with the noise in the harmonics' bins)")
    ax.text(0.985, 0.95, box, transform=ax.transAxes, ha="right", va="top", fontsize=8.4, color=INK,
            multialignment="left", bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="#cbd5e1", lw=0.8))

    a2 = fig.add_subplot(gs[1, 0])
    rng = np.random.default_rng(4)
    groups = [(f"Typical\n({len(reps)} records)", reps, INK2), (f"Monte Carlo\n({len(mc)} dies)", mc, ACCENT),
              (f"Corners\n({len(cor)})", cor, TEAL)]
    for i, (name, rr, c) in enumerate(groups):
        e = np.array([r["enob"] for r in rr])
        x = i + rng.uniform(-0.16, 0.16, len(e))
        a2.plot(x, e, "o", color=c, ms=4.2, mec="white", mew=0.6, zorder=3, alpha=0.85)
        a2.plot([i - 0.22, i + 0.22], [e.mean()] * 2, color=c, lw=1.6, zorder=4)
        a2.text(i + 0.24, e.min(), f"worst {e.min():.2f}", fontsize=7.8, color=INK2, va="center")
        a2.text(i + 0.24, e.max(), f"best {e.max():.2f}", fontsize=7.8, color=INK2, va="center")
        a2.text(i + 0.24, e.mean(), f"mean {e.mean():.2f}", fontsize=7.8, color=c, va="center", fontweight="medium")
    a2.text(0.01, 0.985, f"one 8.2 s record scatters about {e_rep.std(ddof=1):.3f} bit (1σ): most of the spread",
            transform=a2.transAxes, fontsize=7.6, color=MUTED, va="top")
    a2.axhline(TARGET, color=INK, ls=(0, (4, 3)), lw=1)
    a2.text(2.45, TARGET, "target 16.50", fontsize=8, color=INK, ha="right", va="bottom")
    a2.axhline(BUDGET_SUM, color=MUTED, ls=(0, (1, 2)), lw=0.9)
    a2.text(-0.45, BUDGET_SUM + 0.003, "noise budget with the ADC side as allocated (fig. 07): 16.44", fontsize=7.8,
            color=MUTED, ha="left", va="bottom")
    a2.set_xticks(range(len(groups)), [g[0] for g in groups])
    a2.set_xlim(-0.5, 2.5)
    lo = min(min(r["enob"] for r in mc + cor + reps), BUDGET_SUM) - 0.03
    hi = max(r["enob"] for r in mc + cor + reps) + 0.03
    a2.set_ylim(lo, hi)
    a2.set_ylabel("ENOB at full scale (bit)")
    a2.set_title("ENOB per die", loc="left")
    a2.grid(axis="x", visible=False)

    a3 = fig.add_subplot(gs[1, 1])
    x = np.array([r["amp_db"] for r in sw])
    y = np.array([r["sinad"] for r in sw])
    xs = np.linspace(-105, 2, 50)
    snr_mean = float(np.mean([r["snr"] for r in reps]))
    y = np.where(x == 0, s_mean, y)                        # full scale: the mean of the typical records
    a3.plot(xs, xs + snr_mean, color=LIGHT, lw=0.9, ls=(0, (4, 3)), label="noise only (slope 1 from the full-scale SNR)")
    a3.plot(x, y, "o-", color=ACCENT, ms=4.5, lw=1.1, mec="white", mew=0.6,
            label="typical die (one record per level; full scale: the mean)", zorder=3)
    a3.plot([0], [6.02 * TARGET + 1.76], "s", color=INK, ms=5, mfc="white", mew=1.1, zorder=4)
    a3.annotate(f"full scale: {s_mean:.1f} dB\n(open square: 101.1 dB, what 16.5 bit needs)", (0, s_mean),
                xytext=(-50, 32), fontsize=8, color=ACCENT, arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.6))
    a3.set_xlim(-106, 6)
    a3.set_ylim(-5, 120)
    a3.set_xlabel("Input level (dB re 0.943 mV pk)")
    a3.set_ylabel("SINAD (dB)")
    a3.set_title(f"SINAD against the input level (dynamic range {snr_mean:.1f} dB)", loc="left")
    a3.legend(loc="upper left")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_35_enob_sine.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

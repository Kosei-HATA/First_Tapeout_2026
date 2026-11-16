#!/usr/bin/env python3
"""Figure 36 (r12, 11/15): the ADC's own distortion at full scale from its OTAs. The static transfer of the extracted
OTA1 and OTA2 on their stage loads (pex/ota_static.py, runs/ota_static_r12/), its error at the ADC input on the loop
model's integrator outputs at full scale (pex/ota_distortion.py) against the room figure 35's ENOB leaves, and the
ENOB with the nonlinearity in the loop (pex/enob_sine.py --ota-nl) against figure 35's run.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/ota_fig.py
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
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
sys.path.insert(0, PEX)
import ota_static as O  # noqa: E402  (the benches' curves; does not set EEG_PEX_REV)

ENOB = os.path.join(PEX, "runs", f"enob_sine_{V.CHIP}")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL, AMBER = "#0d9488", "#b45309"
CORNERS = ("ss", "ff", "fs", "sf")


def nl_raw(tag):
    """|vx - offset - vo / A0| against vo > 0 (the fit's offset and slope at 0), V"""
    c, _, _ = O.fit(tag)
    _, vo, vx, _, _ = O.load(tag)
    sel = vo > 0
    e = np.abs(vx[sel] - c[0] - c[1] * vo[sel])
    return vo[sel], np.where(e > 2e-11, e, np.nan)       # below 20 pV: the bench's numerical floor


def allowance_dbc(nad_nv, fs_rms_v, gain):
    """the error (dBc at the input) that brings a column with this noise and distortion to 16.5 bit"""
    need = fs_rms_v * 10 ** (-(6.02 * 16.5 + 1.76) / 20) * 1e9
    return 20 * math.log10(math.sqrt(need ** 2 - nad_nv ** 2) * 1e-9 / fs_rms_v)


def main():
    dist = json.load(open(os.path.join(O.OUT, "ota_distortion.json"), encoding="utf-8"))
    rows = dist["rows"]
    base = json.load(open(os.path.join(ENOB, "enob_sine.json"), encoding="utf-8"))
    p_nl = os.path.join(ENOB, "enob_sine_otanl.json")
    nl = json.load(open(p_nl, encoding="utf-8")) if os.path.exists(p_nl) else None
    fs_rms = base["meta"]["fs_pk_v"] / math.sqrt(2)
    reps = [r for r in base["rows"] if r["group"] in ("typical", "repeat")]
    worst = max((r for r in base["rows"] if r["group"] in ("mc", "corner")), key=lambda r: r["nad_nv"])
    a_typ = allowance_dbc(np.mean([r["nad_nv"] for r in reps]), fs_rms, 1)
    a_worst = allowance_dbc(worst["nad_nv"], fs_rms, 1)
    x1 = max(abs(v) for r in rows for v in r["x1_range_mv"]) * 1e-3
    x2 = max(abs(v) for r in rows for v in r["x2_range_mv"]) * 1e-3
    k1 = rows[0]["k1"]

    fig = V.figure(12.6, 8.4, "The ADC's own distortion at full scale: its OTAs",
                   "Static transfer of the extracted OTA1 and OTA2 on their stage loads (DC sweep of the integrator "
                   "output; OTA1 in both chopper phases), applied to the loop model's integrator outputs at full scale "
                   "(0.943 mV pk at the electrodes, 280.8 mV pk at the ADC input) · typical, the four block corners, "
                   "Monte Carlo dies 1–10",
                   note="The loop model has the OTAs linear (a DC gain). An OTA's static nonlinearity is an error at its "
                        "stage's input: OTA1's times 1 + RIN / RD1 = 1.97 at the ADC input, which the loop passes to "
                        "DATA like the signal; OTA2's through R21, at the input RIN C1 times its derivative. Computed "
                        "feed-forward from a noiseless run (per clock the mean over the clock, sinc³ / 1024, FFT); "
                        "the same curves in the loop with figure 35's noise give the ENOB below. Not here: the "
                        "poly resistors' voltage coefficient (the PDK's terms are 0), dynamic OTA errors beyond the "
                        "model's excess delay.")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.92], width_ratios=[1.12, 1.0])

    ax = fig.add_subplot(gs[0, 0])
    for case, c, lw, z in ([("typical", ACCENT, 1.8, 4)] + [(k, TEAL, 0.9, 3) for k in CORNERS]
                           + [(f"mc{k}", LIGHT, 0.6, 2) for k in range(1, 11)]):
        for tag in O.tags_of("ota1", case)[:1]:
            vo, e = nl_raw(tag)
            ax.loglog(vo, np.maximum(e, 1e-13) * 1e9, color=c, lw=lw, zorder=z)
    vo, e = nl_raw("ota2_typical")
    ax.loglog(vo, np.maximum(e, 1e-13) * 1e9, color=INK2, lw=1.2, ls=(0, (4, 2)), zorder=4)
    ax.axvspan(x1 * 0.97, x1 * 1.03, color=ACCENT, alpha=0.12, lw=0)
    ax.axvspan(x2 * 0.97, x2 * 1.03, color=INK2, alpha=0.10, lw=0)
    # what OTA1's cubic part may reach at O1's peak for the worst die's room: HD3 = k1 c3 A^3 / 4 at the input
    lim = 4 * dist["meta"]["u_amp_v"] * 10 ** (a_worst / 20) / k1
    ax.plot([x1], [lim * 1e9], "v", color=AMBER, ms=7, zorder=5)
    ax.annotate(f"room at O1's peak before the worst die drops to\n16.5 bit: {lim * 1e6:.1f} µV as a cubic part, "
                f"{lim * 0.5e6:.1f} µV as a square",
                (x1, lim * 1e9), xytext=(0.0205, 25), fontsize=8, color=AMBER, va="center",
                arrowprops=dict(arrowstyle="-", color=AMBER, lw=0.6))
    ax.text(x1 * 1.06, 2e-3, f"O1's peak at full scale,\nall dies: ±{x1 * 1e3:.0f} mV", fontsize=7.8, color=ACCENT,
            va="bottom")
    ax.text(x2 * 1.06, 2e-3, f"O2's peak\n±{x2 * 1e3:.0f} mV", fontsize=7.8, color=INK2, va="bottom")
    ax.text(0.99, 0.02, "absolute value; the dips are sign changes", transform=ax.transAxes, fontsize=7.6,
            color=MUTED, ha="right", va="bottom")
    ax.plot([], [], color=ACCENT, lw=1.8, label="OTA1, typical")
    ax.plot([], [], color=TEAL, lw=0.9, label="OTA1, corners ss ff fs sf")
    ax.plot([], [], color=LIGHT, lw=0.6, label="OTA1, Monte Carlo 1–10")
    ax.plot([], [], color=INK2, lw=1.2, ls=(0, (4, 2)), label="OTA2, typical")
    ax.legend(loc="upper left")
    ax.set_xlim(0.02, 0.62)
    ax.set_ylim(1e-3, 3e4)
    ax.set_xlabel("Differential output of the OTA (V)")
    ax.set_ylabel("Virtual-ground voltage beyond its offset and gain (nV)")
    ax.set_title("Nonlinear part of the OTA's input voltage", loc="left")

    a2 = fig.add_subplot(gs[0, 1])
    rng = np.random.default_rng(6)
    groups = [("OTA1", [r["ota1_total_dbc"] for r in rows], ACCENT),
              ("OTA2", [r["ota2_total_dbc"] for r in rows], INK2),
              ("DAC1 edge\njitter 10 ps", [20 * math.log10(r["jitter_nv_per_10ps"] * 1e-9 / fs_rms) for r in rows], TEAL),
              ("DAC1 edge\njitter 100 ps", [20 * math.log10(10 * r["jitter_nv_per_10ps"] * 1e-9 / fs_rms) for r in rows],
               TEAL)]
    for i, (name, v, c) in enumerate(groups):
        v = np.array(v)
        a2.plot(i + rng.uniform(-0.15, 0.15, v.size), v, "o", color=c, ms=4.2, mec="white", mew=0.6, alpha=0.85,
                zorder=3)
        a2.text(i, v.max() + 6, f"{v.max():.0f}", fontsize=8, color=INK2, ha="center", va="bottom")
    a2.axhline(a_typ, color=INK, ls=(0, (4, 3)), lw=1)
    a2.axhline(a_worst, color=AMBER, ls=(0, (4, 3)), lw=1)
    a2.text(-0.45, a_typ + 2, f"room to 16.5 bit, typical: {a_typ:.1f} dBc", fontsize=7.8, color=INK, ha="left",
            va="bottom")
    a2.text(-0.45, a_worst - 2, f"room to 16.5 bit, worst die of figure 35: {a_worst:.1f} dBc", fontsize=7.8,
            color=AMBER, ha="left", va="top")
    a2.set_xticks(range(len(groups)), [g[0] for g in groups])
    a2.set_xlim(-0.5, 3.5)
    a2.set_ylim(-290, -90)
    a2.set_ylabel("In-band error at the input (dBc, all bins but the tone)")
    a2.set_title("Error terms at full scale, per die", loc="left")
    a2.grid(axis="x", visible=False)

    a3 = fig.add_subplot(gs[1, :])
    by = {r["label"]: r for r in base["rows"]}
    sets = [("Typical records", ("typical", "repeat"), INK2), ("Monte Carlo dies", ("mc",), ACCENT),
            ("Block corners", ("corner",), TEAL)]
    xs = 0
    ticks = []
    for name, gset, c in sets if nl else ():
        pair = [(by[r["label"]]["enob"], r["enob"]) for r in nl["rows"] if r["group"] in gset and "enob" in r
                and "enob" in by.get(r["label"], {})]
        d = np.array([b - a for a, b in pair]) * 1e3
        x = xs + np.arange(d.size)
        a3.bar(x, d, color=c, width=0.7, zorder=3)
        ticks.append((xs + (d.size - 1) / 2, f"{name}\n(max |change| {np.abs(d).max():.1f} mbit)"))
        xs += d.size + 2
    a3.axhline(0, color=INK, lw=0.8)
    if not nl:
        a3.text(0.5, 0.5, "enob_sine.py --ota-nl has not run yet", transform=a3.transAxes, ha="center", color=MUTED)
        xs = 1
    a3.set_xticks([t[0] for t in ticks], [t[1] for t in ticks])
    a3.set_xlim(-1.5, xs - 0.5)
    lim3 = max([0.6] + [1.3 * abs(p.get_height()) for p in a3.patches])
    a3.set_ylim(-lim3, lim3)
    if nl:
        sd = 1e3 * np.std([r["enob"] for r in reps], ddof=1)
        a3.text(0.995, 0.97, f"for scale: one 8.2 s record scatters {sd:.0f} mbit (1σ)", transform=a3.transAxes,
                fontsize=8, color=MUTED, ha="right", va="top")
    a3.set_ylabel("ENOB with − without (mbit)")
    a3.set_title("ENOB with the OTAs' measured nonlinearity in the loop, against figure 35's run "
                 "(same noise draws; the loop's codes diverge, so the quantization noise is a new draw)", loc="left")
    a3.grid(axis="x", visible=False)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_36_ota_distortion.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()

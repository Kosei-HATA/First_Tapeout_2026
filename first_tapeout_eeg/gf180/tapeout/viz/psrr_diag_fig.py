#!/usr/bin/env python3
"""Figure 47 (r12, 11/19): where the AVDD ripple's conversion between the choppers comes from (a diagnostic).

psrr_diag.py's results (gf180/tapeout/pex/runs/psrr_r12/diag.json) and psrr.py's (results.json): the typical
AVDD-ripple start deck of figure 46 with INN's extracted couplings to the nets that carry the AVDD ripple scaled to
INP's (A: AVDD; B: also VBP and BLP; C: B with ELP 100 ohm + 51 kohm || 47 nF). Not a design change.
  (a) the summing nodes' extracted capacitance to those nets, INN against INP;
  (b) the conversion between the choppers next to 128 kHz, measured and from the static scan;
  (c) what the output chopper folds into band, at the electrodes;
  (d) the MOS corners of figure 46 against the PDK's MIM corner that comes with them;
  (e) where: the summing nodes' Metal3-5 over the amplifier's core, with AVDD's n-wells and Metal5 and VBP's poly
      (psrr_diag.py --layout: afe_top's LVS database);
  (f) the numbers behind them.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/psrr_diag_fig.py     (after gf180/tapeout/pex/psrr_diag.py,
       and psrr_diag.py --layout)
"""
import json
import os
import sys

import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
sys.path.insert(0, PEX)
import psrr as S  # noqa: E402

OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
NETS = [("AVDD/AVDD", "AVDD"), ("VBP/VBP", "VBP"), ("BLP/BLN", "BLP (INP: BLN)"), ("AVSS/AVSS", "AVSS"),
        ("CORE.SP/CORE.SP", "CORE.SP (the input\npair's common source)")]
SCALED = 3                                            # the first three are the ones A / B scale
LABEL = {"typical": "typical", "A": "A: INN–AVDD\nas INP's", "B": "B: also INN–VBP,\nINN–BLP",
         "typical, ELP 51k||47n": "typical, ELP\n51 kΩ || 47 nF", "C": "C: B with ELP\n51 kΩ || 47 nF"}


def minus(s):
    return s.replace("-", "−")


def density(v):
    return f"{v:,.0f} nV/√Hz" if v < 1e3 else f"{v / 1e3:,.1f} µV/√Hz"


def main():
    d = json.load(open(os.path.join(S.OUT, "diag.json"), encoding="utf-8"))
    res = json.load(open(os.path.join(S.OUT, "results.json"), encoding="utf-8"))
    runs = {r["name"]: r for r in d["runs"]}
    tone = lambda r, k: next(x for x in r["tones"] if x["harmonic"] == k)  # noqa: E731
    interim = "C" not in runs
    mc = [tone(r, 1)["between_vv"] for r in res["runs"] if r["supply"] == "AVDD" and r["seed"] is not None
          and r["zp"] == "100" and r["zn"] == "100"]

    fig = V.figure(12.8, 15.6, "Supply rejection: where the conversion between the choppers comes from (diagnostic"
                   + (", interim)" if interim else ")"),
                   "Figure 46's typical AVDD-ripple deck (10 mV pk at the regulator; legs 100 Ω each) with INN's extracted "
                   "couplings to the nets that carry the AVDD ripple scaled to INP's — A: AVDD; B: also VBP and BLP; C: B "
                   "with ELP 100 Ω + 51 kΩ || 47 nF — not a design change, a diagnostic of the r12 extraction · each "
                   "fitted alone · (d) figure 46's MOS corners against the PDK's MIM corner that comes with each",
                   note=minus(
                       "The diagnostic decks are copies of the typical decks (r12 extraction, chip wiring, AFE_IBIAS 3, "
                       "typical, 27 °C, AVDD's regulator at 3.3 V) with the explicit capacitors between INN and AVDD, VBP "
                       "and BLP scaled to INP's counterparts (INP–BLN for BLP); nothing else changes. Without baselines "
                       "(their time grids differ) each is fitted alone (polynomial 4); on the typical run the folded tones "
                       "agree with the baseline fit to 1e−5. With ELP 51 kΩ || 47 nF the start-up drift leaks into the fit "
                       "between the choppers (1.60 V/V alone against 1.47 with the baseline) while the folded tones agree "
                       "(36.94 µV both), so (b) has the balanced legs only. The static estimate takes VBP as following "
                       "AVDD fully, through Cf_eff = Cin / gain = 636 pF / 297.47. The noise allowance next to the "
                       "chopper's harmonics scales with the folded tone from figure 46's value for the same legs. (d): the "
                       "corners' conversion from figure 46 (e); the gain from the corner sine runs at 3.3 V (figure 41) "
                       "the way figure 38's typical run gives it."))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.25])

    # (a) the static scan
    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(NETS))
    for i, (key, _) in enumerate(NETS):
        cp, cn = (v / 1e3 for v in d["static_ff"][key])
        ax.barh(i - 0.19, cp, height=0.36, color=LIGHT, label="INP" if i == 0 else None)
        ax.barh(i + 0.19, cn, height=0.36, color=ACCENT if i < SCALED else "#a5b4fc", label="INN" if i == 0 else None)
        ax.text(cp + 0.08, i - 0.19, f"{cp:.2f}", va="center", fontsize=7.4, color=INK2)
        ax.text(cn + 0.08, i + 0.19, f"{cn:.2f}  ({minus(f'{cn - cp:+.2f}')} pF)", va="center", fontsize=7.4,
                color=INK if i < SCALED else MUTED, fontweight="medium" if i < SCALED else "normal")
    ax.axhline(SCALED - 0.5, color="#cbd5e1", lw=0.8, ls=(0, (3, 2)))
    ax.text(7.9, SCALED - 0.56, "above the line: scaled to INP's in A / B", ha="right", va="bottom", fontsize=7.4, color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels([x[1] for x in NETS], fontsize=8)
    ax.set_ylim(len(NETS) - 0.5, -0.6)
    ax.set_xlim(0, 8)
    ax.set_xlabel("explicit extracted capacitance from the summing node (pF)")
    ax.legend(loc="lower right", fontsize=7.6)
    ax.set_title("(a) The amplifier's summing nodes in r12's extraction: INN has more\ncapacitance than INP to nets that "
                 "carry the AVDD ripple", loc="left")

    # (b) the conversion between the choppers, legs 100 ohm
    ax = fig.add_subplot(gs[0, 1])
    names = [n for n in ("typical", "A", "B") if n in runs]
    for i, n in enumerate(names):
        r = runs[n]
        v = tone(r, 1)["between_vv"]
        ax.bar(i, v, width=0.55, color=ACCENT)
        hi = [tone(r, k)["between_vv"] for k in (1, 2, 3)]
        ax.text(i, v + 0.03, f"{v:.3f} V/V", ha="center", va="bottom", fontsize=7.8, color=INK, fontweight="medium")
        ax.text(i, v + 0.11, f"129–386 kHz: {min(hi):.3f}–{max(hi):.3f}\n1 kHz: {tone(r, 0)['between_vv']:.3f}",
                ha="center", va="bottom", fontsize=6.9, color=MUTED, linespacing=1.3)
        p = d["static_pred_vv"].get(n)
        if p is not None:
            ax.plot([i - 0.36], [p], marker="D", ms=6.5, mfc="white", mec=INK, mew=1.2,
                    label="the static scan's estimate" if i == 0 else None)
            ax.text(i - 0.45, p, f"{p:.2f}", va="center", ha="right", fontsize=7.2, color=INK2)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([LABEL[n] for n in names], fontsize=8)
    ax.set_xlim(-0.85, len(names) - 0.4)
    ax.set_ylim(0, 1.55)
    ax.set_ylabel("OPI − ONI per V of the board's ripple (V/V)")
    ax.legend(loc="upper right", fontsize=7.6)
    ax.set_title("(b) Between the choppers, next to 128 kHz (129.25 kHz), legs 100 Ω each:\nmatching INN to INP takes out "
                 "about 95 % of the conversion", loc="left")

    # (c) folded into band
    ax = fig.add_subplot(gs[1, 0])
    rows = ["typical", "A", "B", "typical, ELP 51k||47n", "C"]
    for i, n in enumerate(rows):
        yy = i + (0.35 if i >= 3 else 0)
        if n not in runs:
            ax.text(64, yy, "running", va="center", ha="center", fontsize=7.6, color=MUTED)
            continue
        r = runs[n]
        a, b = tone(r, 1)["psrr_board_db"], tone(r, 3)["psrr_board_db"]
        ax.plot([a], [yy], "o", ms=7, mec=ACCENT, mew=1.4, mfc=ACCENT, label="1.25 kHz (from 129.25 kHz, k = 1)" if i == 0 else None)
        ax.plot([b], [yy], "o", ms=7, mec=ACCENT, mew=1.4, mfc="white", label="1.75 kHz (from 385.75 kHz, k = 3)" if i == 0 else None)
        ax.plot([a, b], [yy, yy], color=ACCENT, lw=0.8, alpha=0.5, zorder=0)
        ax.text(a - 1.0, yy, f"{a:.1f}", ha="right", va="center", fontsize=7.4, color=INK2)
        ax.text(b + 1.0, yy, f"{b:.1f} dB", ha="left", va="center", fontsize=7.4, color=INK2)
        ax.text(104, yy, density(r["allowed_13"]), ha="right", va="center", fontsize=7.4, color=INK)
    ax.text(104, -0.62, "noise allowed next to\n128 + 384 kHz", ha="right", va="center", fontsize=7.0, color=MUTED,
            linespacing=1.2)
    ax.axhline(2.68, color="#cbd5e1", lw=0.8)
    ax.set_yticks([i + (0.35 if i >= 3 else 0) for i in range(len(rows))])
    ax.set_yticklabels([LABEL[n].replace("\n", " ") for n in rows], fontsize=8)
    ax.set_ylim(len(rows) - 0.3, -1.25)
    ax.set_xlim(40, 105)
    ax.set_xlabel("supply rejection at the electrodes, in band (dB, against the board's ripple)")
    ax.legend(loc="upper left", fontsize=7.4)
    ax.set_title("(c) Folded into band, at the electrodes; right: the regulator noise there\nthat adds 5 % "
                 f"to the AFE's own {S.NOISE_NV} nVrms (k = 1 and 3 together)", loc="left")

    # (d) the corners against the MIM corner
    ax = fig.add_subplot(gs[1, 1])
    cs = {c["corner"]: c for c in d["corners"]}
    t1 = cs["typical"]["between_vv"]
    xx = np.linspace(0.88, 1.13, 2)
    ax.plot(xx, t1 * xx, color=MUTED, lw=1.0, ls=(0, (4, 2)), label="typical × 1 / (MIM factor)")
    if mc:
        ax.plot([1.0, 1.0], [min(mc), max(mc)], color="#c7d2fe", lw=7, solid_capstyle="butt", zorder=1,
                label=f"Monte Carlo dies 1–{len(mc)} (MIM varies too)")
    off = {"typical": (8, -2), "sf": (8, 9), "fs": (8, -13), "ff": (-8, 6), "ss": (8, -4)}
    for c, row in cs.items():
        x = 1 / row["mim"]
        ax.plot([x], [row["between_vv"]], "o", ms=7, mec=ACCENT, mew=1.4, mfc=ACCENT, zorder=3)
        dx, dy = off.get(c, (8, 0))
        ax.annotate(minus(f"{c}: {row['between_vv']:.3f} V/V, gain {row['gain_ratio'] - 1:+.2%}"), (x, row["between_vv"]),
                    xytext=(dx, dy), textcoords="offset points", fontsize=7.4, color=INK2, va="center",
                    ha="right" if dx < 0 else "left")
    ax.set_xlim(0.88, 1.15)
    ax.set_ylim(0.9, 1.32)
    ax.set_xlabel("1 / (the PDK's MIM corner factor): ss 1 / 1.1, typical, sf, fs 1, ff 1 / 0.9")
    ax.set_ylabel("OPI − ONI next to 128 kHz (V/V)")
    ax.legend(loc="upper left", fontsize=7.4)
    ax.set_title("(d) MOS corners (figure 46): the corner also sets the MIM capacitors; Cf is\nMIM, the wiring is not: the "
                 "conversion goes as 1 / MIM, the gain (Cin / Cf) stays", loc="left")

    # (e) where: the summing nodes' wiring over the amplifier core
    ax = fig.add_subplot(gs[2, 0])
    lp = os.path.join(S.OUT, "diag_layout.json")
    if os.path.exists(lp):
        lay = json.load(open(lp, encoding="utf-8"))
        sty = [("AVDD nwell", dict(facecolor="#fef3c7", edgecolor="#f59e0b", linewidth=0.5), "AVDD's n-wells"),
               ("INN M3", dict(facecolor="#a5b4fc", edgecolor="none"), "INN Metal3"),
               ("INN M4", dict(facecolor=ACCENT, edgecolor=ACCENT, alpha=0.45, linewidth=0.6), "INN Metal4"),
               ("VBP poly", dict(facecolor="#b45309", edgecolor="none", alpha=0.75), "VBP's poly (current-source\ngates, under INN's Metal4)"),
               ("AVDD M5", dict(facecolor="none", edgecolor="#b45309", linewidth=1.1, linestyle=(0, (3, 2))), "AVDD Metal5"),
               ("INP M5", dict(facecolor="none", edgecolor=INK, linewidth=1.0), "INP Metal5")]
        hs = []
        for z, (k, kw, lab) in enumerate(sty):
            ax.add_collection(PolyCollection(lay["polygons"][k], zorder=2 + z, **kw))
            hs.append(Patch(label=lab, **kw))
        ax.text(640, 372, "INN's Cin array below", ha="center", va="bottom", fontsize=7.4, color=MUTED,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5), zorder=20)
        ax.text(640, 1068, "INP's Cin array above", ha="center", va="top", fontsize=7.4, color=MUTED,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5), zorder=20)
        ax.set_xlim(180, 1100)
        ax.set_ylim(360, 1080)
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_xlabel("x in afe_top (µm)")
        ax.set_ylabel("y (µm)")
        ax.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=7.4)
        ov = lay["overlap_um2"]
        ax.set_title("(e) Where: over the core, INN runs on Metal3 and Metal4,\nnearer AVDD's n-wells and VBP's gates than "
                     f"INP on Metal5\n(INN's Metal4 over the n-wells {ov['INN M4 / AVDD nwell'] / 1e3:.0f} k µm², "
                     f"INP's {ov['INP M4 / AVDD nwell'] / 1e3:.0f} k)", loc="left")
    else:
        ax.set_axis_off()

    # (f) the numbers
    ax = fig.add_subplot(gs[2, 1])
    ax.set_axis_off()
    items = []
    st = d["static_ff"]
    dav = (st["AVDD/AVDD"][1] - st["AVDD/AVDD"][0]) / 1e3
    dvb = (st["VBP/VBP"][1] - st["VBP/VBP"][0]) / 1e3
    dbl = (st["BLP/BLN"][1] - st["BLP/BLN"][0]) / 1e3
    tot = d["static_total_pf"]
    items.append(f"Static scan of r12's afe_top (explicit capacitance on the summing nodes, in all INP {tot['INP']:.2f}, "
                 f"INN {tot['INN']:.2f} pF): INN {dav:+.2f} pF to AVDD, {dvb:+.2f} pF to VBP, {dbl:+.2f} pF to BLP; "
                 f"through Cf_eff {d['cf_eff_pf']:.2f} pF that is {d['static_pred_vv']['typical']:.2f} V/V if VBP follows "
                 f"AVDD fully (measured {tone(runs['typical'], 1)['between_vv']:.2f}).")
    if "A" in runs and "B" in runs:
        a1, b1, t1v = (tone(runs[n], 1)["between_vv"] for n in ("A", "B", "typical"))
        items.append(f"A takes out {t1v - a1:.2f} V/V (static {dav / d['cf_eff_pf']:.2f}); B a further {a1 - b1:.2f} V/V; "
                     f"left {b1:.3f} V/V ({b1 / t1v:.0%} of the typical). Next differences, not scaled: AVSS "
                     f"{(st['AVSS/AVSS'][1] - st['AVSS/AVSS'][0]) / 1e3:+.2f} pF, the input pair's common source "
                     f"{(st['CORE.SP/CORE.SP'][1] - st['CORE.SP/CORE.SP'][0]) / 1e3:+.2f} pF (both carry less of the "
                     "ripple than AVDD).")
    ff, ss = cs.get("ff"), cs.get("ss")
    if ff and ss:
        items.append(f"Corners: ff {ff['between_vv']:.3f} V/V against {ff['pred_vv']:.3f} (typical / 0.9), ss "
                     f"{ss['between_vv']:.3f} against {ss['pred_vv']:.3f} (/ 1.1); the AFE's gain ff "
                     f"{ff['gain_ratio'] - 1:+.2%}, ss {ss['gain_ratio'] - 1:+.2%}, so the input-referred fold moves "
                     "with the conversion.")
    items.append("Noise next to 128 and 384 kHz together that adds 5 % (with the odd harmonics above 3, (2/π)/k each):")
    rows = [f"  {LABEL[n].replace(chr(10), ' ')}: {density(runs[n]['allowed_13'])} ({density(runs[n]['allowed_odd'])})"
            for n in ("typical", "A", "B", "typical, ELP 51k||47n", "C") if n in runs]
    items.append("\n".join(rows))
    items.append("Typical die only; the diagnostic decks were not run on Monte Carlo dies or corners.")
    txt = "\n".join(V.wrap(minus(x), 6.0, 8.2) for x in items)
    ax.text(0.0, 1.0, txt, transform=ax.transAxes, va="top", fontsize=8.2, color=INK, linespacing=1.45)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_47_psrr_diag.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, "(interim)" if interim else "")


if __name__ == "__main__":
    main()

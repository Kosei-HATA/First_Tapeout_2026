#!/usr/bin/env python3
"""Figure 55 (r14, 11/24): the chip-level timing of the digital interface on the 14th chip against the 13th (VER-08).

OpenSTA with the macros' timing models and the chip wiring extracted from each chip's core LVS
(gf180/tapeout/digital/chip_sta/run_chip_sta.sh):
  r13: the 13th chip's own wiring (runs/chip_top/r13_20261119/eeg_core.lvsdb), the macros f2 / f3 (the re-runs of
       11/19, identical), results in chip_sta/build/r13/ (CHIP_STA_BUILD; build/ itself holds the wiring of 10/24)
  r14: the 14th chip (the r14 macro r14f5_20261124, all 50 outputs clkbuf_2, its preset / clear arcs in the timing
       model), results in chip_sta/build/r14/
  (a) TH setup slack (2-cycle path e0 -> e2, worst of the 31), per corner
  (b) between the blocks: worst setup and hold slack per corner (DWA_EN's setup through the preset arc in r14)
  (c) the blanking margins: CHOP_BLANK's rise before the CHOP_OUT edge, its fall after it at BLANK_LEN 1
  (d) the slews at the analog receivers at max ss (library values, 30-70 %; the transistor runs are figure 56)
  (e) the nets whose wiring differs between the two chips (13 of 112): length and capacitance
Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_chip_sta_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import HAIR, MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r14", "20261124"
V.CHIP_LABEL = "Chip r14 (fourteenth assembly, 24 Nov 2026)"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
STA = os.path.join(REPO, "gf180", "tapeout", "digital", "chip_sta")
sys.path.insert(0, STA)
import chip_sta_report as R  # noqa: E402

BUILDS = {"r13": os.path.join(STA, "build", "r13"), "r14": os.path.join(STA, "build", "r14")}
RUNS = {"r13": "f2_rerun_20261119_f3_rerun_20261119", "r14": "r14f5_20261124_f3_rerun_20261119"}
# the blanking (clocked edges): r14's model without the preset / clear arcs (eeg_digital_top_r14/run_etm_r14.sh), as in
# r14's final/lib CHOP_BLANK's fall is the SOFT_RESET path
RUNS_BLANK = {"r13": RUNS["r13"], "r14": "r14f5_20261124_etmoff_f3_rerun_20261119"}
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
COL = {"r13": "#94a3b8", "r14": "#0d9488"}
LAB = {"r13": "13th chip (r13 macro f2, buf_1 outputs)", "r14": "14th chip (r14 macro, clkbuf_2 outputs)"}
SHORT = {f"{rc}_{pv}": f"{rc}\n{pv.split('_')[0]}" for rc in ("max", "nom", "min")
         for pv in ("ss_125C_3v00", "tt_025C_3v30", "ff_n40C_3v60")}


def rows_of(ver):
    R.B = os.path.join(BUILDS[ver], RUNS[ver])
    out = {}
    for c in R.CORNERS:
        s = R.parse_summary(c)
        pm, pn = R.parse_ports(c, "max"), R.parse_ports(c, "min")
        ep = s["endpoint"]
        th = [v for k, v in ep.items() if k.startswith("u_adc/TH[")]
        blk = {k.split("/")[1]: v for k, v in ep.items() if not k.startswith("u_adc/TH[")}
        out[c] = {"th": min(v["setup"] for v in th),
                  "blk_setup": min(v["setup"] for v in blk.values()),
                  "blk_setup_name": min(blk, key=lambda k: blk[k]["setup"]),
                  "blk_hold": min(v["hold"] for v in blk.values()),
                  "blank_rise": None, "blank_fall1": None,
                  "slew": {p: pm[p][1] for p in ("CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CHOP1",
                                                   "ADC_ZERO", "DAC_CLK")} | {"CMP_STROBE": s["analog"]["u_q/CK"]["slew"]},
                  "dac1": R.T + pn["DAC_CLK"][0] - max(pm[p][0] for p in pm if p.startswith("SEL1_"))}
    R.B = os.path.join(BUILDS[ver], RUNS_BLANK[ver])
    for c in R.CORNERS:
        rise, fall = R.blanking(c, R.parse_ports(c, "max"), R.parse_ports(c, "min"))
        out[c]["blank_rise"], out[c]["blank_fall1"] = rise, fall[1]
    return out


def bars(ax, keys, vals, w=0.38):
    x = np.arange(len(keys))
    for i, ver in enumerate(("r13", "r14")):
        ax.bar(x + (i - 0.5) * w, [vals[ver][k] for k in keys], w, color=COL[ver], label=LAB[ver])
    ax.set_xticks(x)
    return x


def main():
    V.apply()
    d = {v: rows_of(v) for v in ("r13", "r14")}
    nets = {v: json.load(open(os.path.join(BUILDS[v], "nets.json"))) for v in ("r13", "r14")}
    fig = V.figure(13.2, 9.6, "Chip-level timing of the digital interface: the 14th chip against the 13th (VER-08)",
                   "OpenSTA with the macros' timing models and each chip's own wiring from its core LVS, 9 corners: "
                   "every check is met on both chips; r14's clkbuf_2 outputs give TH 5.0 ns more at max ss and halve "
                   "the slews at the analog receivers, its preset arcs bring DWA_EN's setup to +2.8 ns.",
                   note="Corner = the macros' timing-model corner (min / nom / max RC) with the chip wiring of the "
                        "same name (coupling counted 0 / 1 / 2 times); ss 125 °C 3.0 V, tt 25 °C 3.3 V, ff −40 °C "
                        "3.6 V; the quantizer as its strobe-to-TH model (ss at −20 °C, its slowest). Times from the "
                        "MCLK edge at the pad, period 30.5 ns. r13: the 13th chip's routes (the 12th assembly moved "
                        "clock and data lines; section 5 of the verification document holds the wiring of 10/24). "
                        "The two chips' extracted interface nets differ in 13 of 112 (e): the routes to and from the "
                        "r14 macro's pins, which moved with its 900 µm height.")
    gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 1.05])
    # (a) TH
    ax = fig.add_subplot(gs[0, 0])
    keys = R.CORNERS
    x = bars(ax, keys, {v: {k: d[v][k]["th"] for k in keys} for v in d})
    ax.set_xticklabels([SHORT[k] for k in keys], fontsize=7.4)
    ax.set_ylabel("setup slack (ns)")
    ax.set_title("(a) TH from the quantizer (worst of 31)")
    for i, k in enumerate(keys[:1]):
        for j, ver in enumerate(("r13", "r14")):
            v = d[ver][k]["th"]
            ax.annotate(f"{v:+.2f}", (x[i] + (j - 0.5) * 0.38, v), xytext=(-8 if ver == "r13" else 0, 3),
                        textcoords="offset points", ha="right" if ver == "r13" else "center", fontsize=7.2,
                        color=COL[ver] if ver == "r14" else MUTED)
    ax.legend(loc="upper left", fontsize=7.4)
    # (b) between the blocks
    ax = fig.add_subplot(gs[0, 1])
    for ver, mk in (("r13", "o"), ("r14", "s")):
        ax.plot(range(len(keys)), [d[ver][k]["blk_setup"] for k in keys], mk + "-", color=COL[ver], lw=1.2, ms=4.5,
                label=f"{ver} setup")
        ax.plot(range(len(keys)), [d[ver][k]["blk_hold"] for k in keys], mk + "--", color=COL[ver], lw=1.0, ms=4.5,
                mfc="white", label=f"{ver} hold")
    ax.axhline(0, color="#b91c1c", lw=0.8)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([SHORT[k] for k in keys], fontsize=7.4)
    ax.set_ylabel("worst slack (ns)")
    ax.set_ylim(bottom=-1)
    k0 = keys[0]
    ax.annotate(f"{d['r14'][k0]['blk_setup_name']} {d['r14'][k0]['blk_setup']:+.2f}\n(preset arc in the model)",
                (0, d["r14"][k0]["blk_setup"]), xytext=(0.6, 0.3), textcoords="data", fontsize=7.2,
                color=COL["r14"], arrowprops=dict(arrowstyle="->", color=COL["r14"]))
    ax.set_title("(b) Between the two macros (TH_CAPTURE, DAC_LOAD,\nDWA_EN, ADC_RST_N, CODE)")
    ax.legend(loc="upper right", fontsize=7.2, ncol=2)
    # (c) blanking
    ax = fig.add_subplot(gs[0, 2])
    for ver, mk in (("r13", "o"), ("r14", "s")):
        ax.plot(range(len(keys)), [d[ver][k]["blank_rise"] for k in keys], mk + "-", color=COL[ver], lw=1.2,
                ms=4.5, label=f"{ver}: rise before the CHOP_OUT edge")
        ax.plot(range(len(keys)), [d[ver][k]["blank_fall1"] for k in keys], mk + "--", color=COL[ver], lw=1.0,
                ms=4.5, mfc="white", label=f"{ver}: fall after it, BLANK_LEN 1")
    ax.axhline(0, color="#b91c1c", lw=0.8)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([SHORT[k] for k in keys], fontsize=7.4)
    ax.set_ylabel("margin (ns)")
    ax.set_ylim(0, 36)
    ax.set_title("(c) CHOP_BLANK around the CHOP_OUT edges (clocked\nedges; r14 without the reset arcs)")
    ax.legend(loc="lower right", fontsize=7.0)
    # (d) slews at max ss
    ax = fig.add_subplot(gs[1, 0:2])
    nk = ["CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CHOP1", "ADC_ZERO", "CMP_STROBE", "DAC_CLK"]
    x = bars(ax, nk, {v: d[v]["max_ss_125C_3v00"]["slew"] for v in d})
    for i, k in enumerate(nk):
        for j, ver in enumerate(("r13", "r14")):
            v = d[ver]["max_ss_125C_3v00"]["slew"][k]
            ax.text(x[i] + (j - 0.5) * 0.38, v + 0.5, f"{v:.1f}", ha="center", fontsize=7.0,
                    color=MUTED if ver == "r13" else COL["r14"])
    ax.set_xticklabels(nk, fontsize=8)
    ax.set_ylabel("slew 30–70 % at the receiver (ns)")
    ax.set_title("(d) Slews at the analog receivers, max ss 125 °C (STA, library tables; transistor runs: figure 56)")
    ax.legend(loc="upper right", fontsize=7.6)
    # (e) the nets that differ
    ax = fig.add_subplot(gs[1, 2])
    def ctot(n):
        return n["c_iso_fF"] + n["c_cpl_fF"]
    diff = [k for k in nets["r13"] if abs(ctot(nets["r13"][k]) - ctot(nets["r14"][k])) > 0.5
            or abs(max(nets["r13"][k]["r_typ"][0][1:]) - max(nets["r14"][k]["r_typ"][0][1:])) > 1]
    y = np.arange(len(diff))
    for i, ver in enumerate(("r13", "r14")):
        ax.barh(y + (i - 0.5) * 0.38, [ctot(nets[ver][k]) for k in diff], 0.38, color=COL[ver], label=ver)
    for j, k in enumerate(diff):
        l13 = sum(v["perim_um"] / 2 for v in nets["r13"][k]["layers"].values())
        l14 = sum(v["perim_um"] / 2 for v in nets["r14"][k]["layers"].values())
        ax.text(max(ctot(nets["r13"][k]), ctot(nets["r14"][k])) + 4, j,
                f"{l14 - l13:+.0f} µm" if abs(l14 - l13) >= 0.5 else "same length", va="center", fontsize=6.8,
                color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels(diff, fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlabel("C, isolated + coupling (fF)")
    ax.set_xlim(0, 420)
    ax.set_title(f"(e) Wiring that differs ({len(diff)} of {len(nets['r13'])} nets)")
    ax.legend(loc="upper right", fontsize=7.4)
    ax.grid(axis="y", visible=False)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_55_chip_sta.png")
    fig.savefig(p)
    print("wrote", p)
    for v in d:
        k = "max_ss_125C_3v00"
        print(v, {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in d[v][k].items() if kk != "slew"})


if __name__ == "__main__":
    main()

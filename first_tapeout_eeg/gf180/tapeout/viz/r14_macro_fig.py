#!/usr/bin/env python3
"""Figure 53 (r14, 11/24): the r14 digital macro (eeg_digital_top, LibreLane run r14f5_20261124) against the r13 macro
(run f2, the 13th chip): layout, the STA of the 9 corners (VER-05: the flip-flops' preset / clear arcs timed) and the
SOFT_RESET paths through those arcs.
  (a) the two macros to scale (LibreLane's renders)
  (b) setup worst slack per corner: r13 f2 (LibreLane), r14 f5 without and with the preset / clear arcs
  (c) hold worst slack per corner, the same
  (d) the SOFT_RESET paths (rst_n's assertion through the clear / preset arcs): worst setup slack per endpoint group
  (e) the macros in numbers

Data: digital/eeg_digital_top{,_r14}/runs/<run>/final/metrics.json, runs/r14f5_20261124/sta_r14/ (run_sta_r14.sh,
soft_paths.py). Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_macro_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import HAIR, INK2, MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r14", "20261124"
V.CHIP_LABEL = "Chip r14 (fourteenth assembly, 24 Nov 2026)"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
DIG = os.path.join(REPO, "gf180", "tapeout", "digital")
R13 = os.path.join(DIG, "eeg_digital_top", "runs", "f2_rerun_20261119")
R14_TAG = "r14f5_20261124"
R14 = os.path.join(DIG, "eeg_digital_top_r14", "runs", R14_TAG)
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
CORNERS = [f"{rc}_{pv}" for pv in ("ss_125C_3v00", "tt_025C_3v30", "ff_n40C_3v60") for rc in ("max", "nom", "min")]
GREY, TEAL, PLUM = "#94a3b8", "#0d9488", "#7c3aed"


def sta_summary(arcs):
    out = {}
    for c in CORNERS:
        w = open(os.path.join(R14, "sta_r14", f"arcs_{arcs}", c, "summary.txt")).read().split()
        out[c] = {"setup": float(w[w.index("setup") + 1]), "hold": float(w[w.index("hold") + 1])}
    return out


def main():
    V.apply()
    m13 = json.load(open(os.path.join(R13, "final", "metrics.json")))
    m14 = json.load(open(os.path.join(R14, "final", "metrics.json")))
    on, off = sta_summary("on"), sta_summary("off")
    soft = json.load(open(os.path.join(R14, "sta_r14", "soft_paths.json")))
    fig = V.figure(12.4, 9.0, "The r14 digital macro (eeg_digital_top, 440 × 900 µm) against r13's",
                   "LibreLane run r14f5_20261124 of the audited RTL (commit e56bc9da): 9 corners met with the "
                   "flip-flops' preset / clear arcs timed (VER-05), no slew, capacitance or fanout warnings; DRC, LVS "
                   "and antenna clean. r13: run f2 (440 × 700 µm) of the 13th chip.",
                   note="Corners: tt 25 °C 3.3 V, ss 125 °C 3.0 V, ff −40 °C 3.6 V with the min / nom / max parasitics. "
                        "r14's constraints (eeg_digital_top_r14.sdc): r13's, plus the reset exceptions the preset / "
                        "clear arcs need: paths from RESET_N's assertion (it resets every flip-flop) and SOFT_RESET "
                        "paths into flip-flops rst_n holds in reset, or into the FIFO's memory (read only where "
                        "written), are false; every other SOFT_RESET path is timed. r13 f2: LibreLane's signoff, "
                        "arcs off. Slack in ns at the MCLK period of 30.5 ns.")
    gs = fig.add_gridspec(2, 3, width_ratios=[0.95, 1.25, 1.25], height_ratios=[1, 1])
    # (a) the renders to scale: both 1000 px wide = 440 um
    ax = fig.add_subplot(gs[:, 0])
    from PIL import Image
    im13 = np.asarray(Image.open(os.path.join(R13, "final", "render", "eeg_digital_top.png")))
    im14 = np.asarray(Image.open(os.path.join(R14, "final", "render", "eeg_digital_top.png")))
    s = 440.0 / 1000.0
    ax.imshow(im13, extent=(0, 440, 0, im13.shape[0] * s))
    ax.imshow(im14, extent=(500, 940, 0, im14.shape[0] * s))
    ax.set_xlim(-10, 950)
    ax.set_ylim(-60, 930)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([0, 300, 600, 900])
    ax.set_ylabel("µm")
    for x, t in ((220, f"r13 f2\n{m13['design__instance__count__stdcell']:,} cells, 873 FF"),
                 (720, f"r14 f5\n{m14['design__instance__count__stdcell']:,} cells, "
                       f"{m14['design__instance__count__class:sequential_cell']:,} FF")):
        ax.text(x, -45, t, ha="center", va="center", fontsize=8.5, color=INK2)
    ax.set_title("(a) The two macros to scale (LibreLane renders)")
    # (b), (c) setup / hold per corner
    x = np.arange(len(CORNERS))
    lab = [c.replace("_125C_3v00", "").replace("_025C_3v30", "").replace("_n40C_3v60", "").replace("_", " ")
           for c in CORNERS]
    for k, (key, title) in enumerate((("setup", "(b) Setup worst slack (ns)"), ("hold", "(c) Hold worst slack (ns)"))):
        ax = fig.add_subplot(gs[k, 1])
        v13 = [m13[f"timing__{key}__ws__corner:{c}"] for c in CORNERS]
        voff = [off[c][key] for c in CORNERS]
        von = [on[c][key] for c in CORNERS]
        w = 0.26
        ax.bar(x - w, v13, w, color=GREY, label="r13 f2")
        ax.bar(x, voff, w, color=TEAL, label="r14 f5, arcs off")
        ax.bar(x + w, von, w, color=PLUM, label="r14 f5, arcs on")
        ax.set_xticks(x)
        ax.set_xticklabels(lab, rotation=35, ha="right")
        worst = min(von)
        cw = lab[int(np.argmin(von))]
        ax.set_title(f"{title}: r14 worst {worst:+.3f} ({cw}), r13 {min(v13):+.3f}")
        ax.axhline(0, color=INK2, lw=0.8)
        if key == "setup":
            ax.set_yscale("symlog", linthresh=2.0)
            ax.set_yticks([0, 0.5, 1, 2, 5, 10, 20])
            ax.set_yticklabels(["0", "0.5", "1", "2", "5", "10", "20"])
            ax.legend(loc="upper left", fontsize=7.8)
    # (d) SOFT_RESET paths by group
    ax = fig.add_subplot(gs[0, 2])
    groups = ["CIC", "output ports", "rst_n, soft_cnt", "clock generator", "timing and data path (top)", "CHOP1", "RAW"]
    names = {"CIC": "CIC (clear)", "output ports": "output pins", "rst_n, soft_cnt": "rst_n, soft_cnt",
             "clock generator": "clock gen.", "timing and data path (top)": "top (seq_cnt …)", "CHOP1": "CHOP1",
             "RAW": "RAW"}
    ys = np.arange(len(groups))
    for j, (cs, col, lb) in enumerate(((("max_ss_125C_3v00",), PLUM, "max ss"), (("nom_tt_025C_3v30",), TEAL, "nom tt"),
                                       (("min_ff_n40C_3v60",), GREY, "min ff"))):
        vals = [min(soft[c]["setup_by_group"][g]["worst"] for c in cs) for g in groups]
        ax.barh(ys + (j - 1) * 0.26, vals, 0.26, color=col, label=lb)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{names[g]} ({soft['max_ss_125C_3v00']['setup_by_group'][g]['n']})" for g in groups])
    ax.invert_yaxis()
    ax.axvline(0, color=INK2, lw=0.8)
    cic = soft["max_ss_125C_3v00"]["setup_by_group"]["CIC"]["worst"]
    hold = min(soft[c]["hold_worst"] for c in CORNERS)
    ax.set_xlabel(f"worst setup slack (ns)\ntightest: the CIC's clear, {cic:+.2f} ns at max ss; "
                  f"hold of these paths ≥ {hold:+.2f} ns", fontsize=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, fontsize=7.8)
    ax.set_title("(d) SOFT_RESET through the clear arcs (endpoints)")
    # (e) table
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    rows = [("outline (µm)", "440 × 700", "440 × 900"),
            ("standard cells", f"{m13['design__instance__count__stdcell']:,}", f"{m14['design__instance__count__stdcell']:,}"),
            ("flip-flops", "873", f"{m14['design__instance__count__class:sequential_cell']:,}"),
            ("utilization", f"{m13['design__instance__utilization'] * 100:.1f} %", f"{m14['design__instance__utilization'] * 100:.1f} %"),
            ("routed wire (mm)", f"{m13['route__wirelength'] / 1000:.0f}", f"{m14['route__wirelength'] / 1000:.0f}"),
            ("setup, max ss (ns)", f"{m13['timing__setup__ws__corner:max_ss_125C_3v00']:+.3f}", f"{on['max_ss_125C_3v00']['setup']:+.3f}"),
            ("hold, min ff (ns)", f"{m13['timing__hold__ws__corner:min_ff_n40C_3v60']:+.3f}", f"{on['min_ff_n40C_3v60']['hold']:+.3f}"),
            ("slew / cap / fanout warnings", f"{m13['design__max_slew_violation__count']} / {m13['design__max_cap_violation__count']} / {m13['design__max_fanout_violation__count']}",
             f"{m14['design__max_slew_violation__count']} / {m14['design__max_cap_violation__count']} / {m14['design__max_fanout_violation__count']}"),
            ("Magic / KLayout DRC, LVS, antenna", "0 / 0, 0, 0",
             f"{m14['magic__drc_error__count']} / {m14['klayout__drc_error__count']}, {m14['design__lvs_error__count']}, {m14['antenna__violating__nets']}"),
            ("output buffers", "buf_1 (50)", "clkbuf_2 (50)")]
    tab = ax.table(cellText=[r[1:] for r in rows], rowLabels=[r[0] for r in rows], colLabels=["r13 f2", "r14 f5"],
                   loc="center", cellLoc="center", rowLoc="left", colWidths=[0.27, 0.27])
    tab.auto_set_font_size(False)
    tab.set_fontsize(8.3)
    tab.scale(1.0, 1.32)
    for (r, c), cell in tab.get_celld().items():
        cell.set_edgecolor(HAIR)
        if r == 0:
            cell.set_text_props(color=INK2, fontweight="medium")
    ax.set_title("(e) The macros in numbers", loc="left")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_53_digital_macro.png")
    fig.savefig(p)
    print("wrote", p)


if __name__ == "__main__":
    main()

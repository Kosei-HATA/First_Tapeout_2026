#!/usr/bin/env python3
"""Figure 54 (r14, 11/24): the 14th chip against the 13th, layer by layer (VER-08): where the two GDS differ (pre-fill).

chip_xor.py's per-layer XOR of layout/runs/chip_top/r13_20261119/chip_top.gds and the 14th chip's chip_top.gds, rasterized
over the digital column (4 um pixels; runs/chip_top/xor_r13_r14_chip_top_20261124.json):
  (a) the digital column: the differing area per pixel, by layer group, with the two macros' outlines, the DVDD
      decoupling of each chip and the Metal5 power straps;
  (b) the column's south end and the ADC's east edge, where a router wire of the digital interface sits on the router
      column x 2942.24 (0.16 um inside the ADC's outline): the only shapes that differ west of x 2942.4;
  (c) every layer: the area that differs, inside the digital column and outside it.
Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_xor_fig.py
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
JS = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "chip_top", "xor_r13_r14_chip_top_20261124.json")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
NAMES = {"21/0": "Nwell", "22/0": "COMP", "30/0": "Poly2", "31/0": "Pplus", "32/0": "Nplus", "33/0": "Contact",
         "34/0": "Metal1", "35/0": "Via1", "36/0": "Metal2", "38/0": "Via2", "42/0": "Metal3", "40/0": "Via3",
         "46/0": "Metal4", "41/0": "Via4", "81/0": "Metal5", "55/0": "Dualgate", "112/1": "V5_XTOR",
         "166/5": "MOS_CAP_MK", "204/0": "LVPWELL", "21/10": "Nwell label", "63/63": "text", "204/10": "LVPWELL label"}
GROUPS = [("devices (well, COMP, poly, implants, contact, markers)",
           ("21/0", "22/0", "30/0", "31/0", "32/0", "33/0", "55/0", "112/1", "166/5", "204/0"), "#94a3b8"),
          ("Metal1, Via1, Metal2", ("34/0", "35/0", "36/0"), "#0d9488"),
          ("Via2, Metal3, Via3, Metal4", ("38/0", "42/0", "40/0", "46/0"), "#7c3aed"),
          ("Via4, Metal5", ("41/0", "81/0"), "#b45309")]


def raster(js, keys):
    r = js["raster"]
    a = np.zeros((r["ny"], r["nx"]))
    for k in keys:
        for i, j, v in js["layers"].get(k, {}).get("raster", []):
            a[j, i] += v
    return a


def main():
    V.apply()
    js = json.load(open(JS))
    r = js["raster"]
    x1, y1, x2, y2 = r["box"]
    fig = V.figure(12.6, 9.4, "The 14th chip against the 13th: where the GDS differ (VER-08)",
                   "Layer by layer XOR before the fill: everything differs only in the digital column (from the ADC's "
                   "east edge to the east pads), the r14 macro, its power straps, the DVDD decoupling moved 200 µm up "
                   "and the routes of the digital interface; the AFE, the ADC, the bias, the reference, the pad ring "
                   "and every analog route are the same.",
                   note=f"XOR of runs/chip_top/r13_20261119/chip_top.gds (the 13th chip) and the 14th chip's chip_top.gds, "
                        f"flat, per layer (gf180/tapeout/layout/chip_xor.py): {js['same']} layers identical, the rest "
                        "differ only inside the column but for one router wire of the digital interface at x 2942.05–2942.40 "
                        "(b). Pixels of 4 µm: the colour is the group with the most differing area in the pixel, its "
                        "opacity that area's share. Labels: none of the chip's labels differ.")
    gs = fig.add_gridspec(2, 2, width_ratios=[0.78, 1.3], height_ratios=[1.0, 1])
    ax = fig.add_subplot(gs[:, 0])
    ax.set_facecolor("white")
    mats = [raster(js, keys) for _, keys, _ in GROUPS]
    tot = sum(mats)
    best = np.argmax(np.stack(mats), axis=0)
    rgba = np.zeros((r["ny"], r["nx"], 4))
    for g, (_, _, col) in enumerate(GROUPS):
        c = np.array([int(col[k:k + 2], 16) / 255 for k in (1, 3, 5)])
        m = (best == g) & (tot > 0)
        rgba[m, :3] = c
    rgba[..., 3] = np.clip(tot / (r["pixel"] ** 2) * 1.6, 0, 1) * (tot > 0)
    ax.imshow(rgba, origin="lower", extent=(x1, x2, y1, y2), interpolation="nearest")
    for (xa, ya, xb, yb), col, ls, lab in (((3002, 542, 3442, 1242), "#64748b", "--", "r13 macro"),
                                         ((3002, 542, 3442, 1442), "#0f172a", "-", "r14 macro"),
                                         ((3003, 1252, 3346.2, 1432), "#64748b", "--", "r13 DVDD decoupling"),
                                         ((3003, 1452, 3346.2, 1632), "#0f172a", "-", "r14 DVDD decoupling"),
                                         ((2942.4, 376, 3556, 2155), "#4f46e5", ":", "digital column (XOR region)")):
        ax.add_patch(plt.Rectangle((xa, ya), xb - xa, yb - ya, fill=False, ec=col, ls=ls, lw=1.0, label=lab))
    for xs, lab in (((2950, 2992), "DVSS trunk"), ((3500, 3542), "DVDD trunk")):
        ax.axvspan(*xs, color="#e2e8f0", alpha=0.45, lw=0)
        ax.text(sum(xs) / 2, 2110, lab, rotation=90, ha="center", va="top", fontsize=7.5, color=MUTED)
    ax.set_xlim(x1, x2)
    ax.set_ylim(y1, y2)
    ax.set_aspect("equal")
    ax.set_xlabel("x (µm, die)")
    ax.set_ylabel("y (µm, die)")
    from matplotlib.patches import Patch
    h, lb = ax.get_legend_handles_labels()
    h += [Patch(color=col) for _, _, col in GROUPS]
    lb += [lab for lab, _, _ in GROUPS]
    ax.legend(h, lb, loc="upper center", bbox_to_anchor=(0.5, 0.995), fontsize=7.0, handlelength=2.0,
              framealpha=0.92, frameon=True, edgecolor=HAIR)
    ax.set_title("(a) The digital column: differing area")
    ax.grid(False)
    # (b) zoom at the ADC's east edge
    axz = fig.add_subplot(gs[0, 1])
    zx1, zx2, zy1, zy2 = 2900, 3160, 575, 765
    i1, i2 = int((zx1 - x1) / r["pixel"]), int((zx2 - x1) / r["pixel"])
    j1, j2 = int((zy1 - y1) / r["pixel"]), int((zy2 - y1) / r["pixel"])
    axz.imshow(rgba[j1:j2, i1:i2], origin="lower", extent=(zx1, zx2, zy1, zy2), interpolation="nearest")
    axz.axvline(2942.4, color="#4f46e5", ls=":", lw=1.0)
    axz.add_patch(plt.Rectangle((3002, 542), 440, 900, fill=False, ec="#0f172a", lw=1.0))
    axz.axvspan(2950, 2992, color="#e2e8f0", alpha=0.45, lw=0)
    out_boxes = [b for k, v in js["layers"].items() for b in v.get("outside_boxes", [])]
    for b in out_boxes:
        axz.add_patch(plt.Rectangle((b[0] - 1.5, b[1] - 1.5), b[2] - b[0] + 3, b[3] - b[1] + 3, fill=False,
                                    ec="#b91c1c", lw=1.2))
    if out_boxes:
        yb = [b[1] for b in out_boxes] + [b[3] for b in out_boxes]
        axz.annotate("router wire, x 2942.05–2942.40\n(Metal3, Via3, Metal4)", xy=(2942.0, (min(yb) + max(yb)) / 2),
                     xytext=(2902, 745), fontsize=7.4, color="#b91c1c", arrowprops=dict(arrowstyle="->", color="#b91c1c"))
    axz.text(2919, 580, "ADC\n(adc_top)", ha="center", va="bottom", fontsize=8, color=MUTED)
    axz.text(2971, 580, "DVSS\ntrunk", ha="center", va="bottom", fontsize=7.2, color=MUTED)
    axz.text(3080, 590, "r14 macro", ha="center", va="bottom", fontsize=8, color="white")
    axz.set_xlim(zx1, zx2)
    axz.set_ylim(zy1, zy2)
    axz.set_aspect("equal")
    axz.grid(False)
    axz.set_title("(b) The ADC's east edge: the only shapes that differ west of x 2942.4")
    # (c) per layer
    axl = fig.add_subplot(gs[1, 1])
    keys = [k for k in NAMES if k in js["layers"] and not k.endswith("/10") and k != "63/63"]
    keys.sort(key=lambda k: -js["layers"][k]["diff_um2"])
    inside = [js["layers"][k]["diff_um2"] - js["layers"][k].get("outside_um2", 0.0) for k in keys]
    outside = [js["layers"][k].get("outside_um2", 0.0) for k in keys]
    y = np.arange(len(keys))
    axl.barh(y, [max(v, 1e-3) for v in inside], color="#7c3aed", label="inside the digital column")
    axl.barh(y, [max(v, 1e-3) if v > 0 else 0 for v in outside], left=0, color="#b91c1c", height=0.35,
             label="outside (b)")
    axl.set_xscale("log")
    axl.set_xlim(0.05, 1e6)
    axl.set_yticks(y)
    axl.set_yticklabels([f"{NAMES[k]} ({k})" + (f", {o_:.3g} µm² outside" if o_ > 0 else "")
                         for k, o_ in zip(keys, outside)], fontsize=7.6)
    axl.invert_yaxis()
    axl.set_xlabel("differing area (µm²)")
    same = [k for k, v in js["layers"].items() if v["diff_um2"] == 0 and not v["texts_differ"]]
    axl.legend(loc="lower right", fontsize=7.6)
    axl.set_title(f"(c) Every layer that differs ({len(keys)}); {len(same)} layers identical")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_54_xor_r13.png")
    fig.savefig(p)
    print("wrote", p)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Figure 34 (r12, 11/13): switching lines under the sensitive nets, r11 against r12.

  extract  from the blocks' LVS databases (layout nets) the shapes in two windows, by net class and metal:
           ADC: the gap between adc_rdac and OTA1 with the I1N / O1P straps (Metal5) and the SEL1 / DAC_CLK
           lines; AFE: the corridor of the input chopper's gate lanes under the WN plate and the clock
           driver's west rows. The extracted couplings (Magic, pex.py) of the pairs in question, r11 and r12.
           Written to data_r12/crossings.json.
  plot     the figure from that file: four layout views and the couplings.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/crossings_fig.py extract --adc11 GDS LVSDB --afe11 GDS LVSDB
       gf180/tools/venv310/bin/python gf180/tapeout/viz/crossings_fig.py plot
(r12's blocks are layout/gds/{adc,afe}_top.gds with layout/runs/{adc,afe}_top/*.lvsdb; r11's are the saved copies.)
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex", "runs")
LAYOUT = os.path.join(REPO, "gf180", "tapeout", "layout")
DATA = os.path.join(HERE, "data_r12", "crossings.json")
METALS = {"metal2": 16, "metal3": 18, "metal4": 21, "metal5": 24}      # the lvsdb layers (crossings.py matches them)
# windows in block coordinates (um) and the block origins on the die
WIN = {"adc": (400.0, 412.0, 482.0, 506.0), "afe": (96.0, 396.0, 204.0, 496.0)}
ORIGIN = {"adc": (1732.4, 542.0), "afe": (482.0, 542.0)}
CLASSES = {
    "adc": [("I1N", ["ADC.I1N"]), ("O1P", ["ADC.O1P"]), ("switching", [f"SEL1_{k}" for k in range(31)] + ["DAC_CLK"]),
            ("AVSS", ["AVSS"])],
    "afe": [("WN", ["WN"]), ("lanes", ["CIA", "CIB", "NCIA", "NCIB"]),
            ("rows", ["NCDA", "CDB", "NCDB", "RST", "CHOP_EN", "CDA", "CIA", "CIB", "AFE_RST", "OFPH", "CHOP_BLANK",
                      "CHOP_OUT", "CHOP"]), ("AVDD", ["AVDD"]), ("AVSS", ["AVSS"])],
}
PAIRS = {  # (netlist, net a, net-or-group b, label)
    "adc": [("I1P", "SEL1", "I1P - SEL1"), ("I1N", "SEL1", "I1N - SEL1"), ("O1P", "SEL1", "O1P - SEL1"),
            ("I1N", "DAC_CLK", "I1N - DAC_CLK"), ("O1P", "DAC_CLK", "O1P - DAC_CLK")],
    "afe": [("WN", "NCDA", "WN - NCDA"), ("WN", "CDB", "WN - CDB"), ("WN", "NCDB", "WN - NCDB"), ("WN", "RST", "WN - RST"),
            ("WN", "CHOP_EN", "WN - CHOP_EN")],
}
NETLIST = {("adc", "r11"): "adc_top_c_r11/eeg_adc_pex.spice", ("adc", "r12"): "adc_top_c_r12/eeg_adc_pex.spice",
           ("afe", "r11"): "afe_top_c/afe_top_pex.spice", ("afe", "r12"): "afe_top_c_r12/afe_top_pex.spice"}


def couplings(path):
    U = {"": 1, "f": 1e-15, "p": 1e-12, "a": 1e-18, "n": 1e-9, "u": 1e-6}
    cc = collections.defaultdict(float)
    for line in open(path).read().replace("\n+", " ").splitlines():
        if not line.startswith("C"):
            continue
        w = line.split()
        for t in w[3:]:
            m = re.fullmatch(r"([0-9.eE+-]+)([a-zA-Z]*)", t)
            if m:
                cc[tuple(sorted((w[1].upper(), w[2].upper())))] += float(m.group(1)) * U[m.group(2).lower()[:1]]
                break
    return cc


def pair_c(cc, a, b):
    if b == "SEL1":
        return sum(c for (x, y), c in cc.items() if (x == a and y.startswith("SEL1_")) or (y == a and x.startswith("SEL1_")))
    return cc.get(tuple(sorted((a, b))), 0.0)


def extract(a):
    import klayout.db as kdb
    out = {"windows": WIN, "origin": ORIGIN, "shapes": {}, "couplings": {}}
    blocks = {("adc", "r11"): a.adc11, ("afe", "r11"): a.afe11,
              ("adc", "r12"): (os.path.join(LAYOUT, "gds", "adc_top.gds"), os.path.join(LAYOUT, "runs", "adc_top", "adc_top.lvsdb")),
              ("afe", "r12"): (os.path.join(LAYOUT, "gds", "afe_top.gds"), os.path.join(LAYOUT, "runs", "afe_top", "afe_top.lvsdb"))}
    for (blk, rev), (gds, lvsdb) in blocks.items():
        lvs = kdb.LayoutVsSchematic()
        lvs.read(lvsdb)
        win = kdb.Region(kdb.DBox(*WIN[blk]).to_itype(0.001))
        names = {n.name: n for n in next(lvs.reference.each_circuit_top_down()).each_net() if n.name}
        taken = {m: kdb.Region() for m in METALS}
        res = {}

        def boxes(r):
            """the region as boxes (manhattan shapes, so its trapezoid decomposition is boxes)"""
            return [[round(v * 0.001, 3) for v in (b.left, b.bottom, b.right, b.top)]
                    for b in (q.bbox() for q in r.decompose_trapezoids_to_region().each())]
        for cls, nets in CLASSES[blk]:
            for m, li in METALS.items():
                r = kdb.Region()
                for n in nets:
                    ln = lvs.xref().other_net_for(names[n]) if n in names else None
                    if ln is not None:
                        r += lvs.shapes_of_net(ln, lvs.layer_by_index(li), True)
                r = (r & win).merged() - taken[m]
                taken[m] += r
                res.setdefault(cls, {})[m] = boxes(r)
        for m, li in METALS.items():
            res.setdefault("other", {})[m] = boxes((lvs.layer_by_index(li) & win).merged() - taken[m])
        out["shapes"][f"{blk}_{rev}"] = res
        cc = couplings(os.path.join(PEX, NETLIST[(blk, rev)]))
        out["couplings"][f"{blk}_{rev}"] = {lab: round(pair_c(cc, x, y) * 1e15, 3) for x, y, lab in PAIRS[blk]}
        if blk == "afe":
            for k in ("CIA", "NCIA", "CIB", "NCIB"):
                out["couplings"][f"{blk}_{rev}"][f"WN - WP, {k}"] = round((pair_c(cc, "WN", k) - pair_c(cc, "WP", k)) * 1e15, 3)
        print(blk, rev, out["couplings"][f"{blk}_{rev}"])
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(out, open(DATA, "w"))
    print("wrote", DATA)


def plot():
    sys.path.insert(0, HERE)
    import vizstyle as V
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    d = json.load(open(DATA))
    COL = {"I1N": "#2563eb", "O1P": "#d97706", "switching": V.BAD, "AVSS": V.OK, "AVDD": "#0d9488",
           "WN": "#2563eb", "lanes": V.BAD, "rows": "#9333ea", "other": "#94a3b8"}
    ALPHA = {"metal2": 0.95, "metal3": 0.85, "metal4": 0.55, "metal5": 0.18}
    LW = {"metal5": 1.1}
    fig = V.figure(13.2, 15.0, "Switching lines under the sensitive nets: r11 and r12",
                   "Top: the ADC's gap between adc_rdac and OTA1, where the stage-1 straps I1N / O1P (Metal5) run up and "
                   "SEL1_0..30 and DAC_CLK cross. Middle: the AFE's corridor of the input chopper's gate lanes under the "
                   "WN plate, and the clock driver's west rows. Bottom: the extracted couplings (Magic).",
                   "Layout views: the blocks' LVS databases, shapes by net and metal (Metal5 as outlines over the lower "
                   "metals), die coordinates. r11's AFE is r6's (afe_top did not change until r12). Couplings: pex.py's "
                   "netlists runs/adc_top_c_r11 / _r12, runs/afe_top_c / _r12; SEL1 = the sum over the 31 lines.")
    gs = fig.add_gridspec(3, 2, height_ratios=[1.2, 1.2, 0.8])
    titles = {"adc_r11": "ADC, r11: SEL1 / DAC_CLK on Metal4 right under I1N / O1P",
              "adc_r12": "ADC, r12: on Metal2 under a Metal4 AVSS shield; the gap closed to the router",
              "afe_r11": "AFE, r11: the lanes and five west rows under WN's Metal5",
              "afe_r12": "AFE, r12: a Metal4 AVDD shield over the lanes; WN off the rows"}
    for i, blk in enumerate(("adc", "afe")):
        ox, oy = d["origin"][blk]
        x1, y1, x2, y2 = d["windows"][blk]
        for j, rev in enumerate(("r11", "r12")):
            ax = fig.add_subplot(gs[i, j])
            sh = d["shapes"][f"{blk}_{rev}"]
            for m in ("metal2", "metal3", "metal4", "metal5"):
                for cls in ["other"] + [c for c, _ in CLASSES[blk]]:
                    for bx in sh.get(cls, {}).get(m, []):
                        r = Rectangle((bx[0] + ox, bx[1] + oy), bx[2] - bx[0], bx[3] - bx[1], linewidth=LW.get(m, 0),
                                      edgecolor=COL[cls] if m == "metal5" else "none", facecolor=COL[cls],
                                      alpha=ALPHA[m] if cls != "other" else ALPHA[m] * 0.45)
                        ax.add_patch(r)
            ax.set_xlim(x1 + ox, x2 + ox)
            ax.set_ylim(y1 + oy, y2 + oy)
            ax.set_aspect("equal")
            ax.grid(False)
            ax.set_title(titles[f"{blk}_{rev}"], fontsize=9.5)
            ax.set_xlabel("x (um)")
            ax.set_ylabel("y (um)")
            labels = ([("I1N strap", "I1N"), ("O1P strap", "O1P"), ("SEL1 / DAC_CLK", "switching"), ("AVSS", "AVSS")]
                      if blk == "adc" else
                      [("WN", "WN"), ("gate lanes", "lanes"), ("west rows", "rows"), ("AVDD (shield)", "AVDD"), ("AVSS", "AVSS")])
            if rev == "r12":
                hs = [Rectangle((0, 0), 1, 1, facecolor=COL[c], alpha=0.7) for _, c in labels] + \
                    [Rectangle((0, 0), 1, 1, facecolor=COL["other"], alpha=0.35)]
                ax.legend(hs, [l for l, _ in labels] + ["other nets"], loc="upper left", bbox_to_anchor=(1.02, 1.0),
                          fontsize=8, ncol=1, frameon=False)
    for j, blk in enumerate(("adc", "afe")):
        ax = fig.add_subplot(gs[2, j])
        a, b = d["couplings"][f"{blk}_r11"], d["couplings"][f"{blk}_r12"]
        labs = list(a)
        y = range(len(labs))
        ax.barh([k + 0.2 for k in y], [a[l] for l in labs], height=0.38, color=V.LIGHT, label="r11")
        ax.barh([k - 0.2 for k in y], [b[l] for l in labs], height=0.38, color=V.ACCENT, label="r12")
        for k, l in enumerate(labs):
            ax.text(max(a[l], b[l]) + 0.15, k, f"{a[l]:.2f} -> {b[l]:.2f} fF", va="center", fontsize=7.8, color=V.INK2)
        ax.set_yticks(list(y))
        ax.set_yticklabels(labs, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("extracted coupling (fF)")
        ax.set_xlim(0, max(max(a.values()), max(b.values())) * 1.45)
        ax.set_title("ADC: stage-1 nets to the DAC1 lines" if blk == "adc" else
                     "AFE: WN to the west rows; WN - WP per gate lane", fontsize=9.5)
        ax.legend(loc="lower right", fontsize=8)
    out = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"gf180_viz_{V.CHIP}_34_crossings.png")
    fig.savefig(path)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["extract", "plot"])
    ap.add_argument("--adc11", nargs=2)
    ap.add_argument("--afe11", nargs=2)
    a = ap.parse_args()
    extract(a) if a.what == "extract" else plot()


if __name__ == "__main__":
    main()

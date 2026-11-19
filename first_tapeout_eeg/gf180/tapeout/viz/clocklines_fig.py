#!/usr/bin/env python3
"""Figure 48 (r13, 11/19): clock and data lines near the sensitive nets, the visual check over the
whole chip (a checklist item: "the clock lines do not run near sensitive nets, checked by eye").

  extract  from the core LVS database (runs/chip_top/eeg_core.lvsdb: the chip without the pad ring,
           die coordinates) the chip-level nets by class (sensitive analog, the AFE's chopper clocks,
           other clocks and data, static controls) and metal: the whole die without the two digital
           macros, and two windows on the channel south and east of the AFE where the output
           chopper's NCDB runs next to VCM and VBCM. From afe_top's LVS database (r13) the summing
           nodes INP / INN and every switching net of the block over the amplifier core. The
           extracted couplings of sensitive to switching nets (chip wiring: pex/runs/chipnets_r12,
           the same shapes outside afe_top in r13; the AFE: runs/afe_top_c_r13), and VCM / VBCM at
           the AFE's pins around one output chopper edge in r12's typical start-up run (the chip
           wiring's model with these couplings). Written to data_r13/clock_lines.json.
  plot     the figure from that file.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/clocklines_fig.py extract
       gf180/tools/venv310/bin/python gf180/tapeout/viz/clocklines_fig.py plot
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
LAYOUT = os.path.join(REPO, "gf180", "tapeout", "layout")
PEX = os.path.join(REPO, "gf180", "tapeout", "pex", "runs")
DATA = os.path.join(HERE, "data_r13", "clock_lines.json")
CORE_LVSDB = os.path.join(LAYOUT, "runs", "chip_top", "eeg_core.lvsdb")
CHIP_GDS = os.path.join(LAYOUT, "runs", "chip_top", "chip_top.gds")
AFE_LVSDB = os.path.join(LAYOUT, "runs", "afe_top", "afe_top.lvsdb")
AFE_GDS = os.path.join(LAYOUT, "gds", "afe_top.gds")
RUN = os.path.join(PEX, "startup", "start_c1e-08_v3.3_typical_+0mV_afe5ms_ib3_cm0mV50Hz_chip_r12")
# the KLayout LVS deck's layer order (afe_top, adc_top and the core: crossings.py matches Metal3-5)
LAYERS = {"metal1": 14, "metal2": 16, "metal3": 18, "metal4": 21, "metal5": 24}
SHOWN = ("metal2", "metal3", "metal4", "metal5")
AFE_ORIGIN = (482.0, 542.0)
BLOCKS = {"afe_top": (482.0, 542.0, 1582.0, 1989.0), "adc_top": (1732.4, 542.0, 2942.4, 1989.0),
          "eeg_bias": (1745.1, 425.4, 2837.4, 534.6), "eeg_ref": (669.0, 1995.0, 1582.0, 2054.0),
          "eeg_testmux": (1595.1, 1939.8, 1720.6, 1979.8), "eeg_digital_top": (3002.0, 542.0, 3442.0, 1242.0),
          "eeg_adc_dig": (2298.4, 542.0, 2718.4, 782.0), "AFE core": (681.2, 971.2, 1390.6, 1559.6),
          "AFE clock driver": (496.0, 847.0, 642.6, 941.0), "quantizer": (2292.8, 1583.1, 2797.4, 1987.7)}
MACROS = ("eeg_digital_top", "eeg_adc_dig")
SENS = ["ELP", "ELN", "VCM", "VBCM", "VBCM1", "VBN", "VBN1", "BLP", "BLN", "OUTP", "OUTN", "VREFP", "VREFN",
        "VREFP_PAD", "VREFN_PAD", "O2P", "O2N", "IDN", "IDP", "IQ", "ITST", "IB0", "IB1", "BN0", "BN1", "BP0", "BP1",
        "VBNC2", "VBPC2", "VNC1", "VPC1", "ATP"]
CHOP = ["CIA", "CIB", "NCIA", "NCIB", "CDA", "CDB", "NCDA", "NCDB"]
DIG = (["MCLK", "SCLK", "RAW_CLK", "CMP_STROBE", "DAC_CLK", "CHOP1", "CHOP", "CHOP_OUT", "CHOP_BLANK", "TH_CAPTURE",
        "DAC_LOAD", "RAW_DATA", "MOSI", "MISO", "MISO_OE", "CS_N", "DRDY_N", "ADC_ZERO", "ADC_RST_N", "AFE_RST",
        "CHOP_EN", "RSTA", "RESET_N", "DWA_EN"] + [f"SEL1_{k}" for k in range(31)] + [f"SEL2_{k}" for k in range(31)]
       + [f"TH{k}" for k in range(31)] + [f"CODE{k}" for k in range(5)])
STATIC = ([f"OFEN{k}" for k in range(4)] + [f"OFM{k}" for k in range(10)] + ["OFPH", "OFS"]
          + [f"CPF{k}" for k in range(4)] + [f"TC{k}" for k in range(5)] + ["DBG_SEL0", "DBG_SEL1"])
CLASSES = {"sensitive": SENS, "chopper clocks": CHOP, "clocks and data": DIG, "static controls": STATIC}
SHIELD = ["AVSS", "AVDD", "DVSS", "DVDD"]
# zoom windows (die um): the channel south of the AFE and the one east of it
WIN = {"south": (1004.0, 526.0, 1026.0, 546.0), "east": (1572.0, 640.0, 1602.0, 668.0)}
# the amplifier core in afe_top's coordinates, and afe_top's switching nets
CORE_WIN = (199.2, 429.2, 908.6, 1017.6)
AFE_SW = ["CIA", "CIB", "NCIA", "NCIB", "CDA", "CDB", "NCDA", "NCDB", "CDA2", "CDB2", "NCDA2", "NCDB2", "RST", "RST2",
          "AFE_RST", "CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "OFPH", "OFPH_N", "OFPH_P"]
# spots inside the ADC from crossings.py on the flattened core database (11/19), with their extracted couplings
# (runs/adc_top_c_r12, unchanged in r13): (where, label, label position), die um
MARKS = [((2348.0, 826.0), "SEL2 over I2P / I2N\n(9.9 / 11.7 fF in all)", (2480.0, 300.0)),
         ((2908.0, 1140.0), "TH0 / TH1 beside I2P / I2N, 0.4 mm\n(28 / 31 fF; move only at the two lowest thresholds)",
          (2620.0, 2080.0))]


def boxes(r, dbu):
    return [[round(v * dbu, 3) for v in (b.left, b.bottom, b.right, b.top)]
            for b in (q.bbox() for q in r.decompose_trapezoids_to_region().each())]


def check_layers(lvs, gds, top_name=None):
    """The deck's Metal3-5 layers in a window must be LAYERS' (as crossings.py's matching finds them)."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(gds)
    top = ly.top_cell()
    bb = top.bbox()
    found = {}
    for fx, fy in ((0.5, 0.5), (0.4, 0.4), (0.6, 0.6), (0.3, 0.6)):
        cx, cy = int(bb.left + fx * bb.width()), int(bb.bottom + fy * bb.height())
        w = kdb.Box(cx - 40000, cy - 40000, cx + 40000, cy + 40000)
        for m, (l, d) in (("metal3", (42, 0)), ("metal4", (46, 0)), ("metal5", (81, 0))):
            g = (kdb.Region(top.begin_shapes_rec_touching(ly.find_layer(l, d), w)) & kdb.Region(w)).merged()
            r = (lvs.layer_by_index(LAYERS[m]) & kdb.Region(w)).merged()
            if not g.is_empty():
                found.setdefault(m, []).append((r ^ g).area() < 1e-3 * g.area())
    assert all(any(v) for v in found.values()) and len(found) == 3, found


def caps(path):
    U = {"": 1, "f": 1e-15, "p": 1e-12, "a": 1e-18, "n": 1e-9, "u": 1e-6}
    cc = collections.defaultdict(float)
    for line in open(path).read().replace("\n+", " ").splitlines():
        w = line.split()
        if not w or not w[0].upper().startswith("C") or len(w) < 4:
            continue
        for t in w[3:]:
            m = re.fullmatch(r"([0-9.eE+-]+)([a-zA-Z]*)", t)
            if m:
                cc[tuple(sorted((w[1].upper(), w[2].upper())))] += float(m.group(1)) * U.get(m.group(2).lower()[:1], 1)
                break
    return cc


def extract():
    import klayout.db as kdb
    import numpy as np
    out = {"blocks": BLOCKS, "windows": WIN, "core_win": [CORE_WIN[0] + AFE_ORIGIN[0], CORE_WIN[1] + AFE_ORIGIN[1],
                                                          CORE_WIN[2] + AFE_ORIGIN[0], CORE_WIN[3] + AFE_ORIGIN[1]]}
    lvs = kdb.LayoutVsSchematic()
    lvs.read(CORE_LVSDB)
    check_layers(lvs, CHIP_GDS)
    dbu = lvs.internal_layout().dbu
    names = {n.name: n for n in next(lvs.reference.each_circuit_top_down()).each_net() if n.name}
    xref = lvs.xref()

    def net_region(n, m):
        ln = xref.other_net_for(names[n]) if n in names else None
        return kdb.Region() if ln is None else lvs.shapes_of_net(ln, lvs.layer_by_index(LAYERS[m]), True)
    macros = kdb.Region()
    for b in MACROS:
        macros.insert(kdb.DBox(*BLOCKS[b]).to_itype(dbu))
    over = {}
    for cls, nets in CLASSES.items():
        for m in SHOWN:
            r = kdb.Region()
            for n in nets:
                r += net_region(n, m)
            over.setdefault(cls, {})[m] = boxes(r.merged() - macros, dbu)
        print(cls, sum(len(v) for v in over[cls].values()), "boxes")
    out["overview"] = over
    zoom = {}
    for key, w in WIN.items():
        win = kdb.Region(kdb.DBox(*w).to_itype(dbu))
        nets = {}
        for n in list(names):
            for m in SHOWN:
                r = (net_region(n, m) & win).merged()
                if not r.is_empty():
                    nets.setdefault(n, {})[m] = boxes(r, dbu)
        zoom[key] = nets
        print(key, sorted(nets))
    out["zoom"] = zoom
    # the amplifier core (afe_top, r13)
    alvs = kdb.LayoutVsSchematic()
    alvs.read(AFE_LVSDB)
    check_layers(alvs, AFE_GDS)
    anames = {n.name: n for n in next(alvs.reference.each_circuit_top_down()).each_net() if n.name}
    win = kdb.Region(kdb.DBox(*CORE_WIN).to_itype(dbu))
    core = {}
    for cls, nets in (("INP", ["INP"]), ("INN", ["INN"]), ("switching", AFE_SW)):
        for m in SHOWN:
            r = kdb.Region()
            for n in nets:
                ln = alvs.xref().other_net_for(anames[n]) if n in anames else None
                if ln is not None:
                    r += alvs.shapes_of_net(ln, alvs.layer_by_index(LAYERS[m]), True)
            core.setdefault(cls, {})[m] = boxes((r & win).merged(), dbu)
    for m in SHOWN:
        core.setdefault("other", {})[m] = boxes((alvs.layer_by_index(LAYERS[m]) & win).merged()
                                                - sum((kdb.Region([kdb.Box(*[int(round(v / dbu)) for v in b])
                                                                   for b in core[c][m]]) for c in ("INP", "INN", "switching")),
                                                      kdb.Region()), dbu)
    out["core"] = core
    out["core_switching_shapes"] = sum(len(core["switching"][m]) for m in SHOWN)
    # extracted couplings, sensitive to switching nets
    cn = caps(os.path.join(PEX, "chipnets_r12", "chipnets.spice"))
    sw = ("NCDB", "CDB", "NCDA", "CDA", "RST", "OFPH", "CIA", "CIB", "CHOP", "CHOP_OUT", "CHOP_BLANK", "AFE_RST")
    chip = collections.defaultdict(float)
    for (a, b), c in cn.items():
        for s, v in ((a, b), (b, a)):
            base = re.sub(r"_(AFE|BIAS|ADC|TM|REF|P\d+|E\d+|J\d+|DC\d+)$", "", v).replace("VCMN", "VCM").replace("VCMP", "VCM")
            if s in sw and base in SENS:
                chip[f"{base} - {s if s != 'RST' else 'RSTA'}"] += c
    out["chip_couplings"] = {k: round(v * 1e15, 2) for k, v in sorted(chip.items(), key=lambda kv: -kv[1]) if v > 1e-15}
    ac = caps(os.path.join(PEX, "afe_top_c_r13", "afe_top_pex.spice"))
    afe = {}
    for p, n in (("INP", "INN"), ("WP", "WN"), ("OPI", "ONI"), ("OUTP", "OUTN"), ("ELP", "ELN")):
        for s in AFE_SW:
            a, b = ac.get(tuple(sorted((p, s))), 0), ac.get(tuple(sorted((n, s))), 0)
            if max(a, b) > 1e-15:
                afe[f"{p}/{n} - {s}"] = [round(a * 1e15, 2), round(b * 1e15, 2)]
    out["afe_couplings"] = afe
    # VCM / VBCM at the AFE's pins around the largest VCM excursion of r12's typical start-up run
    vec = ("qo qa qip qin avdd_afei avss_afei avdd_bias avss_bias dvddc dvssc vcm_afe vcm_p9 vrefp_adc vrefn_adc "
           "vbn_bias vbn_afe vbcm_afe bln_afe blp_afe").split()
    x = np.fromfile(os.path.join(RUN, "tr.csv"), sep=" ")
    x = x.reshape(-1, 64)
    t = x[:, 0]
    col = {n: x[:, 2 * i + 1] for i, n in enumerate(vec)}
    sel = (t > 20e-3) & (t < 26e-3)
    i0 = np.flatnonzero(sel)[np.argmax(np.abs(col["vcm_afe"][sel] - np.median(col["vcm_afe"][sel])))]
    k = slice(i0 - 10, i0 + 31)
    out["spike"] = {"t_us": [round((v - t[i0]) * 1e6, 3) for v in t[k]],
                    **{n: [round((v - np.median(col[n][sel])) * 1e3, 4) for v in col[n][k]]
                       for n in ("vcm_afe", "vcm_p9", "vbcm_afe", "blp_afe")},
                    "pp_mV": {n: round(float(np.ptp(col[n][sel])) * 1e3, 2) for n in ("vcm_afe", "vcm_p9", "vbcm_afe", "blp_afe")},
                    "t0_ms": round(float(t[i0]) * 1e3, 4)}
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(out, open(DATA, "w"))
    print("wrote", DATA, f"({os.path.getsize(DATA) / 1e6:.1f} MB); core switching shapes {out['core_switching_shapes']}")
    print("chip couplings", out["chip_couplings"])


def plot():
    sys.path.insert(0, HERE)
    import vizstyle as V
    V.CHIP, V.CHIP_DATE, V.CHIP_LABEL = "r13", "20261119", "Chip r13 (thirteenth assembly, 19 Nov 2026)"
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Rectangle
    d = json.load(open(DATA))
    COL = {"sensitive": "#2563eb", "chopper clocks": V.BAD, "clocks and data": "#d97706", "static controls": "#9333ea",
           "shield": "#15803d", "other": "#94a3b8", "INP": "#2563eb", "INN": "#0891b2", "switching": V.BAD}
    ALPHA = {"metal2": 0.95, "metal3": 0.85, "metal4": 0.6, "metal5": 0.3}

    def draw(ax, bxs, color, m, lw=0.0, alpha=None):
        if not bxs:
            return
        polys = [[(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])] for b in bxs]
        ax.add_collection(PolyCollection(polys, facecolors=color, edgecolors=color, linewidths=lw,
                                         alpha=ALPHA[m] if alpha is None else alpha))

    def cls_of(n):
        for c, nets in (("sensitive", SENS), ("chopper clocks", CHOP), ("clocks and data", DIG),
                        ("static controls", STATIC), ("shield", SHIELD)):
            if n in nets:
                return c
        return "other"
    fig = V.figure(14.0, 16.4, "Clock and data lines near the sensitive nets (visual check, r13)",
                   "Every chip-level net by class over the die (the digital macros left out), the channel south and "
                   "east of the AFE where the output chopper's clock NCDB runs next to VCM and VBCM, the amplifier "
                   "core with r13's summing-node straps, what that coupling does at the AFE's pins, and the extracted "
                   "couplings of sensitive to switching nets.",
                   "Layout: the core LVS database of r13 (runs/chip_top/eeg_core.lvsdb, die coordinates) and afe_top's "
                   "(r13); chip-level nets include their parts inside the blocks. Couplings: Magic, the chip wiring "
                   "pex/runs/chipnets_r12 (outside afe_top r13 is r12 by XOR) and the AFE runs/afe_top_c_r13 (same "
                   "values as r12). Waveforms: r12's typical start-up deck (chip wiring with these couplings, 100 ns "
                   "points), around the largest VCM excursion after 20 ms.")
    gs = fig.add_gridspec(4, 3, height_ratios=[1.0, 1.0, 1.05, 0.95])
    # (a) overview
    ax = fig.add_subplot(gs[0:2, 0:2])
    for cls in ("static controls", "clocks and data", "chopper clocks", "sensitive"):
        for m in SHOWN:
            draw(ax, d["overview"][cls][m], COL[cls], m, lw=0.45, alpha=0.9)
    for name, (x1, y1, x2, y2) in d["blocks"].items():
        dig = name in MACROS
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=dig, facecolor="#f1f5f9", edgecolor=V.MUTED,
                               linewidth=0.8, linestyle="-" if name in ("afe_top", "adc_top") else ":", zorder=0))
        if name in ("afe_top", "adc_top", "eeg_bias", "eeg_ref", "eeg_digital_top", "eeg_adc_dig", "AFE core",
                    "quantizer", "AFE clock driver"):
            ax.text(x1 + 6, y2 - 8 if name not in ("eeg_bias", "eeg_ref") else y1 - 10, name, fontsize=7.6,
                    color=V.INK2, va="top", ha="left", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75))
    for key, (x1, y1, x2, y2) in d["windows"].items():
        lab = "b" if key == "south" else "c"
        ax.add_patch(Rectangle((x1 - 6, y1 - 6), x2 - x1 + 12, y2 - y1 + 12, fill=False, edgecolor=V.INK, linewidth=1.2, zorder=6))
        ax.text(x2 + 10, y2 + 10, lab, fontsize=10, fontweight="semibold", color=V.INK, zorder=6)
    cx1, cy1, cx2, cy2 = d["core_win"]
    ax.add_patch(Rectangle((cx1, cy1), cx2 - cx1, cy2 - cy1, fill=False, edgecolor=V.INK, linewidth=1.2, zorder=6))
    ax.text(cx2 - 30, cy1 + 15, "d", fontsize=10, fontweight="semibold", color=V.INK, zorder=6)
    ax.annotate("NCDB next to VCM, 1.1 mm (b)", xy=(1300, 536), xytext=(640, 290), fontsize=8, color=V.INK2,
                arrowprops=dict(arrowstyle="-", color=V.INK2, lw=0.7))
    ax.annotate("NCDB next to VBCM, 0.6 mm (c)", xy=(1590, 800), xytext=(1660, 290), fontsize=8, color=V.INK2,
                arrowprops=dict(arrowstyle="-", color=V.INK2, lw=0.7))
    for (x, y), txt, (tx, ty) in MARKS:
        ax.plot([x], [y], marker="o", markersize=9, markerfacecolor="none", markeredgecolor=V.INK, markeredgewidth=1.1,
                zorder=7)
        ax.annotate(txt, xy=(x, y), xytext=(tx, ty), fontsize=7.6, color=V.INK2, zorder=7,
                    arrowprops=dict(arrowstyle="-", color=V.INK2, lw=0.6))
    ax.set_xlim(380, 3560)
    ax.set_ylim(240, 2110)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.set_title("(a) The die: chip-level nets by class (Metal2-5), the digital macros greyed", fontsize=10)
    hs = [Rectangle((0, 0), 1, 1, facecolor=COL[c]) for c in ("sensitive", "chopper clocks", "clocks and data", "static controls")]
    ax.legend(hs, ["sensitive analog (inputs, VCM, biases, references, OUTP/N)", "the AFE's chopper clocks",
                   "other clocks and data (MCLK, SEL, TH, strobe, SPI, resets)", "static controls (trims, offset DAC, test)"],
              loc="upper left", bbox_to_anchor=(0.0, -0.075), fontsize=7.8, ncol=2)
    # (b), (c) the channel windows
    for i, key in enumerate(("south", "east")):
        ax = fig.add_subplot(gs[i, 2])
        x1, y1, x2, y2 = d["windows"][key]
        labels = []
        for n, ms in d["zoom"][key].items():
            c = cls_of(n)
            for m in SHOWN:
                draw(ax, ms.get(m, []), COL[c], m, lw=0.0, alpha=ALPHA[m] if c != "other" else ALPHA[m] * 0.45)
            if c != "other":
                big = max((b for m in ms for b in ms[m]), key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                labels.append((n, c, big, max(ms, key=lambda m: sum((b[2] - b[0]) * (b[3] - b[1]) for b in ms[m]))))
        for n, c, b, m in labels:
            if key == "south" and b[2] - b[0] > 10:
                ax.text(x2 + 0.3, (b[1] + b[3]) / 2, f"{n} ({m[-1]})", fontsize=6.4, color=COL[c], va="center", ha="left",
                        clip_on=False)
            elif key == "east" and b[3] - b[1] > 10:
                ax.text((b[0] + b[2]) / 2, y2 + 0.3, f"{n} ({m[-1]})", fontsize=6.4, color=COL[c], va="bottom", ha="center",
                        rotation=90, clip_on=False)
        ax.set_xlim(x1, x2)
        ax.set_ylim(y1, y2)
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_xlabel("x (um)")
        ax.set_ylabel("y (um)")
        ax.set_title("(b) South of the AFE: the chip-level bus (labels: net and metal)" if key == "south" else
                     "(c) East of the AFE, between it and the ADC", fontsize=9.5, pad=40 if key == "east" else 8)
    # (d) the amplifier core
    ax = fig.add_subplot(gs[2, 0])
    ox, oy = AFE_ORIGIN
    for cls in ("other", "INP", "INN", "switching"):
        for m in SHOWN:
            bx = [[b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy] for b in d["core"][cls][m]]
            draw(ax, bx, COL[cls], m, lw=0.0, alpha=ALPHA[m] * (0.35 if cls == "other" else 1.0))
    cx1, cy1, cx2, cy2 = d["core_win"]
    ax.set_xlim(cx1, cx2)
    ax.set_ylim(cy1, cy2)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.set_title(f"(d) The amplifier core, r13: INP / INN straps; switching nets: {d['core_switching_shapes']} shapes",
                 fontsize=9.5)
    hs = [Rectangle((0, 0), 1, 1, facecolor=COL[c], alpha=0.8) for c in ("INP", "INN", "switching", "other")]
    ax.legend(hs, ["INP", "INN", "any switching net", "other nets"], loc="upper left", bbox_to_anchor=(0.0, -0.13),
              ncol=4, fontsize=7.8)
    # (e) VCM / VBCM at the AFE's pins around one output chopper edge
    ax = fig.add_subplot(gs[2, 1:3])
    s = d["spike"]
    for n, c, lab in (("vcm_afe", "#2563eb", "VCM at the AFE"), ("vbcm_afe", "#0891b2", "VBCM at the AFE"),
                      ("blp_afe", "#7c3aed", "BLP at the AFE"), ("vcm_p9", V.MUTED, "VCM at its pad")):
        ax.plot(s["t_us"], s[n], marker="o", markersize=3, lw=1.3, color=c,
                label=f"{lab} (p-p over 20-26 ms: {s['pp_mV'][n]:.1f} mV)")
    ax.axhline(0, color=V.HAIR, lw=0.8)
    ax.set_xlabel(f"time from the largest VCM excursion after 20 ms (us; at {s['t0_ms']:.4f} ms)")
    ax.set_ylabel("deviation from the median (mV)")
    ax.set_title("(e) What the coupling does at the AFE's pins: a spike at each NCDB edge, gone within about 0.3 us",
                 fontsize=9.5)
    ax.legend(loc="upper right", fontsize=8)
    # (f) the extracted couplings
    ax = fig.add_subplot(gs[3, :])
    chip = list(d["chip_couplings"].items())[:8]
    afe = sorted(d["afe_couplings"].items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))[:8]
    labs = [k for k, _ in chip] + [f"{k}  (P / N)" for k, _ in afe]
    vals = [v for _, v in chip] + [abs(v[1] - v[0]) for _, v in afe]
    cols = [V.ACCENT] * len(chip) + ["#0891b2"] * len(afe)
    y = range(len(labs))
    ax.barh(list(y), vals, color=cols, height=0.62)
    for k, (l, v) in enumerate(zip(labs, vals)):
        txt = f"{v:.1f} fF" if k < len(chip) else f"{v:.2f} fF ({afe[k - len(chip)][1][0]:.2f} / {afe[k - len(chip)][1][1]:.2f})"
        ax.text(v + 0.8, k, txt, va="center", fontsize=7.6, color=V.INK2)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labs, fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.25)
    ax.set_xlabel("extracted coupling (fF): chip wiring, one net to one clock (purple); inside the AFE, "
                  "|N - P| of a differential pair to one clock (teal)")
    ax.set_title("(f) Sensitive to switching nets: the largest chip-level couplings and the largest P / N differences "
                 "inside the AFE", fontsize=9.5)
    out = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"gf180_viz_{V.CHIP}_48_clock_lines.png")
    fig.savefig(path)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["extract", "plot"])
    a = ap.parse_args()
    extract() if a.what == "extract" else plot()


if __name__ == "__main__":
    main()

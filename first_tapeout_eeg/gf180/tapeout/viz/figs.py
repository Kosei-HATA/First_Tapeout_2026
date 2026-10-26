#!/usr/bin/env python3
"""Static figures of the final GF180 EEG chip: floorplan with routing, routing by layer and
net class, blocks, noise and distortion performance, AFE/ADC layout comparisons,
verification, pads and schedule. Data (data/): the CSV files and routing renders made by
extract.py from the final GDS and the core LVS database, and hand-entered CSVs that restate
recorded values (budget, afe_noise, wiring_r, afe_metrics, adc_metrics, distortion, density,
checks, schedule: documentation/gf180_pex_20261023.md, gf180_adc_d6_fix_20261023.md,
gf180_chip_assembly_20261023.md, gf180_tapeout_tracker.md).

usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/figs.py gf180/tapeout/viz/data documentation/figures/gf180/r6_20261026/viz [names]
       (the chip version, r6, is set in vizstyle.py: file names gf180_viz_<chip>_NN_*.png)"""
import csv
import datetime as dt
import math
import os
import sys

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vizstyle import ACCENT, BAD, CHIP, CHIP_DATE, HAIR, INK, INK2, LIGHT, MUTED, OK, WARN, figure  # noqa: E402

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PREFIX = f"gf180_viz_{CHIP}_"
STAMP = f"Chip {CHIP}"

# net-class palette (checked for colour-vision deficiency separation in this order)
PAL = {"Supply": "#ea580c", "Ground": "#4f46e5", "Electrode input": "#e11d48", "AFE output": "#0d9488",
       "Reference and bias": "#9333ea", "Clocks and phases": "#d97706", "Digital control": "#0284c7",
       "Digital I/O": "#16a34a", "Block-internal": "#cbd5e1", "Unused": "#e2e8f0"}
CLASSES = ["Supply", "Ground", "Electrode input", "AFE output", "Reference and bias", "Clocks and phases",
           "Digital control", "Digital I/O", "Block-internal"]
LAYERS = ["Metal1", "Metal2", "Metal3", "Metal4", "Metal5"]
VER = {"Schematic": INK2, "Extracted 10/23": LIGHT, "Final": ACCENT}



def load(name):
    with open(os.path.join(DATA, name + ".csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(x):
    return float(x) if x not in ("", None) else float("nan")


def save(fig, name):
    path = os.path.join(OUT, PREFIX + name + ".png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", os.path.basename(path))


def transparent(path, ink=None):
    """Render with white made transparent (and optionally recoloured)."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0
    white = a.min(axis=2)
    alpha = np.clip((1.0 - white) * 1.6, 0, 1)
    rgb = a.copy()
    if ink is not None:
        c = np.array(mpl.colors.to_rgb(ink))
        rgb[:] = c
    out = np.dstack([rgb, alpha])
    return out


def fmt_um(x, _):
    return f"{x:,.0f}"


def padclass(sig):
    if sig.startswith(("AVDD", "DVDD")):
        return "Supply"
    if sig.startswith(("AVSS", "DVSS")):
        return "Ground"
    if sig.startswith(("ELP", "ELN")):
        return "Electrode input"
    if sig.startswith(("VCM", "VREFP", "VREFN", "ATP")):
        return "Reference and bias"
    if sig == "unused":
        return "Unused"
    return "Digital I/O"


BLOCKS = load("blocks")
DIE = next(b for b in BLOCKS if b["block"] == "Pad ring")
DW, DH = num(DIE["width_um"]), num(DIE["height_um"])
INNER = [b for b in BLOCKS if b["block"] != "Pad ring"]


def die_axes(ax, pad=40):
    ax.set_xlim(-pad, DW + pad)
    ax.set_ylim(-pad, DH + pad)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(500))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(fmt_um))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_um))
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    ax.add_patch(Rectangle((0, 0), DW, DH, fill=False, ec=INK2, lw=0.8, zorder=1))


def draw_pads(ax, alpha_used=0.38, labels=False, fs=6.5):
    for p in load("pads"):
        k = padclass(p["signal"])
        x0, y0, x1, y1 = (num(p[c]) for c in ("x0", "y0", "x1", "y1"))
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=PAL[k], ec="white", lw=0.4,
                               alpha=0.55 if k == "Unused" else alpha_used, zorder=1.5))
        if labels and k != "Unused":
            name = p["signal"].split(" (")[0]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            ax.text(cx, cy, name, ha="center", va="center", fontsize=fs, color="white", fontweight="medium", zorder=5,
                    rotation=90 if p["side"] in ("north", "south") else 0)


LABEL = {"AFE": ("AFE", "c"), "ADC": ("ADC", "c"), "Digital controller": ("Digital\ncontroller", "c"),
         "DVDD decoupling": ("DVDD decoupling", "c"), "AVDD decoupling": ("AVDD decoupling", "v"),
         "Bias generator": ("Bias generator", "c"), "Reference filter": ("Reference filter", "c"),
         "Test multiplexer": ("Test multiplexer", "out")}


def draw_blocks(ax, sizes=True, lw=0.9, ec=INK2, fs=10):
    for b in INNER:
        x0, y0, x1, y1 = (num(b[c]) for c in ("x0", "y0", "x1", "y1"))
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=ec, lw=lw, zorder=3))
        text, mode = LABEL.get(b["block"], (b["block"], "c"))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        big = b["block"] in ("AFE", "ADC", "Digital controller")
        if mode == "c":
            ax.text(cx, cy + (60 if big and sizes else 0), text, ha="center", va="center", zorder=4,
                    fontsize=fs + 1 if big else fs - 2.5, fontweight="medium" if big else "regular", color=INK,
                    bbox=dict(fc="white", ec="none", alpha=0.88, pad=1.5))
            if big and sizes:
                ax.text(cx, cy - 75, f"{num(b['width_um']):,.0f} × {num(b['height_um']):,.0f} µm", ha="center",
                        va="center", fontsize=fs - 2, color=MUTED, zorder=4, bbox=dict(fc="white", ec="none", alpha=0.88, pad=1.2))
        elif mode == "v":
            ax.text(cx, cy, text, ha="center", va="center", rotation=90, fontsize=fs - 2.5, color=INK, zorder=4,
                    bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2))
        else:
            ax.annotate(text, xy=(x1, y1), xytext=(x1 + 170, y1 + 120), fontsize=fs - 2.5, color=INK, zorder=4,
                        ha="left", va="center", bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.2),
                        arrowprops=dict(arrowstyle="-", color=INK2, lw=0.7, shrinkA=0, shrinkB=0))


# ---------------------------------------------------------------------------------------------
def fig_floorplan():
    routing = load("routing")
    area = {k: 0.0 for k in CLASSES}
    for r in routing:
        area[r["net_class"]] += num(r["top_level_area_um2"]) / 1e6
    fig = figure(12.6, 9.6, "Floorplan and top-level routing",
                 f"{STAMP} · die {DW:,.0f} × {DH:,.0f} µm · top-cell metal coloured by the schematic net it carries (core LVS)",
                 note="Wires are drawn at true width: 0.38 µm signal wires appear as hairlines. Block interiors are not drawn. "
                      "Pad cells are tinted by function in the same colours.")
    ax = fig.add_subplot()
    die_axes(ax)
    draw_pads(ax)
    ax.imshow(transparent(os.path.join(DATA, "route_class_hi.png")), extent=(0, DW, 0, DH), origin="upper",
              interpolation="antialiased", zorder=2)
    draw_blocks(ax)
    handles = [Patch(fc=PAL[k], ec="none", label=f"{k}  {area[k]:.3g} mm²") for k in CLASSES]
    handles.append(Patch(fc=PAL["Unused"], ec="none", alpha=0.55, label="Unused pad"))
    ax.legend(handles=handles, ncols=5, loc="upper center", bbox_to_anchor=(0.5, -0.07), handlelength=1.1,
              handleheight=1.1, columnspacing=1.6, title="Top-cell metal area by net class", title_fontsize=8.5,
              alignment="left")
    save(fig, "01_floorplan_routing")


def fig_layers():
    by = {l: 0.0 for l in LAYERS}
    for r in load("routing"):
        by[r["layer"]] += num(r["top_level_area_um2"]) / 1e6
    vias = {r["via_layer"]: int(r["top_level_cuts"]) for r in load("vias")}
    below = {"Metal2": "Via1", "Metal3": "Via2", "Metal4": "Via3", "Metal5": "Via4"}
    role = {"Metal1": "taps and local jumpers", "Metal2": "pin stubs, pad bars", "Metal3": "vertical signal tracks",
            "Metal4": "horizontal signal tracks, jumpers", "Metal5": "supply and ground straps, electrodes"}
    fig = figure(12.6, 7.4, "Top-level metal, one layer at a time",
                 f"{STAMP} · top-cell metal only, same scale in every panel; block outlines for orientation")
    axs = fig.subplots(2, 3)
    for i, l in enumerate(LAYERS):
        ax = axs.flat[i]
        die_axes(ax, pad=20)
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.tick_params(labelsize=7)
        for b in INNER:
            x0, y0, x1, y1 = (num(b[c]) for c in ("x0", "y0", "x1", "y1"))
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#f1f5f9", ec="#cbd5e1", lw=0.5, zorder=1))
        ax.imshow(transparent(os.path.join(DATA, f"route_{l}_hi.png"), ink=INK2), extent=(0, DW, 0, DH),
                  origin="upper", interpolation="antialiased", zorder=2)
        v = f" · {below[l]} {vias[below[l]]:,} cuts" if l in below else ""
        ax.set_title(f"{l}  ·  {by[l]:.3g} mm²{v}", fontsize=9.5)
        ax.text(0.0, -0.13, role[l], transform=ax.transAxes, fontsize=8, color=MUTED, ha="left", va="top")
    ax = axs.flat[5]
    for j, l in enumerate(LAYERS[::-1]):
        ax.axhline(j, color=HAIR, lw=0.8, zorder=1)
        ax.scatter([by[l]], [j], s=55, color=ACCENT, zorder=3)
        ax.text(by[l] * 1.45, j, f"{by[l]:.3g}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(LAYERS)), LAYERS[::-1])
    ax.set_ylim(-0.6, len(LAYERS) - 0.4)
    ax.set_xscale("log")
    ax.set_xlim(1e-4, 3)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("Top-cell metal area (mm², log)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Area per layer", fontsize=9.5)
    save(fig, "02_routing_layers")


def fig_matrix():
    routing = load("routing")
    m = np.zeros((len(CLASSES), len(LAYERS)))
    for r in routing:
        m[CLASSES.index(r["net_class"]), LAYERS.index(r["layer"])] = num(r["top_level_area_um2"])
    tot = m.sum(axis=1)
    fig = figure(9.6, 5.6, "Top-level metal by net class and layer",
                 f"{STAMP} · area of top-cell metal in µm²; colour is logarithmic", note="Metal1 carries almost nothing at the top level; "
                 "the router uses Metal3 (vertical) and Metal4 (horizontal), the straps Metal5.")
    ax = fig.add_subplot()
    cmap = LinearSegmentedColormap.from_list("ind", ["#eef2ff", "#a5b4fc", "#4f46e5", "#1e1b4b"])
    full = np.column_stack([m, tot])
    vals = full[full > 0]
    norm = LogNorm(vmin=vals.min(), vmax=vals.max())
    shown = np.where(full > 0, full, np.nan)
    im = ax.imshow(shown, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(LAYERS) + 1), LAYERS + ["Total"])
    ax.set_yticks(range(len(CLASSES)), CLASSES)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", pad=16)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axvline(len(LAYERS) - 0.5, color="white", lw=3)
    for i in range(len(CLASSES)):
        for j in range(len(LAYERS) + 1):
            v = full[i, j]
            t = "–" if v <= 0 else (f"{v:,.0f}" if v >= 10 else f"{v:.2g}")
            dark = v > 0 and norm(v) > 0.55
            ax.text(j, i, t, ha="center", va="center", fontsize=8.5, color="white" if dark else INK)
    for i, k in enumerate(CLASSES):
        ax.add_patch(Rectangle((-0.6, i - 0.3), 0.05, 0.6, fc=PAL[k], ec="none", clip_on=False, transform=ax.transData))
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("µm² (log)")
    cb.outline.set_visible(False)
    save(fig, "03_routing_matrix")


def fig_nets():
    nets = sorted(load("nets"), key=lambda r: -num(r["span_mm"]))[:22]
    fig = figure(9.6, 6.8, "Longest top-level nets",
                 f"{STAMP} · span = half-perimeter of the bounding box of a net's top-cell metal, a lower bound on its routed length")
    ax = fig.add_subplot()
    y = np.arange(len(nets))[::-1]
    ax.barh(y, [num(n["span_mm"]) for n in nets], color=[PAL[n["net_class"]] for n in nets], height=0.62)
    ax.set_yticks(y, [n["net"] for n in nets])
    for yi, n in zip(y, nets):
        ax.text(num(n["span_mm"]) + 0.04, yi, f"{num(n['span_mm']):.2f}", va="center", fontsize=8, color=INK2)
    ax.set_xlabel("Span (mm)")
    ax.set_xlim(0, max(num(n["span_mm"]) for n in nets) * 1.1)
    ax.grid(axis="y", visible=False)
    used = [k for k in CLASSES if any(n["net_class"] == k for n in nets)]
    ax.legend(handles=[Patch(fc=PAL[k], label=k) for k in used], loc="lower right", handlelength=1, handleheight=1)
    save(fig, "04_longest_nets")


def block_rows():
    devices = load("devices")
    rows = []
    for b in INNER:
        ds = [d for d in devices if d["block"] == b["block"]]
        s = lambda f, pre: sum(num(d[f]) for d in ds if d["device"].startswith(pre))  # noqa: E731
        rows.append(dict(block=b["block"], w=num(b["width_um"]), h=num(b["height_um"]), area=num(b["area_mm2"]),
                         cells=int(b["instances"]), fets=int(sum(num(d["count"]) for d in ds if "fet" in d["device"])),
                         mim=s("capacitance_pF", "cap_mim"), mos=s("capacitance_pF", "cap_nmos") + s("capacitance_pF", "cap_pmos"),
                         res=s("resistance_kohm", "ppoly")))
    return rows, devices


def fig_blocks():
    rows, devices = block_rows()
    fig = figure(13.2, 5.4, "Blocks",
                 f"{STAMP} · outlines from the GDS; devices from the core LVS netlist after parallel combining, assigned by position",
                 note="MIM capacitance estimated from area and perimeter (1.99 fF/µm², 0.238 fF/µm). The digital blocks use the 5 V "
                      "standard-cell library at a 3.3 V supply.")
    a1, a2, a3 = fig.subplots(1, 3, width_ratios=[1, 1.15, 1])
    names = [r["block"] for r in rows][::-1]
    y = np.arange(len(rows))
    rr = rows[::-1]
    a1.barh(y, [r["area"] for r in rr], color=ACCENT, height=0.6)
    a1.set_yticks(y, names)
    for yi, r in zip(y, rr):
        a1.text(r["area"] + 0.03, yi, f"{r['area']:.3g} mm²  ({100 * r['area'] / (DW * DH / 1e6):.1f} %)", va="center", fontsize=7.8, color=INK2)
    a1.set_xlim(0, 2.6)
    a1.set_xlabel("Outline area (mm²)")
    a1.set_title("Area, and share of the die")
    a1.grid(axis="y", visible=False)
    for a in (a1, a2, a3):
        a.set_ylim(-0.6, len(rows) - 0.4)
    types = [("nfet_03v3", "NMOS 3.3 V", "#0284c7"), ("pfet_03v3", "PMOS 3.3 V", "#ea580c"),
             ("nfet_05v0", "NMOS 5 V", "#0d9488"), ("pfet_05v0", "PMOS 5 V", "#9333ea")]
    for i, (t, lab, c) in enumerate(types):
        xs, ys = [], []
        for yi, r in zip(y, rr):
            d = next((d for d in devices if d["block"] == r["block"] and d["device"] == t), None)
            if d:
                xs.append(num(d["count"]))
                ys.append(yi + (i - 1.5) * 0.12)
        a2.scatter(xs, ys, s=30, color=c, label=lab, zorder=3, edgecolor="white", linewidth=0.6)
    a2.set_xscale("log")
    a2.set_xlim(1, 2e5)
    a2.set_yticks(y, ["" for _ in y])
    a2.set_xlabel("Transistors (log)")
    a2.set_title("Transistors by type")
    a2.legend(loc="lower right", ncols=2, handletextpad=0.3, columnspacing=1.0)
    for yi in y:
        a2.axhline(yi, color=HAIR, lw=0.6, zorder=1)
    a2.grid(axis="y", visible=False)
    a3.barh(y, [r["mim"] for r in rr], color=ACCENT, height=0.6, label="MIM")
    a3.barh(y, [r["mos"] for r in rr], left=[r["mim"] for r in rr], color="#0d9488", height=0.6, label="MOS")
    for yi, r in zip(y, rr):
        tot = r["mim"] + r["mos"]
        if tot > 0:
            a3.text(tot + 20, yi, f"{tot:,.0f} pF", va="center", fontsize=7.8, color=INK2)
    a3.set_yticks(y, ["" for _ in y])
    a3.set_xlim(0, 1900)
    a3.set_xlabel("Capacitance (pF)")
    a3.set_title("On-chip capacitance")
    a3.legend(loc="lower right", handlelength=1, handleheight=1)
    a3.grid(axis="y", visible=False)
    save(fig, "05_blocks")


def table_fig(name, title, sub, cols, rows, widths, note=None, colours=None, h_row=0.34, w=13.2):
    h = 1.25 + h_row * (len(rows) + 1) + (0.35 if note else 0)
    fig = figure(w, h, title, sub, note=note)
    ax = fig.add_subplot()
    ax.axis("off")
    tb = ax.table(cellText=rows, colLabels=cols, colWidths=widths, loc="upper left", cellLoc="left", colLoc="left",
                  bbox=(0, 0, 1, 1))
    tb.auto_set_font_size(False)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor(HAIR)
        cell.visible_edges = "B"
        cell.PAD = 0.02
        txt = cell.get_text()
        txt.set_fontsize(8.6)
        if r == 0:
            txt.set_color(MUTED)
            txt.set_fontweight("medium")
            cell.set_edgecolor("#cbd5e1")
        else:
            txt.set_color(INK)
            if colours and (r - 1, c) in colours:
                txt.set_color(colours[(r - 1, c)])
                txt.set_fontweight("medium")
        if cols[c].endswith(")") or cols[c] in ("Instances", "Transistors", "Violations", "Position"):
            txt.set_ha("right")
            cell._loc = "right"
    save(fig, name)


def fig_block_table():
    rows, _ = block_rows()
    body = [[r["block"], f"{r['w']:,.0f} × {r['h']:,.0f}", f"{r['area']:.3f}", f"{r['cells']:,}", f"{r['fets']:,}" if r["fets"] else "–",
             f"{r['mim']:,.1f}" if r["mim"] else "–", f"{r['mos']:,.1f}" if r["mos"] else "–", f"{r['res']:,.1f}" if r["res"] else "–"]
            for r in rows]
    table_fig("06_block_table", "Block summary",
              f"{STAMP} · devices after LVS parallel combining, assigned to blocks by position",
              ["Block", "Size (µm)", "Area (mm²)", "Instances", "Transistors", "MIM (pF)", "MOS cap (pF)", "Poly R (kΩ)"],
              body, [0.2, 0.14, 0.1, 0.07, 0.11, 0.1, 0.12, 0.12])


# ---------------------------------------------------------------------------------------------
def fig_budget():
    b = load("budget")
    comps = [r for r in b if r["kind"] == "component"]
    target = num(next(r for r in b if r["kind"] == "target")["nvrms"])
    p = np.array([num(r["nvrms"]) ** 2 for r in comps])
    tot = math.sqrt(p.sum())
    enob = lambda n: 16.5 - math.log2(n / target)  # noqa: E731
    cols = ["#4f46e5", "#0d9488", "#d97706", "#e11d48"]
    fig = figure(12.6, 6.4, "Noise budget at the input",
                 f"Input-referred, 0.5–100 Hz, electrode thermal noise excluded · uncorrelated parts add in power · {STAMP}",
                 note=f"ENOB = 16.50 − log2(N / {target:.2f} nV rms); {target:.2f} nV rms gives SNDR 101.1 dB at 0.943 mV peak full scale. "
                      "AFE: 4.81 nV rms extracted, × 1.01 for the chopper blanking.")
    a1, a2 = fig.subplots(2, 1, height_ratios=[1.0, 1.35])
    acc = 0.0
    for r, pi, c in zip(comps, p, cols):
        a1.barh(0, pi, left=acc, color=c, height=0.5, edgecolor="white", linewidth=1.2)
        lab = f"{r['component']}\n{num(r['nvrms']):.2f} nV · {100 * pi / p.sum():.0f} %"
        if pi > 4:
            a1.text(acc + pi / 2, 0, lab, ha="center", va="center", fontsize=8, color="white")
        acc += pi
    small = [(r, pi, c) for r, pi, c in zip(comps, p, cols) if pi <= 4]
    xs = p.sum() - sum(pi for _, pi, _ in small)
    for k, (r, pi, c) in enumerate(small):
        right = k == len(small) - 1
        a1.annotate(f"{r['component']}\n{num(r['nvrms']):.2f} nV · {100 * pi / p.sum():.0f} %", xy=(xs + pi / 2, -0.26),
                    xytext=(xs + pi / 2 + (1.2 if right else -1.2), -0.66), fontsize=7.8, color=INK2,
                    ha="left" if right else "right", va="center", arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.6))
        xs += pi
    a1.axvline(target ** 2, color=INK, ls=(0, (4, 3)), lw=1)
    a1.text(target ** 2, 0.40, f"Target {target:.2f} nV rms = 16.50 bit ", ha="right", va="bottom", fontsize=8.5, color=INK)
    a1.text(p.sum(), 0.40, f"  Total {tot:.2f} nV rms = {enob(tot):.2f} bit", ha="left", va="bottom", fontsize=8.5,
            color=INK, fontweight="medium")
    a1.set_xlim(0, 46)
    a1.set_ylim(-0.95, 0.75)
    a1.set_yticks([])
    a1.set_xlabel("Noise power (nV²)")
    a1.spines["left"].set_visible(False)
    a1.set_title("Where the noise power goes")
    gains = []
    for i, r in enumerate(comps):
        rest = math.sqrt(p.sum() - p[i])
        gains.append((r["component"], enob(rest) - enob(tot), cols[i]))
    yy = np.arange(len(gains))[::-1]
    a2.barh(yy, [g for _, g, _ in gains], color=[c for _, _, c in gains], height=0.55)
    a2.set_yticks(yy, [n for n, _, _ in gains])
    for yi, (_, g, _) in zip(yy, gains):
        a2.text(g + 0.012, yi, f"+{g:.3f} bit", va="center", fontsize=8, color=INK2)
    a2.set_xlim(0, 0.9)
    a2.set_xlabel("ENOB gained if this contribution were removed (bit)")
    a2.set_title(f"What each contribution costs (predicted {enob(tot):.2f} bit, target 16.50 bit)")
    a2.grid(axis="y", visible=False)
    save(fig, "07_noise_budget")


def fig_afe_noise():
    d = load("afe_noise")
    fig = figure(10.0, 4.8, "AFE noise through extraction",
                 "Chopped noise estimate, input-referred (nV rms); thermal and 1/f add in power to the total",
                 note="Harmonic-sum gain 287.3 V/V in the schematic, 284.8 V/V extracted. The rise comes from the larger input-node capacitance and, in the "
                      "last row, the input-path wiring, which the budget books as its own line.")
    ax = fig.add_subplot()
    y = np.arange(len(d))[::-1]
    for yi, r in zip(y, d):
        ax.plot([num(r["flicker_nvrms"]), num(r["total_nvrms"])], [yi, yi], color=HAIR, lw=2, zorder=1)
    ax.scatter([num(r["thermal_nvrms"]) for r in d], y, s=42, facecolor="white", edgecolor="#0d9488", linewidth=1.6, label="Thermal", zorder=3)
    ax.scatter([num(r["flicker_nvrms"]) for r in d], y, s=42, marker="D", facecolor="white", edgecolor="#d97706", linewidth=1.6, label="1/f", zorder=3)
    ax.scatter([num(r["total_nvrms"]) for r in d], y, s=60, color=ACCENT, label="Total", zorder=4)
    for yi, r in zip(y, d):
        v = num(r["total_nvrms"])
        ax.text(v + (0.03 if v > 5.0 else 0), yi + 0.2, f"{v:.2f}", ha="left" if v > 5.0 else "center", va="bottom", fontsize=8.5, color=INK)
    ax.axvline(5.0, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.text(5.0, len(d) - 0.45, " AFE allocation 5.0 nV rms", fontsize=8, color=BAD, va="center")
    ax.set_yticks(y, [r["version"] for r in d])
    ax.set_xlim(0, 6)
    ax.set_ylim(-0.6, len(d) - 0.2)
    ax.set_xlabel("Noise (nV rms)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper left", ncols=3)
    save(fig, "08_afe_noise")


def fig_rwire():
    w = load("wiring_r")
    secs = list(dict.fromkeys(r["section"] for r in w))
    vers = ["10/23 extraction", "Final layout"]
    vc = {"10/23 extraction": LIGHT, "Final layout": ACCENT}
    groups = []
    for s in secs:
        for side in ("P", "N"):
            groups.append((f"{s.split(':')[0]} · {side}", [num(next(r["ohm"] for r in w if r["section"] == s and r["side"] == side and r["version"] == v)) for v in vers]))
    for side in ("P", "N"):
        groups.append((f"Total · {side}", [sum(num(r["ohm"]) for r in w if r["side"] == side and r["version"] == v) for v in vers]))
    fig = figure(11.0, 6.4, "AFE input-path wiring resistance",
                 "Noise-equivalent series resistance per side (Ω, log): E pad to chopper · W chopper to the Cin bottom plate · "
                 "T Cin top plate to the input-pair gates",
                 note="T was set by the auto-routed gate wiring of the input pair (0.38 µm wires, single vias) before the D6 fixes. "
                      "The per-side target for 16.50 bit is 0.35 Ω.")
    ax = fig.add_subplot()
    n = len(groups)
    y = np.arange(n)[::-1] * 1.0
    for yi, g in zip(y, groups):
        ax.plot(g[1], [yi, yi], color=HAIR, lw=2, zorder=1)
        for val in g[1]:
            ax.text(val, yi + 0.2, f"{val:.3g} Ω", ha="center", va="bottom", fontsize=7.8, color=INK2)
    ax.scatter([g[1][0] for g in groups], y, s=48, facecolor="white", edgecolor=LIGHT, linewidth=1.6, label=vers[0], zorder=3)
    ax.scatter([g[1][1] for g in groups], y, s=55, color=ACCENT, label=vers[1], zorder=4)
    ax.set_xscale("log")
    ax.set_xlim(0.05, 500)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_yticks(y, [g[0] for g in groups])
    for i, g in enumerate(groups):
        if g[0].startswith("Total"):
            ax.plot([0.35, 0.35], [y[i] - 0.3, y[i] + 0.3], color=BAD, lw=1.6, zorder=2)
    ax.text(0.35, y[-1] - 0.75, "target 0.35 Ω", color=BAD, fontsize=8, ha="center", va="top")
    ax.axhline((y[-3] + y[-2]) / 2, color="#cbd5e1", lw=0.8)
    ax.set_xlabel("Resistance per side (Ω, log)")
    ax.set_ylim(y[-1] - 1.0, y[0] + 0.6)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper right")
    save(fig, "09_wiring_resistance")


def fig_dist():
    d = load("distortion")
    conds = list(dict.fromkeys(r["condition"] for r in d))
    vcol = {"Schematic": INK2, "Final layout": ACCENT, "Single DC path (before B7)": BAD}
    fig = figure(12.6, 5.4, "AFE distortion at full scale",
                 "Harmonic level relative to the fundamental at 0.943 mV peak (dBc); lower is better",
                 note="Left: chopped transient of the extracted AFE, FFT window 2–4 ms. Right: static transfer through the DC path "
                      "(polynomial fit), before and after the DC path was made symmetric (B7).")
    axs = fig.subplots(1, 2, sharey=True)
    harm = ["HD2", "HD3", "HD4", "HD5"]
    titles = {conds[0]: "2 kHz, chopped transient", conds[1]: "In band, static DC-path transfer"}
    for ax, c in zip(axs, conds):
        vers = list(dict.fromkeys(r["version"] for r in d if r["condition"] == c))
        for vi, v in enumerate(vers):
            off = (vi - (len(vers) - 1) / 2) * 0.22
            for hi, h in enumerate(harm):
                r = next((r for r in d if r["condition"] == c and r["version"] == v and r["harmonic"] == h), None)
                if not r:
                    continue
                val = num(r["dbc"])
                ax.plot([hi + off, hi + off], [-175, val], color=vcol[v], lw=1.6, alpha=0.45, solid_capstyle="butt")
                ax.scatter([hi + off], [val], s=44, color=vcol[v], zorder=3, edgecolor="white", linewidth=0.8,
                           label=v if hi == 0 or (h == "HD2" and v.startswith("Single")) else None)
                left = vi == 0 and len(vers) > 1          # (labels outward, clear of the neighbouring stem)
                ax.text(hi + off + (-0.06 if left else 0.06), val + 2.2, f"{val:.0f}".replace("-", "−"), fontsize=7.4, color=vcol[v],
                        ha="right" if left else "left", va="bottom")
        ax.axhline(-111, color=BAD, ls=(0, (5, 3)), lw=1)
        ax.text(3.45, -111 + 1.5, "spec ≤ −111 dBc", ha="right", va="bottom", fontsize=8, color=BAD)
        ax.set_xticks(range(4), harm)
        ax.set_xlim(-0.6, 3.6)
        ax.set_ylim(-175, -70)
        ax.set_title(titles[c])
        ax.grid(axis="x", visible=False)
        handles, labels = ax.get_legend_handles_labels()
        seen = dict(zip(labels, handles))
        ax.legend(seen.values(), seen.keys(), loc="upper left")
    axs[0].set_ylabel("Level (dBc)")
    axs[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}".replace("-", "−")))
    save(fig, "10_distortion")


def fig_metrics():
    am = {r["metric"]: r for r in load("afe_metrics")}
    dm = {r["metric"]: r for r in load("adc_metrics")}
    fig = figure(13.6, 7.6, "Schematic against layout, AFE and ADC",
                 f"Each panel compares the schematic, the 10/23 extraction (before the D6 fixes) and the extraction of {STAMP.lower()}",
                 note="AFE gain from the ±0.5 mV chopped transient (200 µs); the 70 µs end-to-end sine gives 291.45 V/V (schematic) and 291.34 V/V (final). "
                      "SNDR values are the low end of each simulated range.\nADC loop: 20 kHz, 0.3 V pk, 100 µs, evaluated over 20–100 µs "
                      "(80 frames); the final ADC includes the D6 and B4 (comparator latch) fixes.")
    axs = fig.subplots(2, 5)
    cats3 = ["Schematic", "10/23", "Final"]
    cols3 = [INK2, LIGHT, ACCENT]

    def dots(ax, vals, title, unit, ref=None, ref_label=None, ylim=None, fmt="{:.3g}", logy=False, cats=cats3, cols=cols3, right=False):
        xs = np.arange(len(vals))
        for x, v, c in zip(xs, vals, cols):
            if np.isnan(v):
                ax.text(x, 0.5, "n/a", transform=ax.get_xaxis_transform(), ha="center", va="center", fontsize=8, color=LIGHT)
                continue
            ax.scatter([x], [v], s=55, color=c, zorder=3, edgecolor="white", linewidth=0.8)
            ax.annotate(fmt.format(v).replace("-", "−"), (x, v), textcoords="offset points", xytext=(8, 0) if right else (0, 8),
                        ha="left" if right else "center", va="center" if right else "baseline", fontsize=8, color=INK)
        if logy:
            ax.set_yscale("log")
        if ref is not None:
            ax.axhline(ref, color=BAD, ls=(0, (4, 3)), lw=1)
            ax.annotate(ref_label, (-0.5, ref), textcoords="offset points", xytext=(0, 3), ha="left", va="bottom", fontsize=7.5, color=BAD)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_xticks(xs, cats, fontsize=8)
        ax.set_xlim(-0.6, len(vals) - 0.4)
        ax.set_title(title, fontsize=9.2)
        ax.set_ylabel(unit, fontsize=8.5)
        ax.grid(axis="x", visible=False)

    r = am["Chopped gain, +-0.5 mV input"]
    dots(axs[0, 0], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "AFE chopped gain", "V/V", ylim=(280, 305), fmt="{:.1f}")
    r = am["Residual offset, input-referred"]
    dots(axs[0, 1], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "AFE residual offset", "µV, input-referred", ylim=(-1, 1), fmt="{:.2f}")
    axs[0, 1].axhline(0, color=HAIR, lw=1)
    r = am["Output ripple outside blanking, p-p"]
    dots(axs[0, 2], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "AFE output ripple, p-p", "mV", ref=4, ref_label="limit 4 mV", ylim=(-2, 45), fmt="{:.3g}",
         right=True)
    ax = axs[0, 3]
    rp, rn = am["INP parasitic capacitance"], am["INN parasitic capacitance"]
    x = np.arange(2)
    ax.bar(x - 0.18, [num(rp["pex_1023"]), num(rn["pex_1023"])], width=0.34, color=LIGHT, label="10/23")
    ax.bar(x + 0.18, [num(rp["final"]), num(rn["final"])], width=0.34, color=ACCENT, label="Final")
    for xi, v in zip(list(x - 0.18) + list(x + 0.18), [num(rp["pex_1023"]), num(rn["pex_1023"]), num(rp["final"]), num(rn["final"])]):
        ax.text(xi, v + 0.5, f"{v:.3g}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, ["INP", "INN"], fontsize=8)
    ax.set_ylabel("pF", fontsize=8.5)
    ax.set_title("AFE input-node parasitic C", fontsize=9.2)
    ax.legend(loc="upper left", fontsize=7.8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 30)
    ax = axs[0, 4]
    e1, e31 = dm["DAC1 even-order error, one element"], dm["DAC1 even-order error, 31 elements"]
    for k, (row, mk, lab) in enumerate([(e1, "o", "1 element"), (e31, "s", "31 elements")]):
        vals = [abs(num(row[c])) for c in ("schematic", "pex_1023", "final")]
        ax.scatter(np.arange(3) + (k - 0.5) * 0.18, vals, s=40, marker=mk, color=cols3, zorder=3, edgecolor="white", linewidth=0.8)
    ax.scatter([], [], marker="o", color=INK2, label="1 element")
    ax.scatter([], [], marker="s", color=INK2, label="31 elements")
    ax.set_yscale("log")
    ax.set_ylim(1e-5, 3)
    ax.axhline(0.008, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate("requirement 0.008", (2.55, 0.008), textcoords="offset points", xytext=(0, 3), ha="right", va="bottom", fontsize=7.5, color=BAD)
    ax.set_xticks(range(3), cats3, fontsize=8)
    ax.set_xlim(-0.6, 2.6)
    ax.set_ylabel("|q| per switching (fC, log)", fontsize=8.5)
    ax.set_title("DAC1 even-order error", fontsize=9.2)
    ax.legend(loc="upper left", fontsize=7.6)
    ax.grid(axis="x", visible=False)
    r = dm["SNDR with DAC1 even-order error, behavioural"]
    dots(axs[1, 0], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "SNDR with DAC1 error", "dB (behavioural)",
         ref=101.1, ref_label="16.5 bit needs 101.1", ylim=(50, 185), fmt="{:.0f}")
    ax = axs[1, 1]
    cp, cn = dm["Clock CLKQ to O2P coupling"], dm["Clock CLKQ to O2N coupling"]
    ax.bar(x - 0.18, [num(cp["pex_1023"]), num(cn["pex_1023"])], width=0.34, color=LIGHT, label="10/23")
    ax.bar(x + 0.18, [num(cp["final"]), num(cn["final"])], width=0.34, color=ACCENT, label="Final")
    for xi, v in zip(list(x - 0.18) + list(x + 0.18), [num(cp["pex_1023"]), num(cn["pex_1023"]), num(cp["final"]), num(cn["final"])]):
        ax.text(xi, v + 0.6, f"{v:.3g}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, ["O2P", "O2N"], fontsize=8)
    ax.set_ylabel("fF", fontsize=8.5)
    ax.set_title("Quantizer clock coupling", fontsize=9.2)
    ax.legend(loc="upper right", fontsize=7.8)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 38)
    r = dm["Loop residual, rms"]
    dots(axs[1, 2], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "ADC loop residual", "rms (DAC1 range = 1)",
         ylim=(0, 0.06), fmt="{:.4f}")
    ax = axs[1, 3]
    lo, hi = dm["Second-integrator swing, minimum"], dm["Second-integrator swing, maximum"]
    for k, c in enumerate(("schematic", "pex_1023", "final")):
        a, b = num(lo[c]), num(hi[c])
        ax.plot([k, k], [a, b], color=cols3[k], lw=7, solid_capstyle="butt")
        ax.text(k + 0.2, a, f"{a:.1f}".replace("-", "−"), fontsize=7.5, va="center", color=INK2)
        ax.text(k + 0.2, b, f"{b:.1f}", fontsize=7.5, va="center", color=INK2)
    ax.axhspan(-46.9, 46.9, color="#f1f5f9", zorder=0)
    ax.axhline(46.9, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.axhline(-46.9, color=BAD, ls=(0, (4, 3)), lw=1)
    ax.annotate("quantizer range ±46.9", (2.55, 46.9), textcoords="offset points", xytext=(0, 3), ha="right", va="bottom", fontsize=7.5, color=BAD)
    ax.set_ylim(-60, 60)
    ax.set_xticks(range(3), cats3, fontsize=8)
    ax.set_xlim(-0.6, 2.6)
    ax.set_ylabel("mV", fontsize=8.5)
    ax.set_title("Second-integrator swing", fontsize=9.2)
    ax.grid(axis="x", visible=False)
    r = dm["Decisions at the ideal threshold"]
    dots(axs[1, 4], [num(r["schematic"]), num(r["pex_1023"]), num(r["final"])], "Decisions at the ideal threshold", "% of frames",
         ylim=(0, 110), fmt="{:.1f}")
    save(fig, "11_layout_comparison")


# ---------------------------------------------------------------------------------------------
def fig_density():
    d = load("density")
    fig = figure(9.6, 4.6, "Layer density after fill",
                 f"{STAMP} · share of the die area, from the full DRC of the filled chip",
                 note="Red ticks: global minimum, and for COMP the maximum (DCF.1b, DCF.1d, PL.8, DM.4). Dummy fill counted with drawn shapes.")
    ax = fig.add_subplot()
    y = np.arange(len(d))[::-1]
    ax.barh(y, [num(r["density_pct"]) for r in d], color=ACCENT, height=0.55)
    for yi, r in zip(y, d):
        ax.text(num(r["density_pct"]) + 1.0, yi, f"{num(r['density_pct']):.1f} %", va="center", fontsize=8.5, color=INK2)
        for lim in (r["min_pct"], r["max_pct"]):
            if lim:
                ax.plot([num(lim), num(lim)], [yi - 0.38, yi + 0.38], color=BAD, lw=2)
    ax.set_yticks(y, [r["layer"] for r in d])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Density (%)")
    ax.grid(axis="y", visible=False)
    save(fig, "12_density")


def fig_checks():
    c = load("checks")
    body, colours = [], {}
    for i, r in enumerate(c):
        res = r["result"]
        colours[(i, 3)] = OK if res in ("pass", "match") else BAD if res == "no result" else WARN
        body.append([r["check"], r["scope"], r["tool"], "● " + res, "–" if r["violations"] == "" else f"{int(num(r['violations'])):,}", r["detail"]])
    table_fig("13_checks", "Checks on the final chip",
              "DRC, LVS, wafer.space precheck, Magic and digital verification · 23–26 Oct 2026",
              ["Check", "Scope", "Tool", "Result", "Violations", "Detail"], body, [0.22, 0.15, 0.2, 0.09, 0.07, 0.27],
              note="Until 25 Oct the precheck's Magic step crashed inside Magic (a bin-index bug hit by the PDK's COMP / Poly2 fill "
                   "arrays) and LibreLane reported it as 0. Since 26 Oct those fill cells hold at most 9 instances each, and Magic runs "
                   "to the end with all fill.",
              colours=colours, h_row=0.33, w=15.0)


def fig_pads():
    fig = figure(12.6, 9.0, "Pad ring",
                 f"{STAMP} · {len(load('pads'))} pad cells at their positions on the die, coloured by function; core blocks shown faint",
                 note="Unused positions are analog pads (asig_5p0) with no connection. Multiple AVDD, AVSS, ELP and ELN pads are tied in the core.")
    ax = fig.add_subplot()
    die_axes(ax)
    for b in INNER:
        x0, y0, x1, y1 = (num(b[c]) for c in ("x0", "y0", "x1", "y1"))
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#f1f5f9", ec="#cbd5e1", lw=0.6, zorder=1))
    draw_pads(ax, alpha_used=0.85, labels=True, fs=7.2)
    draw_blocks(ax, sizes=False, lw=0.6, ec="#94a3b8", fs=9)
    kinds = ["Supply", "Ground", "Electrode input", "Reference and bias", "Digital I/O", "Unused"]
    ax.legend(handles=[Patch(fc=PAL[k], alpha=0.85 if k != "Unused" else 0.55, label=k if k != "Unused" else "Unused pad") for k in kinds],
              ncols=6, loc="upper center", bbox_to_anchor=(0.5, -0.07), handlelength=1.1, handleheight=1.1)
    save(fig, "14_pad_ring")


def fig_schedule():
    s = load("schedule")
    items = [r for r in s if r["area"] != "Milestone"]
    ms = [r for r in s if r["area"] == "Milestone"]
    D = lambda t: dt.datetime.strptime(t, "%Y-%m-%d")  # noqa: E731
    today = dt.datetime.strptime(CHIP_DATE, "%Y%m%d")     # the state of the tracker on the chip's day
    col = {"done": OK, "in progress": WARN, "not started": LIGHT}
    fig = figure(12.6, 10.4, "Schedule", "Tracker items at their due dates, coloured by status; vertical rules are milestones",
                 note=f"Status as recorded in gf180_tapeout_tracker.md on {today:%-d %b %Y}; the dashed red rule is that day.")
    ax = fig.add_subplot()
    rows = []
    for r in items:
        if not rows or rows[-1][1]["area"] != r["area"]:
            rows.append(("head", r))
        rows.append(("item", r))
    n = len(rows)
    ys = np.arange(n)[::-1]
    for yi, (kind, r) in zip(ys, rows):
        if kind == "head":
            if yi != ys[0]:
                ax.axhline(yi + 0.5, color="#cbd5e1", lw=0.8)
            continue
        c = col[r["status"]]
        ax.plot([dt.datetime(2026, 10, 21), D(r["due"])], [yi, yi], color=HAIR, lw=1, zorder=1)
        ax.scatter([D(r["due"])], [yi], s=40, facecolor=c if r["status"] != "not started" else "white", edgecolor=c,
                   linewidth=1.5, zorder=3)
    ax.set_yticks(ys, [r["area"].upper() if kind == "head" else f"{r['id']}  {r['title']}" for kind, r in rows], fontsize=8)
    for lab, (kind, _) in zip(ax.get_yticklabels(), rows):
        if kind == "head":
            lab.set(fontsize=7, fontweight="semibold", color=INK2)
    for i, m in enumerate(ms):
        x = D(m["due"])
        ax.axvline(x, color=INK2, lw=0.8, alpha=0.55, zorder=0)
        ax.text(x, n - 0.2 + (i % 2) * 0.9, " " + m["title"], fontsize=7.8, color=INK, va="bottom", ha="left")
    ax.axvline(today, color=BAD, ls=(0, (3, 3)), lw=1)
    ax.set_ylim(-0.8, n + 1.6)
    ax.xaxis.set_major_locator(mpl.dates.WeekdayLocator(byweekday=0))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%b %-d"))
    ax.set_xlim(dt.datetime(2026, 10, 18), dt.datetime(2026, 12, 22))
    ax.grid(axis="y", visible=False)
    ax.legend(handles=[Line2D([], [], marker="o", ls="", markersize=6.5, markerfacecolor=(col[k] if k != "not started" else "white"),
                              markeredgecolor=col[k], label=k) for k in col], loc="upper left", bbox_to_anchor=(0.0, -0.045), ncols=3)
    save(fig, "15_schedule")


ONLY = sys.argv[3:]
for f in (fig_floorplan, fig_layers, fig_matrix, fig_nets, fig_blocks, fig_block_table, fig_budget, fig_afe_noise, fig_rwire,
          fig_dist, fig_metrics, fig_density, fig_checks, fig_pads, fig_schedule):
    if not ONLY or f.__name__ in ONLY:
        f()

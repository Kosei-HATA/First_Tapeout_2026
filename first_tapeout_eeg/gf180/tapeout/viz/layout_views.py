#!/usr/bin/env python3
"""Layout views of the chip as drawn: KLayout renders of the GDS (the PDK layer colours of
gf180mcu.lyp, every hierarchy level, texts and cell frames hidden) in the frame of the other
figures (vizstyle: title, chip version, die coordinates in µm), with names over the block
outlines. The outlines are the cell instances in the GDS, so they follow the layout.

  01 chip       the die before fill (chip_top.gds): blocks, decoupling, pad ring
  02 chip_fill  the die as submitted (chip_top_fill.gds: COMP, poly and metal fill added)
  03 afe        the AFE (afe_top)
  04 adc        the ADC (adc_top)
  05 afe_input  the input chopper (afe_tgin) with the ends of the Cin arrays and the core
  06 afe_core   the AFE core amplifier (eeg_afe_core)
  07 quantizer  the ADC quantizer (eeg_quantizer)
  08 dac1       RIN and DAC1 (adc_rdac)
  09 ota1       the ADC's first integrator OTA (gf180_inside_cascode_ota)

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/layout_views.py <chip run dir> <out dir> [view ...]
  e.g. gf180/tapeout/layout/runs/chip_top documentation/figures/gf180/r6_20261026/layout
"""
import csv
import hashlib
import os
import sys
import tempfile
import textwrap

import klayout.db as db
import klayout.lay as lay
import matplotlib as mpl
import numpy as np
from matplotlib.patches import Rectangle
from PIL import Image

from vizstyle import CHIP, figure

LYP = ("/Users/noah/Codings/ws_gf180/gf180mcu-project-template/gf180mcu/gf180mcuD/libs.tech/klayout/"
       "tech/gf180mcu.lyp")
HERE = os.path.dirname(os.path.abspath(__file__))
RUN, OUT = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3:]
PREFIX = f"gf180_layout_{CHIP}_"
DPI = 220
os.makedirs(OUT, exist_ok=True)

GDS = os.path.join(RUN, "chip_top.gds")
GDS_FILL = os.path.join(RUN, "chip_top_fill.gds")
LY = db.Layout()
LY.read(GDS)
TOP = LY.top_cell()
DIE = TOP.dbbox()


def top_insts():
    return [(i.cell.name, i.dbbox()) for i in TOP.each_inst()]


def block(name):
    """The instance of `name` under the top cell and its children, in die coordinates."""
    inst = next(i for i in TOP.each_inst() if i.cell.name == name)
    t = inst.dcplx_trans
    return inst.dbbox(), [(c.cell.name, c.cell.dbbox().transformed(t * c.dcplx_trans)) for c in inst.cell.each_inst()]


def union(boxes):
    u = db.DBox()
    for b in boxes:
        u += b
    return u


class Render:
    def __init__(self, gds):
        self.v = lay.LayoutView()
        self.v.load_layout(gds, True)
        self.v.load_layer_props(LYP)
        self.v.max_hier()
        for k in ("text-visible", "cell-box-visible", "grid-visible"):
            self.v.set_config(k, "false")

    def image(self, box, wpx, hpx):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "v.png")
            self.v.save_image_with_options(p, wpx, hpx, 0, 1, 0, box, False)
            return np.asarray(Image.open(p).convert("RGB"))


_views = {}


def render(gds):
    if gds not in _views:
        _views[gds] = Render(gds)
    return _views[gds]


def label(ax, b, view, text, fs=9.0, where="tl", dash=False, rot=0):
    """Outline `b` and put `text` in the part of it inside `view` (or just above it: "above")."""
    ax.add_patch(Rectangle((b.left, b.bottom), b.width(), b.height(), fill=False, ec="white", lw=1.2, alpha=0.95,
                           ls=(0, (5, 3)) if dash else "-", zorder=3))
    v = b & view
    pad = 0.008 * max(view.width(), view.height())
    x, y, ha, va = {"tl": (v.left + pad, v.top - pad, "left", "top"), "c": (v.center().x, v.center().y, "center", "center"),
                    "bl": (v.left + pad, v.bottom + pad, "left", "bottom"),
                    "above": (v.center().x, v.top + pad, "center", "bottom")}[where]
    ax.text(x, y, text, color="white", fontsize=fs, fontweight="medium", ha=ha, va=va, zorder=4, linespacing=1.15,
            rotation=rot, bbox=dict(boxstyle="round,pad=0.28", fc="#0f172a", ec="none", alpha=0.80))


def frame(name, title, sub, box, labels=(), note=None, gds=GDS, w=12.6):
    """The KLayout render goes in unscaled (figimage at the axes' pixels): resampling blurs the
    layer stipples, and the blurred image no longer compresses."""
    if ONLY and name not in ONLY:
        return
    ar = box.height() / box.width()
    if note:
        note = textwrap.fill(note, int(w * 17.5))
    fig = figure(w, w * ar * 0.94 + 1.75, title, sub, note=note)
    fig.set_dpi(DPI)
    ax = fig.add_subplot()
    ax.set_xlim(box.left, box.right)
    ax.set_ylim(box.bottom, box.top)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.patch.set_visible(False)
    ax.set_xlabel("x on the die (µm)")
    ax.set_ylabel("y on the die (µm)")
    for args in labels:
        label(ax, *args[:1], box, *args[1:])
    fig.canvas.draw()                  # constrained layout places the axes; freeze it there
    fig.set_layout_engine("none")
    e = ax.get_window_extent()
    x0, y0, x1, y1 = (round(v) for v in (e.x0, e.y0, e.x1, e.y1))
    ax.set_position(fig.transFigure.inverted().transform([(x0, y0), (x1, y1)]).flatten().tolist()[:2] +
                    [(x1 - x0) / fig.bbox.width, (y1 - y0) / fig.bbox.height])
    ax.set_aspect("auto")             # the box now maps onto whole pixels
    fig.figimage(render(gds).image(box, x1 - x0, y1 - y0), xo=x0, yo=y0, origin="upper", zorder=-1)
    path = os.path.join(OUT, f"{PREFIX}{name}.png")
    with mpl.rc_context({"savefig.bbox": "standard"}):   # a tight box would move the axes off the image
        fig.savefig(path, dpi=DPI)
    print("wrote", os.path.basename(path))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


KL = "KLayout 0.30.12, PDK layer colours (gf180mcu.lyp), all hierarchy levels, texts hidden. "

# ---------------------------------------------------------------- die
ti = top_insts()
NAMES = {"afe_top": "AFE", "adc_top": "ADC", "eeg_digital_top": "Digital controller", "eeg_bias": "Bias generator",
         "eeg_ref": "Reference filter", "eeg_testmux": "Test MUX"}
chip_labels = [(b, NAMES[n], 10.5 if n in ("afe_top", "adc_top") else 8.5, "above" if n == "eeg_testmux" else "tl")
               for n, b in ti if n in NAMES]
dec = [b for n, b in ti if n == "chip_decap"]
chip_labels += [(union(b for b in dec if b.center().x < DIE.center().x), "AVDD decoupling", 8.0, "c", False, 90),
                (union(b for b in dec if b.center().x > DIE.center().x), "DVDD decoupling", 8.0, "bl")]
with open(os.path.join(HERE, "data", "pads.csv"), encoding="utf-8") as f:
    el = [r for r in csv.DictReader(f) if r["signal"].startswith(("ELP", "ELN"))]
if el:
    chip_labels.append((union(db.DBox(*(float(r[k]) for k in ("x0", "y0", "x1", "y1"))) for r in el),
                        "Electrode pads\nELP × 2, ELN × 2", 8.0, "tl", True))
frame("01_chip", "Layout of the die",
      f"chip_top.gds before fill, {DIE.width():.0f} × {DIE.height():.0f} µm · pad ring, AFE, ADC, digital controller, "
      "bias, reference filter · outlines are the cell instances",
      DIE, chip_labels, note=KL + "Bias generator rotated by 90°, digital controller mirrored.")

h = sha256(GDS_FILL)[:8] if (not ONLY or "02_chip_fill" in ONLY) else ""
frame("02_chip_fill", "Layout of the die as submitted",
      f"chip_top_fill.gds (sha256 {h}…) · COMP, poly and metal fill added for the density rules",
      DIE, [(b, t, fs) for b, t, fs, *_ in chip_labels if t in ("AFE", "ADC", "Digital controller")],
      note=KL + "The fill covers the free area of every layer; the blocks' own shapes are under it.", gds=GDS_FILL)

# ---------------------------------------------------------------- AFE
afe, kids = block("afe_top")
cin = sorted((b for n, b in kids if n == "eeg_cin"), key=lambda b: -b.center().y)
afe_names = {"afe_tgin": "Input chopper", "eeg_afe_core": "Core amplifier", "offdac_p": "Offset DAC,\nP half",
             "offdac_n": "Offset DAC,\nN half", "eeg_afe_clk": "Chopper clock\ndriver"}
afe_labels = [(b, afe_names[n], 9.0) for n, b in kids if n in afe_names]
afe_labels += [(cin[0], "Cin_P (MIM array)", 10.0), (cin[1], "Cin_N (MIM array)", 10.0, "bl")]
core = next(b for n, b in kids if n == "eeg_afe_core")
out = union(b for n, b in kids if n != "eeg_cin" and b.left >= core.right - 1)   # east of the core
afe_labels.append((out, "Output\nsection", 8.5))
frame("03_afe", "AFE layout",
      f"afe_top, {afe.width():.0f} × {afe.height():.0f} µm · the core band between the two Cin halves; electrodes enter "
      "from the west", afe, afe_labels,
      note=KL + "Output section: hold capacitors, Cc, Cf, Cpf and its trim, output chopper, CMFB, reset and DC-path switches.")

# ---------------------------------------------------------------- ADC
adc, kids = block("adc_top")
c1 = sorted((b for n, b in kids if n == "eeg_c1"), key=lambda b: -b.center().y)
adc_names = {"adc_rdac": "RIN + DAC1", "gf180_inside_cascode_ota": "OTA1", "gf180_ct_ota_tel16_cmfb": "OTA2",
             "eeg_quantizer": "Quantizer", "eeg_dac2": "DAC2", "eeg_adc_dig": "ADC digital\n(eeg_adc_dig)"}
adc_labels = [(b, adc_names[n], 9.0) for n, b in kids if n in adc_names]
adc_labels += [(c1[0], "C1P (MIM array)", 10.0), (c1[1], "C1N (MIM array)", 10.0, "bl")]
adc_labels += [(b, "C2", 7.5, "c") for n, b in kids if n == "adc_c2"]
adc_labels += [(b, n_, 7.5, "c") for n, b in kids for k, n_ in (("eeg_adc_clk", "Clock\ndriver"),) if n == k]
frame("04_adc", "ADC layout",
      f"adc_top, {adc.width():.0f} × {adc.height():.0f} µm · stage 1 (C1, RIN + DAC1, OTA1) at the west, stage 2 and the "
      "quantizer at the east", adc, adc_labels,
      note=KL + "R21 runs in the band's top channel; DAC2's SEL ports face the digital block below it.")

# ---------------------------------------------------------------- details: the cells inside one block
def inside(name):
    """Box of the cell `name` (anywhere in the hierarchy) and {child cell: union of its instances}."""
    def find(cell, t):
        for i in cell.each_inst():
            tt = t * i.dcplx_trans
            if i.cell.name == name:
                return i.cell, tt
            r = find(i.cell, tt)
            if r:
                return r
    cell, t = find(TOP, db.DCplxTrans())
    sub = {}
    for i in cell.each_inst():
        sub[i.cell.name] = sub.get(i.cell.name, db.DBox()) + i.dbbox().transformed(t)
    return cell.dbbox().transformed(t), sub


def pick(sub, *names):
    return union(sub[n] for n in names if n in sub)


afe, kids = block("afe_top")
k = {n: b for n, b in kids}
core = k["eeg_afe_core"]
tg, s = inside("afe_tgin")
win = db.DBox(afe.left, cin[1].top - 70, core.left + 160, cin[0].bottom + 70)
frame("05_afe_input", "AFE input chopper",
      f"afe_tgin, {tg.width():.0f} × {tg.height():.0f} µm, with the ends of the Cin arrays and the core amplifier · "
      "the four TGs in one commutator ring",
      win, [(tg, "Input chopper", 9.5, "above"), (s["afetg_p1"], "PMOS\n2048 fingers", 8.5),
            (s["afetg_n"], "NMOS\n2048 fingers", 8.5), (s["afetg_p0"], "PMOS\n2048 fingers", 8.5),
            (core, "Core\namplifier", 8.5, "tl", True), (cin[0], "Cin_P", 8.5, "bl", True), (cin[1], "Cin_N", 8.5, "tl", True)],
      note=KL + "The electrode spines EP / EN run on the chopper's west edge; WP / WN leave it on Metal5 stripes to the "
                "Cin bottom-plate buses.", w=8.4)
core, s = inside("eeg_afe_core")
frame("06_afe_core", "AFE core amplifier",
      f"eeg_afe_core, {core.width():.0f} × {core.height():.0f} µm · current-reuse input stage with regulated cascodes: "
      "NMOS column at the west, PMOS column at the east", core,
      [(s["afec_ncas"], "NMOS cascodes", 8.5), (s["afec_npair"], "NMOS input pair\n2 × 2048 fingers", 9.0),
       (s["afec_ntail"], "NMOS tail", 8.0, "c"), (s["afec_nboost"], "NMOS boosters", 8.0, "c"),
       (s["afec_pcas"], "PMOS cascodes", 8.5), (s["afec_ppair"], "PMOS input pair\n2 × 4096 fingers", 9.0),
       (s["afec_ptail"], "PMOS tail", 8.5), (s["afec_pboost"], "PMOS boosters", 8.5)],
      note=KL + "The outputs leave both columns' cascodes at the top, under a Metal4 shield.")
q, s = inside("eeg_quantizer")
frame("07_quantizer", "ADC quantizer",
      f"eeg_quantizer, {q.width():.0f} × {q.height():.0f} µm · 5-bit flash: 31 comparator units in two rows", q,
      [(s["eeg_qcmp"], "Comparators, 16 + 15", 9.0), (s["q_loads"], "Preamp loads, 62 × 300 kΩ", 8.5),
       (s["eeg_qladder"], "Threshold\nladder", 8.0, "above"),
       (pick(s, "q_bias_n", "q_bias_p", "q_cvbq", "q_strobe1", "q_strobe2"), "VBQ bias,\nstrobe buffer", 8.0, "above")],
      note=KL + "Each unit: preamp pairs on INP / INN and on the ladder taps, StrongARM latch, NOR SR latch.")
r, s = inside("adc_rdac")
logic = pick(s, *[n for n in s if n.startswith(("eeg_dac1_", "filler_", "dac1_cd"))])
frame("08_dac1", "ADC input resistor and DAC1",
      f"adc_rdac, {r.width():.0f} × {r.height():.0f} µm · RIN and the 31 DAC1 elements share one resistor array", r,
      [(s["rdac_r"], "Resistor array: 156 units of 300 kΩ (ppolyf_u_1k, 291 × 1 µm)\nRIN 16 per side; DAC1 2 in series "
                     "per side and element", 9.0),
       (s["dac1_quad"], "Switches, 31 × dac1_quad", 7.5, "c", False, 90),
       (logic, "Element\nlogic", 8.0)],
      note=KL + "The resistor array lies under its SAB and resistor marker layers. Logic: latch TGs, inverters, NORs, "
                "the common-break driver.")
o, s = inside("gf180_inside_cascode_ota")
frame("09_ota1", "ADC first-integrator OTA",
      f"gf180_inside_cascode_ota (OTA1), {o.width():.0f} × {o.height():.0f} µm · input chopper; the core chops its "
      "currents with two commutators (D1 to N1, P1 to P2)", o,
      [(s["ota1_nin"], "NMOS input pair\nand tail", 9.0), (s["ota1_ncas"], "NMOS cascodes", 8.0, "c"),
       (s["ota1_pload"], "PMOS loads", 9.0), (s["ota1_pcas"], "PMOS cascodes", 8.5),
       (s["ota1_cc"], "Ccomp (MIM)", 8.0, "c"), (pick(s, "ota1_chn", "ota1_chp"), "Input\nchopper", 7.5, "c"),
       (pick(s, "ota1_ntg", "ota1_ptg"), "N-side\ncommutator", 7.0, "c"),
       (pick(s, "ota1_nptg", "ota1_pptg"), "P-side\ncommutator", 7.0, "c"),
       (pick(s, "ota1_cmn", "ota1_cmp"), "CMFB", 7.0, "above")],
      note=KL, w=10.6)

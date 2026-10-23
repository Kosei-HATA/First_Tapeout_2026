#!/usr/bin/env python3
"""Chip top (tracker E7): the padring of the wafer.space 1x0.5 slot with the analog core
and the digital blocks, die coordinates (um, die 3932 x 2531). Top cell chip_top; LVS of
the core against gf180/tapeout/chip/eeg_core.spice.

Padring: LibreLane padring flow of the template work copy (/Users/noah/Codings/ws_gf180/
eeg_padring, run RUN_2026-10-23_13-27-25; copy in gf180/tapeout/chip/padring/): 14 analog pads (asig_5p0) for AVDD x3, AVSS
x3, ELP x2, ELN x2, ATP, VCM, VREFP, VREFN, the nine used digital pads bidir[0..8]
(bi_24t), and every unused signal slot as an unconnected analog pad (no tie-offs).

Floorplan (die um; the pads' inner edges at x 376 / 3556 and y 376 / 2155):
  - AFE afe_top     x  482 .. 1582, y 542 .. 1989
  - Ch-A            x 1582 .. 1732.4: AVDD / AVSS trunks (Metal5), decoupling under them,
                    the wiring corridor, the test multiplexer at the top
  - ADC adc_top     x 1732.4 .. 2942.4
  - digital block   eeg_digital_top mirrored about x (controls on its south edge) at
                    x 3002 .. 3442, y 542 .. 1242; DVDD decoupling above it
  - south band      y 376 .. 542: AVDD / AVSS straps (Metal5), the bias block eeg_bias
                    turned 90 degrees under the ADC (ports to the west, into Ch-A), the
                    control bus from the digital block (Metal3 / Metal4)
  - north band      y 1989 .. 2155: the reference filter eeg_ref (outputs at its east end,
                    into Ch-A), AVDD / AVSS straps above it
  - west gap        x 376 .. 482: the electrode straps ELP / ELN (Metal5) to the input
                    chopper's spines, AVDD / AVSS from the west pads, the AFE's west-edge
                    lines (Metal3)
  - east gap        x 3442 .. 3556: DVDD / DVSS trunks, the digital pads and their ties
Router grid (route.Router): columns x 0.64 + 0.8 i, rows y 0.04 + 0.68 j (the grids of
afe_top and adc_top at their origins).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/chip_lay.py [--drc] [--lvs]
"""
import argparse
import json
import os
import re
import time
import gf180lay as g
import analog as an
import blocks as bl
import route
import assemble as A
import fets as f
import afetg_lay as TG

HERE = os.path.dirname(os.path.abspath(__file__))
# the padring run (work copy eeg_padring, RUN_2026-10-23_13-27-25): its GDS (gzipped) and
# pad table (extract_pads.py / annotate_pads.py) are kept in gf180/tapeout/chip/padring/
PADDIR = os.path.join(os.path.dirname(HERE), "chip", "padring")
PADRING = os.path.join(PADDIR, "padring_1x0p5_20261023.gds.gz")
PADGEOM = os.path.join(PADDIR, "pad_geometry.json")
TOP = "chip_top"
DIE = (3932.0, 2531.0)
PAD_IN = (376.0, 376.0, 3556.0, 2155.0)          # inner edges of the pad cells (W, S, E, N)
GRID = (0.64, 0.8, 0.04, 0.68)
AFE_O = (482.0, 542.0)
ADC_O = (1732.4, 542.0)
CHA = (1582.0, 1732.4)
DIG_O = (3002.0, 1242.0)                         # mirrored: the macro spans y 542 .. 1242
BIAS_O = (2836.4, 425.0)                         # rot 90: x 1745.1 .. 2837.4, y 425.4 .. 534.6
TM_O = (1595.0, 1940.0)
REF_O = (669.0, 1995.0)


# Metal5 power straps (pairs of strips under 30 um, MSLOT5.1): x ranges of vertical ones,
# y ranges of horizontal ones
WG_AVSS = ((384.0, 403.0), (405.0, 424.0))          # west gap
WG_AVDD = ((430.0, 449.0), (451.0, 470.0))
SB_AVDD = ((481.0, 507.0), (509.0, 535.0))          # south band (AVDD next to the blocks)
SB_AVSS = ((412.0, 438.0), (440.0, 466.0))
NB_AVDD = ((2060.0, 2079.0), (2081.0, 2100.0))      # north band, above eeg_ref
NB_AVSS = ((2106.0, 2125.0), (2127.0, 2146.0))
CA_AVDD = ((1592.0, 1618.0), (1620.0, 1646.0))      # Ch-A trunks
CA_AVSS = ((1650.0, 1676.0), (1678.0, 1704.0))
SB_X1 = 2840.0                                       # east end of the south straps (bias)
ADC_RAIL = {"AVSS": (418.0, 426.0), "AVDD": (428.0, 436.0)}   # adc_lay R_AVSS_B / R_AVDD_B


def pads():
    """{clean name: pad dict} from the padring's pad_geometry.json."""
    d = json.load(open(PADGEOM))
    out = {}
    for p in d["pads"]:
        name = p["inst"].replace("\\", "")
        name = re.sub(r"\.pad$", "", name)
        out[name] = p
    return out


def bars(p):
    """The asig_5p0 pad's core-side Metal2 bars (die um)."""
    return [tuple(r[1:]) for r in p["core_pins"]["ASIG5V"]]


def local_shapes(inst, layer, window):
    """Merged shapes of an instance's layer touching a window (block coordinates), as die
    boxes."""
    li = inst.src.find_layer(*g.L[layer])
    win = A.pya.Box(*[int(round(v * 1000)) for v in window])
    r = A.pya.Region(inst.srctop.begin_shapes_rec_touching(li, win)).merged()
    out = []
    for p in r.each():
        b = A.pya.DBox(*A._box_um(p.bbox())).transformed(inst.trans)
        out.append((round(b.left, 4), round(b.bottom, 4), round(b.right, 4), round(b.top, 4)))
    return out


def slab(a, layer, x1, y1, x2, y2, net=None, along="x", maxw=28.0, gap=2.0):
    """A wide Metal4 / Metal5 shape as parallel strips under 30 um across (MSLOT4.1 /
    MSLOT5.1): strips run along x (or y), each at most maxw wide, gap um apart."""
    lo, hi = (y1, y2) if along == "x" else (x1, x2)
    n = max(1, int((hi - lo + gap) / (maxw + gap) + 0.999))
    w = (hi - lo - (n - 1) * gap) / n
    for k in range(n):
        a_, b_ = lo + k * (w + gap), lo + k * (w + gap) + w
        box = (x1, a_, x2, b_) if along == "x" else (a_, y1, b_, y2)
        if layer == "metal5":
            a.box("metal5", *box)
        else:
            a.wire(layer, *box, net)


def slab_stack(a, lo, hi, x1, y1, x2, y2, net, along="x", maxw=28.0, gap=2.0):
    """via_stack over the strips of slab()."""
    l_, h_ = (y1, y2) if along == "x" else (x1, x2)
    n = max(1, int((h_ - l_ + gap) / (maxw + gap) + 0.999))
    w = (h_ - l_ - (n - 1) * gap) / n
    for k in range(n):
        a_, b_ = l_ + k * (w + gap), l_ + k * (w + gap) + w
        box = (x1, a_, x2, b_) if along == "x" else (a_, y1, b_, y2)
        a.via_stack(lo, hi, *box, net)


def pad_plate(a, p, side, ext=7.0):
    """Join an analog pad's eight Metal2 bars outside the pad cell: each bar runs on 0.5 um
    into the core side, then one Metal2 plate (ext um deep) over all of them. Returns the
    plate (die um)."""
    bs = bars(p)
    if side == "west":
        x0 = max(b[2] for b in bs)
        for b in bs:
            a.box("metal2", x0 - 0.5, b[1], x0 + 1.0, b[3])
        plate = (x0 + 1.0, min(b[1] for b in bs), x0 + ext, max(b[3] for b in bs))
    else:                                            # north: bars end at the cell's bottom edge
        y0 = min(b[1] for b in bs)
        for b in bs:
            a.box("metal2", b[0], y0 - 1.0, b[2], y0 + 0.5)
        plate = (min(b[0] for b in bs), y0 - ext, max(b[2] for b in bs), y0 - 1.0)
    a.box("metal2", *plate)
    return plate


def power(a, I):
    """AVDD / AVSS (see the module doc): Metal5 straps from the six pads around the AFE to
    the Ch-A trunks, the trunks to the AFE's east rails and the ADC's west rails, the bias
    block's straps. Returns router pins {net: [pins]}."""
    P = I["pads"]
    pins = {}
    m5 = lambda x1, y1, x2, y2: a.box("metal5", x1, y1, x2, y2)
    # west-pad plates and their way into the west-gap verticals
    pl = {k: pad_plate(a, P[k], "west") for k in ("analog[0]", "analog[1]", "analog[6]", "analog[7]")}
    for k in ("analog[1]", "analog[6]"):                         # AVSS: Metal5 straight in
        x1, y1, x2, y2 = pl[k]
        slab_stack(a, "metal2", "metal5", x1, y1 + 0.5, x2, y2 - 0.5, "AVSS")
        slab(a, "metal5", x1, y1 + 0.5, WG_AVSS[1][1], y2 - 0.5)
    for k in ("analog[0]", "analog[7]"):                         # AVDD: Metal4 under the AVSS verticals
        x1, y1, x2, y2 = pl[k]
        slab_stack(a, "metal2", "metal4", x1, y1 + 0.5, x2, y2 - 0.5, "AVDD")
        slab(a, "metal4", x1, y1 + 0.5, WG_AVDD[0][0] + 6.0, y2 - 0.5, "AVDD")
        slab_stack(a, "metal4", "metal5", WG_AVDD[0][0], y1 + 0.5, WG_AVDD[0][0] + 6.0, y2 - 0.5, "AVDD")
    top = lambda k: max(b[3] for b in bars(P[k]))
    bot = lambda k: min(b[1] for b in bars(P[k]))
    for x1, x2 in WG_AVSS:
        m5(x1, SB_AVSS[0][0], x2, top("analog[6]"))
        m5(x1, bot("analog[1]"), x2, NB_AVSS[1][1])
    for x1, x2 in WG_AVDD:
        m5(x1, SB_AVDD[0][0], x2, top("analog[7]"))
        m5(x1, bot("analog[0]"), x2, NB_AVDD[1][1])
    # bands
    for y1, y2 in SB_AVSS:
        m5(WG_AVSS[0][0], y1, SB_X1, y2)
    for y1, y2 in SB_AVDD:
        m5(WG_AVDD[0][0], y1, SB_X1, y2)
    for y1, y2 in NB_AVSS:
        m5(WG_AVSS[0][0], y1, CA_AVSS[1][1], y2)
    for y1, y2 in NB_AVDD:
        m5(WG_AVDD[0][0], y1, CA_AVDD[1][1], y2)
    # north pads: AVSS straight down into NB_AVSS, AVDD on Metal4 under it into NB_AVDD
    x1, y1, x2, y2 = pad_plate(a, P["analog[13]"], "north")
    a.via_stack("metal2", "metal5", x1 + 0.5, y1, x2 - 0.5, y2, "AVSS")
    m5(x1 + 0.5, NB_AVSS[1][0], x2 - 0.5, y2)
    x1, y1, x2, y2 = pad_plate(a, P["analog[12]"], "north")
    slab_stack(a, "metal2", "metal4", x1 + 0.5, y1, x2 - 0.5, y2, "AVDD", along="y")
    slab(a, "metal4", x1 + 0.5, NB_AVDD[1][1] - 6.0, x2 - 0.5, y2, "AVDD", along="y")
    slab_stack(a, "metal4", "metal5", x1 + 0.5, NB_AVDD[1][1] - 6.0, x2 - 0.5, NB_AVDD[1][1], "AVDD", along="y")
    # Ch-A trunks; AVSS jumps SB_AVDD on Metal4
    for x1, x2 in CA_AVDD:
        m5(x1, SB_AVDD[0][0], x2, NB_AVDD[1][1])
    ya, yb = SB_AVSS[1][1] + 3.0, SB_AVDD[1][1] + 9.0
    for x1, x2 in CA_AVSS:
        m5(x1, SB_AVSS[0][0], x2, ya + 6.0)
        m5(x1, yb - 6.0, x2, NB_AVSS[1][1])
    xa, xb = CA_AVSS[0][0], CA_AVSS[1][1]
    slab_stack(a, "metal4", "metal5", xa, ya, xb, ya + 6.0, "AVSS", along="y", maxw=26.0)
    slab(a, "metal4", xa, ya, xb, yb, "AVSS", along="y", maxw=26.0)
    slab_stack(a, "metal4", "metal5", xa, yb - 6.0, xb, yb, "AVSS", along="y", maxw=26.0)
    # AFE east rails: AVDD into the AVDD trunk on Metal5, AVSS under it on Metal4
    afe = I["afe"]
    rails = [s for s in local_shapes(afe, "metal5", (1099.0, 500.0, 1100.0, 691.0)) if s[3] - s[1] > 10.0]
    xe = afe.bbox[2]
    for x1, y1, x2, y2 in rails:
        net = "AVSS" if y2 < afe.bbox[1] + 570.0 else "AVDD"
        if net == "AVDD":
            m5(xe - 1.0, y1, CA_AVDD[0][0] + 1.0, y2)
        else:
            m5(xe - 1.0, y1, xe + 6.0, y2)
            a.via_stack("metal4", "metal5", xe + 1.0, y1 + 0.5, xe + 6.0, y2 - 0.5, "AVSS")
            a.wire("metal4", xe + 1.0, y1 + 0.5, CA_AVSS[0][0] + 6.0, y2 - 0.5, "AVSS")
            a.via_stack("metal4", "metal5", CA_AVSS[0][0], y1 + 0.5, CA_AVSS[0][0] + 6.0, y2 - 0.5, "AVSS")
    I["afe_rails"] = rails
    # ADC west rails: AVSS into the AVSS trunk, AVDD under it on Metal4 (a taller jumper)
    adc = I["adc"]
    xw = adc.bbox[0]
    y1, y2 = [adc.bbox[1] + v for v in ADC_RAIL["AVSS"]]
    m5(CA_AVSS[1][1] - 1.0, y1, xw + 1.0, y2)
    y1, y2 = [adc.bbox[1] + v for v in ADC_RAIL["AVDD"]]
    m5(CA_AVSS[1][1] + 4.0, y1, xw + 1.0, y2)
    a.via_stack("metal4", "metal5", CA_AVSS[1][1] + 4.0, y1 + 0.5, CA_AVSS[1][1] + 10.0, y2 - 0.5, "AVDD")
    a.wire("metal4", CA_AVDD[1][1] - 6.0, y1 + 0.5, CA_AVSS[1][1] + 10.0, y2 + 20.0, "AVDD")
    a.via_stack("metal4", "metal5", CA_AVDD[1][1] - 6.0, y1 + 0.5, CA_AVDD[1][1], y2 + 20.0, "AVDD")
    # the bias block's Metal3 straps (VSS / VDD, along its length) up to the south straps,
    # via stacks where the block has no Metal4 near the strap
    bias = I["bias"]
    for net, lx in (("AVSS", (0.4, 2.83)), ("AVDD", (107.2, 109.6))):
        st = local_shapes(bias, "metal3", (lx[0], -1.0, lx[1], 1091.26))
        st = max(st, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        m4 = local_shapes(bias, "metal4", (lx[0] - 1.5, -1.0, lx[1] + 1.5, 1091.26))
        x = st[0] + 1.0
        while x + 4.0 < st[2] - 1.0:
            box = (x, st[1], x + 4.0, st[3])
            if not any(b[0] < box[2] + 0.6 and box[0] < b[2] + 0.6 for b in m4):
                a.via_stack("metal3", "metal5", *box, net)
            x += 6.0
    # eeg_ref's VSS (Metal1 bar along its bottom) at its west end, up to NB_AVSS on Metal3
    ref = I["ref"]
    rx, ry = ref.bbox[0], ref.bbox[1]
    # (the riser runs west of the block, clear of its VREFP_PAD / VREFN_PAD pins)
    a.stack("metal1", "metal3", rx + 0.5, ry + 0.4, rx + 3.0, ry + 2.6)
    a.wire("metal3", rx - 8.0, ry + 0.4, rx + 3.0, ry + 2.6, "AVSS")
    a.wire("metal3", rx - 8.0, ry + 0.4, rx - 5.5, NB_AVSS[0][0] + 6.0, "AVSS")
    a.via_stack("metal3", "metal5", rx - 8.0, NB_AVSS[0][0], rx - 5.5, NB_AVSS[0][0] + 6.0, "AVSS")
    return pins


# digital supply: DVSS trunk in the isolation band (fed by the south / north dvss pads
# beside it), DVDD trunk in the east gap (fed by the east dvdd pads); the digital block's
# DVSS straps run west, its DVDD straps east, so neither crosses the other trunk
IB_DVSS = ((2950.0, 2970.0), (2972.0, 2992.0))
EG_DVDD = ((3500.0, 3520.0), (3522.0, 3542.0))
DIG_STRAPS = [("DVDD", 642.0, 648.0), ("DVSS", 654.0, 660.0)] + \
    [(n, y, y + 10.0) for y0 in (760.0, 900.0, 1040.0, 1180.0) for n, y in (("DVDD", y0), ("DVSS", y0 + 14.0))]
ADC_DRAIL = {"DVDD": (100.0, 106.0), "DVSS": (112.0, 118.0)}   # adc_lay R_DVDD / R_DVSS
ADC_DRISER = 1203.0                                               # adc_lay X_DVDD


def cell_power_pad(p, net):
    """Core-side Metal2 rects of a dvdd / dvss pad cell (from the PDK LEF, die um)."""
    xs = [(1.36, 10.86), (13.76, 24.01), (25.61, 35.86), (39.14, 49.39), (50.99, 61.24), (64.14, 73.64)]
    yl = (345.345, 350.0) if net == "DVDD" else (349.0, 350.0)
    x1, y1, x2, y2 = p["bbox"]
    out = []
    for a_, b_ in xs:
        if p["orient"] == "R90":             # east side: local (x, y) -> (x2 - y, y1 + x)
            out.append((x2 - yl[1], y1 + a_, x2 - yl[0], y1 + b_))
        elif p["orient"] == "R0":            # south: local y up
            out.append((x1 + a_, y1 + yl[0], x1 + b_, y1 + yl[1]))
        else:                                # north (MX): local y down from the top
            out.append((x1 + a_, y2 - yl[1], x1 + b_, y2 - yl[0]))
    return out


def dpower(a, I):
    """DVDD / DVSS for the digital block, the ADC's digital rails and the pad ties' anchors.
    Returns router pins {net: [pins]}."""
    P = I["pads"]
    pins = {}
    m5 = lambda x1, y1, x2, y2: a.box("metal5", x1, y1, x2, y2)
    dig, adc = I["dig"], I["adc"]
    # trunks
    for x1, x2 in IB_DVSS:
        m5(x1, PAD_IN[1] + 6.0, x2, PAD_IN[3] - 6.0)
    for x1, x2 in EG_DVDD:
        m5(x1, P["dvdd_pads[2]"]["bbox"][1] + 1.0, x2, P["dvdd_pads[3]"]["bbox"][3] - 1.0)
    # east dvdd pads: their core-side Metal2 joined, up to Metal5 and into the DVDD trunk
    for k in ("dvdd_pads[2]", "dvdd_pads[3]"):
        rs = cell_power_pad(P[k], "DVDD")
        y1, y2 = min(r[1] for r in rs), max(r[3] for r in rs)
        for r in rs:
            a.box("metal2", r[0] - 1.0, r[1], r[0] + 0.5, r[3])
        a.box("metal2", PAD_IN[2] - 7.0, y1, PAD_IN[2] - 1.0, y2)
        a.via_stack("metal2", "metal5", PAD_IN[2] - 7.0, y1, PAD_IN[2] - 1.0, y2, "DVDD")
        m5(EG_DVDD[1][1] - 1.0, y1, PAD_IN[2] - 1.0, y2)
    # south / north dvss pads beside the isolation band: Metal5 into the DVSS trunk
    for k, side in (("dvss_pads[1]", "south"), ("dvss_pads[4]", "north")):
        rs = cell_power_pad(P[k], "DVSS")
        x1, x2 = min(r[0] for r in rs), max(r[2] for r in rs)
        if side == "south":
            for r in rs:
                a.box("metal2", r[0], r[3] - 0.5, r[2], r[3] + 1.0)
            ya, yb = PAD_IN[1] + 1.0, PAD_IN[1] + 7.0
        else:
            for r in rs:
                a.box("metal2", r[0], r[1] - 1.0, r[2], r[1] + 0.5)
            ya, yb = PAD_IN[3] - 7.0, PAD_IN[3] - 1.0
        a.box("metal2", x1, ya, x2, yb)
        a.via_stack("metal2", "metal5", x1, ya, x2, yb, "DVSS")
        m5(x1, ya, IB_DVSS[1][1], yb)
    # straps over the digital block, Via4 onto its Metal4 straps
    xs = {n: [s for s in dig.pins[n.replace("D", "", 1)] if s[0] == "metal4"] for n in ("DVDD", "DVSS")}
    for net, y1, y2 in DIG_STRAPS:
        if net == "DVSS":
            m5(IB_DVSS[1][1] - 1.0, y1, dig.bbox[2] - 2.0, y2)
        else:
            m5(dig.bbox[0] + 2.0, y1, EG_DVDD[0][0] + 1.0, y2)
        for s in xs[net]:
            a.vias("via4", s[1], y1, s[3], y2)
    # the ADC's DVDD rail (and riser) and DVSS rail: Metal4 jumpers across the DVSS trunk
    # (DVDD, from the y 642 strap) and under the riser (DVSS, into the trunk)
    yo = adc.bbox[1]
    y1, y2 = yo + ADC_DRAIL["DVDD"][0], yo + ADC_DRAIL["DVDD"][1]
    xr = adc.bbox[2]
    xj = dig.bbox[0] - 2.0                            # east end of the jumper, west of the macro
    a.via_stack("metal4", "metal5", xr - 4.0, y1, xr - 0.5, y2, "DVDD")
    a.wire("metal4", xr - 4.0, y1, xj, y2, "DVDD")
    a.via_stack("metal4", "metal5", xj - 6.0, y1, xj, y2, "DVDD")
    m5(xj - 6.0, y1, dig.bbox[0] + 3.0, y2)
    y1, y2 = yo + ADC_DRAIL["DVSS"][0], yo + ADC_DRAIL["DVSS"][1]
    xd = adc.bbox[0] + ADC_DRISER - 2.0               # the ADC's DVSS rail ends here
    a.via_stack("metal4", "metal5", xd - 6.0, y1, xd - 0.5, y2, "DVSS")
    a.wire("metal4", xd - 6.0, y1, IB_DVSS[0][0] + 6.0, y2, "DVSS")
    a.via_stack("metal4", "metal5", IB_DVSS[0][0], y1, IB_DVSS[0][0] + 6.0, y2, "DVSS")
    # router anchors: Metal4 pads on the trunks beside the digital pads (tie-offs)
    for k in [f"bidir[{i}]" for i in range(8)]:
        y = P[k]["bbox"][1] + 30.0
        a.via_stack("metal4", "metal5", EG_DVDD[1][0], y, EG_DVDD[1][0] + 4.0, y + 4.0, "DVDD")
        pins.setdefault("DVDD", []).append(("metal4", EG_DVDD[1][0], y, EG_DVDD[1][0] + 4.0, y + 4.0))
    for k in ("dvss_pads[2]", "dvss_pads[3]"):        # east dvss pads: router pins on their Metal2
        rs = cell_power_pad(P[k], "DVSS")
        y1, y2 = min(r[1] for r in rs), max(r[3] for r in rs)
        for r in rs:
            a.box("metal2", r[0] - 1.0, r[1], r[0] + 0.5, r[3])
        a.box("metal2", PAD_IN[2] - 7.0, y1, PAD_IN[2] - 1.0, y2)
        a.via_stack("metal2", "metal4", PAD_IN[2] - 7.0, y1, PAD_IN[2] - 1.0, y2, "DVSS")
        pins.setdefault("DVSS", []).append(("metal4", PAD_IN[2] - 7.0, y1, PAD_IN[2] - 1.0, y2))
    return pins


DECAP_A_X = 1593.0                       # Ch-A decoupling: three units per row under the trunks
DECAP_A_Y = (556.0, 1924.0)
DECAP_D = (3003.0, 1252.0, 12, 4)        # DVDD decoupling above the digital block: x0, y0, nx, ny


def decaps(a, I):
    """MOS capacitor arrays (analog.moscap_cell, cap_nmos_03v3 28.6 x 44 um): gate on the
    upper net, source/drain and ring on the lower. Per row a Metal2 strap joins the gate
    pins and one the bulk pins; via stacks lift them to the Metal5 trunks / straps above
    (rows whose straps would meet a Metal4 jumper are left out). Returns the unit counts."""
    unit = an.moscap_cell(a, "chip_decap", "n", "G", "B")
    uw, uh = unit.width, unit.height
    g_, b_ = unit.pins["G"][0], unit.pins["B"][0]
    jumpers = [m for m in a.manual if m[0] == "metal4" and m[2] in ("AVDD", "AVSS") and m[1][2] - m[1][0] > 20.0]
    counts = {}

    def row(x0, y, n, gnet, bnet, gx, bx):
        """n units from x0 at y; gate via stack at gx, bulk via stack at bx (x ranges)."""
        ys = {"G": (y + g_[2], y + g_[4]), "B": (y + b_[2], y + b_[4])}
        for net, (lo, hi), (xa, xb) in ((gnet, ys["G"], gx), (bnet, ys["B"], bx)):
            for lay, (x1, y1, x2, y2), _ in jumpers:
                if x1 < xb and xa < x2 and y1 < hi + 1.0 and lo - 1.0 < y2:
                    return 0
        for k in range(n):
            a.place(unit.cell, x0 + k * uw, y)
        for (lo, hi), (xa, xb), net in ((ys["G"], gx, gnet), (ys["B"], bx, bnet)):
            a.box("metal2", x0 + 2.0, lo, x0 + (n - 1) * uw + uw - 2.0, hi)
            a.via_stack("metal2", "metal5", xa, lo, xb, hi, net)
        return n
    n = 0
    y = DECAP_A_Y[0]
    while y + uh <= DECAP_A_Y[1]:
        n += row(DECAP_A_X, y, 3, "AVDD", "AVSS", (CA_AVDD[0][0] + 12.0, CA_AVDD[0][0] + 18.0),
                 (CA_AVSS[1][0] + 8.0, CA_AVSS[1][0] + 14.0))
        y += uh + 1.0
    counts["A"] = n
    x0, y0, nx, ny = DECAP_D
    n = 0
    for j in range(ny):
        y = y0 + j * (uh + 1.0)
        ys = {"G": (y + g_[2], y + g_[4]), "B": (y + b_[2], y + b_[4])}
        for k in range(nx):
            a.place(unit.cell, x0 + k * uw, y)
        n += nx
        for (lo, hi), net in ((ys["G"], "DVDD"), (ys["B"], "DVSS")):
            a.box("metal2", x0 + 2.0, lo, x0 + nx * uw - 2.0, hi)
            # Metal5 strap over the row's strap: DVSS west to the isolation trunk, DVDD east
            a.box("metal5", (IB_DVSS[1][1] - 1.0) if net == "DVSS" else x0 + 1.0, lo - 3.0,
                  x0 + nx * uw - 1.0 if net == "DVSS" else EG_DVDD[0][0] + 1.0, hi + 3.0)
            for k in range(nx):
                xa = x0 + k * uw + uw / 2 - 3.0
                a.via_stack("metal2", "metal5", xa, lo, xa + 6.0, hi, net)
    counts["D"] = n
    return counts


def electrodes(a, I):
    """ELP / ELN pad straps to the input chopper's Metal5 spines (EP outer, EN inner):
    Metal5 over Metal4 (via4 between them, west of the chopper), each split in strips
    (slot rule). ELP's strap runs onto the EP spine (its Metal4 onto the chopper's EP
    bands). ELN's crosses the EP spine on Metal4 jumpers (one per gap between the
    chopper's EP bands: Metal4 rows from the EP spine east, afetg_lay.band_rows) into the
    chopper's EN bands (Metal4 rows from the EN spine east, with their own via4 onto it)."""
    P = I["pads"]
    sp = {}
    for n in ("ELP", "ELN"):            # the whole spines (a pin can be a via island on one)
        b = A.pya.DBox(*I["afe"].pin(n, "metal5")[1:]).transformed(I["afe"].trans.inverted())
        sp[n] = max(local_shapes(I["afe"], "metal5", (b.left, b.bottom, b.right, b.top)), key=lambda s: s[3] - s[1])
    ep, en = (sp["ELP"][0], sp["ELP"][2]), (sp["ELN"][0], sp["ELN"][2])
    rows = TG.band_rows(sp["ELP"][1], sp["ELP"][3])                       # spines = the lanes' span
    ep_rows = [(y1, y2) for kind, y1, y2 in rows if kind == "EP"]
    en_rows = [(y1, y2) for kind, y1, y2 in rows if kind == "EN"]
    for k, net in (("analog[2]", "ELP"), ("analog[3]", "ELP"), ("analog[4]", "ELN"), ("analog[5]", "ELN")):
        x1, y1, x2, y2 = pad_plate(a, P[k], "west")
        y1, y2 = y1 + 0.5, y2 - 0.5
        slab_stack(a, "metal2", "metal5", x1, y1, x2, y2, net, maxw=20.0)
        xe = ep[1] if net == "ELP" else ep[0] - 4.0
        slab(a, "metal5", x1, y1, xe, y2, maxw=20.0)
        slab(a, "metal4", x2, y1, xe, y2, net, maxw=20.0)
        xlast = ep[0] - 8.0 if net == "ELP" else xe - 14.0      # via4 stays off the chopper
        for xa in range(int(x2) + 4, int(xlast) - 5, 12):
            slab_stack(a, "metal4", "metal5", xa, y1, xa + 6.0, y2, net, maxw=20.0)
        if net == "ELN":
            n = max(1, int((y2 - y1 + 2.0) / 22.0 + 0.999))      # the strap's Metal5 strips (slab)
            w = (y2 - y1 - (n - 1) * 2.0) / n
            for (_, ra), (rb, _) in zip(ep_rows, ep_rows[1:]):
                ga, gb = max(ra + TG.ROW_GAP, y1), min(rb - TG.ROW_GAP, y2)
                if not any(min(gb, r2) - max(ga, r1) >= 3.0 for r1, r2 in en_rows):
                    continue                                     # must land on an EN band
                a.wire("metal4", xe - 6.0, ga, en[0] + 6.0, gb, net)
                # west via4: on the strap's Metal5 strips only (not in their slots)
                for j in range(n):
                    sa, sb = max(ga, y1 + j * (w + 2.0)), min(gb, y1 + j * (w + 2.0) + w)
                    if sb - sa > 1.0:
                        a.via_stack("metal4", "metal5", xe - 6.0, sa, xe, sb, net)


def pin_pads(a, inst, names=None, w=4.0, h=1.4):
    """Router pads for a turned block's port stubs (narrow Metal3 stubs on the block's
    edge that hold no router row): a Metal3 pad reaching w um outwards from the edge."""
    x1m, y1m, x2m, y2m = inst.bbox
    for net, segs in inst.pins.items():
        if names is not None and net not in names:
            continue
        new = []
        for lay, x1, y1, x2, y2 in segs:
            if lay == "metal3" and y2 - y1 < 0.5 and abs(x1 - x1m) < 0.01:      # west edge
                yc = (y1 + y2) / 2
                box = ("metal3", x1 - w, yc - h / 2, x1 + 0.6, yc + h / 2)
                a.wire(*box, net)
                new.append(box)
            else:
                new.append((lay, x1, y1, x2, y2))
        inst.pins[net] = new


def pad_pin(a, p, side, net):
    """An analog signal pad's bars joined and lifted to a Metal4 router pin."""
    x1, y1, x2, y2 = pad_plate(a, p, side)
    if side == "north":
        a.via_stack("metal2", "metal4", x1 + 0.5, y1, x2 - 0.5, y2, net)
        return ("metal4", x1 + 0.5, y1, x2 - 0.5, y2)
    a.via_stack("metal2", "metal4", x1, y1 + 0.5, x2, y2 - 0.5, net)
    return ("metal4", x1, y1 + 0.5, x2, y2 - 0.5)


# digital pads: signal pin and tie-offs (1 = DVDD, 0 = DVSS); see the RTL README
DPAD = {
    "bidir[0]": ("MCLK", "Y", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=0)),
    "bidir[1]": ("RESET_N", "Y", dict(A=0, OE=0, IE=1, CS=1, SL=0, PU=1, PD=0)),
    "bidir[2]": ("SCLK", "Y", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=1)),
    "bidir[3]": ("CS_N", "Y", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=1, PD=0)),
    "bidir[4]": ("MOSI", "Y", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=1)),
    "bidir[5]": ("MISO", "A", dict(OE="MISO_OE", IE=0, CS=0, SL=1, PU=0, PD=0)),
    "bidir[6]": ("DRDY_N", "A", dict(OE=1, IE=0, CS=0, SL=1, PU=0, PD=0)),
    "bidir[7]": ("RAW_DATA", "A", dict(OE=1, IE=0, CS=0, SL=1, PU=0, PD=0)),
    "bidir[8]": ("RAW_CLK", "A", dict(OE=1, IE=0, CS=0, SL=1, PU=0, PD=0)),
}


def digital_pads(a, I):
    """Metal2 breakouts of the used bidir pads' core-side pins (outside the pad cell) as
    router pins: the signal pin to its net, the others to DVDD / DVSS."""
    P = I["pads"]
    pins = {}
    for k, (sig, sp, ties) in DPAD.items():
        p = P[k]
        for pn, rects in p["core_pins"].items():
            if pn == "Y" and sp != "Y":
                continue
            net = sig if pn == sp else ties.get(pn)
            if net is None:
                continue
            net = {0: "DVSS", 1: "DVDD"}.get(net, net)
            _, x1, y1, x2, y2 = rects[0]
            if p["orient"] == "R90":                    # east: horizontal pins at x = 3556
                stub = (PAD_IN[2] - 26.0, y1, PAD_IN[2] + 0.5, y2)
                pin = ("metal2", PAD_IN[2] - 26.0, y1, PAD_IN[2] - 6.0, y2)
            else:                                       # north (RAW_CLK): vertical pins at y = 2155,
                ye = PAD_IN[3] - 8.0 - 3.0 * (int(round((x1 - p["bbox"][0]) / 0.73)) % 4)   # staggered ends
                stub = (x1, ye, x2, PAD_IN[3] + 0.5)
                pin = ("metal2", x1, ye, x2, ye + 1.5)
            a.box("metal2", *stub)
            pins.setdefault(net, []).append(pin)
    return pins


# long control nets from the digital block to small gates (antenna rule ANT.5 on Metal4:
# the macro's driver diffusion alone, 1.4 um2, is too small for 2-4 mm of wire)
ANT_NETS = ["CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "OFS"] + [f"OFM{k}" for k in range(10)] + \
    [f"OFEN{k}" for k in range(4)] + [f"TC{k}" for k in range(5)] + ["IB0", "IB1", "BP0", "BP1", "BN0", "BN1"] + \
    [f"CPF{k}" for k in range(4)] + ["CHOP1", "ADC_ZERO"]


def antenna_row(a, nets, x0, y0, d=2.4, pitch=4.4, g=1.2):
    """Antenna diodes: an N+ diffusion d x d um per net (no diode marker: the LVS sees a
    conductor, the antenna check counts its area) in a row inside one P+ substrate-tap
    ring (DF.14), each lifted to a Metal3 router pin; the ring to DVSS through a Metal3
    pad on a Metal1 tab at its west end. Returns {net: [pins]}."""
    n = len(nets)
    w, h = 2 * g + (n - 1) * pitch + d, 2 * g + d
    f.ring(a, "p", x0, y0, x0 + w, y0 + h, w=f.TAP_W, well=False)
    pins = {}
    for k, net in enumerate(nets):
        x = x0 + g + k * pitch
        box = (x, y0 + g, x + d, y0 + g + d)
        f.tap(a, "n", *box, well=False)
        a.vias("via1", *box)
        a.via_stack("metal2", "metal3", *box, net)
        pins[net] = [("metal3",) + box]
    tab = (x0 - 3.0, y0, x0 + 0.42, y0 + h)
    a.box("metal1", *tab)
    a.vias("via1", *tab)
    a.via_stack("metal2", "metal3", *tab, "DVSS")
    pins["DVSS"] = [("metal3",) + tab]
    return pins


AFE_NET = {"CIA2": "CIA", "CIB2": "CIB", "CDA2": "CDA", "NCDA2": "NCDA", "CDB2": "CDB", "NCDB2": "NCDB",
           "RST2": "RSTA", "RST": "RSTA"}
ADC_NET = {"INP": "OUTP", "INN": "OUTN", "RST": "AFE_RST"}
TM_NET = {"AOP": "OUTP", "AON": "OUTN"}
POWER = ("AVDD", "AVSS", "DVDD", "DVSS", "VDD", "VSS", "ELP", "ELN")


def dig_net(n):
    m = re.match(r"(\w+)\[(\d+)\]$", n)
    if not m:
        return n
    base, k = m.group(1), int(m.group(2))
    if base == "TEST_CFG":
        return f"TC{k}" if k <= 4 else ("ADC_ZERO" if k == 5 else None)
    return {"AFE_IBIAS": "IB", "BTRIM_N": "BN", "BTRIM_P": "BP", "CPF_TRIM": "CPF", "OFEN": "OFEN", "OFM": "OFM",
            "CODE": "CODE"}[base] + str(k)


def afe_net(n):
    m = re.match(r"(\w+?)(\d*)_([NP])$", n)
    if m and m.group(1) in ("VCM", "OFPH", "OFS", "OFM", "OFEN"):
        return m.group(1) + m.group(2)
    return AFE_NET.get(n, n)


def rename_pins(inst, fn):
    """Rename an instance's pins to chip nets (so that the router's obstacles of the
    block's port stubs belong to the chip net); fn -> None keeps the block's name."""
    new = {}
    for n, segs in inst.pins.items():
        new.setdefault(fn(n) or n, []).extend(segs)
    inst.pins = new


def signals(a, I):
    """The router's nets {chip net: [pins]} from the blocks' ports and the pads."""
    nets = {}

    def add(net, segs):
        if net is not None and net not in POWER:
            nets.setdefault(net, []).extend(segs)
    blocks = (("afe", afe_net), ("adc", lambda n: ADC_NET.get(n, n)), ("dig", dig_net),
              ("bias", lambda n: n), ("tm", lambda n: TM_NET.get(n, n)))
    for k, fn in blocks:                  # chip net names first: the pads below take them
        rename_pins(I[k], fn)
    A.macro_pads(a, I["dig"])
    pin_pads(a, I["bias"])
    a.cover(I["tm"])
    for k, fn in blocks:
        for n, segs in I[k].pins.items():
            if k != "dig" or dig_net(n) is not None or n in nets:
                add(n, segs)
    # eeg_ref: pad inputs on its west edge (Metal2), outputs from its Metal5 strips, run on
    # east of the block and lifted down to Metal4
    ref = I["ref"]
    for n in ("VREFP_PAD", "VREFN_PAD"):
        add(n, [s for s in ref.pins[n] if s[0] == "metal2"])
    for n in ("VREFP", "VREFN"):
        s = [s for s in ref.pins[n] if s[0] == "metal5"][0]
        x0 = ref.bbox[2]
        a.box("metal5", x0 - 1.0, s[2], x0 + 8.0, s[4])
        a.via_stack("metal3", "metal5", x0 + 2.0, s[2], x0 + 8.0, s[4], n)
        add(n, [("metal4", x0 + 2.0, s[2], x0 + 8.0, s[4])])
    P = I["pads"]
    for k, n, side in (("analog[8]", "ATP", "north"), ("analog[9]", "VCM", "north"),
                       ("analog[10]", "VREFP_PAD", "north"), ("analog[11]", "VREFN_PAD", "north")):
        add(n, [pad_pin(a, P[k], side, n)])
    for n, segs in digital_pads(a, I).items():
        nets.setdefault(n, []).extend(segs)
    # antenna diodes for the long control nets, under the digital block's south edge
    for n, segs in antenna_row(a, ANT_NETS, I["dig"].bbox[0] + 8.0, I["dig"].bbox[1] - 24.0).items():
        nets.setdefault(n, []).extend(segs)
    # the test multiplexer's supply straps (Metal3, west edge) to anchors on the trunks
    tm = I["tm"]
    for n, (x1, x2) in (("AVDD", CA_AVDD[0]), ("AVSS", CA_AVSS[0])):
        y = tm.bbox[1] - 12.0
        a.via_stack("metal4", "metal5", x1 + 8.0, y, x1 + 12.0, y + 4.0, n)
        nets.setdefault(n, []).extend([s for s in tm.pins[n] if s[0] == "metal3"][:1] +
                                       [("metal4", x1 + 8.0, y, x1 + 12.0, y + 4.0)])
    return nets


def route_all(a, I, nets):
    t0 = time.time()
    gx0, px, gy0, py = GRID
    x0 = gx0 + px * int((PAD_IN[0] + 4.0 - gx0) / px + 1)
    y0 = gy0 + py * int((PAD_IN[1] + 4.0 - gy0) / py + 1)
    r = route.Router(x0, y0, PAD_IN[2] - 4.0, PAD_IN[3] - 4.0, px=px, py=py)
    print(f"grid {r.nx} x {r.ny} ({time.time() - t0:.0f} s)")
    a.obstacles(r)
    a.give(r)
    print(f"obstacles ({time.time() - t0:.0f} s)")
    for n in nets:
        uniq = []
        for p_ in nets[n]:
            key = (p_[0],) + tuple(round(v, 3) for v in p_[1:])
            if key not in [(q[0],) + tuple(round(v, 3) for v in q[1:]) for q in uniq]:
                uniq.append(p_)
        nets[n] = uniq
    single = sorted(n for n, p in nets.items() if len(p) < 2)
    if single:
        print("single-pin nets:", single)
    failed = r.route({n: p for n, p in nets.items() if len(p) >= 2}, rounds=3)
    print(f"routed in {time.time() - t0:.0f} s")
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
    r.draw(a)
    return failed


TAPEOUT = os.path.dirname(HERE)
SCL = os.path.join(g.PDK, "libs.ref")
NETLISTS = [os.path.join(TAPEOUT, "chip", "eeg_core.spice"), os.path.join(TAPEOUT, "afe", "eeg_afe.spice"),
            os.path.join(TAPEOUT, "afe", "eeg_afe_clk.spice")] + \
    [os.path.join(TAPEOUT, "adc", n) for n in ("eeg_adc_otas.spice", "eeg_adc_clk.spice", "eeg_dac1.spice",
                                                "eeg_dac2.spice", "eeg_quantizer.spice", "eeg_adc.spice", "eeg_ref.spice")] + \
    [os.path.join(TAPEOUT, "bias", "eeg_bias.spice"), os.path.join(TAPEOUT, "test", "eeg_testmux.spice"),
     os.path.join(HERE, "gds", "eeg_adc_dig.cdl"), os.path.join(HERE, "gds", "eeg_digital_top.cdl")] + \
    [os.path.join(SCL, f"gf180mcu_fd_sc_mcu{t}t5v0", "spice", f"gf180mcu_fd_sc_mcu{t}t5v0.spice") for t in (7, 9)]
TIES = [("AVSS_CLK", "AVSS"), ("DVSS", "AVSS")]          # nets the p-substrate joins


def core_labels(a, I):
    """Labels on the top cell for the LVS of the core (eeg_core's ports where the core
    meets the pads) and the ADC's LVS hints (nets that only the deep matcher tells apart)."""
    P = I["pads"]
    for k, n in (("analog[2]", "ELP"), ("analog[4]", "ELN")):
        bs = bars(P[k])
        a.label("metal5", n, WG_AVDD[0][0], min(b[1] for b in bs) + 5.0)      # on the strap's first strip
    for k, n in (("analog[8]", "ATP"), ("analog[9]", "VCM"), ("analog[10]", "VREFP_PAD"), ("analog[11]", "VREFN_PAD")):
        bs = bars(P[k])
        a.label("metal2", n, (min(b[0] for b in bs) + max(b[2] for b in bs)) / 2, PAD_IN[3] - 4.0)
    for k, (sig, sp, ties) in DPAD.items():
        for pn, rects in P[k]["core_pins"].items():
            n = sig if pn == sp else (ties.get(pn) if isinstance(ties.get(pn), str) else None)
            if n is None:
                continue
            _, x1, y1, x2, y2 = rects[0]
            if P[k]["orient"] == "R90":
                a.label("metal2", n, PAD_IN[2] - 3.0, (y1 + y2) / 2)
            else:
                a.label("metal2", n, (x1 + x2) / 2, PAD_IN[3] - 3.0)
    a.label("metal5", "AVDD", sum(CA_AVDD[0]) / 2, 1500.0)
    a.label("metal5", "AVSS", sum(CA_AVSS[0]) / 2, 1500.0)
    a.label("metal5", "DVDD", sum(EG_DVDD[0]) / 2, 1500.0)
    a.label("metal5", "DVSS", sum(IB_DVSS[0]) / 2, 1500.0)
    adc = I["adc"]
    li = {k: adc.src.find_layer(*g.L[k + "_label"]) for k in ("metal3", "metal4", "metal5")}
    for lay, l_ in li.items():
        if l_ is None:
            continue
        for sh in adc.srctop.shapes(l_).each():
            if sh.is_text() and "." in sh.text.string:
                pt = adc.trans * A.pya.DPoint(sh.text.trans.disp.x / 1000, sh.text.trans.disp.y / 1000)
                a.label(lay, sh.text.string, pt.x, pt.y)


NDMY, PMNDMY = (111, 5), (152, 5)        # no dummy COMP; no dummy poly / metal (PDK fill scripts)


def nofill(a, I):
    """No poly / metal fill (PMNDMY) over the AFE band between the Cin buses (input
    chopper, core, output section) and the ADC's first and second stages (between the C1
    buses): no floating metal next to the amplifier inputs and the integrators' virtual
    grounds. Dummy COMP stays allowed there (NDMY is limited to 15000 um2, DE.3)."""
    afe, adc = I["afe"], I["adc"]
    boxes = [(afe.bbox[0], afe.bbox[1] + 411.0, afe.bbox[2], afe.bbox[1] + 1036.0),
             (adc.bbox[0], adc.bbox[1] + 400.0, adc.bbox[0] + 900.0, adc.bbox[1] + 1047.0)]
    for b in boxes:              # PMNDMY only: NDMY may not exceed 15000 um2 (DE.3)
        a.cell.shapes(a.ly.layer(*PMNDMY)).insert(A.pya.DBox(*b))


def fill(gds, out, runs):
    """The PDK's dummy fill (COMP, Poly2, Metal1..5 on their dummy layers) over the chip."""
    rb = os.path.join(g.TECH, "scripts", "fill_all.rb")
    g._nix(f"klayout -b -r {rb} -rd input={gds} -rd output={out}", os.path.join(runs, "fill.log"))
    return out


def strip_block_labels(a):
    """Delete the pin labels inside the blocks (the LVS runs flat, where a subcell label
    would name a net at the top), keeping the padring's own cells as they are."""
    pr = a.ly.cell("padring")
    keep = {pr.cell_index()} | set(pr.called_cells())
    keys = [a.ly.find_layer(*g.L[k]) for k in g.L if k.endswith("_label")]
    for cell in a.ly.each_cell():
        if cell.cell_index() == a.cell.cell_index() or cell.cell_index() in keep:
            continue
        for li in keys:
            if li is not None:
                cell.shapes(li).clear()


def lvs_core(a, I, runs):
    """LVS of the core: the chip without the padring (top cell eeg_core) against
    gf180/tapeout/chip/eeg_core.spice."""
    a.ly.cell("padring").prune_cell()          # the cell and its subcells (one top cell left)
    a.cell.name = "eeg_core"
    core_labels(a, I)
    return bl.check(a, "eeg_core", NETLISTS, runs, drc=False, lvs=True, ties=TIES)


def build():
    a = A.Assembly(TOP)
    P = pads()
    # the padring (pads, corners, fillers, seal ring, ID cells), not a router block
    pr = a.ly.create_cell("padring")
    src = A.pya.Layout()
    src.read(PADRING)
    pr.copy_tree(src.top_cell())
    a.cell.insert(A.pya.DCellInstArray(pr.cell_index(), A.pya.DTrans(0, 0)))
    I = {"pads": P}
    I["afe"] = a.put("afe_top", *AFE_O, name="AFE")
    I["adc"] = a.put("adc_top", *ADC_O, name="ADC")
    I["dig"] = a.put("eeg_digital_top", *DIG_O, mirror=True, name="DIG")
    I["bias"] = a.put("eeg_bias", *BIAS_O, rot=1, name="BIAS", nets={"VDD": "AVDD", "VSS": "AVSS"})
    I["tm"] = a.put("eeg_testmux", *TM_O, name="TM", grid=GRID)
    I["ref"] = a.put("eeg_ref", *REF_O, name="REF", nets={"VSS": "AVSS"})
    nets = {}
    for n, p in list(power(a, I).items()) + list(dpower(a, I).items()):
        nets.setdefault(n, []).extend(p)
    I["decaps"] = decaps(a, I)
    electrodes(a, I)
    for n, p in signals(a, I).items():
        nets.setdefault(n, []).extend(p)
    return a, I, nets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    ap.add_argument("--place", action="store_true", help="placement and power only, no routing")
    ap.add_argument("--fill", action="store_true",
                    help="dummy fill on the routed chip_top.gds, then DRC with density and antenna")
    args = ap.parse_args()
    runs = os.path.join(HERE, "runs", TOP)
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    t0 = time.time()
    if args.fill:
        full = os.path.join(runs, "chip_top.gds")
        out = fill(full, os.path.join(runs, "chip_top_fill.gds"), runs)
        print(f"filled ({time.time() - t0:.0f} s)")
        print("chip_top (filled) DRC:", g.drc(out, TOP, os.path.join(runs, "drc_fill"), decks="all,-cup") or "clean")
        return
    a, I, nets = build()
    print("decap units", I["decaps"])
    a.write(os.path.join(runs, "chip_place.gds"))
    print({n: len(p) for n, p in sorted(nets.items())})
    if args.place:
        return
    failed = route_all(a, I, nets)
    nofill(a, I)
    strip_block_labels(a)
    full = a.write(os.path.join(runs, "chip_top.gds"))
    print(f"wrote {full} ({time.time() - t0:.0f} s)")
    if failed:
        return
    if args.drc:
        print("chip_top DRC:", g.drc(full, TOP, os.path.join(runs, "drc")) or "clean")
    if args.lvs:
        lvs_core(a, I, runs)


if __name__ == "__main__":
    main()

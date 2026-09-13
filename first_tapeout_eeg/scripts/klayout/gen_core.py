#!/usr/bin/env python3
"""
Batch layout generator for the stage-1 differential core of the EEG OTA
(subckt eeg_fd_ota_core_soft), SkyWater sky130A, KLayout batch flow.

Runs with the pinned venv interpreter (scripts/klayout/.venv), NOT inside the
KLayout app, because the sky130A KLayout pcell generators need
gdsfactory 8.x + kfactory which require Python >= 3.10 (the KLayout.app
bundles Python 3.9).

    scripts/klayout/.venv/bin/python scripts/klayout/gen_core.py

Output: GDSII/eeg_fd_ota_core_soft.gds   (top cell: eeg_fd_ota_core_soft)

Devices (all drawn with the PDK's own generators, unmodified):
  M1/M2  nfet_01v8 L=4 W=240 nf=24  -> one shared-diffusion 50-finger strip
         (48 signal fingers + 2 dummies), gate pattern D ABBAx6 BAABx6 D
         (centroid-balanced, dummy-terminated, mirror-symmetric loading).
  M3/M4  pfet_01v8 L=4 W=48 nf=8   (mirrored placement)
  M5     nfet_01v8 L=4 W=96 nf=16
  RCM1/RCM2   5 MOhm: 50 x res_xhigh_po_0p69 segments (100 kOhm each)
  RLOADP/RLOADN 2 MOhm: 20 segments
Resistor segment: l=34.38um, w=0.69um -> poly_res marker length 34.62-0.12=34.5
  -> R = 2000 Ohm/sq * 34.5/0.69 = 100 kOhm exactly (LVS deck sheet rho).

Pins (text labels, attached per sky130.lvs label rules: met<n>/5 texts):
  INP INN VBP VBN OUTP OUTN VCM_SENSE VCM_REF on met3 buses, VBN on met1,
  VDD18 on met3 bus, VSS on met3 bus (VSS is also the global substrate net
  for LVS: run with -rd lvs_sub=VSS).
"""

import os
import sys
import math

# ----------------------------------------------------------------------------
# PDK + venv setup
# ----------------------------------------------------------------------------
PDK = os.environ.get(
    "SKY130A_PDK",
    "/Users/noah/.volare/volare/sky130/versions/"
    "0fe599b2afb6708d281543108caf8310912f54af/sky130A",
)
PYMACROS = os.path.join(PDK, "libs.tech/klayout/pymacros")
sys.path.insert(0, PYMACROS)

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_GDS = os.path.join(PROJECT, "GDSII", "eeg_fd_ota_core_soft.gds")

import warnings

warnings.filterwarnings("ignore")

import gdsfactory as gf
from loguru import logger

logger.remove()  # silence deprecation spam

# gf.boolean in gdsfactory 8 renamed the operations ("A-B" -> "not" etc.)
_gf_boolean = gf.boolean


def _boolean_compat(A=None, B=None, operation="A-B", **kw):
    table = {"A-B": ("not", A, B), "B-A": ("not", B, A), "A+B": ("or", A, B)}
    op, a, b = table.get(operation, (operation, A, B))
    return _gf_boolean(A=a, B=b, operation=op, **kw)


gf.boolean = _boolean_compat

import klayout.db as kdb

from cells.draw_fet import draw_nfet, draw_pfet
from cells.res_poly_child import res_poly_draw

# ----------------------------------------------------------------------------
# Layers (sky130A)
# ----------------------------------------------------------------------------
L_DIFF = (65, 20)
L_TAP = (65, 44)
L_NWELL = (64, 20)
L_POLY = (66, 20)
L_LICON = (66, 44)
L_LI = (67, 20)
L_MCON = (67, 44)
L_M1 = (68, 20)
L_M1L = (68, 5)
L_VIA1 = (68, 44)
L_M2 = (69, 20)
L_M2L = (69, 5)
L_VIA2 = (69, 44)
L_M3 = (70, 20)
L_M3L = (70, 5)

DBU = 0.001  # um


def u(v):
    """um -> dbu, snapped to the 5 nm manufacturing grid."""
    return int(round(v * 1000.0 / 5.0)) * 5


class Core:
    def __init__(self):
        self.ly = kdb.Layout()
        self.ly.dbu = DBU
        self.top = self.ly.create_cell("eeg_fd_ota_core_soft")
        self._layers = {}

    def layer(self, spec):
        if spec not in self._layers:
            self._layers[spec] = self.ly.layer(spec[0], spec[1])
        return self._layers[spec]

    def box(self, layer, x0, y0, x1, y1, cell=None):
        (cell or self.top).shapes(self.layer(layer)).insert(
            kdb.Box(u(x0), u(y0), u(x1), u(y1))
        )

    def label(self, layer, text, x, y, cell=None):
        (cell or self.top).shapes(self.layer(layer)).insert(kdb.Text(text, u(x), u(y)))

    # -- via helpers (all single-cut or small arrays, conservative enclosures)
    def via1(self, x, y):
        """m1 -> m2 cut at (x, y) center; m1/m2 enclosures drawn by caller's shapes."""
        self.box(L_VIA1, x - 0.075, y - 0.075, x + 0.075, y + 0.075)

    def via2(self, x, y):
        self.box(L_VIA2, x - 0.10, y - 0.10, x + 0.10, y + 0.10)

    def strap_down(self, x, y_m1, y_bus_c):
        """m1 pad at y_m1 -> via1 -> m2 vertical down -> via2 into m3 bus centered y_bus_c."""
        self.box(L_M1, x - 0.17, y_m1 - 0.17, x + 0.17, y_m1 + 0.17)  # via.4a enc
        self.via1(x, y_m1)
        self.box(L_M2, x - 0.19, y_bus_c - 0.15, x + 0.19, y_m1 + 0.17)
        self.via2(x, y_bus_c)

    def strap_up(self, x, y_m1, y_bus_c):
        self.box(L_M1, x - 0.17, y_m1 - 0.17, x + 0.17, y_m1 + 0.17)  # via.4a enc
        self.via1(x, y_m1)
        self.box(L_M2, x - 0.19, y_m1 - 0.17, x + 0.19, y_bus_c + 0.15)
        self.via2(x, y_bus_c)

    def bus_m3(self, x0, x1, yc, w=0.6):
        self.box(L_M3, x0, yc - w / 2, x1, yc + w / 2)
        return yc

    # ------------------------------------------------------------------------
    # Device cells
    # ------------------------------------------------------------------------
    def make_pair(self):
        """M1+M2 common-centroid strip: nf=50 = 2 dummies + 48 signal fingers."""
        cell = self.ly.create_cell("m12_pair")
        draw_nfet(
            cell=cell, l=4.0, w=10.0, nf=50, sd_con_col=5, inter_sd_l=0.5,
            grw=0.17, type="sky130_fd_pr__nfet_01v8", bulk="guard ring",
            con_bet_fin=1, gate_con_pos="alternating", interdig=0, patt="",
        )
        return cell

    def make_tail(self):
        cell = self.ly.create_cell("m5_tail")
        draw_nfet(
            cell=cell, l=4.0, w=6.0, nf=16, sd_con_col=3, inter_sd_l=0.5,
            grw=0.17, type="sky130_fd_pr__nfet_01v8", bulk="guard ring",
            con_bet_fin=1, gate_con_pos="bottom", interdig=0, patt="",
        )
        return cell

    def make_load(self, name):
        cell = self.ly.create_cell(name)
        draw_pfet(
            cell=cell, l=4.0, w=6.0, nf=8, sd_con_col=3, inter_sd_l=0.5,
            grw=0.17, type="sky130_fd_pr__pfet_01v8", bulk="guard ring",
            con_bet_fin=1, gate_con_pos="bottom", interdig=0, patt="",
        )
        return cell

    def make_res_seg(self):
        cell = self.ly.create_cell("res_xhigh_seg")
        res_poly_draw("sky130_fd_pr__res_xhigh_po_0p69").your_res(
            cell, type="sky130_fd_pr__res_xhigh_po_0p69", l=34.38, w=0.69, gr=0
        )
        return cell

    # ------------------------------------------------------------------------
    # Anchor extraction: find the generator's m1 terminal shapes in a cell
    # ------------------------------------------------------------------------
    def scan_m1(self, cell):
        """Return (diff_box, region_strips, gate_pads_top, gate_pads_bot).

        region strips: m1 boxes taller than the diffusion (S/D contact strips),
        sorted by x center.  gate pads: small m1 boxes above/below the diff.
        All coordinates in um, cell-local.
        """
        boxes = []
        for s in cell.shapes(self.layer(L_M1)).each():
            b = s.bbox()
            boxes.append((b.left / 1000.0, b.bottom / 1000.0,
                          b.right / 1000.0, b.top / 1000.0))
        # diff extent
        db = None
        for s in cell.shapes(self.layer(L_DIFF)).each():
            b = s.bbox()
            if db is None:
                db = [b.left, b.bottom, b.right, b.top]
            else:
                db[0] = min(db[0], b.left); db[1] = min(db[1], b.bottom)
                db[2] = max(db[2], b.right); db[3] = max(db[3], b.top)
        diff = [v / 1000.0 for v in db]
        strips, pads_top, pads_bot = [], [], []
        for x0, y0, x1, y1 in boxes:
            h = y1 - y0
            if h > 1.0:  # tall S/D contact strip over the diffusion
                strips.append(((x0 + x1) / 2, y0, y1))
            elif (y0 + y1) / 2 > diff[3]:
                pads_top.append(((x0 + x1) / 2, y0, y1))
            elif (y0 + y1) / 2 < diff[1]:
                pads_bot.append(((x0 + x1) / 2, y0, y1))
        strips.sort()
        pads_top.sort()
        pads_bot.sort()
        return diff, strips, pads_top, pads_bot

    # ------------------------------------------------------------------------
    def ring_bottom_band(self, cell):
        """Locate the bottom guard-ring band (tap layer) of a device cell."""
        diff_db = None
        bands = []
        for s in cell.shapes(self.layer(L_TAP)).each():
            b = s.bbox()
            bands.append((b.left / 1000.0, b.bottom / 1000.0,
                          b.right / 1000.0, b.top / 1000.0))
        # bottom band = widest, lowest
        bands.sort(key=lambda b: b[1])
        return bands[0] if bands else None


def main():
    core = Core()
    ly = core.ly

    pair = core.make_pair()
    tail = core.make_tail()
    loadp = core.make_load("m3_load")
    loadn = core.make_load("m4_load")
    seg = core.make_res_seg()

    # ------------------------------------------------------------------------
    # Placement (um, absolute)
    # ------------------------------------------------------------------------
    # pair: diff y in [0,10]; local diff starts at x=0 -> center strip on x=0
    p_diff, p_strips, p_ptop, p_pbot = core.scan_m1(pair)
    pair_w = p_diff[2] - p_diff[0]
    pair_dx = -(p_diff[0] + p_diff[2]) / 2.0  # shift so diff centered at x=0
    pair_dy = -p_diff[1]
    pair_tr = kdb.Trans(u(pair_dx), u(pair_dy))
    core.top.insert(kdb.CellInstArray(pair.cell_index(), pair_tr))

    assert len(p_strips) == 51, f"pair strips: {len(p_strips)}"
    assert len(p_ptop) + len(p_pbot) == 50, f"pair gate pads: {len(p_ptop)}+{len(p_pbot)}"

    # finger index -> (x, is_top) using analytic finger centers matched to pads
    l, isl, sd_l = 4.0, 0.5, 1.74
    finger_x = [sd_l + l / 2 + i * (l + isl) for i in range(50)]  # cell-local

    def pad_finger(pads):
        out = {}
        for cx, y0, y1 in pads:
            i = min(range(50), key=lambda k: abs(finger_x[k] - cx))
            assert abs(finger_x[i] - cx) < 0.3
            out[i] = (cx, (y0 + y1) / 2)
        return out

    pads_top = pad_finger(p_ptop)
    pads_bot = pad_finger(p_pbot)

    # region strip centers (absolute)
    reg_x = [cx + pair_dx for cx, y0, y1 in p_strips]
    reg_top_y = pair_dy + max(y1 for _, _, y1 in p_strips)      # top of S/D m1 strips
    reg_bot_y = pair_dy + min(y0 for _, y0, _ in p_strips)

    # gate pattern: D ABBAx12 D.  In a shared-diffusion strip, the region
    # between two fingers is a drain iff both fingers belong to the same
    # device (their sources are common TAIL); every finger needs exactly one
    # drain region, which forces strict drain/source alternation and hence
    # the plain ABBA repetition.  Consequence: both end dummies sit on OUTP
    # (they combine into one W=20u device, see core_ref.spice MMDP) - a small
    # documented gate-cap asymmetry on OUTP vs OUTN.
    patt = ["D"] + list("ABBA" * 12) + ["D"]
    assert len(patt) == 50

    gate_net = {"A": "INP", "B": "INN", "D": "VSS"}
    drain_net = {"A": "OUTP", "B": "OUTN"}

    # region nets: r0..r50
    reg_net = []
    for i in range(51):
        if i == 0 or i == 50:
            reg_net.append("TAIL")
            continue
        gl, gr = patt[i - 1], patt[i]
        if gl == gr:
            reg_net.append("TAIL" if gl == "D" else drain_net[gl])
        elif gl == "D":
            reg_net.append(drain_net[gr])
        elif gr == "D":
            reg_net.append(drain_net[gl])
        else:
            reg_net.append("TAIL")

    # ------------------------------------------------------------------------
    # Bus plan (m3 y-centers)
    # ------------------------------------------------------------------------
    Y_OUTN, Y_OUTP, Y_INN_T, Y_INP_T = 12.0, 13.3, 14.6, 15.9
    Y_INP_B, Y_INN_B, Y_VSSD, Y_TAIL = -2.0, -3.0, -4.0, -5.0
    Y_VSS = -6.1
    Y_VSSD_T = 17.2  # top-row dummy gate stub

    x_pair_l, x_pair_r = reg_x[0] - 1.0, reg_x[-1] + 1.0

    # buses (spans must enclose the join-via2 columns at x_pair_l-5.5/-4.5
    # and x_pair_r+4.5/+6.0)
    # OUTP extends left to the P-side resistor banks only, OUTN extends right
    # to the N-side banks only - the extensions must never cross the other
    # side's m3 terminal verticals.
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_OUTN)          # OUTN core
    core.bus_m3(x_pair_r - 1.0, 298.5, Y_OUTN)                     # OUTN extension
    core.bus_m3(x_pair_l - 5.75 - 178.6, x_pair_r + 5.75, Y_OUTP)  # OUTP+ext left
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_INN_T)         # INN top
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_INP_T)         # INP top
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_INP_B)
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_INN_B)
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 6.5, Y_VSSD)
    core.bus_m3(x_pair_l - 5.75, x_pair_r + 5.75, Y_TAIL)
    core.bus_m3(x_pair_l - 6.0, x_pair_r + 6.0, Y_VSS)

    # pair S/D straps
    for i, x in enumerate(reg_x):
        net = reg_net[i]
        if net == "TAIL":
            core.strap_down(x, reg_bot_y + 0.55, Y_TAIL)
        elif net == "OUTN":
            core.strap_up(x, reg_top_y - 0.55, Y_OUTN)
        elif net == "OUTP":
            core.strap_up(x, reg_top_y - 0.55, Y_OUTP)

    # pair gate straps
    for i in range(50):
        net = gate_net[patt[i]]
        if i in pads_bot:
            cx, cy = pads_bot[i]
            ybus = {"INP": Y_INP_B, "INN": Y_INN_B, "VSS": Y_VSSD}[net]
            core.strap_down(cx + pair_dx, cy + pair_dy, ybus)
        else:
            cx, cy = pads_top[i]
            if net == "VSS":
                # dummy finger 49 sits in the top gate row: strap up to a
                # local m3 stub, joined to the VSSD bus further right
                ybus = Y_VSSD_T
            else:
                ybus = {"INP": Y_INP_T, "INN": Y_INN_T}[net]
            core.strap_up(cx + pair_dx, cy + pair_dy, ybus)

    # join top/bottom gate buses (m2 verticals + via2 at ends), outside strip
    for yb, yt, x in ((Y_INP_B, Y_INP_T, x_pair_l - 4.5),
                      (Y_INN_B, Y_INN_T, x_pair_r + 4.5)):
        core.via2(x, yb)
        core.via2(x, yt)
        core.box(L_M2, x - 0.19, yb - 0.15, x + 0.19, yt + 0.15)
    # dummy-gate bus to VSS
    x = x_pair_l - 5.5
    core.via2(x, Y_VSSD)
    core.via2(x, Y_VSS)
    core.box(L_M2, x - 0.19, Y_VSS - 0.15, x + 0.19, Y_VSSD + 0.15)
    # top-row dummy gate stub (finger 49) down to the VSSD bus
    core.bus_m3(reg_x[-2], x_pair_r + 6.3, Y_VSSD_T, w=0.6)
    x = x_pair_r + 6.0
    core.via2(x, Y_VSSD_T)
    core.via2(x, Y_VSSD)
    core.box(L_M2, x - 0.19, Y_VSSD - 0.15, x + 0.19, Y_VSSD_T + 0.15)

    # ------------------------------------------------------------------------
    # M5 tail (centered below the pair)
    # ------------------------------------------------------------------------
    t_diff, t_strips, t_ptop, t_pbot = core.scan_m1(tail)
    assert len(t_strips) == 17 and len(t_pbot) == 16 and not t_ptop
    tail_dx = -(t_diff[0] + t_diff[2]) / 2.0
    tail_dy = -14.0 - t_diff[1]
    tail_tr = kdb.Trans(u(tail_dx), u(tail_dy))
    core.top.insert(kdb.CellInstArray(tail.cell_index(), tail_tr))
    t_reg_x = [cx + tail_dx for cx, _, _ in t_strips]
    t_reg_top = tail_dy + max(y1 for _, _, y1 in t_strips)
    # M5 S/D: even regions -> VSS, odd -> TAIL
    for i, x in enumerate(t_reg_x):
        if i % 2 == 0:
            core.strap_up(x, t_reg_top - 0.55, Y_VSS)
        else:
            core.strap_up(x, t_reg_top - 0.55, Y_TAIL)
    # M5 gate: m1 bar over bottom pads
    pb = t_pbot
    gx0 = pb[0][0] + tail_dx
    gx1 = pb[-1][0] + tail_dx
    gy0 = min(y0 for _, y0, _ in pb) + tail_dy
    gy1 = max(y1 for _, _, y1 in pb) + tail_dy
    core.box(L_M1, gx0 - 2.0, gy0, gx1 + 2.0, gy1)
    core.label(L_M1L, "VBN", (gx0 + gx1) / 2, (gy0 + gy1) / 2)

    # ------------------------------------------------------------------------
    # M3/M4 loads (mirrored about x=0, above the pair)
    # ------------------------------------------------------------------------
    for cell, xc, net_out, name in ((loadp, -60.0, "OUTP", "M3"),
                                    (loadn, +60.0, "OUTN", "M4")):
        d_diff, d_strips, d_ptop, d_pbot = core.scan_m1(cell)
        assert len(d_strips) == 9 and len(d_pbot) == 8 and not d_ptop
        mirror = xc > 0
        if mirror:
            # Trans(2, True): mirror about the vertical axis (x -> dx - x)
            dx = xc + (d_diff[0] + d_diff[2]) / 2.0
            dy = 22.0 - d_diff[1]
            tr = kdb.Trans(2, True, u(dx), u(dy))
        else:
            dx = xc - (d_diff[0] + d_diff[2]) / 2.0
            dy = 22.0 - d_diff[1]
            tr = kdb.Trans(u(dx), u(dy))
        core.top.insert(kdb.CellInstArray(cell.cell_index(), tr))
        tie_ring(core, cell, tr, "top", 31.9, (xc,))
        sx = -1.0 if mirror else 1.0
        d_reg_x = [dx + sx * cx for cx, _, _ in d_strips]
        # S/D straps: even -> VDD18 (up), odd -> OUTx (down)
        for i, x in enumerate(sorted(d_reg_x)):
            if i % 2 == 0:
                core.strap_up(x, dy + max(y1 for _, _, y1 in d_strips) - 0.55, 31.9)
            else:
                core.strap_down(x, dy + min(y0 for _, y0, _ in d_strips) + 0.55,
                                Y_OUTP if net_out == "OUTP" else Y_OUTN)
        # gate bar
        gy0 = dy + min(y0 for _, y0, _ in d_pbot)
        gy1 = dy + max(y1 for _, _, y1 in d_pbot)
        xs = [dx + sx * cx for cx, _, _ in d_pbot]
        core.box(L_M1, min(xs) - 2.0, gy0, max(xs) + 2.0, gy1)

    # join M3/M4 gate bars (VBP) with m1 between the devices
    core.box(L_M1, -60.0, 21.20, 60.0, 21.53)
    core.label(L_M1L, "VBP", 0.0, 21.36)

    # VDD18 bus
    core.bus_m3(-100.0, 100.0, 31.9)
    core.label(L_M3L, "VDD18", 0.0, 31.9)

    # ------------------------------------------------------------------------
    # Resistor banks (vertical segments, horizontal serpentine chain on m1)
    # ------------------------------------------------------------------------
    seg_bb = seg.bbox()
    seg_hw = (seg_bb.right - seg_bb.left) / 2000.0   # half width
    seg_hh = (seg_bb.top - seg_bb.bottom) / 2000.0   # half height
    pad_x = 0.295      # m1 pad half width (measured)
    pad_top = (17.215, 19.320)
    pad_bot = (-19.320, -17.215)

    PITCH = 2.14

    def bank(x0, nseg):
        """Chain of nseg segments starting at x0; returns (termA_x, termB_x)
        absolute x of the two top terminal pads (seg0 top, seg{nseg-1} top)."""
        # urpm marker is 1.27 wide; MR_urpm.SP.1 needs 0.84 spacing
        # between markers -> pitch >= 2.11 (2.14 with margin)
        for i in range(nseg):
            rot = 2 if i % 2 else 0  # 0 or 180 deg (Trans rot codes: 2=R180)
            core.top.insert(kdb.CellInstArray(
                seg.cell_index(), kdb.Trans(rot, False, u(x0 + i * PITCH), 0)))
        for i in range(nseg - 1):
            xa, xb = x0 + i * PITCH, x0 + (i + 1) * PITCH
            if i % 2 == 0:
                core.box(L_M1, xa - pad_x, pad_bot[0], xb + pad_x, pad_bot[1])
            else:
                core.box(L_M1, xa - pad_x, pad_top[0], xb + pad_x, pad_top[1])
        return x0, x0 + (nseg - 1) * PITCH

    Y_VCM_S, Y_VCM_R = 33.65, 35.25
    core.bus_m3(-296.0, 296.0, Y_VCM_S)
    core.bus_m3(-296.0, 296.0, Y_VCM_R)

    # left banks: RCM1 (OUTP side), RLOADP; right mirrored
    a, b = bank(-240.0, 50)     # RCM1
    core_res_connect(core, a, "OUTP", Y_OUTP, pad_top)
    core_res_connect_vcm(core, b, Y_VCM_S, pad_top)
    a, b = bank(-292.0, 20)     # RLOADP
    core_res_connect(core, a, "OUTP", Y_OUTP, pad_top)
    core_res_connect_vcm(core, b, Y_VCM_R, pad_top)
    a, b = bank(240.0 - 49 * 2.14, 50)   # RCM2
    core_res_connect(core, b, "OUTN", Y_OUTN, pad_top)
    core_res_connect_vcm(core, a, Y_VCM_S, pad_top)
    a, b = bank(292.0 - 19 * 2.14, 20)   # RLOADN
    core_res_connect(core, b, "OUTN", Y_OUTN, pad_top)
    core_res_connect_vcm(core, a, Y_VCM_R, pad_top)

    # ------------------------------------------------------------------------
    # Guard-ring ties
    # ------------------------------------------------------------------------
    # pair/tail psub rings -> VSS ; load nwell-tap rings -> VDD18
    # (tie columns sit on drain-only region columns r3/r47, which have no
    #  downward straps, avoiding the bottom-row gate strap columns)
    tie_ring(core, pair, pair_tr, "bottom", Y_VSS, (-99.0, 99.0))
    tie_ring(core, tail, tail_tr, "top", Y_VSS, (-30.0, 30.0))

    # ------------------------------------------------------------------------
    # Pin labels
    # ------------------------------------------------------------------------
    core.label(L_M3L, "OUTP", -110.0, Y_OUTP)
    core.label(L_M3L, "OUTN", 110.0, Y_OUTN)
    core.label(L_M3L, "INP", -100.0, Y_INP_T)
    core.label(L_M3L, "INN", 100.0, Y_INN_T)
    core.label(L_M3L, "VSS", 0.0, Y_VSS)
    core.label(L_M3L, "VCM_SENSE", 0.0, Y_VCM_S)
    core.label(L_M3L, "VCM_REF", 0.0, Y_VCM_R)

    # strip kfactory artifact layers (>65535) before writing
    for li in list(ly.layer_indices()):
        if ly.get_info(li).layer > 65535:
            for c in ly.each_cell():
                c.shapes(li).clear()
            ly.delete_layer(li)

    os.makedirs(os.path.dirname(OUT_GDS), exist_ok=True)
    ly.write(OUT_GDS)
    print("wrote", OUT_GDS)
    print("top bbox (um):", [v / 1000.0 for v in
                             (core.top.bbox().left, core.top.bbox().bottom,
                              core.top.bbox().right, core.top.bbox().top)])


def core_res_connect(core, x, net, y_bus, pad_top):
    """Bank terminal pad (m1, top) to OUTP/OUTN m3 bus extended under the bank."""
    # m3 vertical from bus level up to pad level, then via2/m2/via1 into pad
    y_pad = (pad_top[0] + pad_top[1]) / 2
    core.box(L_M3, x - 0.25, y_bus - 0.3, x + 0.25, y_pad)
    core.via2(x, y_pad - 0.4)
    core.box(L_M2, x - 0.19, y_pad - 0.70, x + 0.19, y_pad - 0.10)
    core.box(L_M1, x - 0.17, y_pad - 0.72, x + 0.17, y_pad - 0.31)
    core.via1(x, y_pad - 0.55)


def core_res_connect_vcm(core, x, y_vcm, pad_top):
    """Bank terminal pad up to a VCM m3 bus."""
    y_pad = (pad_top[0] + pad_top[1]) / 2
    core.strap_up(x, y_pad, y_vcm)


def tie_ring(core, cell, trans, side, y_bus, columns):
    """Contact a guard-ring band (li) and strap it to a bus.

    The generator's guard ring is a tap+licon frame (a single polygon with a
    hole) plus a 0.17um-wide li band (too narrow for mcon).  We isolate the
    bottom/top band by booleans, land a wider li patch on it, then
    mcon -> m1 -> via1 -> m2 strap to the bus.
    trans: the kdb.Trans used to place the cell instance (maps local->abs).
    """
    reg = kdb.Region(cell.begin_shapes_rec(core.layer(L_TAP)))
    if reg.is_empty():
        return
    bb = reg.bbox()  # local, dbu
    band_h = u(0.17)
    if side == "bottom":
        strip = kdb.Box(bb.left, bb.bottom, bb.right, bb.bottom + band_h)
    else:
        strip = kdb.Box(bb.left, bb.top - band_h, bb.right, bb.top)
    band = (reg & kdb.Region(strip)).transformed(trans)
    if band.is_empty():
        return
    b = band.bbox()
    y0, y1 = b.bottom / 1000.0, b.top / 1000.0
    yc = (y0 + y1) / 2
    for cx in columns:
        core.box(L_LI, cx - 0.3, y0 - 0.1, cx + 0.3, y1 + 0.1)
        for k in (-1, 1):
            core.box(L_MCON, cx + k * 0.18 - 0.085, yc - 0.085,
                     cx + k * 0.18 + 0.085, yc + 0.085)
        core.box(L_M1, cx - 0.3, y0 - 0.1, cx + 0.3, y1 + 0.1)
        if side == "top":
            core.strap_up(cx, yc, y_bus)
        else:
            core.strap_down(cx, yc, y_bus)


if __name__ == "__main__":
    main()

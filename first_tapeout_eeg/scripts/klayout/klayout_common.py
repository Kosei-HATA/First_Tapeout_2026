#!/usr/bin/env python3
"""
Shared helpers for the KLayout batch layout generators (gen_core.py,
gen_full2.py) — sky130A, PDK device generators + klayout.db routing.

Importing this module sets up the PDK pymacros path and the gdsfactory 8
compatibility shim (gf.boolean operation names).  Nothing here modifies PDK
files.
"""

import os
import sys
import warnings

PDK = os.environ.get(
    "SKY130A_PDK",
    "/Users/noah/.volare/volare/sky130/versions/"
    "0fe599b2afb6708d281543108caf8310912f54af/sky130A",
)
PYMACROS = os.path.join(PDK, "libs.tech/klayout/pymacros")
if PYMACROS not in sys.path:
    sys.path.insert(0, PYMACROS)

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
L_VIA3 = (70, 44)
L_M4 = (71, 20)
L_M4L = (71, 5)
L_VIA4 = (71, 44)
L_M5 = (72, 20)
L_M5L = (72, 5)
L_CAPM = (89, 44)   # MIM top electrode (m3 bottom plate / m4 top plate)

DBU = 0.001  # um


def u(v):
    """um -> dbu, snapped to the 5 nm manufacturing grid."""
    return int(round(v * 1000.0 / 5.0)) * 5


class Layouter:
    """Layout + drawing helpers (all coordinates in um)."""

    def __init__(self, top_name):
        self.ly = kdb.Layout()
        self.ly.dbu = DBU
        self.top = self.ly.create_cell(top_name)
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
        (cell or self.top).shapes(self.layer(layer)).insert(
            kdb.Text(text, u(x), u(y))
        )

    def place(self, cell, x, y, mirror=False, rot=0, into=None):
        """Place cell instance; mirror=True mirrors about the vertical axis
        (Trans(2, True): local x -> -x)."""
        if mirror:
            tr = kdb.Trans(2, True, u(x), u(y))
        else:
            tr = kdb.Trans(rot, False, u(x), u(y))
        (into or self.top).insert(kdb.CellInstArray(cell.cell_index(), tr))
        return tr

    # -- via helpers (conservative enclosures; centers snapped so the
    # snapped edges keep the exact via size)
    def via1(self, x, y, cell=None):
        x, y = u(x) / 1000.0, u(y) / 1000.0
        self.box(L_VIA1, x - 0.075, y - 0.075, x + 0.075, y + 0.075, cell)

    def via2(self, x, y, cell=None):
        x, y = u(x) / 1000.0, u(y) / 1000.0
        self.box(L_VIA2, x - 0.10, y - 0.10, x + 0.10, y + 0.10, cell)

    def via3(self, x, y, cell=None):
        x, y = u(x) / 1000.0, u(y) / 1000.0
        self.box(L_VIA3, x - 0.10, y - 0.10, x + 0.10, y + 0.10, cell)

    def via4(self, x, y, cell=None):
        """via4 is exactly 0.8x0.8 (deck via4.1a); m4 encloses 0.19, m5 0.31."""
        x, y = u(x) / 1000.0, u(y) / 1000.0
        self.box(L_VIA4, x - 0.4, y - 0.4, x + 0.4, y + 0.4, cell)

    def via1_array(self, x0, y0, x1, y1, cell=None):
        """Fill a region with via1 (0.15, pitch 0.32)."""
        self._via_array(self.via1, 0.15, 0.32, x0, y0, x1, y1, cell)

    def via2_array(self, x0, y0, x1, y1, cell=None):
        self._via_array(self.via2, 0.20, 0.40, x0, y0, x1, y1, cell)

    def via3_array(self, x0, y0, x1, y1, cell=None, pitch=0.40):
        self._via_array(self.via3, 0.20, pitch, x0, y0, x1, y1, cell)

    def _via_array(self, via_fn, size, pitch, x0, y0, x1, y1, cell):
        import math
        nx = max(1, int(math.floor((x1 - x0 - size) / pitch)) + 1)
        ny = max(1, int(math.floor((y1 - y0 - size) / pitch)) + 1)
        sx = x0 + ((x1 - x0) - (nx - 1) * pitch) / 2
        sy = y0 + ((y1 - y0) - (ny - 1) * pitch) / 2
        for i in range(nx):
            for j in range(ny):
                via_fn(sx + i * pitch, sy + j * pitch, cell)

    def strap_down(self, x, y_m1, y_bus_c, cell=None):
        """m1 pad at (x, y_m1) -> via1 -> m2 vertical -> via2 into m3 bus."""
        self.box(L_M1, x - 0.17, y_m1 - 0.17, x + 0.17, y_m1 + 0.17, cell)
        self.via1(x, y_m1, cell)
        self.box(L_M2, x - 0.19, y_bus_c - 0.15, x + 0.19, y_m1 + 0.17, cell)
        self.via2(x, y_bus_c, cell)

    def strap_up(self, x, y_m1, y_bus_c, cell=None):
        self.box(L_M1, x - 0.17, y_m1 - 0.17, x + 0.17, y_m1 + 0.17, cell)
        self.via1(x, y_m1, cell)
        self.box(L_M2, x - 0.19, y_m1 - 0.17, x + 0.19, y_bus_c + 0.15, cell)
        self.via2(x, y_bus_c, cell)

    def bus_m3(self, x0, x1, yc, w=0.6, cell=None):
        self.box(L_M3, x0, yc - w / 2, x1, yc + w / 2, cell)
        return yc

    def join_m3_m2(self, x, ya, yb, cell=None):
        """Vertical m2 link between two m3 buses at ya and yb (via2 ends)."""
        self.via2(x, ya, cell)
        self.via2(x, yb, cell)
        self.box(L_M2, x - 0.19, min(ya, yb) - 0.15, x + 0.19,
                 max(ya, yb) + 0.15, cell)

    # ------------------------------------------------------------------
    # device cells
    # ------------------------------------------------------------------
    def make_nfet(self, name, l, w, nf, gate_con_pos="bottom", bulk="guard ring",
                  sd_con_col=3, inter_sd_l=0.5):
        cell = self.ly.create_cell(name)
        ncol = max(1, min(sd_con_col, int((w + 0.19) // 0.36)))
        draw_nfet(cell=cell, l=l, w=w, nf=nf, sd_con_col=ncol,
                  inter_sd_l=inter_sd_l, grw=0.17,
                  type="sky130_fd_pr__nfet_01v8", bulk=bulk, con_bet_fin=1,
                  gate_con_pos=gate_con_pos, interdig=0, patt="")
        return cell

    def make_pfet(self, name, l, w, nf, gate_con_pos="bottom", bulk="guard ring",
                  sd_con_col=3, inter_sd_l=0.5):
        cell = self.ly.create_cell(name)
        ncol = max(1, min(sd_con_col, int((w + 0.19) // 0.36)))
        draw_pfet(cell=cell, l=l, w=w, nf=nf, sd_con_col=ncol,
                  inter_sd_l=inter_sd_l, grw=0.17,
                  type="sky130_fd_pr__pfet_01v8", bulk=bulk, con_bet_fin=1,
                  gate_con_pos=gate_con_pos, interdig=0, patt="")
        return cell

    def make_res_seg(self, l=34.38):
        """One res_xhigh_po_0p69 segment; marker length l+0.12 um.
        l=34.38 -> exactly 100 kohm under the LVS deck (2000 ohm/sq)."""
        cell = self.ly.create_cell(f"res_xhigh_seg_{str(l).replace('.', 'p')}")
        res_poly_draw("sky130_fd_pr__res_xhigh_po_0p69").your_res(
            cell, type="sky130_fd_pr__res_xhigh_po_0p69", l=l, w=0.69, gr=0)
        return cell

    def res_pads(self, seg_cell):
        """(top_yc, bot_yc) of a res segment's m1 terminal pads, cell-local."""
        ys = []
        for s in seg_cell.shapes(self.layer(L_M1)).each():
            b = s.bbox()
            ys.append((b.bottom + b.top) / 2000.0)
        ys.sort()
        return ys[-1], ys[0]

    # ------------------------------------------------------------------
    # anchors from generated FET cells
    # ------------------------------------------------------------------
    def scan_m1(self, cell):
        """Return (diff_box, strips, pads_top, pads_bot) of a FET cell.

        strips: tall m1 S/D contact boxes, sorted by x center.
        pads_*: small m1 gate-contact boxes above/below the diffusion.
        Cell-local um."""
        boxes = []
        for s in cell.shapes(self.layer(L_M1)).each():
            b = s.bbox()
            boxes.append((b.left / 1000.0, b.bottom / 1000.0,
                          b.right / 1000.0, b.top / 1000.0))
        db = None
        for s in cell.shapes(self.layer(L_DIFF)).each():
            b = s.bbox()
            db = ([b.left, b.bottom, b.right, b.top] if db is None else
                  [min(db[0], b.left), min(db[1], b.bottom),
                   max(db[2], b.right), max(db[3], b.top)])
        diff = [v / 1000.0 for v in db]
        strips, pads_top, pads_bot = [], [], []
        for x0, y0, x1, y1 in boxes:
            if y1 > diff[1] and y0 < diff[3]:
                # overlaps the diffusion -> S/D contact strip/pad
                strips.append(((x0 + x1) / 2, y0, y1))
            elif (y0 + y1) / 2 > diff[3]:
                pads_top.append(((x0 + x1) / 2, y0, y1))
            elif (y0 + y1) / 2 < diff[1]:
                pads_bot.append(((x0 + x1) / 2, y0, y1))
        strips.sort()
        pads_top.sort()
        pads_bot.sort()
        return diff, strips, pads_top, pads_bot

    def tie_ring(self, cell, trans, side, y_bus, columns, into=None):
        """Contact a guard-ring band (mcon + m1 on the ring li) and strap it.

        side: "bottom" or "top" band of the ring.  trans maps cell-local ->
        target coordinates.  The band is located via the tap ring (clean
        rectangle even for tall-W FETs whose S/D strips poke above the
        ring), then refined with the ring li so the mcon lands on li.
        The strap direction follows the bus position.  No new li is drawn
        (avoids li.3 slivers against the band edges).
        """
        tap = kdb.Region(cell.begin_shapes_rec(self.layer(L_TAP)))
        li = kdb.Region(cell.begin_shapes_rec(self.layer(L_LI)))
        if tap.is_empty() or li.is_empty():
            return
        tb = tap.bbox()
        if side == "bottom":
            strip = kdb.Box(tb.left, tb.bottom, tb.right, tb.bottom + u(0.17))
        else:
            strip = kdb.Box(tb.left, tb.top - u(0.17), tb.right, tb.top)
        band_tap = tap & kdb.Region(strip)
        band = (li & band_tap).transformed(trans)
        if band.is_empty():
            return
        # the strip also catches the ring's corner jogs; take the widest
        # polygon = the actual horizontal band
        pieces = sorted(band.each(), key=lambda p: p.bbox().width(),
                        reverse=True)
        b = pieces[0].bbox()
        y0, y1 = b.bottom / 1000.0, b.top / 1000.0
        x0, x1 = b.left / 1000.0, b.right / 1000.0
        yc = (y0 + y1) / 2
        tgt = into or self.top
        for cx in columns:
            if not (x0 + 0.25 < cx < x1 - 0.25):
                raise ValueError(f"tie column {cx} too close to band ends "
                                 f"[{x0}, {x1}]")
            # no new li: mcon lands directly on the ring's own li band
            # (avoids li.3 slivers against the band edges)
            self.box(L_MCON, cx - 0.085, yc - 0.085, cx + 0.085, yc + 0.085, tgt)
            self.box(L_M1, cx - 0.3, y0 - 0.1, cx + 0.3, y1 + 0.1, tgt)
            if y_bus > yc:
                self.strap_up(cx, yc, y_bus, tgt)
            else:
                self.strap_down(cx, yc, y_bus, tgt)

    # ------------------------------------------------------------------
    # resistor banks (res_xhigh_po_0p69 serpentine chains)
    # ------------------------------------------------------------------
    SEG_PAD_X = 0.295
    SEG_PAD_TOP = (17.215, 19.320)
    SEG_PAD_BOT = (-19.320, -17.215)
    SEG_HALF_H = 19.61

    def res_bank(self, into, x0, y0, nseg, seg_cell, ncols=None):
        """Serpentine chain of nseg segments starting at (x0, y0).

        Single row if ncols is None; otherwise rows of ncols segments,
        alternating direction per row, chained by m1 jumpers.
        Returns ((xa, ya), (xb, yb)) absolute terminal pad centers
        (both on top pads)."""
        pitch = 2.0
        row_pitch = 2 * self.SEG_HALF_H + 5.0
        ncols = ncols or nseg
        nrows = (nseg + ncols - 1) // ncols
        pad_yc = (self.SEG_PAD_TOP[0] + self.SEG_PAD_TOP[1]) / 2

        def seg_xy(k):
            """Absolute center of segment k (serpentine order)."""
            row = k // ncols
            col = k % ncols
            if row % 2 == 1:
                col = ncols - 1 - col
            return x0 + col * pitch, y0 + row * row_pitch

        for k in range(nseg):
            cx, cy = seg_xy(k)
            rot = 2 if k % 2 else 0
            into.insert(kdb.CellInstArray(seg_cell.cell_index(),
                                          kdb.Trans(rot, False, u(cx), u(cy))))
        # jumpers within rows
        for k in range(nseg - 1):
            row, nrow = k // ncols, (k + 1) // ncols
            ax, ay = seg_xy(k)
            bx, by = seg_xy(k + 1)
            if row == nrow:
                ya = ay + (self.SEG_PAD_BOT[0] if k % 2 == 0 else self.SEG_PAD_TOP[0])
                yb = ay + (self.SEG_PAD_BOT[1] if k % 2 == 0 else self.SEG_PAD_TOP[1])
                self.box(L_M1, ax - self.SEG_PAD_X, ya, bx + self.SEG_PAD_X, yb, into)
            else:
                # end of row: both pads are top pads (even ncols required)
                assert ncols % 2 == 0, "multi-row banks need even ncols"
                xj = max(ax, bx)
                # jog OUTWARD (away from the bank columns): a straight
                # vertical link at xj would cross the next row's first
                # segment's bottom pad and short it
                xmid = x0 + (ncols - 1) * pitch / 2
                xo = xj + (1.2 if xj >= xmid else -1.2)
                self.box(L_M1, min(xj, xo) - self.SEG_PAD_X,
                         ay + self.SEG_PAD_TOP[0],
                         max(xj, xo) + self.SEG_PAD_X,
                         ay + self.SEG_PAD_TOP[1], into)
                self.box(L_M1, xo - 0.15, ay + self.SEG_PAD_TOP[0],
                         xo + 0.15, by + self.SEG_PAD_TOP[1], into)
                self.box(L_M1, min(xj, xo) - self.SEG_PAD_X,
                         by + self.SEG_PAD_TOP[0],
                         max(xj, xo) + self.SEG_PAD_X,
                         by + self.SEG_PAD_TOP[1], into)
        (sx, sy), (ex, ey) = seg_xy(0), seg_xy(nseg - 1)
        return (sx, sy + pad_yc), (ex, ey + pad_yc)

    # ------------------------------------------------------------------
    # MIM cap array (capm / m3 bottom sheet / m4 top mesh)
    # ------------------------------------------------------------------
    def mim_array(self, into, x0, y0, ncols, nrows, cw=20.0, ch=20.0,
                  via_pitch=1.6):
        """Parallel array of capm MIM units. Returns (bot_pt, top_pt, area, perim)
        with bottom/top terminal access points (m3 / m4) and total A/P in um."""
        pitch_x, pitch_y = cw + 2.5, ch + 2.5
        w_tot = ncols * pitch_x - 2.5
        h_tot = nrows * pitch_y - 2.5
        # bottom plate: m3 sheet with 0.2 enclosure beyond capm field
        self.box(L_M3, x0 - 0.2, y0 - 0.2, x0 + w_tot + 0.2, y0 + h_tot + 0.2, into)
        # bottom exit tab (m3) at the left
        self.box(L_M3, x0 - 4.2, y0 - 0.2, x0 - 0.2, y0 + 3.0, into)
        for r in range(nrows):
            for c in range(ncols):
                cx0 = x0 + c * pitch_x
                cy0 = y0 + r * pitch_y
                self.box(L_CAPM, cx0, cy0, cx0 + cw, cy0 + ch, into)
                # m4 top plate (inset 0.195) merged into a solid sheet below
                self.via3_array(cx0 + 0.3, cy0 + 0.3, cx0 + cw - 0.3,
                                cy0 + ch - 0.3, into, pitch=via_pitch)
        # m4 top plate: one solid sheet inset 0.195 from the capm field,
        # with an exit tab at the top center (avoids m4.5ab notch artifacts
        # that a bar/rail mesh creates under the 3um closing).  The tab is
        # 1.6 tall so a via3 can land on it with its m4 pad fully inside
        # (pad overshoot = notch) while its m3 pad clears the bottom sheet.
        self.box(L_M4, x0 + 0.195, y0 + 0.195,
                 x0 + w_tot - 0.195, y0 + h_tot - 0.195, into)
        xm = x0 + w_tot / 2
        self.box(L_M4, xm - 1.6, y0 + h_tot - 0.195, xm + 1.6,
                 y0 + h_tot + 1.6, into)
        area = ncols * nrows * cw * ch
        perim = ncols * nrows * 2 * (cw + ch)
        return ((x0 - 2.0, y0 + 1.0), (xm, y0 + h_tot + 1.0),
                area, perim)

    def set_top(self, cell):
        """Make an existing cell the only top cell (test-GDS mode)."""
        if self.top.cell_index() != cell.cell_index():
            self.ly.delete_cell(self.top.cell_index())
            self.top = cell

    # ------------------------------------------------------------------
    def finish(self, out_gds):
        for li in list(self.ly.layer_indices()):
            if self.ly.get_info(li).layer > 65535:
                for c in self.ly.each_cell():
                    c.shapes(li).clear()
                self.ly.delete_layer(li)
        os.makedirs(os.path.dirname(out_gds), exist_ok=True)
        self.ly.write(out_gds)
        bb = self.top.bbox()
        print("wrote", out_gds)
        print("top bbox (um):", [v / 1000.0 for v in
                                 (bb.left, bb.bottom, bb.right, bb.top)])


def fet_anchors(lay, cell, x, y):
    """Absolute anchors of a placed (unmirrored) FET cell."""
    diff, strips, ptop, pbot = lay.scan_m1(cell)
    return {
        "strips": [(sx + x, (y0 + y1) / 2 + y) for sx, y0, y1 in strips],
        "g": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in pbot],
        "gt": [(px + x, (y0 + y1) / 2 + y) for px, y0, y1 in ptop],
    }


# ----------------------------------------------------------------------------
# eeg_pseudo_res: A B
#   XMP1 M M A A pfet L=4 W=1 nf=1 ; XMP2 M M B B pfet L=4 W=1 nf=1
# Two diode-connected pfets sharing the floating mid node M.  Each device
# sits in its OWN nwell (bulk = its source), so the guard rings tie to the
# A/B buses, not to VDD.  Gates+drains (M) strap down/up to an M link that
# joins the M bus at the left end; sources strap up to A/B.
# ----------------------------------------------------------------------------
def build_pseudo_res(lay):
    """Build (or fetch) the eeg_pseudo_res cell + its A/B bus anchors.

    Idempotent: if the cell already exists in the layout (built earlier in
    this run, or read in from a block GDS — e.g. gen_pga reads full2, which
    contains one inside eeg_bias_gen), returns the existing cell with
    anchors taken from its A/B labels.  This keeps one definition per
    layout, which the SkipNewCell GDS-merge identity probe relies on."""
    cached = getattr(lay, "_pseudo_res_cache", None)
    if cached is not None:
        return cached
    c = lay.ly.cell("eeg_pseudo_res")
    if c is not None:
        anchors = {}
        for s in c.shapes(lay.layer(L_M3L)).each():
            if s.is_text() and s.text_string in ("A", "B"):
                t = s.text_trans
                anchors[s.text_string] = (t.disp.x / 1000.0, t.disp.y / 1000.0)
        lay._pseudo_res_cache = (c, anchors)
        return c, anchors
    mp1 = lay.make_pfet("pr_p1", 4.0, 1.0, 1)
    mp2 = lay.make_pfet("pr_p2", 4.0, 1.0, 1)
    c = lay.ly.create_cell("eeg_pseudo_res")

    b1 = mp1.bbox()
    w1 = b1.right / 1000.0
    x2 = w1 + 3.0                      # separate nwells: keep rings apart
    lay.place(mp1, 0.0, 0.0, into=c)
    lay.place(mp2, x2, 0.0, into=c)
    g1 = fet_anchors(lay, mp1, 0.0, 0.0)
    g2 = fet_anchors(lay, mp2, x2, 0.0)

    b2 = mp2.bbox()
    top = max(b1.top, b2.top) / 1000.0
    bot = min(b1.bottom, b2.bottom) / 1000.0
    right = (x2 * 1000 + b2.right) / 1000.0

    Y_M = bot - 1.2
    Y_ML, Y_A, Y_B = top + 1.2, top + 2.4, top + 3.6
    XL, XR = -1.0, right + 1.0
    for y in (Y_M, Y_ML, Y_A, Y_B):
        lay.bus_m3(XL, XR, y, cell=c)

    # gates (bottom pads) -> M bus, with m1 offset to a clear via column
    def gate_down(g, x_via):
        x_pad, y_pad = g["g"][0]
        lay.box(L_M1, min(x_pad, x_via) - 0.17, y_pad - 0.17,
                max(x_pad, x_via) + 0.17, y_pad + 0.17, c)
        lay.via1(x_via, y_pad, c)
        lay.box(L_M2, x_via - 0.19, Y_M - 0.15, x_via + 0.19, y_pad + 0.17, c)
        lay.via2(x_via, Y_M, c)

    gate_down(g1, g1["g"][0][0] + 0.6)
    gate_down(g2, g2["g"][0][0] + 0.6)

    # drains -> M link (up), sources -> A/B (up; m2 crosses lower m3 buses)
    lay.strap_up(*g1["strips"][0], Y_ML, c)
    lay.strap_up(*g1["strips"][1], Y_A, c)
    lay.strap_up(*g2["strips"][0], Y_ML, c)
    lay.strap_up(*g2["strips"][1], Y_B, c)

    # M link joins the M bus at the left end
    lay.box(L_M3, XL, Y_M - 0.3, XL + 0.6, Y_ML + 0.3, c)

    # guard rings: mp1 -> A, mp2 -> B (floating nwells follow their source)
    lay.tie_ring(mp1, kdb.Trans(0, False, 0, 0), "bottom", Y_A,
                 (g1["strips"][1][0],), into=c)
    lay.tie_ring(mp2, kdb.Trans(0, False, u(x2), 0), "bottom", Y_B,
                 (g2["strips"][1][0],), into=c)

    lay.label(L_M3L, "A", XR - 0.5, Y_A, c)
    lay.label(L_M3L, "B", XR - 0.5, Y_B, c)
    anchors = {"A": (XR - 0.5, Y_A), "B": (XR - 0.5, Y_B)}
    lay._pseudo_res_cache = (c, anchors)
    return c, anchors

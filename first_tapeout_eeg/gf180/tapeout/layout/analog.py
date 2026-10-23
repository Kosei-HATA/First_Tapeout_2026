"""Analog cells for the block layouts (tracker E1): guarded MOS strips, ppolyf_u_1k
resistor rows and MIM capacitors, each with Metal2 (or Metal4) pins that route.Router
can reach.

strip_cell: one fets.Strip inside a guard ring (substrate tap ring for NMOS; Nwell and
    Nwell-tap ring for PMOS). Every S/D net gets a Metal2 strap along the whole strip
    over the COMP (so it is a wide pin); nets that do not fit over the COMP get straps
    below it, reached by lengthened S/D columns (gate bars then only above). Gate bars
    get a Metal2 pin over them. The ring carries a Metal2 band along its bottom side (the
    bulk pin). No dummy transistors (LVS would see them); the strip ends get dummy poly.
res_cell: n ppolyf_u_1k strips side by side (fets.res_array) with a Metal2 pad of
    1.2 um or more at every head, and a substrate-tap ring.
mim_cell: cap_mim_2f0ff units in a row (PDK pcell, MIM-B); the top plates (Metal5) and
    the bottom plates (Metal4 tabs through Via4 to Metal5) each come down through Via4
    to a Metal4 pad outside the capacitor (the bottom plate itself may only be reached
    through Via4, MIMTM.10), 1.2 um from the bottom-plate Metal4 (MIMTM.1).
"""
import gf180lay as g
import fets as f

RING_W = 0.42
GAP = 0.80            # strip COMP (or bar) to the inner edge of the ring
PIN_MIN = 1.6         # gate pins at least this wide (two 0.8 um router columns)
STRAP_P = 0.80        # Metal2 strap pitch (0.5 wide, 0.3 apart)


class AnalogCell:
    def __init__(self, cell, width, height, pins):
        self.cell, self.width, self.height, self.pins = cell, width, height, pins


def strip_cell(b, name, kind, w, l, seq, gates=None, bulk=None, order=None, label=True):
    """A guarded strip as a cell (lower-left corner of the ring at (0, 0)).
    kind 'n'/'p'; seq as fets.Strip; gates as fets.draw_strip (default: all on top);
    bulk: the ring's net (default VSS for NMOS, VDD for PMOS); order: S/D nets in strap
    order from the bottom (default: first appearance; nets left out get no strap).
    Returns an AnalogCell."""
    return multi_strip_cell(b, name, kind, [dict(w=w, l=l, seq=seq, gates=gates, order=order)], bulk, label)


def _plan(spec):
    """Vertical plan of one strip: (Strip, gates, inside, outside, below, bar_b, bar_t).
    spec["straps"] = {net: k} gives a net k straps over the COMP (k entries in order)."""
    s = f.Strip(spec.get("kind"), spec["w"], spec["l"], spec["seq"])
    nets = spec.get("order") or list(dict.fromkeys(s.sd))
    reps = spec.get("straps") or {}
    nets = [n for n in nets for _ in range(reps.get(n, 1))]
    gnets = list(dict.fromkeys(s.g))
    gates = spec.get("gates") or {n: ("t", k) for k, n in enumerate(gnets)}
    nfit = max(1, int((s.w - 0.6) / STRAP_P) + 1)       # straps that fit over the COMP
    inside, outside = nets[:nfit], nets[nfit:]
    if outside and any(gates[n][0] == "b" for n in gnets):
        raise ValueError("straps below the strip need all gate bars on top")
    lev_t = max([gates[n][1] for n in gnets if gates[n][0] == "t"] + [-1]) + 1
    lev_b = max([gates[n][1] for n in gnets if gates[n][0] == "b"] + [-1]) + 1
    below = len(outside) * STRAP_P + (0.6 if outside else 0.0)
    bar_t = (f.PO_EXT + lev_t * f.GBAR + 0.1) if lev_t else 0.0
    bar_b = (f.PO_EXT + lev_b * f.GBAR + 0.1) if lev_b else 0.0
    return s, gates, inside, outside, max(below, bar_b), bar_t


def multi_strip_cell(b, name, kind, specs, bulk=None, label=True, gap=1.0, bars=None, bar_w=1.2):
    """Several strips of one kind stacked inside one guard ring (and one Nwell for PMOS).
    specs: list of dict(w, l, seq, gates=None, order=None, straps=None), bottom to top.
    Every strip gets its S/D straps across the whole inside of the ring and Metal2 pins
    over its gate bars (see strip_cell).
    bars: {net: [x, ...]} vertical Metal3 bars (bar_w wide, x = left edge, cell
    coordinates) from the net's lowest to its highest strap, with via2 arrays on every
    strap of the net they cross: low-resistance joins for high-current nets, and wide
    Metal3 pins (they replace the net's Metal2 strap pins). Returns an AnalogCell."""
    bulk = bulk or ("VSS" if kind == "n" else "VDD")
    plans = [_plan(dict(sp, kind=kind)) for sp in specs]
    m = GAP + (f.NW_ENC if kind == "p" else 0.0)
    x_s = RING_W + m + 0.5                          # strip COMP left (0.5 for dummy poly)
    width = x_s + max(pl[0].length for pl in plans) + 0.5 + m + RING_W
    c = b.new_cell(name)
    pins = {}
    strap_y = {}
    sx1, sx2 = RING_W + 0.4, width - RING_W - 0.4
    lo_x, hi_x = RING_W + GAP, width - RING_W - GAP
    y = RING_W + m
    for s, gates, inside, outside, below, bar_t in plans:
        y_s = y + below
        w = s.w
        k = len(inside)
        ys_in = [y_s + w / 2 + (j - (k - 1) / 2) * STRAP_P for j in range(k)]
        ys_out = [y_s - 0.6 - (j + 0.5) * STRAP_P for j in range(len(outside))][::-1]
        ext = {}
        yc = f._contacts(y_s + f.CO_ENC, y_s + w - f.CO_ENC)
        col_bot = yc[0] - f.CO / 2 - f.M1_ENC
        for n, yy in zip(outside[::-1], ys_out[::-1]):
            ext[n] = (col_bot - (yy - 0.3), 0.0)
        geo = f.draw_strip(c, s, x_s, y_s, gates=gates, ext=ext, well=False)
        for xd in (x_s - 0.24 - 0.28, x_s + s.length + 0.24):    # dummy poly at both ends
            c.box("poly2", xd, y_s - f.PO_EXT, xd + 0.28, y_s + w + f.PO_EXT)
        # S/D straps across the whole inside of the ring (more router columns per pin)
        for n, yy in list(zip(inside, ys_in)) + list(zip(outside[::-1], ys_out[::-1])):
            x1, x2 = f.strap(c, geo, n, yy, w=0.5, x1=sx1, x2=sx2)
            pins.setdefault(n, []).append(("metal2", x1, yy - 0.25, x2, yy + 0.25))
            strap_y.setdefault(n, []).append(yy)
        # gate pins: Metal2 over each bar, widened to PIN_MIN where the bars of that level
        # leave room (route.Router needs a grid column inside a pin)
        by_level = {}
        for n, bx in geo.bars.items():
            by_level.setdefault(gates[n], []).append((bx[0], n))
        for lev, items in by_level.items():
            items.sort()
            for kk, (_, n) in enumerate(items):
                x1, y1, x2, y2 = geo.bars[n]
                left = geo.bars[items[kk - 1][1]][2] + 0.3 if kk > 0 else lo_x
                right = geo.bars[items[kk + 1][1]][0] - 0.3 if kk + 1 < len(items) else hi_x
                grow = max(0.0, (PIN_MIN - (x2 - x1)) / 2)
                px1, px2 = max(left, x1 - grow), min(right, x2 + grow)
                if px2 - px1 < PIN_MIN:        # against a neighbour: use the room on the other side
                    px1, px2 = max(left, px2 - PIN_MIN), min(right, px1 + PIN_MIN)
                c.box("metal2", px1, y1, px2, y2)
                for j, gn in enumerate(s.g):
                    if gn == n:
                        xg = x_s + s.gx[j] + s.ls[j] / 2
                        c.box("via1", xg - 0.13, (y1 + y2) / 2 - 0.13, xg + 0.13, (y1 + y2) / 2 + 0.13)
                pins.setdefault(n, []).append(("metal2", px1, y1, px2, y2))
        y = y_s + w + bar_t + gap
    height = y - gap + m + RING_W
    for n, xs in (bars or {}).items():
        ys = strap_y.get(n)
        if not ys:
            raise ValueError(f"{name}: no straps of {n} for its bars")
        y1, y2 = min(ys) - 0.25, max(ys) + 0.25
        for x in xs:
            c.box("metal3", x, y1, x + bar_w, y2)
            for yy in ys:
                c.vias("via2", x, yy - 0.25, x + bar_w, yy + 0.25)
        pins[n] = [("metal3", x, y1, x + bar_w, y2) for x in xs]
    # ring (and the Nwell of a PMOS cell, covering the ring)
    f.ring(c, "p" if kind == "n" else "n", 0, 0, width, height, w=RING_W, well=False)
    if kind == "p":
        c.box("nwell", -0.22, -0.22, width + 0.22, height + 0.22)
    # bulk pin: Metal2 along the ring's bottom side, via1 every 0.8 um
    c.box("metal2", 0, 0, width, RING_W)
    x = 0.4
    while x < width - 0.4:
        c.box("via1", x - 0.13, RING_W / 2 - 0.13, x + 0.13, RING_W / 2 + 0.13)
        x += 0.8
    pins.setdefault(bulk, []).append(("metal2", 0, 0, width, RING_W))
    if label:
        for n, segs in pins.items():
            lay, x1, y1, x2, y2 = segs[0]
            c.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return AnalogCell(c, width, height, pins)


def res_cell(b, name, l, w, terms, sub="VSS", gap=f.RES_GAP, pad=1.6, label=True, west_bus=False):
    """Resistor row: len(terms) ppolyf_u_1k strips (body l x w um along x; l may be a
    list of lengths), strip k from terms[k][0] (west) to terms[k][1] (east); Metal2 pads
    (pad um long, outwards) on the heads; substrate-tap ring (net sub). Returns an
    AnalogCell."""
    n = len(terms)
    lmax = max(l) if isinstance(l, (list, tuple)) else l
    if isinstance(l, (list, tuple)) and len(set(l)) > 1:
        gap = max(gap, 1.0)
    m = RING_W + 0.8                         # ring to the RESISTOR layer
    x0 = m + f.RES_RX + pad                  # body start (pads sit west of it)
    y0 = m + f.RES_RY
    c = b.new_cell(name)
    heads = f.res_array(c, x0, y0, l, w, n, gap=gap)
    width = x0 + lmax + f.RES_RX + pad + m
    height = y0 + n * (w + gap) - gap + f.RES_RY + m
    pins = {}
    for k, ((xa, ya), (xb, yb)) in enumerate(heads):
        for (xt, yt), net, sgn in (((xa, ya), terms[k][0], -1), ((xb, yb), terms[k][1], 1)):
            # via1 on the head's Metal1 column, Metal2 pad running outwards
            c.box("via1", xt - 0.13, yt - 0.13, xt + 0.13, yt + 0.13)
            xe = xt + sgn * pad
            c.box("metal2", min(xt, xe) - 0.19, yt - 0.19, max(xt, xe) + 0.19, yt + 0.19)
            pins.setdefault(net, []).append(("metal2", min(xt, xe) - 0.19, yt - 0.19, max(xt, xe) + 0.19, yt + 0.19))
    if west_bus:            # all west ends on one net: a Metal2 bar joins their pads (one pin)
        wnet = terms[0][0]
        if any(t[0] != wnet for t in terms):
            raise ValueError(f"{name}: west_bus needs one west net")
        segs = pins.pop(wnet)
        xb1 = min(sg[1] for sg in segs)
        yb1, yb2 = min(sg[2] for sg in segs), max(sg[4] for sg in segs)
        c.box("metal2", xb1, yb1, xb1 + 1.6, yb2)
        pins[wnet] = [("metal2", xb1, yb1, xb1 + 1.6, yb2)] + segs
    f.ring(c, "p", 0, 0, width, height, w=RING_W, well=False)
    c.box("metal2", 0, 0, width, RING_W)
    x = 0.4
    while x < width - 0.4:
        c.box("via1", x - 0.13, RING_W / 2 - 0.13, x + 0.13, RING_W / 2 + 0.13)
        x += 0.8
    pins.setdefault(sub, []).append(("metal2", 0, 0, width, RING_W))
    if label:
        for net, segs in pins.items():
            lay, x1, y1, x2, y2 = segs[0]
            c.label(lay, net, (x1 + x2) / 2, (y1 + y2) / 2)
    return AnalogCell(c, width, height, pins)


def mim_cell(b, name, side, top, bot, n=1, label=True):
    """n square cap_mim_2f0ff units (side um) in a row between `top` (top plates) and
    `bot` (bottom plates). Pins are Metal4 islands for route.Router:
      below the row: Metal5 straps from the top plates join a Metal5 bar over a Metal4
        island (Via4 array), the `top` pin;
      above the row: a Metal4 tab up from each bottom plate, Via4 to a Metal5 bar that
        also covers a Metal4 island 1.4 um above the tabs (MIMTM.1: 1.2), the `bot` pin.
    The bottom plates are only reached through Via4 (MIMTM.10). Returns an AnalogCell
    with keepout = the capacitor box (no Metal3/Metal4 routing there)."""
    gx = 3.0                                      # between units (bottom plates 1.8 apart)
    c = b.new_cell(name)
    y0 = 4.0                                      # capacitor bottom edge
    xs = [1.0 + k * (side + gx) for k in range(n)]
    xe = xs[-1] + side
    for x in xs:
        c.pcell("cap_mim", {"mim_option": "MIM-B", "metal_level": "M5", "wc": side, "lc": side}, x=x, y=y0)
        a = min(2.0, side / 2)
        # top plate down to the bar
        c.box("metal5", x + side / 2 - a / 2, 1.0, x + side / 2 + a / 2, y0 + 0.5)
        # bottom-plate tab up, Via4 onto the upper bar
        yt = y0 + side + 0.6
        c.box("metal4", x + side / 2 - a / 2, yt - 0.01, x + side / 2 + a / 2, yt + 2.0)
        c.vias("via4", x + side / 2 - a / 2, yt + 1.0, x + side / 2 + a / 2, yt + 2.0)
    yt = y0 + side + 0.6
    # lower bar and island (top plates): 1.6 um tall, 1.4 um below the bottom plates
    c.box("metal5", xs[0], 0.4, xe, 2.0)
    c.vias("via4", xs[0], 0.4, xe, 2.0)
    # upper bar and island (bottom plates): 1.4 um above the tabs
    c.box("metal5", xs[0], yt + 1.0, xe, yt + 5.0)
    c.box("metal4", xs[0], yt + 3.4, xe, yt + 5.0)
    c.vias("via4", xs[0], yt + 3.4, xe, yt + 5.0)
    width, height = xe + 1.0, yt + 5.6
    pins = {top: [("metal4", xs[0], 0.4, xe, 2.0)], bot: [("metal4", xs[0], yt + 3.4, xe, yt + 5.0)]}
    if label:
        for net, segs in pins.items():
            lay, x1, y1, x2, y2 = segs[0]
            c.label(lay, net, (x1 + x2) / 2, (y1 + y2) / 2)
    cell = AnalogCell(c, width, height, pins)
    cell.keepout = (xs[0] - 0.6, y0 - 0.6, xe + 0.6, yt + 2.0)
    # Metal4 must keep 1.2 um from the bottom plates and their tabs (MIMTM.1); the router
    # adds its own 0.28 um spacing (route.KEEP), so the box grows by 0.92 um
    cell.keepout4 = (xs[0] - 1.52, y0 - 1.52, xe + 1.52, yt + 2.92)
    return cell


def moscap_cell(b, name, kind, gate, bulk, lc=28.6, wc=44.0, label=True):
    """One MOS capacitor (PDK pcell cap_nmos / cap_pmos, 3.3 V, with its guard ring):
    gate = `gate`, source/drain, well and ring = `bulk`. The pcell joins both S/D columns
    with a Metal1 bar below the gate; a Metal1 bridge ties that bar to the ring. Pins:
    Metal2 over the gate plate's top edge (gate) and over the S/D bar (bulk). The gate
    is covered with Metal1 by the pcell, so lc stays under 30 um (MSLOT1.1)."""
    c = b.new_cell(name)
    ox, oy = 3.42, 3.73                        # ring's outer corner at (0.4, 0.4)
    inst, _ = c.pcell("cap_nmos" if kind == "n" else "cap_pmos",
                      {"volt": "3.3V", "lc": lc, "wc": wc, "pcmpgr": True}, x=ox, y=oy)
    x1, y1, x2, y2 = [v / 1000 for v in (inst.bbox().left, inst.bbox().bottom, inst.bbox().right, inst.bbox().top)]
    w_comp = lc + 0.88                          # device COMP (gate plus 0.44 S/D each side)
    # S/D bar (pcell: y -1.955..-0.955 under the COMP, x -0.63..w+0.65) to the ring
    xm = ox + w_comp / 2
    c.box("metal1", xm - 4.0, oy - 2.97, xm + 4.0, oy - 1.955)
    pins = {}
    # bulk pin: Metal2 over the S/D bar
    ya, yb = oy - 1.955 + 0.25, oy - 0.955 - 0.25
    c.box("metal2", ox - 0.63, ya - 0.0, ox + w_comp + 0.65, yb)
    x = ox - 0.3
    while x < ox + w_comp + 0.4:
        c.box("via1", x - 0.13, (ya + yb) / 2 - 0.13, x + 0.13, (ya + yb) / 2 + 0.13)
        x += 0.8
    pins[bulk] = [("metal2", ox - 0.63, ya, ox + w_comp + 0.65, yb)]
    # gate pin: Metal2 over the top of the gate plate (pcell Metal1 1.035..lc-0.155 x -0.47..wc+0.47)
    gx1, gx2 = ox + 1.035, ox + lc - 0.155
    gy1, gy2 = oy + wc - 0.4, oy + wc + 0.1
    c.box("metal2", gx1, gy1, gx2, gy2)
    x = gx1 + 0.3
    while x < gx2 - 0.3:
        c.box("via1", x - 0.13, (gy1 + gy2) / 2 - 0.13, x + 0.13, (gy1 + gy2) / 2 + 0.13)
        x += 0.8
    pins[gate] = [("metal2", gx1, gy1, gx2, gy2)]
    if label:
        for net, segs in pins.items():
            lay, a, b_, c_, d = segs[0]
            c.label(lay, net, (a + c_) / 2, (b_ + d) / 2)
    return AnalogCell(c, x2 + 0.4, y2 + 0.4, pins)


def ladder_cell(b, name, nodes, l=2.0, w=2.0, per_row=20, sub="VSS", taps=(), gap=0.6, row_gap=1.2, label=True):
    """Series chain of ppolyf_u_1k resistors (body l x w um) laid out as a serpentine:
    nodes = [n0, n1, ..., nN] names the chain's nodes (N resistors; n0 / nN are the
    ends). Resistors of a row are linked head to head with Metal1; rows turn at
    alternate ends. Each end and each node in `taps` gets a Metal2 pad (pin). The
    heads of neighbouring resistors share one PPLUS box (PP.2), every resistor keeps its
    own SAB box (HRES.10: PPLUS over SAB by 0.1 exactly); one RESISTOR box per row.
    Substrate-tap ring (net sub). Returns an AnalogCell."""
    n = len(nodes) - 1
    rows = [list(range(i, min(i + per_row, n))) for i in range(0, n, per_row)]
    pitch = l + 2 * f.RES_HEAD + gap
    m = RING_W + 0.8 + f.RES_RX
    c = b.new_cell(name)
    ycur = m + 1.6 + f.RES_RY
    pos = {}                                   # resistor index -> (x_body, y_body, direction)
    for r, idx in enumerate(rows):
        yb = ycur
        for j, k in enumerate(idx):
            jj = j if r % 2 == 0 else (per_row - 1 - j)
            xb = m + f.RES_HEAD + 1.6 + jj * pitch
            pos[k] = (xb, yb, 1 if r % 2 == 0 else -1)
        ycur = yb + w + row_gap
    width = m + 1.6 + per_row * pitch + 1.6 + m
    height = ycur - row_gap + f.RES_RY + 1.6 + m
    heads = {}                                 # node index -> list of (x, y) head centres
    for k, (xb, yb, d) in pos.items():
        c.box("poly2", xb - f.RES_HEAD, yb, xb + l + f.RES_HEAD, yb + w)
        c.box("res_mk", xb, yb, xb + l, yb + w)
        c.box("sab", xb - f.RES_SAB_X, yb - f.RES_SAB_Y, xb + l + f.RES_SAB_X, yb + w + f.RES_SAB_Y)
        ys = f._contacts(yb + f.CO_ENC, yb + w - f.CO_ENC)
        ends = []
        for xc in (xb - f.RES_CO - f.CO / 2, xb + l + f.RES_CO + f.CO / 2):
            for y in ys:
                c.box("contact", xc - f.CO / 2, y - f.CO / 2, xc + f.CO / 2, y + f.CO / 2)
            c.box("metal1", xc - f.M1_COL / 2, ys[0] - f.CO / 2 - f.M1_ENC, xc + f.M1_COL / 2, ys[-1] + f.CO / 2 + f.M1_ENC)
            ends.append((xc, yb + w / 2))
        west, east = ends
        a, bnode = (west, east) if d > 0 else (east, west)     # node k at a, node k+1 at b
        heads.setdefault(k, []).append(a)
        heads.setdefault(k + 1, []).append(bnode)
    for r, idx in enumerate(rows):             # PPLUS over the heads, RESISTOR per row
        yb = pos[idx[0]][1]
        xs = sorted(pos[k][0] for k in idx)
        c.box("resistor", xs[0] - f.RES_RX, yb - f.RES_RY, xs[-1] + l + f.RES_RX, yb + w + f.RES_RY)
        for x in xs:
            c.box("pplus", x - f.RES_PP, yb - 0.18, x, yb + w + 0.18)
            c.box("pplus", x + l, yb - 0.18, x + l + f.RES_PP, yb + w + 0.18)
        for x1, x2 in zip(xs, xs[1:]):         # merge the PPLUS between neighbours
            c.box("pplus", x1 + l, yb - 0.18, x2, yb + w + 0.18)
    pins = {}
    for k, hs in heads.items():
        if len(hs) == 2:                       # Metal1 link between the two heads of node k
            (x1, y1), (x2, y2) = hs
            if abs(y1 - y2) < 1e-6:
                c.box("metal1", min(x1, x2) - 0.19, y1 - 0.4, max(x1, x2) + 0.19, y1 + 0.4)
            else:                              # row turn: vertical link at the row end
                c.box("metal1", x1 - 0.19, min(y1, y2) - 0.4, x1 + 0.19, max(y1, y2) + 0.4)
        net = nodes[k]
        if k in (0, n) or net in taps:
            x, y = hs[0] if len(hs) == 1 else ((hs[0][0] + hs[1][0]) / 2, (hs[0][1] + hs[1][1]) / 2)
            if len(hs) == 1:                   # chain end: pad out of the row end
                x2 = x - 1.6 if (pos[0 if k == 0 else n - 1][2] > 0) == (k == 0) else x + 1.6
                c.box("via1", x - 0.13, y - 0.13, x + 0.13, y + 0.13)
                c.box("metal2", min(x, x2) - 0.19, y - 0.19, max(x, x2) + 0.19, y + 0.19)
                pins.setdefault(net, []).append(("metal2", min(x, x2) - 0.19, y - 0.19, max(x, x2) + 0.19, y + 0.19))
            else:
                (x1, y1), (x2, y2) = hs
                c.box("via1", x1 - 0.13, y1 - 0.13, x1 + 0.13, y1 + 0.13)
                xa, xb2 = min(x1, x2) - 0.19, max(x1, x2) + 0.19
                if xb2 - xa < 1.6:
                    xa, xb2 = (xa + xb2) / 2 - 0.8, (xa + xb2) / 2 + 0.8
                c.box("metal2", xa, y1 - 0.19, xb2, y1 + 0.19)
                pins.setdefault(net, []).append(("metal2", xa, y1 - 0.19, xb2, y1 + 0.19))
    f.ring(c, "p", 0, 0, width, height, w=RING_W, well=False)
    c.box("metal2", 0, 0, width, RING_W)
    x = 0.4
    while x < width - 0.4:
        c.box("via1", x - 0.13, RING_W / 2 - 0.13, x + 0.13, RING_W / 2 + 0.13)
        x += 0.8
    pins.setdefault(sub, []).append(("metal2", 0, 0, width, RING_W))
    if label:
        for net, segs in pins.items():
            lay, x1, y1, x2, y2 = segs[0]
            c.label(lay, net, (x1 + x2) / 2, (y1 + y2) / 2)
    return AnalogCell(c, width, height, pins)

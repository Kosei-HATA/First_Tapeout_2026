"""FEOL generators for the GF180 3.3 V devices (tracker E1): MOS finger strips, substrate
and well taps, guard rings, and ppolyf_u_1k resistor arrays.

They are drawn from rectangles instead of the PDK pcells so that every terminal lands
where the routing wants it (the pfet pcell also fails with this gdsfactory). The
dimensions follow the PDK nfet and ppolyf_u_high_Rs_resistor pcells and the DRC deck
(variant gf180mcuD; rule names in the comments).

MOS strip: one COMP band of height w (the finger width) with n poly fingers of length l
crossing it vertically. The sequence seq = [sd0, g1, sd1, ..., gn, sdn] names the net
of every S/D region and every gate, left to right, so shared diffusion, interdigitation
and dummies (gate on the source net) are all written the same way.
  - S/D: one contact column per region, covered by a Metal1 column (0.38 um wide) over
    the COMP; nets join through Metal2 straps across the strip (strap()).
  - Gates: each gate net gets a Metal1 bar above ('t') or below ('b') the COMP at a
    level (0 nearest); its fingers run out to that bar and are contacted there. Bars of
    different nets on one side need different levels where their x ranges overlap.
  - Implant (NPLUS / PPLUS) around the COMP; Nwell around a PMOS strip.
"""
import gf180lay as g

# ---- rules (um)
CO = 0.22            # contact (CO.1)
CO_SP = 0.28         # contact spacing (CO.2b in arrays; CO.2a 0.25)
CO_ENC = 0.08        # COMP and poly enclosure of contact (CO.3, CO.4: 0.07)
CO_GATE = 0.15       # S/D contact to gate (CO.7)
M1_ENC = 0.08        # Metal1 beyond contact (CO.6a: 0.06 at line ends)
M1_COL = CO + 2 * M1_ENC   # 0.38
SD_IN = 2 * CO_GATE + CO   # 0.52, S/D between two gates
SD_END = CO_GATE + CO + CO_ENC   # 0.45, S/D at a strip end (DF.6: 0.24)
PO_EXT = 0.30        # poly beyond COMP (PL.4: 0.22); also COMP to the first gate contact row
PO_PAD = 0.36        # poly pad around a gate contact (CO.3)
GBAR = 0.80          # pitch of the gate-bar levels
IMP_X, IMP_Y = 0.18, 0.24   # implant beyond COMP across / along the gates (NP.5b 0.16, NP.5a 0.23)
NW_ENC = 0.45        # Nwell beyond PCOMP (DF.4c 0.43); Nwell to outside NCOMP (DF.16 0.43)
TAP_W = 0.42         # tap COMP width (one contact row)
TAP_GAP = 0.40       # tap COMP to device COMP of the other implant (NP.3ci / PP.3a 0.16 + implants)
M2_W = 0.50          # default Metal2 strap width (via1 enclosure 0.06 + 0.06)


def _contacts(lo, hi):
    """Centers of the contacts that fit between lo and hi (contact edges inside)."""
    n = int((hi - lo + CO_SP + 1e-9) // (CO + CO_SP))
    if n < 1:
        return []
    span = n * CO + (n - 1) * CO_SP
    x0 = lo + (hi - lo - span) / 2 + CO / 2
    return [x0 + k * (CO + CO_SP) for k in range(n)]


class Strip:
    """A MOS finger strip (see the module doc). kind 'n' or 'p'; w, l in um."""

    def __init__(self, kind, w, l, seq):
        if len(seq) % 2 != 1 or len(seq) < 3:
            raise ValueError("seq must be sd0, g1, sd1, ..., gn, sdn")
        if w < 2 * CO_ENC + CO:
            raise ValueError(f"finger width {w} um too small for a contact")
        self.kind, self.w, self.l, self.seq = kind, w, l, list(seq)
        self.sd, self.g = self.seq[0::2], self.seq[1::2]
        self.n = len(self.g)
        self.gx = [SD_END + k * (l + SD_IN) for k in range(self.n)]   # gate left edges
        self.length = 2 * SD_END + self.n * l + (self.n - 1) * SD_IN
        self.sdx = [SD_END - CO_GATE - CO / 2] + [x + l + CO_GATE + CO / 2 for x in self.gx]

    def devices(self):
        """(gate net, sd left, sd right) per finger"""
        return [(self.g[k], self.sd[k], self.sd[k + 1]) for k in range(self.n)]


class StripGeom:
    """Where a drawn strip's terminals are (absolute um)."""

    def __init__(self, strip, x0, y0):
        self.s, self.x0, self.y0 = strip, x0, y0
        self.cols = []      # (net, x, y1, y2): Metal1 S/D columns
        self.bars = {}      # net -> (x1, y1, x2, y2): Metal1 gate bars
        self.comp = (x0, y0, x0 + strip.length, y0 + strip.w)
        self.outline = None  # (x1, y1, x2, y2) incl. implant, well, gate bars

    def cols_of(self, net):
        return [c for c in self.cols if c[0] == net]


def draw_strip(c, s, x0, y0, gates=None, ext=None, well=True):
    """Draw Strip s with its COMP's lower-left corner at (x0, y0).

    gates: {net: (side, level)}, side 't' or 'b'; default all gates on top, level 0, if
           there is one gate net, else level by first appearance. ('T', y) or ('B', y)
           instead runs the fingers of that net out to the absolute height y without a
           contact (to meet the fingers of another strip: shared gates in logic cells).
    ext:   {net or '*': (bottom, top)}: lengthen those S/D Metal1 columns beyond the
           COMP (only on a side without gate bars).
    well:  draw the Nwell of a PMOS strip (False when the caller draws one well around
           several strips).
    Returns a StripGeom."""
    w, l = s.w, s.l
    nets = list(dict.fromkeys(s.g))
    if gates is None:
        gates = {n: ("t", k) for k, n in enumerate(nets)}
    for n in nets:
        if n not in gates:
            raise ValueError(f"gate net {n} has no bar")
    sides = {gates[n][0] for n in nets}  # contacted bars ('t', 'b') block S/D column extensions
    geo = StripGeom(s, x0, y0)
    c.box("comp", x0, y0, x0 + s.length, y0 + w)
    # ---- gates: fingers, pads, contacts, bars
    span = {}
    for k, net in enumerate(s.g):
        side, lev = gates[net]
        gx = x0 + s.gx[k]
        cx = gx + l / 2
        if side == "T":
            c.box("poly2", gx, y0 - PO_EXT, gx + l, lev)
            continue
        if side == "B":
            c.box("poly2", gx, lev, gx + l, y0 + w + PO_EXT)
            continue
        if side == "t":
            p0 = y0 + w + PO_EXT + lev * GBAR
            p1 = p0 + PO_PAD
            c.box("poly2", gx, y0 - PO_EXT, gx + l, p1)
        else:
            p1 = y0 - PO_EXT - lev * GBAR
            p0 = p1 - PO_PAD
            c.box("poly2", gx, p0, gx + l, y0 + w + PO_EXT)
        if l < PO_PAD:
            c.box("poly2", cx - PO_PAD / 2, p0, cx + PO_PAD / 2, p1)
            xs = [cx]
        else:
            xs = _contacts(gx + CO_ENC - 0.01, gx + l - CO_ENC + 0.01) or [cx]
        cy = (p0 + p1) / 2
        for x in xs:
            c.box("contact", x - CO / 2, cy - CO / 2, x + CO / 2, cy + CO / 2)
        lo, hi = xs[0] - CO / 2 - M1_ENC, xs[-1] + CO / 2 + M1_ENC
        a = span.setdefault(net, [lo, hi, cy])
        a[0], a[1] = min(a[0], lo), max(a[1], hi)
    for net, (lo, hi, cy) in span.items():
        geo.bars[net] = (lo, cy - M1_COL / 2, hi, cy + M1_COL / 2)
        c.box("metal1", *geo.bars[net])
    # bars of different nets at the same level must not touch
    items = sorted(geo.bars.items(), key=lambda kv: (gates[kv[0]], kv[1][0]))  # (contacted bars only)
    for (n1, b1), (n2, b2) in zip(items, items[1:]):
        if gates[n1] == gates[n2] and b2[0] < b1[2] + 0.23:
            raise ValueError(f"gate bars {n1} and {n2} overlap at {gates[n1]}")
    # ---- S/D contacts and Metal1 columns
    ys = _contacts(y0 + CO_ENC, y0 + w - CO_ENC)
    ext = ext or {}
    for k, net in enumerate(s.sd):
        x = x0 + s.sdx[k]
        for y in ys:
            c.box("contact", x - CO / 2, y - CO / 2, x + CO / 2, y + CO / 2)
        y1, y2 = ys[0] - CO / 2 - M1_ENC, ys[-1] + CO / 2 + M1_ENC
        eb, et = ext.get(net, ext.get("*", (0.0, 0.0)))
        if (eb and "b" in sides) or (et and "t" in sides):
            raise ValueError(f"S/D column {net} extended into the gate-bar side")
        y1, y2 = y1 - eb, y2 + et
        c.box("metal1", x - M1_COL / 2, y1, x + M1_COL / 2, y2)
        geo.cols.append((net, x, y1, y2))
    # ---- implant and well
    imp = "nplus" if s.kind == "n" else "pplus"
    c.box(imp, x0 - IMP_X, y0 - IMP_Y, x0 + s.length + IMP_X, y0 + w + IMP_Y)
    if s.kind == "p" and well:
        c.box("nwell", x0 - NW_ENC, y0 - NW_ENC, x0 + s.length + NW_ENC, y0 + w + NW_ENC)
    ylo = min([b[1] for b in geo.bars.values()] + [y0 - (NW_ENC if s.kind == "p" else IMP_Y)]
              + [cl[2] for cl in geo.cols])
    yhi = max([b[3] for b in geo.bars.values()] + [y0 + w + (NW_ENC if s.kind == "p" else IMP_Y)]
              + [cl[3] for cl in geo.cols])
    m = NW_ENC if s.kind == "p" else IMP_X
    geo.outline = (x0 - m, ylo, x0 + s.length + m, yhi)
    return geo


# ----------------------------------------------------------------------------------
# metal helpers
# ----------------------------------------------------------------------------------
def via(c, vname, x, y, pad=0.38):
    """One via centred at (x, y) with square pads (pad um) on both metals."""
    lo = g.METALS[g.VIAS.index(vname)]
    hi = g.METALS[g.VIAS.index(vname) + 1]
    h = g.VIA_SIZE / 2
    c.box(vname, x - h, y - h, x + h, y + h)
    p = pad / 2
    c.box(lo, x - p, y - p, x + p, y + p)
    c.box(hi, x - p, y - p, x + p, y + p)


def via_stack(c, lo, hi, x, y, pad=0.38):
    """Single vias from metal lo up to metal hi at (x, y)."""
    for k in range(g.METALS.index(lo), g.METALS.index(hi)):
        via(c, g.VIAS[k], x, y, pad)


def hw(c, layer, y, x1, x2, w):
    """Horizontal wire centred on y."""
    c.box(layer, min(x1, x2), y - w / 2, max(x1, x2), y + w / 2)


def vw(c, layer, x, y1, y2, w):
    """Vertical wire centred on x."""
    c.box(layer, x - w / 2, min(y1, y2), x + w / 2, max(y1, y2))


def strap(c, geo, net, y, w=M2_W, layer="metal2", x1=None, x2=None):
    """Metal2 strap at height y across the strip, with a via1 on every S/D column of
    `net`; spans the net's columns (or x1..x2). Returns (x1, x2)."""
    cols = geo.cols_of(net) if not isinstance(geo, list) else [cl for gg in geo for cl in gg.cols_of(net)]
    if not cols:
        raise ValueError(f"no S/D column of {net}")
    a = min(cl[1] for cl in cols) - M1_COL / 2 if x1 is None else x1
    b = max(cl[1] for cl in cols) + M1_COL / 2 if x2 is None else x2
    hw(c, layer, y, a, b, w)
    for _, x, y1, y2 in cols:
        if not (y1 + 0.19 <= y <= y2 - 0.19):
            raise ValueError(f"strap {net} at y {y:.3f} misses the column {x:.3f} ({y1:.3f}..{y2:.3f})")
        h = g.VIA_SIZE / 2
        c.box("via1", x - h, y - h, x + h, y + h)
    return a, b


def bar_via(c, geo, net, x=None, up="metal2"):
    """Via from the Metal1 gate bar of `net` up to `up` at x (default: bar centre).
    Returns (x, y)."""
    x1, y1, x2, y2 = geo.bars[net]
    x = (x1 + x2) / 2 if x is None else x
    y = (y1 + y2) / 2
    via_stack(c, "metal1", up, x, y)
    return x, y


# ----------------------------------------------------------------------------------
# taps and guard rings
# ----------------------------------------------------------------------------------
def tap(c, kind, x1, y1, x2, y2, well=True):
    """Tap COMP (x1..x2, y1..y2) with a contact grid and Metal1 over it. kind 'p': substrate
    tap (PCOMP, PPLUS); 'n': Nwell tap (NCOMP, NPLUS, Nwell around it unless well=False).
    Returns the Metal1 box."""
    return _tap(c, kind, x1, y1, x2, y2, (x1, y1, x2, y2), well)


def _tap(c, kind, x1, y1, x2, y2, co_box, well=True):
    c.box("comp", x1, y1, x2, y2)
    c.box("pplus" if kind == "p" else "nplus", x1 - 0.16, y1 - 0.16, x2 + 0.16, y2 + 0.16)
    if kind == "n" and well:   # 0.22 around a 0.42 tap keeps the well 0.86 wide (NW.1a)
        m = max(0.16, (0.86 - min(x2 - x1, y2 - y1)) / 2)
        c.box("nwell", x1 - m, y1 - m, x2 + m, y2 + m)
    cx1, cy1, cx2, cy2 = co_box
    for x in _contacts(cx1 + CO_ENC, cx2 - CO_ENC):
        for y in _contacts(cy1 + CO_ENC, cy2 - CO_ENC):
            c.box("contact", x - CO / 2, y - CO / 2, x + CO / 2, y + CO / 2)
    return c.box("metal1", x1, y1, x2, y2)


def ring(c, kind, x1, y1, x2, y2, w=TAP_W, well=True):
    """Tap ring of COMP width w whose outer edge is the box (x1, y1, x2, y2); the side
    contacts stop short of the corners, which the top and bottom rows contact."""
    tap(c, kind, x1, y1, x2, y1 + w, well)
    tap(c, kind, x1, y2 - w, x2, y2, well)
    ya, yb = y1 + w + CO_SP - CO_ENC, y2 - w - CO_SP + CO_ENC
    _tap(c, kind, x1, y1, x1 + w, y2, (x1, ya, x1 + w, yb), well)
    _tap(c, kind, x2 - w, y1, x2, y2, (x2 - w, ya, x2, yb), well)


# ----------------------------------------------------------------------------------
# ppolyf_u_1k resistors
# ----------------------------------------------------------------------------------
# geometry of the PDK ppolyf_u_high_Rs_resistor pcell (body = the RES_MK box l x w):
RES_HEAD = 0.64      # poly head beyond the body, each end
RES_PP = 0.82        # PPLUS over the head, from the body edge outwards (HRES.10: 0.1 over SAB)
RES_SAB_X, RES_SAB_Y = 0.10, 0.28   # SAB beyond the body (HRES.9 0.28)
RES_RX, RES_RY = 1.04, 0.40         # RESISTOR beyond the body (HRES.4: 0.4 beyond the poly)
RES_CO = 0.35        # body edge to the head contacts (HRES.8: SAB to contact 0.22)
RES_GAP = 0.60       # poly to poly between strips of an array (HRES.3 0.4; SAB merged)


def res_array(c, x0, y0, l, w, n, gap=RES_GAP):
    """n parallel ppolyf_u_1k strips (body l x w um, along x) stacked in y at pitch w + gap,
    sharing one RESISTOR, one SAB and one PPLUS box per end. Body k spans
    x0..x0+l, y0 + k * (w + gap) .. + w. Returns a list of ((xa, y), (xb, y)) Metal1
    terminal centres (west, east) per strip; the Metal1 pads are 0.38 x (w - 0.16)."""
    pitch = w + gap
    yt = y0 + (n - 1) * pitch + w
    c.box("resistor", x0 - RES_RX, y0 - RES_RY, x0 + l + RES_RX, yt + RES_RY)
    c.box("sab", x0 - RES_SAB_X, y0 - RES_SAB_Y, x0 + l + RES_SAB_X, yt + RES_SAB_Y)
    c.box("pplus", x0 - RES_PP, y0 - 0.18, x0, yt + 0.18)
    c.box("pplus", x0 + l, y0 - 0.18, x0 + l + RES_PP, yt + 0.18)
    out = []
    for k in range(n):
        yb = y0 + k * pitch
        c.box("poly2", x0 - RES_HEAD, yb, x0 + l + RES_HEAD, yb + w)
        c.box("res_mk", x0, yb, x0 + l, yb + w)
        ys = _contacts(yb + CO_ENC, yb + w - CO_ENC)
        term = []
        for xc in (x0 - RES_CO - CO / 2, x0 + l + RES_CO + CO / 2):
            for y in ys:
                c.box("contact", xc - CO / 2, y - CO / 2, xc + CO / 2, y + CO / 2)
            c.box("metal1", xc - M1_COL / 2, ys[0] - CO / 2 - M1_ENC, xc + M1_COL / 2, ys[-1] + CO / 2 + M1_ENC)
            term.append((xc, yb + w / 2))
        out.append(tuple(term))
    return out

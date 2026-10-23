"""Logic cells for the analog blocks (tracker E1): inverters, NAND/NOR gates and
transmission gates with the exact device sizes of the netlists (3.3 V devices, L 0.28),
on one row template so that cells abut left to right and rows stack (every other row
mirrored about its rail).

Template (y in um, cell height H = 15.9; x from the cell's left edge):
    0.0 .. 0.6    VSS rail, Metal1 + Metal2, substrate tap under it
    1.7 .. 4.7    NMOS strip (COMP bottom at 1.7, finger width <= 3.0)
    5.25 6.05 6.85  Metal2 tracks for the output and the internal nodes that repeat
    7.7 .. 12.7   PMOS strip (COMP bottom at 7.7, finger width <= 5.0)
    above it      gate bars (Metal1, up to three levels), each covered by a Metal2 pin
    15.3 .. 15.9  VDD rail, Metal1 + Metal2, Nwell tap under it
P and N fingers of the same gate share one poly line, contacted on the bar above the
PMOS strip. VSS sources reach the rail through their Metal1 columns; VDD sources through
a Metal2 strap across the PMOS strip and a Metal2 riser at the cell's left edge. A
transmission gate has its NMOS gate bar below the NMOS strip (G) and its PMOS gate bar
above the PMOS strip (GN).

Pins (LogicCell.pins): Metal2 segments, inputs over their gate bars, outputs and other
S/D nets on the middle tracks, VDD/VSS on the rails. Connections from outside come down
on Metal3 with a via2 anywhere on the segment.
"""
import gf180lay as g
import fets as f

H = 15.9
VSS_RAIL = (0.0, 0.6)
VDD_RAIL = (15.3, 15.9)
YN0, WN_MAX = 1.7, 3.0
YP0, WP_MAX = 7.7, 5.0
TRACKS = (5.25, 6.05, 6.85)          # bottom (N-only nets), middle (shared), top (P-only)
NW_Y0, NW_Y1 = YP0 - f.NW_ENC, VDD_RAIL[1] + 0.2
MX = 0.45                            # cell edge to COMP
L_LOGIC = 0.28
PIN_H = 0.38                         # Metal2 pin height over a gate bar
PITCH = 0.80                         # finger pitch at L 0.28; cell widths are multiples of it,
GATE0 = MX + 0.45 + L_LOGIC / 2      # so with cells at multiples of PITCH every gate centre
                                     # sits at GATE0 + k * PITCH (the router's Metal3 grid)


def _width(strip_len):
    import math
    return math.ceil((strip_len + 2 * MX) / PITCH - 1e-9) * PITCH


class LogicCell:
    def __init__(self, cell, width, pins):
        self.cell, self.width, self.height, self.pins = cell, width, H, pins

    def pin(self, net):
        return self.pins[net][0]


def _rails(c, width):
    """Rails, taps and the Nwell band of a cell. The tap COMP touches the cell's top /
    bottom edge, so the taps of a mirrored neighbour row merge with it; contacts stay
    0.14 um inside the side edges (CO.2a across abutting cells)."""
    for (y1, y2), kind, (t1, t2), (c1, c2) in ((VSS_RAIL, "p", (0.0, 0.44), (0.06, 0.44)),
                                                (VDD_RAIL, "n", (H - 0.44, H), (H - 0.44, H - 0.06))):
        c.box("metal1", 0, y1, width, y2)
        c.box("metal2", 0, y1, width, y2)
        # contact row 0.14 from the edge: 0.28 to the contacts of a mirrored neighbour (CO.2a)
        f._tap(c, kind, 0, t1, width, t2, (0.06, c1, width - 0.06, c2), well=False)
        n = int((width - 0.3) // 0.62)
        for k in range(max(n, 1)):
            x = 0.15 + 0.13 + k * 0.62
            c.box("via1", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
    c.box("nwell", -0.2, NW_Y0, width + 0.2, NW_Y1)   # 0.2 past the edges covers the tap ends (DF.4d)


def filler_cell(b, name, width):
    """Rails, taps and Nwell only (width a multiple of PITCH): fills gaps in a row."""
    c = b.new_cell(name)
    _rails(c, width)
    return LogicCell(c, width, {})


def _levels(spans):
    """Greedy level assignment for gate bars: spans {net: (x1, x2)} -> {net: level}"""
    lev, ends = {}, []
    for net, (a, b) in sorted(spans.items(), key=lambda kv: kv[1][0]):
        for k, e in enumerate(ends):
            if a > e + 0.5:
                lev[net], ends[k] = k, b
                break
        else:
            lev[net] = len(ends)
            ends.append(b)
    return lev


def cmos_cell(b, name, pseq, nseq, wp, wn, ports, rails=("VDD", "VSS")):
    """Static CMOS cell: pseq / nseq are the PMOS / NMOS strip sequences (same gate
    order, see fets.Strip); wp / wn the finger widths; ports the nets that get a label
    (inputs, outputs). Returns a LogicCell."""
    if pseq[1::2] != nseq[1::2]:
        raise ValueError(f"{name}: P and N gate orders differ")
    if wp > WP_MAX or wn > WN_MAX:
        raise ValueError(f"{name}: finger width over the template ({wp}, {wn})")
    vdd, vss = rails
    ps, ns = f.Strip("p", wp, L_LOGIC, pseq), f.Strip("n", wn, L_LOGIC, nseq)
    width = _width(ps.length)
    c = b.new_cell(name)
    _rails(c, width)
    # S/D nets other than the rails that occur more than once get a Metal2 track:
    # N-only nets low, P-only nets high, shared nets (the output) in between
    sd = [n for n in ps.sd + ns.sd if n not in rails]
    pnets, nnets = set(ps.sd), set(ns.sd)
    tracked = sorted({n for n in sd if sd.count(n) > 1},
                     key=lambda n: (0 if n not in pnets else 2 if n not in nnets else 1, n))
    if len(tracked) > 3:
        raise ValueError(f"{name}: more than three tracked nets {tracked}")
    if len(tracked) == 1:
        n = tracked[0]
        slots = [0 if n not in pnets else 2 if n not in nnets else 1]
    else:
        slots = [0, 2] if len(tracked) == 2 else [0, 1, 2]
    ty = {n: TRACKS[k] for n, k in zip(tracked, slots)}
    # gate bars: all above the PMOS strip, levels by overlap
    xs = {}
    for k, gnet in enumerate(ps.g):
        x = MX + ps.gx[k] + L_LOGIC / 2
        a = xs.setdefault(gnet, [x, x])
        a[0], a[1] = min(a[0], x), max(a[1], x)
    lev = _levels({n: tuple(v) for n, v in xs.items()})
    if max(lev.values()) > 2:
        raise ValueError(f"{name}: gate bars need more than three levels")
    pg = {n: ("t", lev[n]) for n in xs}
    ng = {n: ("T", YP0) for n in xs}
    # S/D column extensions (Metal1): VSS down into the rail, tracked nets to their track
    yc_n = f._contacts(YN0 + f.CO_ENC, YN0 + wn - f.CO_ENC)
    yc_p = f._contacts(YP0 + f.CO_ENC, YP0 + wp - f.CO_ENC)
    nbot, ntop = yc_n[0] - f.CO / 2 - f.M1_ENC, yc_n[-1] + f.CO / 2 + f.M1_ENC
    pbot = yc_p[0] - f.CO / 2 - f.M1_ENC
    n_ext, p_ext = {vss: (nbot - 0.3, 0.0)}, {}
    for n in tracked:
        if n in nnets:
            n_ext[n] = (0.0, max(0.0, ty[n] + 0.2 - ntop))
        if n in pnets:
            p_ext[n] = (max(0.0, pbot - (ty[n] - 0.2)), 0.0)
    # a P column reaching down and an N column reaching up at the same x must not meet
    for k in range(len(ps.sd)):
        pn, nn = ps.sd[k], ns.sd[k]
        if pn != nn and pn in p_ext and nn in ty:
            if ty[pn] - 0.2 < ty[nn] + 0.2 + 0.23:
                raise ValueError(f"{name}: columns {pn} / {nn} collide at S/D {k}")
    pgeo = f.draw_strip(c, ps, MX, YP0, gates=pg, ext=p_ext, well=False)
    ngeo = f.draw_strip(c, ns, MX, YN0, gates=ng, ext=n_ext)
    pins = {vdd: [("metal2", 0, VDD_RAIL[0], width, VDD_RAIL[1])],
            vss: [("metal2", 0, VSS_RAIL[0], width, VSS_RAIL[1])]}
    # VDD: strap across the PMOS strip and a riser at the left edge
    ys = YP0 + wp / 2
    f.strap(c, pgeo, vdd, ys, x1=0.0)
    c.box("metal2", 0.0, ys - 0.25, 0.40, VDD_RAIL[0])
    for n in tracked:   # tracks run the full cell width (only their own net is at that y)
        cols = [cl for cl in pgeo.cols + ngeo.cols if cl[0] == n]
        x1, x2 = 0.5, width - 0.5
        f.hw(c, "metal2", ty[n], x1, x2, 0.40)
        for _, x, _, _ in cols:
            c.box("via1", x - 0.13, ty[n] - 0.13, x + 0.13, ty[n] + 0.13)
        pins[n] = [("metal2", x1, ty[n] - 0.2, x2, ty[n] + 0.2)]
    # gate pins: Metal2 over each bar, a via1 per finger
    for n, (x1, y1, x2, y2) in pgeo.bars.items():
        c.box("metal2", x1, y1, x2, y2)
        for k, gnet in enumerate(ps.g):
            if gnet == n:
                x = MX + ps.gx[k] + L_LOGIC / 2
                c.box("via1", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
        pins[n] = [("metal2", x1, y1, x2, y2)]
    for n in list(ports) + [vdd, vss]:
        lay, x1, y1, x2, y2 = pins[n][0]
        c.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return LogicCell(c, width, {n: pins[n] for n in pins if n in ports or n in rails})


def tg_cell(b, name, nf_n, nf_p, wn, wp, a="A", y="Y", gn="G", gp="GN", rails=("VDD", "VSS")):
    """Transmission gate: NMOS (gate gn, bar below) and PMOS (gate gp, bar above) between
    a and y; nf_n / nf_p fingers of wn / wp um. The strips keep their own poly."""
    nf = max(nf_n, nf_p)
    seq = lambda gate, k: [a] + sum(([gate, y if j % 2 == 0 else a] for j in range(k)), [])
    ps, ns = f.Strip("p", wp, L_LOGIC, seq(gp, nf_p)), f.Strip("n", wn, L_LOGIC, seq(gn, nf_n))
    if wp > WP_MAX or wn > WN_MAX:
        raise ValueError(f"{name}: finger width over the template ({wp}, {wn})")
    width = _width(max(ps.length, ns.length))
    c = b.new_cell(name)
    _rails(c, width)
    ty = {y: TRACKS[0], a: TRACKS[2]}
    yc_n = f._contacts(YN0 + f.CO_ENC, YN0 + wn - f.CO_ENC)
    yc_p = f._contacts(YP0 + f.CO_ENC, YP0 + wp - f.CO_ENC)
    ntop = yc_n[-1] + f.CO / 2 + f.M1_ENC
    pbot = yc_p[0] - f.CO / 2 - f.M1_ENC
    n_ext = {n: (0.0, ty[n] + 0.2 - ntop) for n in (a, y)}
    p_ext = {n: (pbot - (ty[n] - 0.2), 0.0) for n in (a, y)}
    pgeo = f.draw_strip(c, ps, MX, YP0, gates={gp: ("t", 0)}, ext=p_ext, well=False)
    ngeo = f.draw_strip(c, ns, MX, YN0, gates={gn: ("b", 0)}, ext=n_ext)
    pins = {rails[0]: [("metal2", 0, VDD_RAIL[0], width, VDD_RAIL[1])],
            rails[1]: [("metal2", 0, VSS_RAIL[0], width, VSS_RAIL[1])]}
    for n in (a, y):
        cols = [cl for cl in pgeo.cols + ngeo.cols if cl[0] == n]
        x1, x2 = 0.5, width - 0.5
        f.hw(c, "metal2", ty[n], x1, x2, 0.40)
        for _, x, _, _ in cols:
            c.box("via1", x - 0.13, ty[n] - 0.13, x + 0.13, ty[n] + 0.13)
        pins[n] = [("metal2", x1, ty[n] - 0.2, x2, ty[n] + 0.2)]
    for geo, s, n in ((pgeo, ps, gp), (ngeo, ns, gn)):
        x1, y1, x2, y2 = geo.bars[n]
        c.box("metal2", x1, y1, x2, y2)
        for k in range(s.n):
            x = MX + s.gx[k] + L_LOGIC / 2
            c.box("via1", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
        pins[n] = [("metal2", x1, y1, x2, y2)]
    for n, segs in pins.items():
        lay, x1, y1, x2, y2 = segs[0]
        c.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return LogicCell(c, width, pins)


# ----------------------------------------------------------------------------------
# sequences of the common gates (same gate order on both strips)
# ----------------------------------------------------------------------------------
def inv_seq(nf, a="A", y="Y", vdd="VDD", vss="VSS"):
    p, n = [vdd], [vss]
    for k in range(nf):
        p += [a, y if k % 2 == 0 else vdd]
        n += [a, y if k % 2 == 0 else vss]
    return p, n


def nand_seq(inputs, nf, y="Y", vdd="VDD", vss="VSS", mid="M"):
    """NAND of inputs with the NMOS stack of the netlists, Y - A - M1 - B - M2 - C - VSS
    (A nearest the output); nf fingers per device, every other repeat mirrored."""
    k = len(inputs)
    order = list(reversed(inputs))                       # VSS side first
    mids = [f"{mid}{i}" for i in range(k - 1, 0, -1)]   # internal nodes, VSS side first
    gates, n = [], [vss]
    for r in range(nf):
        gs = order if r % 2 == 0 else order[::-1]
        nsd = (mids + [y]) if r % 2 == 0 else (mids[::-1] + [vss])
        for j, gname in enumerate(gs):
            n += [gname, nsd[j]]
        gates += gs
    p = [vdd]
    for j, gname in enumerate(gates):
        p += [gname, y if j % 2 == 0 else vdd]
    return p, n


def nor_seq(inputs, nf, y="Y", vdd="VDD", vss="VSS", mid="M"):
    """NOR with the PMOS stack of the netlists, VDD - A - M1 - B - ... - Y (A at VDD);
    NMOS in parallel."""
    k = len(inputs)
    order = list(inputs)                                 # VDD side first
    mids = [f"{mid}{i}" for i in range(1, k)]
    gates, p = [], [vdd]
    for r in range(nf):
        gs = order if r % 2 == 0 else order[::-1]
        psd = (mids + [y]) if r % 2 == 0 else (mids[::-1] + [vdd])
        for j, gname in enumerate(gs):
            p += [gname, psd[j]]
        gates += gs
    n = [vss]
    for j, gname in enumerate(gates):
        n += [gname, y if j % 2 == 0 else vss]
    return p, n


def slow_inv_cell(b, name, wp, lp, wn, ln, a="A", y="Y", rails=("VDD", "VSS")):
    """Inverter with different P and N gate lengths (the slow edge cells): each strip has
    its own gate bar (PMOS above, NMOS below), joined by a Metal2 riser at the right
    edge; the output on the middle track."""
    vdd, vss = rails
    ps, ns = f.Strip("p", wp, lp, [vdd, a, y]), f.Strip("n", wn, ln, [vss, a, y])
    xr = MX + max(ps.length, ns.length) + 0.6      # riser centre
    width = _width(xr + 0.6 - 2 * MX)
    c = b.new_cell(name)
    _rails(c, width)
    ty = TRACKS[1]
    yc_n = f._contacts(YN0 + f.CO_ENC, YN0 + wn - f.CO_ENC)
    yc_p = f._contacts(YP0 + f.CO_ENC, YP0 + wp - f.CO_ENC)
    nbot, ntop = yc_n[0] - f.CO / 2 - f.M1_ENC, yc_n[-1] + f.CO / 2 + f.M1_ENC
    pbot = yc_p[0] - f.CO / 2 - f.M1_ENC
    pgeo = f.draw_strip(c, ps, MX, YP0, gates={a: ("t", 0)}, ext={y: (pbot - (ty - 0.2), 0.0)}, well=False)
    ngeo = f.draw_strip(c, ns, MX, YN0, gates={a: ("b", 0)}, ext={y: (0.0, ty + 0.2 - ntop)})
    # VSS: the NMOS gate bar is below, so the source reaches the rail through Metal2
    yn = YN0 + wn / 2
    f.strap(c, ngeo, vss, yn, x1=0.0)
    c.box("metal2", 0.0, VSS_RAIL[1], 0.40, yn + 0.25)
    ys = YP0 + wp / 2
    f.strap(c, pgeo, vdd, ys, x1=0.0)
    c.box("metal2", 0.0, ys - 0.25, 0.40, VDD_RAIL[0])
    cols = [cl for cl in pgeo.cols + ngeo.cols if cl[0] == y]
    x1, x2 = 0.5, xr - 0.6
    f.hw(c, "metal2", ty, x1, x2, 0.40)
    for _, x, _, _ in cols:
        c.box("via1", x - 0.13, ty - 0.13, x + 0.13, ty + 0.13)
    pins = {vdd: [("metal2", 0, VDD_RAIL[0], width, VDD_RAIL[1])],
            vss: [("metal2", 0, VSS_RAIL[0], width, VSS_RAIL[1])],
            y: [("metal2", x1, ty - 0.2, x2, ty + 0.2)]}
    ybar = []
    for geo in (pgeo, ngeo):
        bx1, by1, bx2, by2 = geo.bars[a]
        c.box("metal2", bx1, by1, xr + 0.2, by2)
        xv = (bx1 + bx2) / 2
        c.box("via1", xv - 0.13, (by1 + by2) / 2 - 0.13, xv + 0.13, (by1 + by2) / 2 + 0.13)
        ybar.append((by1, by2))
    c.box("metal2", xr - 0.2, ybar[1][0], xr + 0.2, ybar[0][1])
    bx1, by1, bx2, by2 = pgeo.bars[a]
    pins[a] = [("metal2", bx1, by1, xr + 0.2, by2)]
    for n in (a, y, vdd, vss):
        lay, x1, y1, x2, y2 = pins[n][0]
        c.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return LogicCell(c, width, pins)


def nmos_cell(b, name, w, l, nf, d, gate, s, rails=("VDD", "VSS")):
    """One NMOS (nf fingers of w x l um) in the template: gate bar above the strip (in the
    middle band), the source to the VSS rail when it is the rail, the other S/D nets on
    Metal2 straps across the strip (one strap fits for w >= 0.5, two for w >= 1.4)."""
    vdd, vss = rails
    seq = [s] + sum(([gate, d if k % 2 == 0 else s] for k in range(nf)), [])
    ns = f.Strip("n", w, l, seq)
    width = _width(ns.length)
    c = b.new_cell(name)
    _rails(c, width)
    yc = f._contacts(YN0 + f.CO_ENC, YN0 + w - f.CO_ENC)
    nbot = yc[0] - f.CO / 2 - f.M1_ENC
    ext = {vss: (nbot - 0.3, 0.0)} if s == vss else {}
    geo = f.draw_strip(c, ns, MX, YN0, gates={gate: ("t", 0)}, ext=ext)
    pins = {vdd: [("metal2", 0, VDD_RAIL[0], width, VDD_RAIL[1])],
            vss: [("metal2", 0, VSS_RAIL[0], width, VSS_RAIL[1])]}
    sd = [n for n in dict.fromkeys(seq[0::2]) if n != vss]
    if len(sd) == 1:
        ys = [YN0 + w / 2]
    elif w >= 1.4:
        ys = [YN0 + w / 2 - 0.33, YN0 + w / 2 + 0.33]
    else:
        raise ValueError(f"{name}: two S/D straps need w >= 1.4")
    for n, y in zip(sd, ys):
        x1, x2 = f.strap(c, geo, n, y, w=0.38, x1=0.5, x2=width - 0.5) if len(sd) == 1 else \
            f.strap(c, geo, n, y, w=0.38)
        pins[n] = [("metal2", x1, y - 0.19, x2, y + 0.19)]
    x1, y1, x2, y2 = geo.bars[gate]
    c.box("metal2", x1, y1, x2, y2)
    for k in range(ns.n):
        x = MX + ns.gx[k] + l / 2
        c.box("via1", x - 0.13, (y1 + y2) / 2 - 0.13, x + 0.13, (y1 + y2) / 2 + 0.13)
    pins[gate] = [("metal2", x1, y1, x2, y2)]
    for n in pins:
        lay, x1, y1, x2, y2 = pins[n][0]
        c.label(lay, n, (x1 + x2) / 2, (y1 + y2) / 2)
    return LogicCell(c, width, pins)


def driver_cell(b, name, wp_tot, wn_tot, wfp=10.0, wfn=8.0, a="A", y="Y", rails=("VDD", "VSS")):
    """Large inverter for the clock drivers: total widths wp_tot / wn_tot (um, L 0.28) in
    fingers of about wfp / wfn um (LVS adds parallel fingers up, so only the totals must
    match the netlist's W). Wide rails (1.2 um, Metal1 + Metal2, taps under them), the
    sources reach them through lengthened S/D columns; the output joins Metal2 straps
    over both strips with 1.2 um Metal3 bars and a Metal4 bus between the strips (pin);
    the input is a Metal1 plate over both gate bars with Metal2 on it (pin).
    Cell (0, 0)..(width, height); returns a LogicCell (height in .height)."""
    vdd, vss = rails

    def split(w_tot, wf):
        """finger count near w_tot / wf whose finger width is on the 5 nm grid"""
        n0 = max(1, round(w_tot / wf))
        for n in sorted(range(max(1, n0 - 3), n0 + 4), key=lambda n: abs(n - n0)):
            wk = w_tot / n
            if abs(wk / 0.005 - round(wk / 0.005)) < 1e-6 and wk <= wf * 1.3:
                return n
        raise ValueError(f"{name}: no on-grid finger width for W {w_tot}")

    nfp, nfn = split(wp_tot, wfp), split(wn_tot, wfn)
    wp, wn = wp_tot / nfp, wn_tot / nfn
    seq = lambda r, n: [r] + sum(([a, y if k % 2 == 0 else r] for k in range(n)), [])
    ps, ns = f.Strip("p", wp, L_LOGIC, seq(vdd, nfp)), f.Strip("n", wn, L_LOGIC, seq(vss, nfn))
    yn0 = 2.0
    yp0 = yn0 + wn + 1.8
    ytop = yp0 + wp + 2.0                         # VDD rail centre line region top
    ox = MX + 1.6                                 # strips start 1.6 um in: a west zone without
    width = _width(max(ps.length, ns.length) + 1.6)   # Metal3 bars, where the input is reached
    c = b.new_cell(name)
    # rails and taps
    for (y1, y2), kind in (((0.0, 1.2), "p"), ((ytop - 1.2, ytop), "n")):
        c.box("metal1", 0, y1, width, y2)
        c.box("metal2", 0, y1, width, y2)
        f._tap(c, kind, 0, y1 + 0.39, width, y2 - 0.39, (0.06, y1 + 0.39, width - 0.06, y2 - 0.39), well=False)
        c.vias("via1", 0.2, y1 + 0.1, width - 0.2, y2 - 0.1)
    c.box("nwell", -0.2, yp0 - f.NW_ENC, width + 0.2, ytop + 0.2)
    yc_n = f._contacts(yn0 + f.CO_ENC, yn0 + wn - f.CO_ENC)
    yc_p = f._contacts(yp0 + f.CO_ENC, yp0 + wp - f.CO_ENC)
    nbot = yc_n[0] - f.CO / 2 - f.M1_ENC
    ptop = yc_p[-1] + f.CO / 2 + f.M1_ENC
    ngeo = f.draw_strip(c, ns, ox, yn0, gates={a: ("t", 0)}, ext={vss: (nbot - 0.6, 0.0)})
    pgeo = f.draw_strip(c, ps, ox, yp0, gates={a: ("b", 0)}, ext={vdd: (0.0, (ytop - 0.6) - ptop)}, well=False)
    # input: Metal1 plate over both bars, Metal2 pin on it
    nb, pb = ngeo.bars[a], pgeo.bars[a]
    x1, x2 = max(nb[0], pb[0]), min(nb[2], pb[2])
    c.box("metal1", 0.2, nb[1], x2, pb[3])
    c.vias("via1", x1, nb[1], x2, pb[3])
    # the Metal2 pin spans both bars and runs to the west edge, where the output bars
    # leave Metal3 free (nothing else is on Metal2 between the strips)
    px1, px2 = 0.2, max(nb[2], pb[2])
    c.box("metal2", px1, nb[1], px2, pb[3])
    pins = {a: [("metal2", px1, nb[1], px2, pb[3])]}
    # output straps (Metal2, 1.0 um) over both strips, then Metal3 bars and the Metal4 bus
    ys = []
    for geo, y0s, w in ((ngeo, yn0, wn), (pgeo, yp0, wp)):
        k = max(1, int((w - 0.4) / 2.0))
        for j in range(k):
            yy = y0s + w / 2 + (j - (k - 1) / 2) * 2.0
            f.strap(c, geo, y, yy, w=1.0)
            ys.append(yy)
    xa = ox + min(ps.sdx[1], ns.sdx[1]) - 0.4
    xb = ox + min(ps.sdx[-1], ns.sdx[-1]) + 0.4
    xs = []
    x = xa
    while x + 1.2 <= xb + 1e-6:
        xs.append(x)
        x += 4.0
    yb1, yb2 = ys[0] - 0.5, ys[-1] + 0.5
    for x in xs:
        c.box("metal3", x, yb1, x + 1.2, yb2)
        for yy in ys:
            c.vias("via2", x, yy - 0.5, x + 1.2, yy + 0.5)
    ybus = (nb[1] + pb[3]) / 2
    c.box("metal4", xs[0], ybus - 1.0, xs[-1] + 1.2, ybus + 1.0)
    for x in xs:
        c.vias("via3", x, ybus - 1.0, x + 1.2, ybus + 1.0)
    pins[y] = [("metal4", xs[0], ybus - 1.0, xs[-1] + 1.2, ybus + 1.0)]
    pins[vdd] = [("metal2", 0, ytop - 1.2, width, ytop)]
    pins[vss] = [("metal2", 0, 0.0, width, 1.2)]
    for n in (a, y, vdd, vss):
        lay, x1_, y1_, x2_, y2_ = pins[n][0]
        c.label(lay, n, (x1_ + x2_) / 2, (y1_ + y2_) / 2)
    cell = LogicCell(c, width, pins)
    cell.height = ytop
    return cell

"""Block assembly helpers (tracker E1): rows of logic cells, block ports, power straps,
routing with route.Router, and the DRC/LVS loop for one block.
"""
import os
import gf180lay as g
import logic as lg
import route


class Placed:
    """A cell instance with its pins in block coordinates."""

    def __init__(self, cell, x, y, mirror, inst_name):
        self.cell, self.x, self.y, self.mirror, self.name = cell, x, y, mirror, inst_name
        self.pins = {}
        for net, segs in cell.pins.items():
            out = []
            for lay, x1, y1, x2, y2 in segs:
                if mirror:
                    y1, y2 = y - y2, y - y1
                else:
                    y1, y2 = y + y1, y + y2
                out.append((lay, x + x1, y1, x + x2, y2))
            self.pins[net] = out


class Rows:
    """Logic rows stacked from y0 upwards; odd rows mirrored so that neighbouring rows
    share a rail (VDD between rows 0 and 1, VSS between rows 1 and 2, ...)."""

    def __init__(self, top, x0, y0):
        self.top, self.x0, self.y0 = top, x0, y0
        self.rows = []      # per row: list of Placed
        self.xcur = []

    def row_y(self, r):
        """(origin y, mirrored) of row r"""
        if r % 2 == 0:
            return self.y0 + r * lg.H, False
        return self.y0 + (r + 1) * lg.H, True

    def add(self, r, cell, inst_name, gap=0.0):
        while len(self.rows) <= r:
            self.rows.append([])
            self.xcur.append(self.x0)
        y, m = self.row_y(r)
        if gap > 0:
            self.fill(r, self.xcur[r] + gap)
        x = self.xcur[r]
        self.top.place(cell.cell, x, y, rot=0, mirror=m)
        p = Placed(cell, x, y, m, inst_name)
        self.rows[r].append(p)
        self.xcur[r] = x + cell.width
        return p

    def fill(self, r, x_to):
        """Filler (rails, taps, Nwell) in row r from the current end to x_to."""
        w = round((x_to - self.xcur[r]) / lg.PITCH) * lg.PITCH
        if w < lg.PITCH - 1e-6:
            return
        name = f"filler_{int(round(w * 1000))}"
        cell = self.top.find_cell(name) if hasattr(self.top, "find_cell") else None
        cell = lg.LogicCell(cell, w, {}) if cell else lg.filler_cell(self.top, name, w)
        y, m = self.row_y(r)
        self.top.place(cell.cell, self.xcur[r], y, rot=0, mirror=m)
        self.xcur[r] += w

    def fill_all(self):
        """Fill every row up to the longest one."""
        end = max(self.xcur)
        for r in range(len(self.rows)):
            self.fill(r, end)

    def width(self):
        return max(self.xcur) - self.x0

    def height(self):
        return len(self.rows) * lg.H

    def rails(self):
        """[(net, y1, y2)] of the Metal2 rails in block coordinates"""
        out = []
        for r in range(len(self.rows)):
            y, m = self.row_y(r)
            for net, (a, b) in (("VSS", lg.VSS_RAIL), ("VDD", lg.VDD_RAIL)):
                y1, y2 = (y - b, y - a) if m else (y + a, y + b)
                out.append((net, y1, y2))
        return out


def power_straps(c, rows, x_vss, x_vdd, names=("VDD", "VSS"), w=1.2):
    """Metal3 straps at x_vss / x_vdd (centres) over the full row height, joined to the
    row rails (extended in Metal2 to the left) by via2 arrays. Returns the strap boxes as
    (net, box) for the router's obstacles and the block pins."""
    vdd, vss = names
    y1, y2 = rows.y0, rows.y0 + rows.height()
    out = []
    for net, x in ((vss, x_vss), (vdd, x_vdd)):
        c.box("metal3", x - w / 2, y1, x + w / 2, y2)
        out.append((net, (x - w / 2, y1, x + w / 2, y2)))
    seen = set()
    for net, a, b in rows.rails():
        key = (net, round(a, 3))
        if key in seen:
            continue
        seen.add(key)
        x = x_vss if net == "VSS" else x_vdd
        c.box("metal2", min(x_vss, x_vdd) - w / 2, a, rows.x0 + 0.5, b)
        c.vias("via2", x - w / 2, a, x + w / 2, b)
    return out


def ports_top(c, names, x_list, y_top, length=1.5):
    """Signal ports: Metal3 stubs ending at the block's top edge, labelled. Returns
    {net: ('metal3', box)}."""
    out = {}
    for n, x in zip(names, x_list):
        c.box("metal3", x - 0.15, y_top - length, x + 0.15, y_top)
        c.label("metal3", n, x, y_top - 0.3)
        out[n] = ("metal3", x - 0.15, y_top - length, x + 0.15, y_top)
    return out


def route_nets(c, region, nets, obstacles=(), rounds=6):
    """Route {net: [pin, ...]} inside region (x1, y1, x2, y2) on Metal3/Metal4 and draw it.
    obstacles: [(layer, x1, y1, x2, y2)]. Raises if a net fails."""
    r = route.Router(*region)
    for lay, *box in obstacles:
        r.obstacle(lay, *box)
    failed = r.route(nets, rounds=rounds)
    if failed:
        raise RuntimeError(f"unrouted nets: {failed}")
    r.draw(c)
    return r


def check(b, top, netlists, outdir, drc=True, lvs=True):
    """Write the block, run DRC and LVS against the netlists; prints and returns results."""
    os.makedirs(outdir, exist_ok=True)
    b.strip_sublabels()
    gds = b.write(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gds", f"{top}.gds"))
    res = {}
    if drc:
        res["drc"] = g.drc(gds, top, outdir)
        print(f"{top} DRC:", res["drc"] or "clean")
    if lvs:
        cdl = os.path.join(outdir, f"{top}.cdl")
        open(cdl, "w").write(g.to_cdl(netlists, top))
        ok, lines = g.lvs(gds, cdl, top, outdir)
        res["lvs"] = ok
        print(f"{top} LVS:", "match" if ok else "MISMATCH", *([] if ok else lines), sep="\n  " if not ok else " ")
    return res


class Shelves:
    """Shelf placement of cells (AnalogCell / LogicCell) from (x0, y0) upwards, left to
    right within max_w; gap between cells. place() returns a Placed."""

    def __init__(self, top, x0, y0, max_w, gap=2.0):
        self.top, self.x0, self.y0, self.max_w, self.gap = top, x0, y0, max_w, gap
        self.x, self.y, self.h = x0, y0, 0.0
        self.placed = []

    def newline(self):
        if self.h > 0:
            self.y += self.h + self.gap
        self.x, self.h = self.x0, 0.0

    def place(self, cell, inst_name, newline=False):
        h = getattr(cell, "height", lg.H)
        if newline or (self.x > self.x0 and self.x + cell.width > self.x0 + self.max_w):
            self.newline()
        self.top.place(cell.cell, self.x, self.y)
        p = Placed(cell, self.x, self.y, False, inst_name)
        if hasattr(cell, "keepout"):
            k = cell.keepout
            p.keepout = (self.x + k[0], self.y + k[1], self.x + k[2], self.y + k[3])
        self.placed.append(p)
        self.x += cell.width + self.gap
        self.h = max(self.h, h)
        return p

    def top_y(self):
        return self.y + self.h


def cell_shapes(p, layer):
    """Boxes (x1, y1, x2, y2) of `layer` inside placed cell p, in block coordinates
    (all levels of its hierarchy)."""
    c = p.cell.cell
    li = c.ly.find_layer(*g.L[layer])
    out = []
    if li is None:
        return out
    it = c.cell.begin_shapes_rec(li)
    while not it.at_end():
        bb = it.shape().bbox().transformed(it.trans())
        x1, y1, x2, y2 = bb.left / 1000, bb.bottom / 1000, bb.right / 1000, bb.top / 1000
        if p.mirror:
            y1, y2 = p.y - y2, p.y - y1
        else:
            y1, y2 = p.y + y1, p.y + y2
        out.append((p.x + x1, y1, p.x + x2, y2))
        it.next()
    return out


class Unit:
    """A unit cell (one element of an array): parts stacked bottom to top above a set of
    Metal4 bus rows that span the whole width, so that units placed side by side join
    their buses; the unit's own nets are routed inside it (route.Router) with the bus
    rows as fixed shapes of their nets. Routed shapes keep `margin` from the side edges.
    Port nets get a Metal3 stub at the top edge."""

    def __init__(self, cell, width, height, pins, ports):
        self.cell, self.width, self.height, self.pins, self.ports = cell, width, height, pins, ports


def unit_cell(b, name, parts, buses, ports, width=None, gap=1.2, margin=0.8, bus_w=1.0, bus_gap=0.8,
              px=lg.PITCH, gx0=None):
    """parts: [(cell, {cell pin: net}, x)] bottom to top (x = left offset, None: 1.0 um);
    buses: [net] bottom to top; ports: [net] (top-edge Metal3 stubs, spread over the width).
    Returns a Unit; its .pins hold the bus rows ('metal4') and the port stubs ('metal3')."""
    top = b.new_cell(name)
    c = g.Cell(b.ly, top.cell) if not isinstance(top, g.Cell) else top
    nets, fixed = {}, []
    y = 0.6
    bus_y = {}
    w_max = max(cell.width + (x if x is not None else 1.0) for cell, _, x in parts) + margin + 0.2
    width = max(width or 0.0, w_max)
    for n in buses:
        c.box("metal4", 0.0, y, width, y + bus_w)
        bus_y[n] = (y, y + bus_w)
        fixed.append(("metal4", (0.0, y, width, y + bus_w), n))
        nets.setdefault(n, []).append(("metal4", 0.0, y, width, y + bus_w))
        y += bus_w + bus_gap
    y += gap
    placed = []
    for cell, cmap, x in parts:
        x = 1.0 if x is None else x
        c.place(cell.cell, x, y)
        p = Placed(cell, x, y, False, cell.cell.name)
        placed.append(p)
        for pn, segs in p.pins.items():
            if pn in cmap:
                nets.setdefault(cmap[pn], []).extend(segs)
        y += getattr(cell, "height", lg.H) + gap
    height = y + 2.0
    pins = {n: [("metal4", 0.0, a, width, bb)] for n, (a, bb) in bus_y.items()}
    gx0 = (margin + 0.24) if gx0 is None else gx0
    snap = lambda x: gx0 + round((x - gx0) / px) * px
    for k, n in enumerate(ports):
        x = snap(margin + (width - 2 * margin) * (k + 0.5) / len(ports))
        c.box("metal3", x - 0.19, height - 1.6, x + 0.19, height)
        fixed.append(("metal3", (x - 0.19, height - 1.6, x + 0.19, height), n))
        nets.setdefault(n, []).append(("metal3", x - 0.19, height - 1.6, x + 0.19, height))
        pins[n] = [("metal3", x - 0.19, height - 1.6, x + 0.19, height)]
    r = route.Router(gx0, 0.0, width - margin, height - 0.2, px=px)
    # keep the router's shapes clear of the side edges: block the first/last columns
    r.obstacle("metal3", -1.0, -1.0, margin - 0.2, height + 1.0)
    r.obstacle("metal4", -1.0, -1.0, margin - 0.2, height + 1.0)
    for lay, box, n in fixed:
        r.obstacle(lay, *box, n)
    for p in placed:   # wires already inside the parts (e.g. driver buses) are obstacles
        for lay in ("metal3", "metal4"):
            for bx in cell_shapes(p, lay):
                r.obstacle(lay, *bx)
    failed = r.route({n: v for n, v in nets.items() if len(v) > 1}, rounds=6)
    if failed:
        raise RuntimeError(f"{name}: unrouted {failed}")
    r.draw(c)
    return Unit(c, width, height, pins, ports)

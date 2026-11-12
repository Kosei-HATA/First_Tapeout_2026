"""Assembly of hard blocks (tracker E4/E7): the GDS of finished blocks (gds/<name>.gds, from
the block scripts) placed into a larger layout with transforms, their pins read back from
the pin labels, obstacles for route.Router around them, and helpers for the wide wiring
drawn by hand (Metal4 / Metal5 straps and via stacks).

Pins. A block's ports are labels on its top cell (metal<n>_label) over a shape of that
metal. The pin is the shape under the label: a strap or bus (a shape spanning most of the
block's height or width) when there is one, else the smallest shape there (a port stub).

Obstacles for the router (Metal3 / Metal4). Inside a block the router may not go: the
block's outline, less a margin band along its edges, is one obstacle per layer; in the
margin band every Metal3 / Metal4 shape of the block is an obstacle of its own (named
for its net when it is a pin), and every via3 a via keep-out. Port stubs reach the edge,
so the router meets them in the band. MIM arrays block Metal3 and Metal4 over their whole
outline (Metal4 1.2 um beyond it, MIMTM.1).
"""
import os
import gf180lay as g
import route

pya = g.pya
HERE = os.path.dirname(os.path.abspath(__file__))
GDS = os.path.join(HERE, "gds")
MARGIN = 6.0
METAL_OF = {(34, 10): "metal1", (36, 10): "metal2", (42, 10): "metal3", (46, 10): "metal4", (81, 10): "metal5"}


def _box_um(b):
    return b.left / 1000, b.bottom / 1000, b.right / 1000, b.top / 1000


def lef_pins(path):
    """Pins of a LibreLane macro from its LEF: {name: [(layer key, (x1, y1, x2, y2))]}."""
    pins, name, layer = {}, None, None
    for line in open(path):
        w = line.split()
        if not w:
            continue
        if w[0] == "PIN":
            name = w[1]
        elif w[0] == "END" and len(w) > 1 and w[1] == name:
            name = None
        elif name and w[0] == "LAYER":
            layer = w[1].lower()
        elif name and w[0] == "RECT" and layer in g.METALS:
            x1, y1, x2, y2 = map(float, w[1:5])
            pins.setdefault(name, []).append((layer, (x1, y1, x2, y2)))
    return pins


class Inst:
    """A placed block: name, cell, transform, outline and pins in assembly coordinates."""

    def __init__(self, name, block, cell, trans, bbox, pins, mim=False):
        self.name, self.block, self.cell, self.trans, self.bbox, self.pins, self.mim = \
            name, block, cell, trans, bbox, pins, mim

    def pin(self, net, layer=None):
        segs = [p for p in self.pins.get(net, []) if layer is None or p[0] == layer]
        if not segs:
            raise KeyError(f"{self.name}: no pin {net} {layer or ''}")
        return segs[0]


class Assembly(g.Block):
    def __init__(self, name):
        super().__init__(name)
        self.cache = {}
        self.insts = []
        self.manual = []        # (layer, box, net): hand-drawn Metal3/4 shapes (router fixed shapes)
        self.via3s = []         # boxes of hand-drawn via3 arrays (router via keep-outs)

    # ---- blocks
    def load(self, block, path=None):
        """Copy gds/<block>.gds (top cell <block>) into this layout once; returns
        (cell, local pins {net: [(layer, box)]}, local bbox)."""
        if block in self.cache:
            return self.cache[block]
        path = path or os.path.join(GDS, block + ".gds")
        src = pya.Layout()
        src.read(path)
        top = src.cell(block) if src.has_cell(block) else src.top_cells()[0]
        cell = self.ly.create_cell(block)
        cell.copy_tree(top)
        bb = _box_um(top.bbox())
        pins = {}
        span_x, span_y = bb[2] - bb[0], bb[3] - bb[1]
        for li in src.layer_indexes():
            info = src.get_info(li)
            metal = METAL_OF.get((info.layer, info.datatype))
            if metal is None:
                continue
            ml = src.find_layer(*g.L[metal])
            for sh in top.shapes(li).each():
                if not sh.is_text():
                    continue
                pt = sh.text.trans.disp
                cands = []
                it = top.begin_shapes_rec(ml)
                while not it.at_end():
                    b = it.shape().bbox().transformed(it.trans())
                    if b.left <= pt.x <= b.right and b.bottom <= pt.y <= b.top:
                        cands.append(_box_um(b))
                    it.next()
                if not cands:
                    continue
                long_ = [c for c in cands if (c[3] - c[1]) > 0.8 * span_y or (c[2] - c[0]) > 0.8 * span_x]
                box = max(long_, key=lambda c: (c[2] - c[0]) * (c[3] - c[1])) if long_ else \
                    min(cands, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
                pins.setdefault(sh.text.string, []).append((metal, box))
        lef = os.path.splitext(path)[0] + ".lef"
        if os.path.exists(lef):            # a LibreLane macro: the LEF has the exact pins
            pins = lef_pins(lef)
        self.cache[block] = (cell, pins, bb, src, top)
        return self.cache[block]

    def put(self, block, x, y, rot=0, mirror=False, name=None, nets=None, mim=False, path=None, grid=None):
        """Place a block with its local origin at (x, y) um; rot in 90-degree steps, mirror
        about the x axis before the rotation (KLayout's Trans). nets renames pins
        ({block port: assembly net}). grid = (x0, px, y0, py) of the router: x and y are
        moved by less than half a pitch so that the block's narrow Metal3 port stubs sit on
        router columns and its narrow Metal4 stubs on router rows (rot = 0, no mirror).
        Returns the Inst."""
        cell, pins, bb, src, top = self.load(block, path)
        if grid is not None and rot == 0 and not mirror:
            gx0, px, gy0, py = grid
            xs = {round(((b[0] + b[2]) / 2) % px, 3) for segs in pins.values() for lay, b in segs
                  if lay == "metal3" and b[2] - b[0] < 0.5 and b[3] - b[1] >= 1.0}
            ys = {round(((b[1] + b[3]) / 2) % py, 3) for segs in pins.values() for lay, b in segs
                  if lay == "metal4" and b[3] - b[1] < 0.5 and b[2] - b[0] >= 1.0}
            if len(xs) > 1 or len(ys) > 1:
                raise ValueError(f"{block}: port stubs on several grid phases {xs} {ys}")
            if xs:
                d = (gx0 - x - xs.pop()) % px
                x += d if d <= px / 2 else d - px
            if ys:
                d = (gy0 - y - ys.pop()) % py
                y += d if d <= py / 2 else d - py
            x, y = round(x / 0.005) * 0.005, round(y / 0.005) * 0.005     # 5 nm grid
        t = pya.DCplxTrans(1.0, rot * 90.0, mirror, x, y)
        self.cell.insert(pya.DCellInstArray(cell.cell_index(), t))

        def tb(box):
            b = pya.DBox(*box).transformed(t)
            return (round(b.left, 4), round(b.bottom, 4), round(b.right, 4), round(b.top, 4))
        out = {}
        for n, segs in pins.items():
            net = (nets or {}).get(n, n)
            out.setdefault(net, []).extend((lay,) + tb(box) for lay, box in segs)
        inst = Inst(name or block, block, cell, t, tb(bb), out, mim)
        inst.src, inst.srctop, inst.bbox_local = src, top, bb
        self.insts.append(inst)
        return inst

    # ---- router obstacles
    def obstacles(self, r, skip=()):
        """Register every placed block with the router r (see the module doc)."""
        for inst in self.insts:
            if inst.name in skip:
                continue
            x1, y1, x2, y2 = inst.bbox
            if inst.mim:
                r.obstacle("metal3", x1, y1, x2, y2)
                r.obstacle("metal4", x1 - 1.2, y1 - 1.2, x2 + 1.2, y2 + 1.2)
                continue
            r.obstacle("metal3", x1 + MARGIN, y1 + MARGIN, x2 - MARGIN, y2 - MARGIN)
            r.obstacle("metal4", x1 + MARGIN, y1 + MARGIN, x2 - MARGIN, y2 - MARGIN)
            pinboxes = {}
            for n, segs in inst.pins.items():
                for lay, *box in segs:
                    pinboxes[(lay, tuple(round(v, 3) for v in box))] = n
            inner = pya.DBox(x1 + MARGIN + 0.5, y1 + MARGIN + 0.5, x2 - MARGIN - 0.5, y2 - MARGIN - 0.5)
            for lay in ("metal3", "metal4", "via3"):
                li = inst.src.find_layer(*g.L[lay])
                if li is None:
                    continue
                it = inst.srctop.begin_shapes_rec(li)
                while not it.at_end():
                    b = pya.DBox(*_box_um(it.shape().bbox().transformed(it.trans()))).transformed(inst.trans)
                    it.next()
                    if inner.contains(b.p1) and inner.contains(b.p2):
                        continue                # deep inside: covered by the outline obstacle
                    box = (round(b.left, 3), round(b.bottom, 3), round(b.right, 3), round(b.top, 3))
                    if lay == "via3":
                        r.via_keepout(*box)
                        continue
                    net = pinboxes.get((lay, box))
                    if net is None:              # a wire into a pin belongs to the pin's net
                        for (pl, pb), pn in pinboxes.items():
                            if pl == lay and box[0] <= pb[2] and pb[0] <= box[2] and box[1] <= pb[3] and \
                                    pb[1] <= box[3]:
                                net = pn
                                break
                    r.obstacle(lay, *box, net)
            # MIM bottom plates near the edge (MIMTM.1: other Metal4 1.2 um away): the top
            # plate (FuseTop) sized by the bottom plate's 0.6 um and the rule, less the
            # router's own keep-out
            li = inst.src.find_layer(75, 0)
            if li is not None:
                it = inst.srctop.begin_shapes_rec(li)
                while not it.at_end():
                    b = pya.DBox(*_box_um(it.shape().bbox().transformed(it.trans()))).transformed(inst.trans)
                    it.next()
                    if inner.contains(b.p1) and inner.contains(b.p2):
                        continue
                    g_ = 0.6 + 1.2 - 0.28
                    r.obstacle("metal4", b.left - g_, b.bottom - g_, b.right + g_, b.top + g_)

    # ---- hand-drawn wiring
    def wire(self, layer, x1, y1, x2, y2, net=None):
        """A Metal3/4/5 rectangle; Metal3/4 ones are given to the router as fixed shapes
        of `net` (None: an obstacle)."""
        self.box(layer, x1, y1, x2, y2)
        if layer in ("metal3", "metal4"):
            self.manual.append((layer, (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), net))

    def via_stack(self, lo, hi, x1, y1, x2, y2, net=None):
        """Via arrays from metal lo up to metal hi over the box (both metals drawn)."""
        self.stack(lo, hi, x1, y1, x2, y2)
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        for m in g.METALS[g.METALS.index(lo):g.METALS.index(hi) + 1]:
            if m in ("metal3", "metal4"):
                self.manual.append((m, box, net))
        if g.METALS.index(lo) <= 2 < g.METALS.index(hi):
            self.via3s.append(box)

    def cover(self, inst):
        """Widen a block's narrow Metal3 port stubs to the router's wire width (0.38 um),
        so that a router wire ending on a stub leaves no notch (M3.2a)."""
        for net, segs in inst.pins.items():
            for k, (lay, x1, y1, x2, y2) in enumerate(segs):
                if lay == "metal3" and x2 - x1 < 0.38 and y2 - y1 >= 1.0:
                    xc = (x1 + x2) / 2
                    self.box("metal3", xc - 0.19, y1, xc + 0.19, y2)
                    segs[k] = (lay, xc - 0.19, y1, xc + 0.19, y2)

    def give(self, r):
        for lay, box, net in self.manual:
            r.obstacle(lay, *box, net)
        for box in self.via3s:
            r.via_keepout(*box)


def macro_pads(a, inst):
    """Router pins outside a LibreLane macro for its edge pins: Metal3 pads (1.4 um tall)
    on the outer ends of the horizontal Metal3 pins (west / east edges), so that each
    holds a router node, and 3 um Metal2 extensions of the vertical Metal2 pins (north /
    south edges). The macro's own pins are replaced by these in inst.pins."""
    x1m, y1m, x2m, y2m = inst.bbox
    for net, segs in inst.pins.items():
        new = []
        for seg in segs:
            lay, x1, y1, x2, y2 = seg
            box = None
            if lay == "metal3" and y2 - y1 <= 1.0:
                yc = (y1 + y2) / 2
                if abs(x1 - x1m) < 0.01:
                    box = ("metal3", x1 - 2.5, yc - 0.7, x1 + 0.5, yc + 0.7)
                elif abs(x2 - x2m) < 0.01:
                    box = ("metal3", x2 - 0.5, yc - 0.7, x2 + 2.5, yc + 0.7)
            elif lay == "metal2":
                if abs(y2 - y2m) < 0.01:
                    box = ("metal2", x1, y2 - 0.5, x2, y2 + 3.0)
                elif abs(y1 - y1m) < 0.01:
                    box = ("metal2", x1, y1 - 3.0, x2, y1 + 0.5)
            if box is None:
                new.append(seg)
                continue
            if box[0] == "metal3":
                a.wire(*box, net)
            else:
                a.box(*box)
            new.append(box)
        inst.pins[net] = new

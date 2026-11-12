"""Grid router for the block layouts (tracker E1): Metal3 vertical, Metal4 horizontal,
over cells that use only Metal1/Metal2 inside.

Grid: pitch 0.68 um in x (Metal3 columns) and y (Metal4 rows), wires 0.30 um, via pads
0.38 um, so neighbouring columns or rows never conflict (pad to pad 0.30 >= 0.28) and
only shapes in the same column or row are checked: a node is free for a net when no
other net's shape in that column (row) comes within 0.47 um (pad half 0.19 + space
0.28) of it.

Pins:
  ('metal2', x1, y1, x2, y2)  a horizontal Metal2 segment (a cell pin): reached with a
                              via2 at a grid column inside it and a short Metal3 stub
                              from the pin's centre line to the nearest grid row;
  ('metal3', ...), ('metal4', ...)  existing wires: any grid node inside.
Each net is a Steiner tree grown by A* from the tree to the next pin. Nets that fail are
moved to the front and everything is routed again (a few rounds).
"""
import heapq
import gf180lay as g

P = 0.68          # grid pitch
W = 0.38          # wire width (as wide as the via pads, so pads leave no notches)
PAD = 0.38        # via pad
KEEP = 0.47       # node centre to another net's shape
VIA_COST = 3.0
FREE, OBS = -1, -2


class Router:
    def __init__(self, x0, y0, x1, y1, px=P, py=P):
        """Grid over x0..x1, y0..y1 with Metal3 columns at x0 + i * px and Metal4 rows at
        y0 + j * py (px >= 0.68, py >= 0.68)."""
        self.x0, self.y0, self.px, self.py = x0, y0, px, py
        self.nx = int((x1 - x0) / px) + 1
        self.ny = int((y1 - y0) / py) + 1
        # owner[layer][i][j]: FREE, OBS or net index (layer 0 = Metal3, 1 = Metal4)
        self.owner = [[[FREE] * self.ny for _ in range(self.nx)] for _ in range(2)]
        self.index = {}         # net name -> owner id
        self.stubs = {}         # column -> [(lo, hi, net)] of the via2 stubs
        self.why = {}           # failed net -> reason (last round)
        self._fixing = False
        self.shapes = []        # (layer key, x1, y1, x2, y2, net)
        self.fixed = []         # (layer key, (x1, y1, x2, y2), net name or None): existing shapes
        self.novia = set()      # (i, j): no via3 here (an existing via3 is too close)

    # ---- coordinates
    def X(self, i):
        return self.x0 + i * self.px

    def Y(self, j):
        return self.y0 + j * self.py

    def ci(self, x):
        return int(round((x - self.x0) / self.px))

    def cj(self, y):
        return int(round((y - self.y0) / self.py))

    # ---- occupancy
    def _claim(self, layer, lo, hi, idx, net):
        """Mark the nodes of column (layer 0) / row (layer 1) idx whose centres come within
        KEEP of a shape spanning lo..hi along it (the shape's full extent, pads included)."""
        if not (0 <= idx < (self.nx if layer == 0 else self.ny)):
            return
        n = self.ny if layer == 0 else self.nx
        o = self.y0 if layer == 0 else self.x0
        p = self.py if layer == 0 else self.px
        a = max(0, int((lo - KEEP - o) / p) - 1)
        b = min(n - 1, int((hi + KEEP - o) / p) + 1)
        for k in range(a, b + 1):
            c = o + k * p
            if lo - KEEP < c < hi + KEEP:
                cur = self.owner[layer][idx][k] if layer == 0 else self.owner[layer][k][idx]
                if cur == FREE or net == OBS or cur == OBS and self._fixing:
                    if layer == 0:
                        self.owner[0][idx][k] = net
                    else:
                        self.owner[1][k][idx] = net
                elif cur != net and cur != OBS:
                    if not self._fixing:
                        raise RuntimeError(f"claim conflict at layer {layer} idx {idx} k {k}: {cur} vs {net}")
                    if layer == 0:     # between fixed shapes of two nets: nobody's
                        self.owner[0][idx][k] = OBS
                    else:
                        self.owner[1][k][idx] = OBS

    def obstacle(self, layer, x1, y1, x2, y2, net=None):
        """An existing Metal3 (layer 'metal3') or Metal4 shape: other nets keep clear of it;
        with net = a net name, that net may use it (e.g. a power strap the net joins)."""
        self.fixed.append((layer, (x1, y1, x2, y2), net))

    def via_keepout(self, x1, y1, x2, y2):
        """An existing via3 (box): no via3 of the router within 0.36 of it (V3.2a/b) and
        none overlapping it (V3.1)."""
        h = 0.13 + 0.36
        for i in range(max(0, self.ci(x1 - 1.0)), min(self.nx, self.ci(x2 + 1.0) + 1)):
            if x1 - h < self.X(i) < x2 + h:
                for j in range(max(0, self.cj(y1 - 1.0)), min(self.ny, self.cj(y2 + 1.0) + 1)):
                    if y1 - h < self.Y(j) < y2 + h:
                        self.novia.add((i, j))

    def _apply_fixed(self, layer, x1, y1, x2, y2, owner):
        """Claim the nodes around a fixed shape: nodes on the lines (columns / rows) that
        touch the shape go to `owner` (OBS for anonymous shapes) within KEEP of it; lines
        that pass beside it closer than the spacing rule are blocked for everyone, also
        for the owner (a parallel wire of the same net would leave a gap under 0.28)."""
        x1, x2, y1, y2 = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
        H = PAD / 2
        if layer == "metal3":
            idx = range(max(0, self.ci(x1 - 0.5)), min(self.nx, self.ci(x2 + 0.5) + 1))
            across = lambda i: self.X(i)
            along_lo, along_hi, a_lo, a_hi = y1, y2, x1, x2
            n_along, o_along, p_along = self.ny, self.y0, self.py
        else:
            idx = range(max(0, self.cj(y1 - 0.5)), min(self.ny, self.cj(y2 + 0.5) + 1))
            across = lambda j: self.Y(j)
            along_lo, along_hi, a_lo, a_hi = x1, x2, y1, y2
            n_along, o_along, p_along = self.nx, self.x0, self.px
        lay = 0 if layer == "metal3" else 1
        for t in idx:
            c = across(t)
            if not (a_lo - KEEP < c < a_hi + KEEP):
                continue
            touching_line = a_lo - H <= c <= a_hi + H
            k0 = max(0, int((along_lo - KEEP - o_along) / p_along) - 1)
            k1 = min(n_along - 1, int((along_hi + KEEP - o_along) / p_along) + 1)
            for k in range(k0, k1 + 1):
                v = o_along + k * p_along
                if not (along_lo - KEEP < v < along_hi + KEEP):
                    continue
                # on the shape's own line the owner may use the nodes beyond its ends too
                # (its wire continues the shape); lines beside it are closed to everyone
                who = owner if touching_line else OBS
                i, j = (t, k) if lay == 0 else (k, t)
                cur = self.owner[lay][i][j]
                if who == OBS or cur == OBS:
                    self.owner[lay][i][j] = OBS
                elif cur == FREE or cur == who:
                    self.owner[lay][i][j] = who
                else:                          # touching shapes of two nets: nobody's
                    self.owner[lay][i][j] = OBS

    def free(self, layer, i, j, net):
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        o = self.owner[layer][i][j]
        return o == FREE or o == net

    # ---- pins
    def access(self, pin, net):
        """Candidate (node, stub) pairs for a pin: node = (layer, i, j); stub = None or
        (x, yc, yj) for a metal2 pin."""
        lay, x1, y1, x2, y2 = pin
        out = []
        if lay == "metal2":
            yc = (y1 + y2) / 2
            j = self.cj(yc)
            for i in range(max(0, self.ci(x1)), min(self.nx, self.ci(x2) + 1)):
                x = self.X(i)
                if x1 + 0.19 - 1e-6 <= x <= x2 - 0.19 + 1e-6 and self._stub_free(i, yc, self.Y(j), net):
                    out.append(((0, i, j), (x, yc, self.Y(j))))
            if not out and 0.38 - 1e-6 <= x2 - x1 < PAD + self.px - 1e-6:
                # (only pins too narrow to hold a column: on a wider pin the pad at its
                # centre could sit on a wire between the columns)
                # narrow pin between two columns: via2 at the pin centre, a Metal3 jog to the
                # nearest column (it reaches into the neighbour column's keep-out, so that
                # column must be free around the pin too)
                xc = (x1 + x2) / 2
                i = self.ci(xc)
                if 0 <= i < self.nx and self._stub_free(i, yc, self.Y(j), net) and \
                        self._jog_free(i, xc, yc, net):
                    out.append(((0, i, j), (xc, yc, self.Y(j))))
        else:
            layer = 0 if lay == "metal3" else 1
            for i in range(max(0, self.ci(x1)), min(self.nx, self.ci(x2) + 1)):
                for j in range(max(0, self.cj(y1)), min(self.ny, self.cj(y2) + 1)):
                    if x1 - 1e-6 <= self.X(i) <= x2 + 1e-6 and y1 - 1e-6 <= self.Y(j) <= y2 + 1e-6 and \
                            self.free(layer, i, j, net):
                        out.append(((layer, i, j), None))
        return out

    def _jog_free(self, i, xc, yc, net):
        """The neighbour column on the jog's side must be free within KEEP of yc."""
        k = i + (1 if xc > self.X(i) else -1)
        if not (0 <= k < self.nx):
            return True
        for jj in range(max(0, self.cj(yc) - 2), min(self.ny, self.cj(yc) + 3)):
            if abs(self.Y(jj) - yc) < PAD / 2 + KEEP and not self.free(0, k, jj, net):
                return False
        for a, b, n in self.stubs.get(k, ()):
            if n != net and yc - PAD / 2 < b + 0.28 and yc + PAD / 2 > a - 0.28:
                return False
        return True

    def _stub_free(self, i, yc, yj, net):
        lo, hi = min(yc, yj) - PAD / 2, max(yc, yj) + PAD / 2
        for k in range(max(0, self.cj(lo) - 2), min(self.ny, self.cj(hi) + 3)):
            c = self.Y(k)
            if lo - KEEP < c < hi + KEEP and not self.free(0, i, k, net):
                return False
        # off-grid stubs of other nets in this column (they may sit between grid rows)
        for a, b, n in self.stubs.get(i, ()):
            if n != net and lo < b + 0.28 and hi > a - 0.28:
                return False
        return True

    # ---- search
    def _astar(self, net, sources, targets):
        tset = {n for n, _ in targets}
        if not tset:
            return None
        tx = [n[1] for n in tset]
        ty = [n[2] for n in tset]
        bx0, bx1, by0, by1 = min(tx), max(tx), min(ty), max(ty)

        def h(n):
            _, i, j = n
            dx = 0 if bx0 <= i <= bx1 else min(abs(i - bx0), abs(i - bx1))
            dy = 0 if by0 <= j <= by1 else min(abs(j - by0), abs(j - by1))
            return dx * self.px + dy * self.py

        dist, prev, pq = {}, {}, []
        for s in sources:
            dist[s] = 0.0
            heapq.heappush(pq, (h(s), 0.0, s))
        while pq:
            _, d, n = heapq.heappop(pq)
            if d > dist.get(n, 1e18):
                continue
            if n in tset:
                path = [n]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            layer, i, j = n
            nbrs = []
            if layer == 0:
                nbrs = [((0, i, j + 1), self.py), ((0, i, j - 1), self.py), ((1, i, j), VIA_COST)]
            else:
                nbrs = [((1, i + 1, j), self.px), ((1, i - 1, j), self.px), ((0, i, j), VIA_COST)]
            for m, c in nbrs:
                if not self.free(m[0], m[1], m[2], net):
                    continue
                if m[0] != layer and (i, j) in self.novia:
                    continue
                nd = d + c
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    prev[m] = n
                    heapq.heappush(pq, (nd + h(m), nd, m))
        return None

    def route(self, nets, rounds=4):
        """nets: {name: [pin, ...]}. Returns the list of failed net names."""
        order = sorted(nets, key=lambda n: self._hpwl(nets[n]))
        # Metal3 / Metal4 pins are wires of their nets: other nets keep clear of them
        known = {(lay, tuple(round(v, 4) for v in box), n) for lay, box, n in self.fixed}
        for n, pins in nets.items():
            for pin in pins:
                if pin[0] in ("metal3", "metal4"):
                    key = (pin[0], tuple(round(v, 4) for v in pin[1:]), n)
                    if key not in known:
                        known.add(key)
                        self.fixed.append((pin[0], tuple(pin[1:]), n))
        names = sorted(set(nets) | {n for _, _, n in self.fixed if n})
        self.index = {n: k for k, n in enumerate(names)}
        for _ in range(rounds):
            self.owner = [[[FREE] * self.ny for _ in range(self.nx)] for _ in range(2)]
            self._fixing = True
            for lay, box, n in self.fixed:     # named shapes first claim, obstacles override
                if n is not None:
                    self._apply_fixed(lay, *box, self.index[n])
            for lay, box, n in self.fixed:
                if n is None:
                    self._apply_fixed(lay, *box, OBS)
            self._fixing = False
            self.stubs = {}
            self._reserve(nets)
            self.shapes, failed = [], []
            for name in order:
                if not self._route_net(name, nets[name]):
                    failed.append(name)
            if not failed:
                return []
            order = failed + [n for n in order if n not in failed]
        return failed

    def _reserve(self, nets, per_pin=2):
        """Keep the access of every pin free from other nets' through-routes: claim (for the
        pin's own net) up to per_pin Metal2-pin stubs nearest the pin's centre."""
        for name in sorted(nets):
            net = self.index[name]
            for pin in nets[name]:
                if pin[0] != "metal2":
                    continue
                xc = (pin[1] + pin[3]) / 2
                cand = sorted(self.access(pin, net), key=lambda c: abs(c[1][0] - xc))
                for node, (x, yc, yj) in cand[:per_pin]:
                    if self._stub_free(node[1], yc, yj, net):
                        self._claim(0, min(yc, yj) - PAD / 2, max(yc, yj) + PAD / 2, node[1], net)
                        self.stubs.setdefault(node[1], []).append(
                            (min(yc, yj) - PAD / 2, max(yc, yj) + PAD / 2, net))
                        if abs(x - self.X(node[1])) > 1e-6:
                            k = node[1] + (1 if x > self.X(node[1]) else -1)
                            if 0 <= k < self.nx and self._jog_free(node[1], x, yc, net):
                                self._claim(0, yc - PAD / 2, yc + PAD / 2, k, net)
                                self.stubs.setdefault(k, []).append((yc - PAD / 2, yc + PAD / 2, net))

    @staticmethod
    def _hpwl(pins):
        xs = [p[1] for p in pins] + [p[3] for p in pins]
        ys = [p[2] for p in pins] + [p[4] for p in pins]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    def _route_net(self, name, pins):
        net = self.index[name]
        if len(pins) < 2:
            return True
        cand = [self.access(p, net) for p in pins]
        if any(not c for c in cand):
            self.why[name] = ("no access at start", [p for p, c in zip(pins, cand) if not c])
            return False
        tree = set()
        # start from a wire pin (a strap or port of this net: all its nodes join the tree),
        # else from the Metal2 pin with the fewest candidates
        wires = [k for k in range(len(pins)) if pins[k][0] != "metal2"]
        if wires:
            k0 = max(wires, key=lambda k: len(cand[k]))
            for n0, _ in cand[k0]:
                tree.add(n0)
        else:
            k0 = min(range(len(pins)), key=lambda k: len(cand[k]))
            xc = (pins[k0][1] + pins[k0][3]) / 2
            n0, s0 = min(cand[k0], key=lambda c: abs(self.X(c[0][1]) - xc))
            tree.add(n0)
            self._commit_node(n0, net)
            if s0:
                self._commit_stub(s0, n0[1], net, name)
        # grow the tree towards whichever remaining pin it reaches first (all remaining
        # pins are targets of each search), so big nets get short Steiner trees
        rest = set(k for k in range(len(pins)) if k != k0)
        while rest:
            owner = {}
            for k in rest:
                for n, st in self.access(pins[k], net):
                    owner.setdefault(n, (k, st))
            blocked = [k for k in rest if not any(o[0] == k for o in owner.values())]
            if blocked:
                self.why[name] = ("no access", [pins[k] for k in blocked])
                return False
            path = self._astar(net, list(tree), [(n, None) for n in owner])
            if path is None:
                self.why[name] = ("unreachable", [pins[k] for k in rest][:4])
                return False
            end = path[-1]
            k, stub = owner[end]
            for a, b in zip(path, path[1:]):
                self._commit_edge(a, b, net, name)
            for n in path:
                self._commit_node(n, net)
                tree.add(n)
            if stub:
                self._commit_stub(stub, end[1], net, name)
            rest.discard(k)
            # a pin whose access nodes are already in the tree is joined too
            for k2 in list(rest):
                if pins[k2][0] != "metal2" and any(n in tree for n, _ in self.access(pins[k2], net)):
                    rest.discard(k2)
        return True

    # ---- committing shapes
    def _commit_node(self, n, net):
        layer, i, j = n
        if layer == 0:
            self._claim(0, self.Y(j) - PAD / 2, self.Y(j) + PAD / 2, i, net)
        else:
            self._claim(1, self.X(i) - PAD / 2, self.X(i) + PAD / 2, j, net)

    def _commit_edge(self, a, b, net, name):
        la, ia, ja = a
        lb, ib, jb = b
        if la != lb:   # via3
            x, y = self.X(ia), self.Y(ja)
            self.shapes.append(("via3", x - 0.13, y - 0.13, x + 0.13, y + 0.13, name))
            self.shapes.append(("metal3", x - PAD / 2, y - PAD / 2, x + PAD / 2, y + PAD / 2, name))
            self.shapes.append(("metal4", x - PAD / 2, y - PAD / 2, x + PAD / 2, y + PAD / 2, name))
        elif la == 0:
            x = self.X(ia)
            y1, y2 = sorted((self.Y(ja), self.Y(jb)))
            self.shapes.append(("metal3", x - W / 2, y1 - W / 2, x + W / 2, y2 + W / 2, name))
            self._claim(0, y1 - PAD / 2, y2 + PAD / 2, ia, net)
        else:
            y = self.Y(ja)
            x1, x2 = sorted((self.X(ia), self.X(ib)))
            self.shapes.append(("metal4", x1 - W / 2, y - W / 2, x2 + W / 2, y + W / 2, name))
            self._claim(1, x1 - PAD / 2, x2 + PAD / 2, ja, net)

    def _commit_stub(self, stub, i, net, name):
        x, yc, yj = stub
        xi = self.X(i)
        self.shapes.append(("via2", x - 0.13, yc - 0.13, x + 0.13, yc + 0.13, name))
        if abs(x - xi) > 1e-6:                 # jog from the pin centre to the column
            self.shapes.append(("metal3", min(x, xi) - PAD / 2, yc - PAD / 2, max(x, xi) + PAD / 2, yc + PAD / 2, name))
            k = i + (1 if x > xi else -1)
            if 0 <= k < self.nx:
                self._claim(0, yc - PAD / 2, yc + PAD / 2, k, net)
                self.stubs.setdefault(k, []).append((yc - PAD / 2, yc + PAD / 2, net))
        self.shapes.append(("metal3", xi - PAD / 2, min(yc, yj) - PAD / 2, xi + PAD / 2, max(yc, yj) + PAD / 2, name))
        self._claim(0, min(yc, yj) - PAD / 2, max(yc, yj) + PAD / 2, i, net)
        self.stubs.setdefault(i, []).append((min(yc, yj) - PAD / 2, max(yc, yj) + PAD / 2, net))

    def draw(self, c):
        """Draw the routed shapes into Cell c. Same-net shapes of one column (row) that come
        closer than 0.3 um are joined, so no narrow gaps or notches are left."""
        for lay, x1, y1, x2, y2, _ in self.shapes:
            c.box(lay, x1, y1, x2, y2)
        groups = {}
        for lay, x1, y1, x2, y2, net in self.shapes:
            if lay == "metal3":
                groups.setdefault((lay, net, round((x1 + x2) / 2, 3)), []).append((y1, y2))
            elif lay == "metal4":
                groups.setdefault((lay, net, round((y1 + y2) / 2, 3)), []).append((x1, x2))
        for (lay, net, mid), iv in groups.items():
            iv.sort()
            end = iv[0][1]
            for a, b in iv[1:]:
                if 0 < a - end < 0.3:
                    if lay == "metal3":
                        c.box(lay, mid - PAD / 2, end, mid + PAD / 2, a)
                    else:
                        c.box(lay, end, mid - PAD / 2, a, mid + PAD / 2)
                end = max(end, b)

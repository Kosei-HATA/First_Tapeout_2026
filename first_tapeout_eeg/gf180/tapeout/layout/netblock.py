"""Netlist-driven layout of logic-type blocks (tracker E1): read a subcircuit from the
simulation netlists, flatten it down to gate-level leaves, make a layout cell for every
leaf from its devices (logic.py), place the cells (logic rows, large drivers on shelves),
and connect everything with route.Router.

Leaves are recognised from their devices, not their names:
  inverter   one PMOS (VDD to Y) and one NMOS (VSS to Y) with one gate net
             -> logic.cmos_cell (logic.driver_cell when the PMOS is 60 um or wider;
                logic.slow_inv_cell when P and N lengths differ)
  NAND / NOR PMOS in parallel and NMOS in series (or the reverse), 2..5 inputs, the
             series stack read from the output (NAND) or from VDD (NOR) as the netlists
             write it -> logic.cmos_cell with nand_seq / nor_seq
  TG         one NMOS and one PMOS between the same two signal nets -> logic.tg_cell
  NMOS       a single NMOS -> logic.nmos_cell
The cell is named after the subcircuit variant (gf180lay.variant_name), so equal leaves
share one cell. Device widths come from the netlist (W is the total width over nf).
"""
import os
import re
import gf180lay as g
import logic as lg
import blocks as bl
import route

FET = ("nfet_03v3", "pfet_03v3")


class Dev:
    def __init__(self, name, model, d, gate, s, bulk, w, l, nf):
        self.name, self.model, self.d, self.g, self.s, self.b = name, model, d, gate, s, bulk
        self.w, self.l, self.nf = w, l, nf

    def __repr__(self):
        return f"{self.name}({self.model[0]} {self.d} {self.g} {self.s} W{self.w:g} L{self.l:g} nf{self.nf})"


def parse(files):
    text = re.sub(r"\n\+", " ", "\n".join(open(f).read() for f in files))
    subs, cur = {}, None
    for line in text.split("\n"):
        w = line.split()
        if not w or line.lstrip().startswith("*"):
            continue
        if w[0].lower() == ".subckt":
            cur = w[1]
            ports = [t for t in w[2:] if "=" not in t and t.lower() != "params:"]
            defs = {t.split("=")[0].lower(): t.split("=")[1] for t in w[2:] if "=" in t}
            subs[cur] = (ports, defs, [])
        elif w[0].lower() == ".ends":
            cur = None
        elif cur:
            subs[cur][2].append(w)
    return subs


def flatten(subs, top, leaf=None, env=None, nets=None, prefix=""):
    """Leaves of `top`: list of (path, subckt, params, {port: net}) for subcircuits that
    leaf(name) accepts (default: those with only FET / resistor / capacitor devices),
    and (path, Dev or raw line, nets) for devices sitting directly in non-leaf cells."""
    ports, defs, lines = subs[top]
    env = env if env is not None else {k: g.spice_num(v) for k, v in defs.items()}
    nets = nets if nets is not None else {p: p for p in ports}
    out = []
    local = lambda n: nets.get(n, prefix + n)
    for w in lines:
        if w[0][0] not in "Xx":
            out.append((prefix + w[0], "raw", None, [local(t) for t in w[1:3]]))
            continue
        pos = [t for t in w[1:] if "=" not in t]
        model = pos[-1]
        kv = {t.split("=", 1)[0].lower(): t.split("=", 1)[1] for t in w[1:] if "=" in t}
        if model in subs:
            cports, cdefs, clines = subs[model]
            cenv = {k: g.spice_num(v) for k, v in cdefs.items()}
            for k, v in kv.items():
                cenv[k] = g.spice_num(v, env)
            cnets = {p: local(n) for p, n in zip(cports, pos[:-1])}
            is_leaf = leaf(model) if leaf else all(t[0][0] in "Xx" and [x for x in t[1:] if "=" not in x][-1] not in subs
                                                  for t in clines)
            if is_leaf:
                out.append((prefix + w[0], model, cenv, cnets))
            else:
                out += flatten(subs, model, leaf, cenv, cnets, prefix + w[0] + ".")
        else:
            vals = {k: g.spice_num(v, env) for k, v in kv.items() if k in ("w", "l", "nf", "m")}
            tn = [local(t) for t in pos[:-1]][:4]
            tn += [model] * (4 - len(tn))          # two-terminal devices: pad
            d = Dev(prefix + w[0], model, *tn, vals.get("w", 0) * 1e6,
                    vals.get("l", 0) * 1e6, int(round(vals.get("nf", 1))) * int(round(vals.get("m", 1))))
            if model in FET:
                d.w *= vals.get("m", 1)
            out.append((prefix + w[0], "dev", d, None))
    return out


def leaf_devices(subs, model, env):
    """Devices of a leaf subcircuit (local net names) with evaluated sizes."""
    ports, defs, lines = subs[model]
    devs = []
    for w in lines:
        pos = [t for t in w[1:] if "=" not in t]
        kv = {t.split("=", 1)[0].lower(): t.split("=", 1)[1] for t in w[1:] if "=" in t}
        vals = {k: g.spice_num(v, env) for k, v in kv.items() if k in ("w", "l", "nf", "m")}
        m = vals.get("m", 1)
        devs.append(Dev(w[0], pos[-1], *pos[:4], vals.get("w", 0) * 1e6 * m, vals.get("l", 0) * 1e6,
                        int(round(vals.get("nf", 1) * m))))
    return ports, devs


def _stack(devs, top, bottom):
    """Gate nets of a series stack from `top` to `bottom` through the devices, or None."""
    order, node, left = [], top, list(devs)
    while left:
        nxt = [d for d in left if node in (d.d, d.s)]
        if len(nxt) != 1:
            return None
        d = nxt[0]
        order.append(d.g)
        node = d.s if d.d == node else d.d
        left.remove(d)
    return order if node == bottom else None


def make_leaf(b, name, ports, devs, vdd="VDD", vss="VSS"):
    """Layout cell for a leaf (see the module doc). Returns a LogicCell or raises."""
    if b.find_cell(name):
        return CELLS[(id(b), name)]
    P = [d for d in devs if d.model == "pfet_03v3"]
    N = [d for d in devs if d.model == "nfet_03v3"]
    sig = [p for p in ports if p not in (vdd, vss)]
    is_inv = (len(P) == 1 and len(N) == 1 and P[0].g == N[0].g and vdd in (P[0].d, P[0].s)
              and vss in (N[0].d, N[0].s)
              and ({P[0].d, P[0].s} - {vdd}) == ({N[0].d, N[0].s} - {vss}))
    if is_inv:
        p, n = P[0], N[0]
        a = p.g
        y = p.d if p.s == vdd else p.s
        if p.l != n.l:
            cell = lg.slow_inv_cell(b, name, p.w / p.nf, p.l, n.w / n.nf, n.l, a=a, y=y)
        elif p.w >= 60:
            cell = lg.driver_cell(b, name, p.w, n.w, a=a, y=y)
        else:
            ps, ns = lg.inv_seq(p.nf, a=a, y=y)
            cell = lg.cmos_cell(b, name, ps, ns, p.w / p.nf, n.w / n.nf, [a, y])
    elif len(P) == 1 and len(N) == 1 and P[0].g != N[0].g and {P[0].d, P[0].s} == {N[0].d, N[0].s}:
        n, p = N[0], P[0]
        cell = lg.tg_cell(b, name, n.nf, p.nf, n.w / n.nf, p.w / p.nf, a=n.d, y=n.s, gn=n.g, gp=p.g)
    elif len(P) == len(N) >= 2 and len({d.nf for d in P + N}) == 1:
        nf = P[0].nf
        y = [x for x in sig if all(x in (d.d, d.s) for d in P) or all(x in (d.d, d.s) for d in N)]
        y = [x for x in y if x in ports][0]
        nst = _stack(N, y, vss)
        pst = _stack(P, vdd, y)
        if nst and all(vdd in (d.d, d.s) for d in P):          # NAND: N in series, P in parallel
            ps, ns = lg.nand_seq(nst, nf, y=y)
        elif pst and all(vss in (d.d, d.s) for d in N):         # NOR: P in series
            ps, ns = lg.nor_seq(pst, nf, y=y)
        else:
            raise ValueError(f"{name}: unknown gate {devs}")
        cell = lg.cmos_cell(b, name, ps, ns, P[0].w / nf, N[0].w / nf, sig)
    elif len(N) == 1 and not P:
        n = N[0]
        cell = lg.nmos_cell(b, name, n.w / n.nf, n.l, n.nf, n.d, n.g, n.s)
    else:
        raise ValueError(f"{name}: no generator for {devs}")
    CELLS[(id(b), name)] = cell
    return cell


CELLS = {}


def build(b, subs, top, rows_x0=4.0, max_w=150.0, vdd="VDD", vss="VSS", leaf=None, extra=None):
    """Make and place the leaves of `top` in logic rows (cells of the template height) and
    driver shelves above them. Returns (placed list, nets {net: [pins]}, Rows, top_y).
    extra: {path: cell} to override the cell of a leaf or a device."""
    items = flatten(subs, top, leaf)
    rows = bl.Rows(b, rows_x0, 0.0)
    placed, nets = [], {}
    big = []
    r = 0
    for path, model, env, cnets in items:
        if model == "raw":
            raise ValueError(f"{path}: ideal element in a logic block")
        if model == "dev":
            d = env
            sn = "VSS" if d.s == vss else "S"
            name = f"{top}_{d.model[0]}_{d.w:g}_{d.l:g}_{d.nf}{'_s' if sn == 'VSS' else ''}".replace(".", "p")
            cell = (extra or {}).get(path) or make_leaf(b, name, ["D", "G", sn],
                                                        [Dev("X", d.model, "D", "G", sn, "VSS", d.w, d.l, d.nf)])
            cmap = {"D": d.d, "G": d.g, "S": d.s, "VDD": vdd, "VSS": vss}
        else:
            ports, devs = leaf_devices(subs, model, env)
            vname = g.variant_name(model, env) if subs[model][1] else model
            cell = (extra or {}).get(path) or make_leaf(b, vname, ports, devs)
            cmap = dict(cnets)
            cmap.setdefault("VDD", vdd)
            cmap.setdefault("VSS", vss)
        if getattr(cell, "height", lg.H) != lg.H:
            big.append((path, cell, cmap))
            continue
        if rows.rows and rows.xcur[r] + cell.width > rows_x0 + max_w:
            r += 1
        p = rows.add(r, cell, path)
        placed.append(p)
        for pn, segs in p.pins.items():
            nets.setdefault(cmap.get(pn, pn), []).extend(segs)
    rows.fill_all()
    y = rows.y0 + rows.height() + 2.0
    shelf = bl.Shelves(b, rows_x0, y, max_w, gap=1.6)
    for path, cell, cmap in big:
        p = shelf.place(cell, path)
        placed.append(p)
        for pn, segs in p.pins.items():
            nets.setdefault(cmap.get(pn, pn), []).extend(segs)
    return placed, nets, rows, (shelf.top_y() if big else y)


def logic_block(name, files, max_w=140.0, vdd="VDD", vss="VSS", sw=2.4, x0=4.0, leaf=None, extra=None):
    """A whole logic-type block from its netlist: leaves (build()), Metal3 power straps
    on the west (vss) and east (vdd) edges joined to the logic rails and the driver
    rails, ports (every other subcircuit port) as Metal3 stubs on the top edge, routing.
    Returns (Block, (width, height))."""
    b = g.Block(name)
    subs = parse(files)
    placed, nets, rows, ytop = build(b, subs, name, rows_x0=x0, max_w=max_w, vdd=vdd, vss=vss, leaf=leaf,
                                     extra=extra)
    right = max([x0 + rows.width()] + [p.x + p.cell.width for p in placed])
    width = right + 2.0 + sw + 0.6
    y_top = ytop + 10.0
    xs_vss, xs_vdd = sw / 2 + 0.4, width - sw / 2 - 0.4
    for net, x in ((vss, xs_vss), (vdd, xs_vdd)):
        b.box("metal3", x - sw / 2, -1.0, x + sw / 2, y_top)
        b.label("metal3", net, x, 2.0)
    for net, a, c_ in rows.rails():
        if net == "VSS":
            b.box("metal2", xs_vss - sw / 2, a, x0 + 0.5, c_)
            b.vias("via2", xs_vss - sw / 2, a, xs_vss + sw / 2, c_)
        else:
            b.box("metal2", x0 + rows.width() - 0.5, a, xs_vdd + sw / 2, c_)
            b.vias("via2", xs_vdd - sw / 2, a, xs_vdd + sw / 2, c_)
    drivers = [p for p in placed if p.cell.height != lg.H]
    for p in drivers:
        for pn, net in (("VDD", vdd), ("VSS", vss)):
            lay, x1, y1, x2, y2 = p.pins[pn][0]
            if net == vss:
                b.box("metal2", xs_vss - sw / 2, y1, x2, y2)
                b.vias("via2", xs_vss - sw / 2, y1, xs_vss + sw / 2, y2)
            else:
                b.box("metal2", x1, y1, xs_vdd + sw / 2, y2)
                b.vias("via2", xs_vdd - sw / 2, y1, xs_vdd + sw / 2, y2)
    for n in (vdd, vss, "VDD", "VSS"):
        nets.pop(n, None)
    ports = [n for n in subs[name][0] if n not in (vdd, vss)]
    gx0 = (x0 + lg.GATE0) % lg.PITCH
    snap = lambda x: gx0 + round((x - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (sw + 2.0)) / len(ports)
    pp = bl.ports_top(b, ports, [snap(sw + 2.0 + step * (k + 0.5)) for k in range(len(ports))], y_top)
    for n, pin in pp.items():
        nets.setdefault(n, []).append(pin)
    r = route.Router(gx0, -1.5, width, y_top + 0.5, px=lg.PITCH)
    for n, pin in pp.items():
        r.obstacle(pin[0], *pin[1:], n)
    for x in (xs_vss, xs_vdd):
        r.obstacle("metal3", x - sw / 2, -1.0, x + sw / 2, y_top)
    for p in drivers:   # the driver cells' Metal3 bars and Metal4 bus belong to their output
        ynet = [n for n, segs in nets.items() if any(sg in segs for sg in p.pins["Y"])][0]
        for lay in ("metal3", "metal4"):
            for bx in bl.cell_shapes(p, lay):
                r.obstacle(lay, *bx, ynet)
        for bx in bl.cell_shapes(p, "via3"):
            r.via_keepout(*bx)
    failed = r.route(nets, rounds=6)
    if failed:
        raise RuntimeError(f"{name}: unrouted {failed}")
    r.draw(b)
    return b, (width, y_top)

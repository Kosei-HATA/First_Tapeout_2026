#!/usr/bin/env python3
"""Layout of the AFE electrode-offset DAC (tracker E3, B7): its two halves
eeg_afe_offdac_p (into INP) and eeg_afe_offdac_n (into INN) of
gf180/tapeout/afe/eeg_afe.spice, as the blocks offdac_p and offdac_n for the two west
corners of the AFE beside Cin_P and Cin_N. LVS wrappers: lvs/offdac_p.spice,
lvs/offdac_n.spice (written by this script).

offdac_n, bottom to top (offdac_p is the same drawn upside down, so its control ports are
on the top edge and INP on the bottom edge; it has no decoupling capacitor):
  - control ports (VCM S PH M0..9 EN0..3) on the bottom edge (Metal3 stubs);
  - one logic row: the half's copy of the shared logic (S and PH inverters, XOR TGs, X
    chain, EN inverters), per bit the plate NAND3 and driver and the clamp NAND2
    (netblock.make_leaf cells);
  - the plate resistors R_k (ppolyf_u_1k, W 1 um), each folded into series segments of
    at most 175 um (KLayout's LVS adds series resistors back together), and the clamps
    of all ten plates in one NMOS cell;
  - the MIMs (analog.mim_cell, drawn bottom plate down): a lower row with bits 8, 7, 6, 5
    and bits 2, 1, 0, 3, 4 stacked over 7, 6, 5, and above it bit 9 (two units) with the
    range TGs (eeg_afe_rg, NMOS and PMOS strip cells) and the park TGs at its east end;
    INN on the top edge above them. The group top plates T0..T3 leave the MIMs upwards;
  - under the MIMs (offdac_n only): the decoupling of the AFE clock driver's supply,
    cap_nmos_03v3 units between AVDD_CLK (gate) and AVSS_CLK (source/drain), each in a
    guard ring on AVSS; AVDD_CLK and AVSS_CLK leave on Metal3 straps through the top edge
    (their via2 where no MIM top plate is above: the LVS deck drops via2 under fusetop).
Supplies: Metal3 straps AVSS (west edge) and AVDD (east edge) over the full height.
Routing: route.Router on Metal3/Metal4; Metal3 may pass under the MIMs (no Via3 there:
Metal4 is kept 1.2 um from every bottom plate, MIMTM.1 / MIMTM.10).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/offdac_lay.py [--drc] [--lvs] [--only offdac_p offdac_n]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import netblock as nb
import route

pya = g.pya
HERE = os.path.dirname(os.path.abspath(__file__))
AFE = os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
W = 234.0
SW = 2.4
SEG = 175.0                    # longest resistor segment (um)
N_BITS = 10
GROUP = [0, 0, 0, 0, 0, 0, 0, 1, 2, 3]
DC_L, DC_W = 28.6, 92.0                   # decap unit gate (um)
DC_ROWS = [6, 4]                          # decap units per row (the upper row ends west of the TGs)
X0 = 0.24                                 # router column phase (block origin)
GAP_MIM = 0.6                             # between MIM cells side by side: their bottom plates are
                                          # 0.4 um inside the cell edges, MIMTM.1 wants 1.2 um
BOTTOM_PORTS = ["VCM", "S", "PH"] + [f"M{k}" for k in range(N_BITS)] + [f"EN{g_}" for g_ in range(4)]


def snap(v):
    return X0 + round((v - X0) / lg.PITCH) * lg.PITCH


def sizes(subs, top):
    """{device name: value}: MIM side (um) and resistor length (um) from the netlist."""
    out = {}
    for w in subs[top][2]:
        kv = {t.split("=", 1)[0].lower(): t.split("=", 1)[1] for t in w[1:] if "=" in t}
        if "c_length" in kv:
            out[w[0]] = float(kv["c_length"].rstrip("u"))
        elif "r_length" in kv:
            out[w[0]] = float(kv["r_length"].rstrip("u"))
    return out


def segments(length):
    """Series segment lengths (5 nm grid) summing exactly to length, each <= SEG."""
    n = max(1, -(-int(round(length * 1000)) // int(SEG * 1000)))
    base = round(length / n / 0.005) * 0.005
    segs = [base] * (n - 1)
    segs.append(round((length - sum(segs)) / 0.005) * 0.005)
    return segs


def decap_cell(b, name):
    """cap_nmos_03v3 (DC_L x DC_W gate) between AVDD_CLK (gate) and AVSS_CLK (source and
    drain), its guard ring a substrate tap on AVSS: analog.moscap_cell without the bridge
    from the S/D bar to the ring, plus a Metal2 pin on the ring's bottom side."""
    c = b.new_cell(name)
    ox, oy = 3.42, 3.73
    inst, _ = c.pcell("cap_nmos", {"volt": "3.3V", "lc": DC_L, "wc": DC_W, "pcmpgr": True}, x=ox, y=oy)
    x1, y1, x2, y2 = [v / 1000 for v in (inst.bbox().left, inst.bbox().bottom, inst.bbox().right, inst.bbox().top)]
    w_comp = DC_L + 0.88
    pins = {}
    ya, yb = oy - 1.955 + 0.25, oy - 0.955 - 0.25
    c.box("metal2", ox - 0.63, ya, ox + w_comp + 0.65, yb)
    x = ox - 0.3
    while x < ox + w_comp + 0.4:
        c.box("via1", x - 0.13, (ya + yb) / 2 - 0.13, x + 0.13, (ya + yb) / 2 + 0.13)
        x += 0.8
    pins["AVSS_CLK"] = [("metal2", ox - 0.63, ya, ox + w_comp + 0.65, yb)]
    gx1, gx2 = ox + 1.035, ox + DC_L - 0.155
    gy1, gy2 = oy + DC_W - 0.4, oy + DC_W + 0.1
    c.box("metal2", gx1, gy1, gx2, gy2)
    x = gx1 + 0.3
    while x < gx2 - 0.3:
        c.box("via1", x - 0.13, (gy1 + gy2) / 2 - 0.13, x + 0.13, (gy1 + gy2) / 2 + 0.13)
        x += 0.8
    pins["AVDD_CLK"] = [("metal2", gx1, gy1, gx2, gy2)]
    return an.AnalogCell(c, x2 + 0.4, y2 + 0.4, pins), (x1, y1, x2, y2)


def rg_cells(b, s, node):
    """Range TGs of one half: NMOS strips (gate ENg, W 10 um x s) and PMOS strips (gate
    ENBg, W 20 um x s), one strip per group, between T<s>g and the amplifier input."""
    sn = {0: 1, 1: 1, 2: 2, 3: 4}
    nspecs, pspecs = [], []
    for g_ in range(4):
        t = f"T{s}{g_}"
        for kind, nf, gate, specs in (("n", sn[g_], f"EN{g_}", nspecs), ("p", 2 * sn[g_], f"ENB{g_}", pspecs)):
            seq = [t]
            for k in range(nf):
                seq += [gate, node if k % 2 == 0 else t]
            specs.append(dict(w=10.0, l=0.28, seq=seq, order=[t, node]))
    nc = an.multi_strip_cell(b, f"od{s.lower()}_rgn", "n", nspecs, bulk="VSS")
    pc = an.multi_strip_cell(b, f"od{s.lower()}_rgp", "p", pspecs, bulk="VDD")
    return nc, pc


def clamp_cell(b, s, wcl):
    """The clamp NMOS of the plates in one cell, one strip per bit: bits 0..4 (W 0.5..3 um,
    one finger) and bits 5..9 (W 6, 12, 24, 48, 96 um, fingers of 6 um). The one-finger
    strips get the full width of the cell for their straps, so the router reaches their
    gate and drain pins on different columns."""
    specs = []
    for k in range(N_BITS):
        nf, w = (int(round(wcl[k] / 6.0)), 6.0) if k >= 5 else (1, wcl[k])
        seq = ["VSS"]
        for j in range(nf):
            seq += [f"NA{k}", f"B{s}{k}" if j % 2 == 0 else "VSS"]
        specs.append(dict(w=w, l=0.28, seq=seq, order=["VSS", f"B{s}{k}"]))
    return an.multi_strip_cell(b, f"od{s.lower()}_clamp", "n", specs, bulk="VSS")


def build(side):
    s = side.upper()
    node = "INP" if s == "P" else "INN"
    name = f"offdac_{side.lower()}"
    top = f"eeg_afe_offdac_{side.lower()}"
    b = g.Block(name)
    core = b.new_cell(name + "_core")
    subs = nb.parse([AFE])
    val = sizes(subs, top)
    nets = {}
    placed = []
    keep4 = []

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def put(cell, x, y, pname, cmap=None, mirror=False):
        core.place(cell.cell, x, y, mirror=mirror)
        p = bl.Placed(cell, x, y, mirror, pname)
        for pn, segs in p.pins.items():
            conn((cmap or {}).get(pn, pn), segs)
        placed.append(p)
        return p

    # ---- leaves
    items = nb.flatten(subs, top)
    logic, wcl = [], {}
    for path, model, env, cnets in items:
        if model == "dev":
            d = env
            if d.model == "nfet_03v3":                       # clamp of bit k
                wcl[int(path.split("CL" + s)[1])] = d.w
            continue
        if model == "eeg_afe_rg" or path.startswith("XPK"):      # placed by the TGs east of bit 9
            continue
        ports, devs = nb.leaf_devices(subs, model, env)
        vname = g.variant_name(model, env) if subs[model][1] else model
        cell = nb.make_leaf(b, vname, ports, devs)
        logic.append((path, cell, dict(cnets)))
    # ---- logic rows at the bottom
    y_rows = 8.0
    x_rows = round(6.0 / lg.PITCH) * lg.PITCH
    rows = bl.Rows(core, x_rows, y_rows)
    max_w = W - 10.0
    r = 0
    for path, cell, cmap in logic:
        if rows.rows and rows.xcur[r] + cell.width > x_rows + max_w:
            r += 1
        p = rows.add(r, cell, path)
        for pn, segs in p.pins.items():
            if pn in ("VDD", "VSS"):
                continue
            conn(cmap.get(pn, pn), segs)
    rows.fill_all()
    y = y_rows + rows.height() + 1.5
    # ---- resistors (folded) and the large clamps
    terms, lens, links = [], [], []
    for k in range(N_BITS):
        segs = segments(val[f"XRD{s}{k}"])
        nodes = [f"D{s}{k}"] + [f"R{s}{k}_{j}" for j in range(1, len(segs))] + [f"B{s}{k}"]
        for j, ln in enumerate(segs):
            a_, c_ = nodes[j], nodes[j + 1]
            terms.append((a_, c_) if j % 2 == 0 else (c_, a_))
            lens.append(ln)
        links += nodes[1:-1]
    res = an.res_cell(b, f"od{side.lower()}_r", lens, 1.0, terms, sub="VSS")
    pr = put(res, 4.0, y, "R")
    # serpentine links: the two pads of an intermediate node are on adjacent rows at the
    # same end; a Metal2 bar joins them (the node is internal, not routed)
    for n in links:
        segs = pr.pins.pop(n)
        nets.pop(n, None)
        x1 = min(sg[1] for sg in segs)
        x2 = max(sg[3] for sg in segs)
        core.box("metal2", x1, min(sg[2] for sg in segs), x2, max(sg[4] for sg in segs))
    cl = clamp_cell(b, s, wcl)
    xc = W - 4.0 - cl.width
    assert xc > 4.0 + res.width, "clamps run into the resistors"
    put(cl, xc, y, "CL")
    y_band = y + max(res.height, cl.height)
    # ---- MIMs (bottom plate down: placed mirrored, origin at the cell's top)
    mims = {}
    for k in range(N_BITS):
        a = val[f"XCOF{s}{k}"] if f"XCOF{s}{k}" in val else val[f"XCOF{s}{k}_0"]
        mims[k] = an.mim_cell(b, f"od{side.lower()}_c{k}", a, f"T{s}{GROUP[k]}", f"B{s}{k}", n=2 if k == 9 else 1)
    yl = y_band + 3.0                                  # bottom of the lower MIM row
    h_row = mims[8].height

    def put_mim(k, x, ybot):
        m = mims[k]
        p = put(m, x, ybot + m.height, f"C{k}", mirror=True)
        k4 = m.keepout4
        keep4.append((p.x + k4[0], p.y - k4[3], p.x + k4[2], p.y - k4[1]))
        return p

    x = 0.0
    put_mim(8, x, yl)
    x += mims[8].width + GAP_MIM
    put_mim(7, x, yl)
    xa = x
    for k in (2, 1, 0):                                # over bit 7
        put_mim(k, xa, yl + mims[7].height + 2.0)
        xa += mims[k].width + GAP_MIM
    x += mims[7].width + GAP_MIM
    put_mim(6, x, yl)
    put_mim(3, x, yl + mims[6].height + 2.0)
    x += mims[6].width + GAP_MIM
    put_mim(5, x, yl)
    put_mim(4, x, yl + mims[5].height + 2.0)
    assert x + mims[5].width <= W, "lower MIM row too wide"
    yu = yl + h_row + 5.0                              # bottom of the upper row
    put_mim(9, 0.0, yu)
    height = yu + h_row + 4.5
    # ---- range and park TGs east of bit 9
    rgn, rgp = rg_cells(b, s, node)
    xr = mims[9].width + 2.0
    put(rgn, xr, yu + 2.0, "RGN")
    put(rgp, xr + rgn.width + 1.0, yu + 2.0, "RGP")
    pk = nb.make_leaf(b, "eeg_afe_tg", ["A", "Y", "G", "GN", "VDD", "VSS"],
                      nb.leaf_devices(subs, "eeg_afe_tg", {})[1])
    yk = yu + 2.0 + max(rgn.height, rgp.height) + 2.0
    xk = round(xr / lg.PITCH) * lg.PITCH
    for g_ in range(4):
        p = put(pk, xk + g_ * pk.width, yk, f"PK{g_}",
                {"A": f"T{s}{g_}", "Y": "VCM", "G": f"ENB{g_}", "GN": f"EN{g_}"})
    pk_rails = [(xk, yk, xk + 4 * pk.width)]
    assert yk + lg.H < height - 2.0, "park TGs do not fit east of bit 9"
    assert xr + rgn.width + 1.0 + rgp.width < W - 3.0, "range TGs do not fit east of bit 9"
    # ---- decoupling under the MIMs (offdac_n)
    straps3 = []
    if s == "N":
        dc, _ = decap_cell(b, "odn_decap")
        xd0 = 14.0
        rows_y = [yl - 2.0, yl - 2.0 + dc.height + 1.0]
        assert rows_y[-1] + dc.height < height, "decap rows do not fit under the MIMs"
        assert xd0 + DC_ROWS[0] * dc.width <= W, "decap row 0 too wide"
        assert xd0 + DC_ROWS[1] * dc.width < xr, "decap row 1 runs into the TGs"
        for j, yd in enumerate(rows_y):
            for i in range(DC_ROWS[j]):
                put(dc, xd0 + i * dc.width, yd, f"DC{j}_{i}")
        n_dc = sum(DC_ROWS)
        # per row: Metal2 straps over the gate pins (AVDD_CLK) and the S/D bars (AVSS_CLK)
        # to two Metal3 straps west of the units, up through the top edge
        xs_clk = {"AVDD_CLK": (4.0, 7.0), "AVSS_CLK": (9.5, 12.5)}
        for net, (x1, x2) in xs_clk.items():
            core.box("metal3", x1, rows_y[0], x2, height)
            straps3.append(("metal3", x1, rows_y[0], x2, height, net))
        # A via2 under a MIM top plate is no connection for the LVS deck (via2.not(fusetop)),
        # so each via2 goes where no top plate is above: the S/D straps' at the units' bottom
        # edges; the gate straps of both rows meet on a Metal2 bar under the AVDD_CLK strap
        # (west of the AVSS_CLK straps) with its via2 between the MIM rows.
        ft = pya.Region(core.cell.begin_shapes_rec(core.li("fusetop")))

        def free(x1, y1, x2, y2):
            um = g.Cell.um
            return ft.interacting(pya.Region(pya.Box(um(x1), um(y1), um(x2), um(y2)))).is_empty()

        dc_rows = {}
        for p in placed:
            if p.name.startswith("DC"):
                dc_rows.setdefault(p.name.split("_")[0], []).append(p)
        gy = []
        for row in dc_rows.values():
            for net in ("AVDD_CLK", "AVSS_CLK"):
                _, _, b1, _, b2 = row[0].pins[net][0]
                x1, x2 = xs_clk[net]
                core.box("metal2", x1, b1, max(p.pins[net][0][3] for p in row), b2)
                if net == "AVDD_CLK":
                    gy += [b1, b2]
                else:
                    assert free(x1, b1 - 0.5, x2, b2 + 0.5), "AVSS_CLK via2 under a MIM"
                    core.vias("via2", x1, b1, x2, b2)
        x1, x2 = xs_clk["AVDD_CLK"]
        core.box("metal2", x1, min(gy), x2, max(gy))
        yv = min(gy)
        while not free(x1, yv - 0.5, x2, yv + 1.5):
            yv += 0.1
            assert yv + 1.0 < max(gy), "no place for the AVDD_CLK via2"
        core.vias("via2", x1, yv, x2, yv + 1.0)
        for net in ("AVDD_CLK", "AVSS_CLK"):
            nets.pop(net, None)
        # the units' rings are substrate taps (AVSS); the substrate joins them to AVSS
    else:
        n_dc = 0
    # ---- supplies: Metal3 straps (AVSS west, AVDD east); logic rails to them
    xs_vss, xs_vdd = SW / 2 + 0.4, W - SW / 2 - 0.4
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        core.box("metal3", x - SW / 2, 0.0, x + SW / 2, height)
        conn(net, [("metal3", x - SW / 2, 0.0, x + SW / 2, height)])
    for net, a_, c_ in rows.rails():
        if net == "VSS":
            core.box("metal2", xs_vss - SW / 2, a_, x_rows + 0.5, c_)
            core.vias("via2", xs_vss - SW / 2, a_, xs_vss + SW / 2, c_)
        else:
            core.box("metal2", x_rows + rows.width() - 0.5, a_, xs_vdd + SW / 2, c_)
            core.vias("via2", xs_vdd - SW / 2, a_, xs_vdd + SW / 2, c_)
    # park TGs' rails east to the AVDD strap and west by router (VSS)
    for x1, y1, x2 in pk_rails:
        for net, (a_, c_) in (("VDD", lg.VDD_RAIL), ("VSS", lg.VSS_RAIL)):
            if net == "VDD":
                core.box("metal2", x2 - 0.5, y1 + a_, xs_vdd + SW / 2, y1 + c_)
                core.vias("via2", xs_vdd - SW / 2, y1 + a_, xs_vdd + SW / 2, y1 + c_)
    # ---- ports: control on the bottom edge, the amplifier input on the top edge
    step = (W - 2 * (SW + 6.0)) / len(BOTTOM_PORTS)
    pp = bl.ports_bottom(core, BOTTOM_PORTS, [snap(SW + 6.0 + step * (k + 0.5)) for k in range(len(BOTTOM_PORTS))], 0.0)
    pp.update(bl.ports_top(core, [node], [snap(W - 18.0)], height))
    for n, pin in pp.items():
        conn(n, [pin])
    # ---- route
    rt = route.Router(X0, -1.5, W, height + 0.5, px=lg.PITCH)
    for box in keep4:
        rt.obstacle("metal4", *box)
    for lay, x1, y1, x2, y2, net in straps3:
        rt.obstacle(lay, x1, y1, x2, y2)
    failed = rt.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, rt.why.get(n))
        raise RuntimeError(f"{name}: unrouted {failed}")
    rt.draw(core)
    # ---- the block: the core as drawn (offdac_n) or upside down (offdac_p)
    flip = s == "P"
    t = pya.DTrans(0, True, 0.0, height) if flip else pya.DTrans(0, False, 0.0, 0.0)
    b.cell.insert(pya.DCellInstArray(core.cell.cell_index(), t))
    fy = (lambda yy: height - yy) if flip else (lambda yy: yy)

    def label(lay, net, x1, y1, x2, y2):
        b.label(lay, net, (x1 + x2) / 2, fy((y1 + y2) / 2))

    for n, pin in pp.items():
        lay, x1, y1, x2, y2 = pin
        label(lay, n, x1, (y1 + y2) / 2 - 0.45 if y1 < 1.0 else y2 - 0.3, x2, (y1 + y2) / 2 - 0.45 if y1 < 1.0 else y2 - 0.3)
    label("metal3", "AVSS", xs_vss, 2.0, xs_vss, 2.0)
    label("metal3", "AVDD", xs_vdd, 2.0, xs_vdd, 2.0)
    if s == "N":
        for lay, x1, y1, x2, y2, net in straps3:
            label(lay, net, x1, y2 - 1.0, x2, y2 - 1.0)
    info = dict(width=W, height=height, decap_pf=n_dc * DC_L * DC_W * 3.983e-3, n_decap=n_dc,
                ports={n: (round(p[1], 2), round(fy(p[2]), 2), round(p[3], 2), round(fy(p[4]), 2)) for n, p in pp.items()})
    return b, name, info


def write_wrappers():
    bits = " ".join(f"M{k}" for k in range(N_BITS))
    ens = "EN0 EN1 EN2 EN3"
    p = (f"* LVS wrapper for the layout block offdac_p (gf180/tapeout/layout/offdac_lay.py): the\n"
         f"* P half of the offset DAC (gf180/tapeout/afe/eeg_afe.spice) with the block's supply names.\n"
         f".subckt offdac_p INP VCM PH S {bits} {ens} AVDD AVSS\n"
         f"XH INP VCM PH S {bits} {ens} AVDD AVSS eeg_afe_offdac_p\n.ends offdac_p\n")
    dc = "\n".join(f"XDC{k} AVDD_CLK AVSS_CLK cap_nmos_03v3 c_length={DC_L:g}u c_width={DC_W:g}u"
                   for k in range(sum(DC_ROWS)))
    n = (f"* LVS wrapper for the layout block offdac_n (gf180/tapeout/layout/offdac_lay.py): the\n"
         f"* N half of the offset DAC (gf180/tapeout/afe/eeg_afe.spice) and, under its MIMs, the\n"
         f"* decoupling of the AFE clock driver's supply ({sum(DC_ROWS)} cap_nmos_03v3, AVDD_CLK gate,\n"
         f"* AVSS_CLK source/drain; the guard rings tap the substrate, AVSS).\n"
         f".subckt offdac_n INN VCM PH S {bits} {ens} AVDD AVSS AVDD_CLK AVSS_CLK\n"
         f"XH INN VCM PH S {bits} {ens} AVDD AVSS eeg_afe_offdac_n\n{dc}\n.ends offdac_n\n")
    open(os.path.join(HERE, "lvs", "offdac_p.spice"), "w").write(p)
    open(os.path.join(HERE, "lvs", "offdac_n.spice"), "w").write(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    ap.add_argument("--only", nargs="+", default=["offdac_p", "offdac_n"])
    a = ap.parse_args()
    write_wrappers()
    for name in a.only:
        runs = os.path.join(HERE, "runs", name)
        os.makedirs(runs, exist_ok=True)
        os.chdir(runs)
        b, name, info = build(name[-1])
        print(f"{name}: {info['width']:.1f} x {info['height']:.1f} um, decap {info['n_decap']} units "
              f"{info['decap_pf']:.1f} pF")
        print("  ports:", info["ports"])
        bl.check(b, name, [AFE, os.path.join(HERE, "lvs", f"{name}.spice")], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

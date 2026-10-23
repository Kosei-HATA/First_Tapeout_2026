#!/usr/bin/env python3
"""Layout of adc_rdac (LVS wrapper gf180/tapeout/layout/lvs/adc_rdac.spice, tracker E4):
the ADC's stage-1 input resistors RIN and the DAC1 (gf180/tapeout/adc/eeg_dac1.spice).

RIN is 32 DAC1-unit resistors per side (RIN/RD1 = 31/32 by construction), so all 126
units (300 kohm ppolyf_u_1k, 291.28 x 1 um) sit in one resistor array, interleaved
per DAC1 cell k as RIN_P, RD_P(k), RIN_N, RD_N(k) (plus two RIN units at the end); west
ends to INP / VREFP / INN / VREFN, east ends to I1P / XP(k) / I1N / XN(k).
East of the array: the 31 steering switch strips (four NMOS W1/L0.28 per cell, one
strip [OUTP D XP DB OUTN D XN DB OUTP]) and the logic (latch TGs, inverters, NORs of
every cell, and the common-break driver eeg_dac1_brk) in rows. Routing: route.Router.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/rdac1_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import netblock as nb
import route

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [os.path.join(HERE, "lvs", "adc_rdac.spice"), os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_dac1.spice")]
SW = 2.4


def build():
    b = g.Block("adc_rdac")
    subs = nb.parse(FILES)
    items = nb.flatten(subs, "adc_rdac")
    nets = {}

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    # ---- sort the leaves: resistors, switch NMOS (per DAC1 cell), gates
    res, sw, gates = [], {}, []
    for path, model, env, cnets in items:
        if model == "dev" and env.model == "ppolyf_u_1k":
            res.append(env)
        elif model == "dev" and env.model == "nfet_03v3" and ".XS" in path:
            cell = path.rsplit(".", 1)[0]
            sw.setdefault(cell, []).append(env)
        else:
            gates.append((path, model, env, cnets))
    # the wrapper's RIN lines (m=32) are written out by hand below; DAC1 cells have XRP / XRN
    terms = []
    cells = sorted(sw, key=lambda s: int(s.split(".XC")[-1]))
    for k, cell in enumerate(cells):
        rp = [d for d in res if d.name == f"{cell}.XRP"][0]
        rn = [d for d in res if d.name == f"{cell}.XRN"][0]
        terms += [("INP", "I1P"), (rp.d, rp.g), ("INN", "I1N"), (rn.d, rn.g)]
    terms += [("INP", "I1P"), ("INN", "I1N")]
    ra = an.res_cell(b, "rdac_r", 291.28, 1.0, terms, sub="AVSS")
    x0 = SW + 2.0
    b.place(ra.cell, x0, 0.0)
    pr = bl.Placed(ra, x0, 0.0, False, "R")
    # res_cell names pins by net; every strip end is a separate segment of its net
    for n, segs in pr.pins.items():
        conn(n, segs)
    # ---- switch strips, one master
    swc = an.strip_cell(b, "dac1_sw", "n", 1.0, 0.28, ["OUTP", "D", "XP", "DB", "OUTN", "D", "XN", "DB", "OUTP"],
                        gates={"D": ("t", 0), "DB": ("t", 1)}, order=["OUTP", "OUTN", "XP", "XN"], bulk="VSS")
    xs = x0 + ra.width + 3.0
    per_col = 16
    for k, cell in enumerate(cells):
        col, row = divmod(k, per_col)
        x = xs + col * (swc.width + 2.0)
        y = row * (swc.height + 1.0)
        b.place(swc.cell, x, y)
        p = bl.Placed(swc, x, y, False, cell + ".SW")
        d0 = sw[cell][0]
        m = {"OUTP": "I1P", "OUTN": "I1N", "XP": f"{cell}.XP", "XN": f"{cell}.XN", "D": f"{cell}.D",
             "DB": f"{cell}.DB", "VSS": "AVSS"}
        for pn, segs in p.pins.items():
            conn(m[pn], segs)
    x_logic = xs + 2 * (swc.width + 2.0) + 3.0
    x_logic = round(x_logic / lg.PITCH) * lg.PITCH
    # ---- logic leaves in rows (netblock.make_leaf), to the east
    rows = bl.Rows(b, x_logic, 0.0)
    r = 0
    max_w = 60.0
    for path, model, env, cnets in gates:
        if model == "dev":                       # the brk's MOS capacitor (nfet, S/D/B on VSS)
            d = env
            cell = nb.make_leaf(b, "dac1_cd", ["D", "G", "VSS"], [nb.Dev("X", d.model, "D", "G", "VSS", "VSS", d.w, d.l, d.nf)])
            cmap = {"D": "AVSS", "G": d.g, "VSS": "AVSS", "VDD": "AVDD"}
        else:
            ports, devs = nb.leaf_devices(subs, model, env)
            vname = g.variant_name(model, env) if subs[model][1] else model
            cell = nb.make_leaf(b, vname, ports, devs)
            cmap = dict(cnets)
            cmap.setdefault("VDD", "AVDD")
            cmap.setdefault("VSS", "AVSS")
        if getattr(cell, "height", lg.H) != lg.H:
            raise ValueError(f"{path}: driver cell in the DAC1 logic")
        if rows.rows and rows.xcur[r] + cell.width > x_logic + max_w:
            r += 1
        p = rows.add(r, cell, path)
        for pn, segs in p.pins.items():
            if pn in ("VDD", "VSS"):            # rails: joined to the straps at the row ends
                continue
            net = cmap.get(pn, pn)
            conn(net, segs)
    rows.fill_all()
    width = x_logic + rows.width() + 2.0 + 2 * (SW + 1.0) + 0.6
    height = max(ra.height, per_col * (swc.height + 1.0), rows.height()) + 10.0
    # ---- power: AVSS straps on the west edge and east of the logic, AVDD on the east
    # edge; the logic rails run east to their strap (VDD under the AVSS strap)
    xs_vss, xs_vss2, xs_vdd = SW / 2 + 0.4, width - 1.5 * SW - 1.4, width - SW / 2 - 0.4
    for net, x in (("AVSS", xs_vss), ("AVSS", xs_vss2), ("AVDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
    for net, a, c_ in rows.rails():
        x = xs_vss2 if net == "VSS" else xs_vdd
        b.box("metal2", x_logic + rows.width() - 0.5, a, x + SW / 2, c_)
        b.vias("via2", x - SW / 2, a, x + SW / 2, c_)
    nets.pop("AVDD", None)
    for x in (xs_vss, xs_vss2):
        conn("AVSS", [("metal3", x - SW / 2, -1.0, x + SW / 2, height)])
    # ---- ports: Metal3 stubs on the top edge
    ports = ["INP", "INN", "I1P", "I1N", "VREFP", "VREFN"] + [f"SEL1_{k}" for k in range(31)] + ["DAC_CLK"]
    gx0 = (x_logic + lg.GATE0) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (SW + 2.0)) / len(ports)
    pp = bl.ports_top(b, ports, [snap(SW + 2.0 + step * (k + 0.5)) for k in range(len(ports))], height)
    for n, pin in pp.items():
        conn(n, [pin])
    rt = route.Router(gx0, -1.5, xs_vss2 + SW / 2 + 0.5, height + 0.5, px=lg.PITCH)
    failed = rt.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, rt.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    rt.draw(b)
    return b, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "adc_rdac")
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    b, (w, h) = build()
    print(f"adc_rdac: {w:.1f} x {h:.1f} um")
    bl.check(b, "adc_rdac", FILES, runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Layout of adc_rdac (LVS wrapper gf180/tapeout/layout/lvs/adc_rdac.spice, tracker E4):
the ADC's stage-1 input resistors RIN and the DAC1 (gf180/tapeout/adc/eeg_dac1.spice).

Since C1 was halved (10/23) RIN is 16 unit resistors per side and every DAC1 element
two units in series (RIN/RD1 = 31/32 by construction), so all 156 units (300 kohm
ppolyf_u_1k, 291.28 x 1 um) sit in one resistor array, interleaved per DAC1 cell k as
[RIN_P], RD_P(k) x 2, [RIN_N], RD_N(k) x 2 (RIN rows at even k). An element is folded:
its two units have the middle node MP / MN on their west ends (joined by the router)
and XP(k) and VREFP (XN(k), VREFN) on their east ends; RIN runs from INP / INN (west)
to I1P / I1N (east).
Ports (for the ADC assembly, gf180/tapeout/layout/adc_lay.py): INP, INN, VREFP, VREFN on
the west part of the top edge and I1P, I1N at its east end (towards OTA1 and the C1
buses); SEL1_0..30 and DAC_CLK on the east part of the bottom edge, above a 14 um
channel (the SEL1 lines come from eeg_adc_dig along the bottom of the ADC band).
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
YB = 14.0           # bottom channel for the SEL1 / DAC_CLK ports


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
    # the wrapper's RIN lines (m=16) are written out by hand below; a DAC1 cell has
    # XRPA (VRP - MP), XRPB (MP - XP) and the same on the N side
    terms = []
    cells = sorted(sw, key=lambda s: int(s.split(".XC")[-1]))
    dev = {d.name: d for d in res}
    for k, cell in enumerate(cells):
        for side, rin in (("P", ("INP", "I1P")), ("N", ("INN", "I1N"))):
            ra, rb = dev[f"{cell}.XR{side}A"], dev[f"{cell}.XR{side}B"]
            if k % 2 == 0:
                terms.append(rin)
            terms += [(rb.d, rb.g), (ra.g, ra.d)]       # middle node on both west ends
    ra = an.res_cell(b, "rdac_r", 291.28, 1.0, terms, sub="AVSS")
    x0 = SW + 2.0
    b.place(ra.cell, x0, YB)
    pr = bl.Placed(ra, x0, YB, False, "R")
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
        y = YB + row * (swc.height + 1.0)
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
    rows = bl.Rows(b, x_logic, YB)
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
    height = YB + max(ra.height, per_col * (swc.height + 1.0), rows.height()) + 10.0
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
    # ---- ports: Metal3 stubs, analog on the top edge, SEL1 / DAC_CLK on the bottom edge
    gx0 = (x_logic + lg.GATE0) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    top = {"INP": 12.0, "INN": 22.0, "VREFP": 40.0, "VREFN": 50.0, "I1P": width - 28.0, "I1N": width - 18.0}
    pp = bl.ports_top(b, list(top), [snap(v) for v in top.values()], height)
    bot = [f"SEL1_{k}" for k in range(31)] + ["DAC_CLK"]
    xb0 = xs - 20.0
    stepb = (xs_vss2 - SW / 2 - 3.0 - xb0) / len(bot)
    pp.update(bl.ports_bottom(b, bot, [snap(xb0 + stepb * (k + 0.5)) for k in range(len(bot))], -1.0))
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

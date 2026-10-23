#!/usr/bin/env python3
"""Layout of eeg_afe_core (gf180/tapeout/afe/eeg_afe.spice, tracker E3): the AFE's
current-reuse input stage with regulated cascodes.

Two columns of guarded multi-strip cells (analog.multi_strip_cell), joined by Metal3
lanes for the high-current nets (blocks.lanes; 0.67 mA/um of Metal3 width):
  column N (west): NMOS input pair XN_P / XN_N (W10/L1.5, 2048 + 2048 fingers, A B B A
    by finger pairs, every other strip B A A B), the NMOS tail XNT (L1, 768), the NMOS
    cascodes XNC_P / XNC_N (L1, 512 + 512) and the NMOS boosters (XGNCPB / XGNCNB L4,
    XGPCPL / XGPCNL L8, XBLND L8)
  column P (east): PMOS input pair XP_P / XP_N (W10/L0.28, 4096 + 4096), the PMOS tail
    XPT (L2, 2048), the PMOS cascodes XPC_P / XPC_N (L1, 1024 + 1024) and the PMOS
    boosters (XGNCPL / XGNCNL L8, XGPCPB / XGPCNB L2, XBLPD L8)
Branch currents about 9.6 mA (SN, SP 19.2 mA): 12 lanes of 1.2 um per branch net, 24 for
SN, SP, VDD and VSS. OUTP / OUTN join the columns through Metal4 trunks near the top;
INP / INN (both pairs' gates) and the booster nets go through route.Router.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/afecore_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import route
from ota_lay import pair_seq, dev_seq

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
SW = 2.4


def cells(b):
    C = {}
    # ---- column N
    C["npair"] = an.multi_strip_cell(b, "afec_npair", "n", [
        dict(w=10.0, l=1.5, seq=pair_seq("DNP", "INP", "DNN", "INN", "SN", 16, start_b=(k % 2 == 1)),
             gates={"INP": ("t", 0), "INN": ("t", 1)}, order=["SN", "DNP", "DNN"],
             straps={"SN": 2, "DNP": 2, "DNN": 2}) for k in range(32)], bulk="VSS")
    C["ntail"] = an.multi_strip_cell(b, "afec_ntail", "n", [
        dict(w=10.0, l=1.0, seq=dev_seq("SN", "VBN", "VSS", 128), order=["VSS", "SN"], straps={"VSS": 3, "SN": 3})
        for _ in range(6)], bulk="VSS")
    ncp = dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "GNCP", "DNP", 128), order=["DNP", "OUTN"],
               straps={"DNP": 3, "OUTN": 3})
    ncn = dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "GNCN", "DNN", 128), order=["DNN", "OUTP"],
               straps={"DNN": 3, "OUTP": 3})
    C["ncas"] = an.multi_strip_cell(b, "afec_ncas", "n", [ncp, ncn, ncn, ncp, ncp, ncn, ncn, ncp], bulk="VSS")
    C["nboost"] = an.multi_strip_cell(b, "afec_nboost", "n", [
        dict(w=10.0, l=4.0, seq=dev_seq("GNCP", "DNP", "VSS", 32), order=["VSS", "GNCP"]),
        dict(w=10.0, l=4.0, seq=dev_seq("GNCN", "DNN", "VSS", 32), order=["VSS", "GNCN"]),
        dict(w=10.0, l=8.0, seq=dev_seq("GPCP", "BLN", "VSS", 40), order=["VSS", "GPCP"]),
        dict(w=10.0, l=8.0, seq=dev_seq("GPCN", "BLN", "VSS", 40), order=["VSS", "GPCN"]),
        dict(w=10.0, l=8.0, seq=dev_seq("BLN", "BLN", "VSS", 8), order=["VSS", "BLN"])], bulk="VSS")
    # ---- column P
    C["ppair"] = an.multi_strip_cell(b, "afec_ppair", "p", [
        dict(w=10.0, l=0.28, seq=pair_seq("DPP", "INP", "DPN", "INN", "SP", 64, start_b=(k % 2 == 1)),
             gates={"INP": ("t", 0), "INN": ("t", 1)}, order=["SP", "DPP", "DPN"],
             straps={"SP": 2, "DPP": 2, "DPN": 2}) for k in range(16)], bulk="VDD")
    C["ptail"] = an.multi_strip_cell(b, "afec_ptail", "p", [
        dict(w=10.0, l=2.0, seq=dev_seq("SP", "VBP", "VDD", 128), order=["VDD", "SP"], straps={"VDD": 3, "SP": 3})
        for _ in range(16)], bulk="VDD")
    pcp = dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "GPCP", "DPP", 256), order=["DPP", "OUTN"],
               straps={"DPP": 3, "OUTN": 3})
    pcn = dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "GPCN", "DPN", 256), order=["DPN", "OUTP"],
               straps={"DPN": 3, "OUTP": 3})
    C["pcas"] = an.multi_strip_cell(b, "afec_pcas", "p", [pcp, pcn, pcn, pcp, pcp, pcn, pcn, pcp], bulk="VDD")
    C["pboost"] = an.multi_strip_cell(b, "afec_pboost", "p", [
        dict(w=10.0, l=8.0, seq=dev_seq("GNCP", "BLP", "VDD", 64), order=["VDD", "GNCP"]),
        dict(w=10.0, l=8.0, seq=dev_seq("GNCN", "BLP", "VDD", 64), order=["VDD", "GNCN"]),
        dict(w=10.0, l=2.0, seq=dev_seq("GPCP", "DPP", "VDD", 128), order=["VDD", "GPCP"]),
        dict(w=10.0, l=2.0, seq=dev_seq("GPCN", "DPN", "VDD", 128), order=["VDD", "GPCN"]),
        dict(w=10.0, l=8.0, seq=dev_seq("BLP", "BLP", "VDD", 8), order=["VDD", "BLP"])], bulk="VDD")
    return C


def build():
    name = "eeg_afe_core"
    b = g.Block(name)
    C = cells(b)
    nets, placed = {}, []

    def place(key, x, y):
        cell = C[key]
        b.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, key.upper())
        for pn, segs in p.pins.items():
            nets.setdefault(pn, []).extend(segs)
        placed.append(p)
        return p

    x0 = round((SW + 2.4) / lg.PITCH) * lg.PITCH
    # column N, bottom to top: boosters, tail, input pair, cascodes
    y = 0.0
    pn = []
    for key in ("nboost", "ntail", "npair", "ncas"):
        pn.append(place(key, x0, y))
        y += C[key].height + 3.0
    yn_top = y
    xp = x0 + max(C[k].width for k in ("nboost", "ntail", "npair", "ncas")) + 8.0
    y = 0.0
    pp = []
    for key in ("pboost", "ptail", "ppair", "pcas"):
        pp.append(place(key, xp, y))
        y += C[key].height + 3.0
    yp_top = y
    height = max(yn_top, yp_top) + 14.0
    width = xp + max(C[k].width for k in ("pboost", "ptail", "ppair", "pcas")) + 4.0 + SW

    def spread(x1, x2, nets_here, per):
        out = {}
        k = sum(per[n] for n in nets_here)
        order = []
        m = max(per.values())
        for r in range(m):
            for n in nets_here:
                if r < per[n]:
                    order.append(n)
        step = (x2 - x1) / len(order)
        for i, n in enumerate(order):
            out.setdefault(n, []).append(round((x1 + (i + 0.5) * step - 0.6) / 0.005) * 0.005)
        return out

    pd = {p.name: p for p in placed}
    # lanes over the narrower cells of each column must fall inside every cell that
    # carries the net: tail / cascodes are narrower than the pairs, so their lanes sit in
    # their x range (5 um left open at the west end for the gate pins)
    def rng(key):
        p = pd[key.upper()]
        return p.x + 2.2 + 5.0, p.x + p.cell.width - 2.2

    per_n = {"VSS": 12, "SN": 24, "DNP": 12, "DNN": 12, "OUTN": 12, "OUTP": 12}
    a1 = max(rng("ntail")[0], rng("ncas")[0], rng("npair")[0])
    a2 = min(rng("ntail")[1], rng("ncas")[1], rng("npair")[1])
    la = spread(a1, a2, ["VSS", "SN", "DNP", "DNN", "OUTN", "OUTP"], per_n)
    per_p = {"VDD": 12, "SP": 24, "DPP": 12, "DPN": 12, "OUTN": 12, "OUTP": 12}
    b1 = max(rng("ptail")[0], rng("pcas")[0], rng("ppair")[0])
    b2 = min(rng("ptail")[1], rng("pcas")[1], rng("ppair")[1])
    lb = spread(b1, b2, ["VDD", "SP", "DPP", "DPN", "OUTN", "OUTP"], per_p)
    top_y = height - 6.0
    bars_n = bl.lanes(b, pn, la, extend={"OUTP": (0, top_y), "OUTN": (0, top_y)})
    bars_p = bl.lanes(b, pp, lb, extend={"OUTP": (0, top_y), "OUTN": (0, top_y)})
    trunk_vias = []
    for k, n in enumerate(("OUTP", "OUTN")):
        yt = top_y - 2.5 - k * 4.0
        segs = bars_n.get(n, []) + bars_p.get(n, [])
        xs_all = [bx[1] for bx in segs]
        b.box("metal4", min(xs_all), yt - 1.5, max(xs_all) + 1.2, yt + 1.5)
        for bx in segs:
            b.vias("via3", bx[1], yt - 1.5, bx[1] + 1.2, yt + 1.5)
            trunk_vias.append((bx[1], yt - 1.5, bx[1] + 1.2, yt + 1.5))
        nets.setdefault(n, []).append(("metal4", min(xs_all), yt - 1.5, max(xs_all) + 1.2, yt + 1.5))
    lanes_nets = {"VSS", "SN", "DNP", "DNN", "OUTN", "OUTP", "VDD", "SP", "DPP", "DPN"}
    big = {p.name for p in placed if p.name in ("NTAIL", "NPAIR", "NCAS", "PTAIL", "PPAIR", "PCAS")}
    for n in lanes_nets:
        keep = [sg for sg in nets.get(n, []) if not any(p.name in big and sg in p.pins.get(n, []) for p in placed)]
        nets[n] = keep + bars_n.get(n, []) + bars_p.get(n, [])
    xs_vss, xs_vdd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
        nets.setdefault(net, []).append(("metal3", x - SW / 2, -1.0, x + SW / 2, height))
    ports = ["INP", "INN", "OUTP", "OUTN", "VBN", "VBP", "BLP", "BLN"]
    gx0 = 0.24
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (SW + 2.0)) / len(ports)
    ppins = bl.ports_top(b, ports, [snap(SW + 2.0 + step * (k + 0.5)) for k in range(len(ports))], height)
    for n, pin in ppins.items():
        nets.setdefault(n, []).append(pin)
    r = route.Router(gx0, -1.5, width, height + 0.5, px=lg.PITCH)
    for bx in trunk_vias:
        r.via_keepout(*bx)
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(b)
    return b, name, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    b, name, (w, h) = build()
    runs = os.path.join(HERE, "runs", name)
    os.makedirs(runs, exist_ok=True)
    print(f"{name}: {w:.1f} x {h:.1f} um")
    bl.check(b, name, [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

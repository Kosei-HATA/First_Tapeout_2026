#!/usr/bin/env python3
"""Layouts of the ADC integrator OTAs (gf180/tapeout/adc/eeg_adc_otas.spice, tracker E4).

gf180_ct_ota_tel16_cmfb (OTA2, 52 uA tail): telescopic core and CMFB.
  NMOS (one ring): the input pair (W10/L4, 32 + 32 fingers in four strips, A B B A per
  four fingers, every other strip starting with B: common centroid), the tail, the two
  NMOS cascodes, the CMFB pairs and tails. PMOS (one ring): the loads (W10/L2, 8 + 8
  interleaved), the two PMOS cascodes, the CMFB mirror. Two 10 pF MIM (CCOMP).
  Routing: route.Router (the currents are small).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/ota_lay.py [--drc] [--lvs] [--only ota2]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import route

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "adc", "eeg_adc_otas.spice")
SW = 2.4


def pair_seq(da, ga, db, gb, s, n4, start_b=False):
    """Interleaved differential pair on a common source s. A finger pair shares its drain
    (s g d g s), so the unit is a finger pair; n4 groups of four pairs in the order
    A B B A (B A A B when start_b): 8 * n4 fingers, half of each device."""
    seq = [s]
    for k in range(n4):
        order = ("A", "B", "B", "A") if (k % 2 == 0) != start_b else ("B", "A", "A", "B")
        for which in order:
            d, gt = (da, ga) if which == "A" else (db, gb)
            seq += [gt, d, gt, s]
    return seq


def dev_seq(d, gt, s, n):
    """n fingers of one device, sources at the ends: s g d g s g d ..."""
    seq = [s]
    for k in range(n):
        seq += [gt, d if k % 2 == 0 else s]
    return seq


def ota2(b):
    nets = {}
    # ---- NMOS
    pair = [dict(w=10.0, l=4.0, seq=pair_seq("N1P", "INP", "N1N", "INN", "TAIL", 2, start_b=(k % 2 == 1)),
                 order=["TAIL", "N1P", "N1N"]) for k in range(4)]
    tail = [dict(w=10.0, l=1.0, seq=dev_seq("TAIL", "VBN", "VSS", 2), order=["VSS", "TAIL"])]
    casc = [dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "VNC", "N1P", 4), order=["N1P", "OUTN"]),
            dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "VNC", "N1N", 4), order=["N1N", "OUTP"])]
    cmfb = [dict(w=10.0, l=2.0, seq=["ND", "OUTP", "NTA", "VCMREF", "VBP", "VCMREF", "NTA", "OUTP", "ND"],
                 gates={"OUTP": ("t", 0), "VCMREF": ("t", 1)}, order=["NTA", "ND", "VBP"]),
            dict(w=10.0, l=2.0, seq=["ND", "OUTN", "NTB", "VCMREF", "VBP", "VCMREF", "NTB", "OUTN", "ND"],
                 gates={"OUTN": ("t", 0), "VCMREF": ("t", 1)}, order=["NTB", "ND", "VBP"]),
            dict(w=10.0, l=2.0, seq=["NTA", "VBCM", "VSS", "VBCM", "NTB"], order=["VSS", "NTA", "NTB"])]
    ncell = an.multi_strip_cell(b, "ota2_n", "n", pair + tail + casc + cmfb, bulk="VSS")
    # ---- PMOS
    loads = [dict(w=10.0, l=2.0, seq=pair_seq("P1P", "VBP", "P1N", "VBP", "VDD", 2), order=["VDD", "P1P", "P1N"])]
    pcas = [dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "VPC", "P1P", 8), order=["P1P", "OUTP"]),
            dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "VPC", "P1N", 8), order=["P1N", "OUTN"])]
    pmir = [dict(w=10.0, l=2.0, seq=["VDD", "ND", "ND", "ND", "VDD", "ND", "VBP", "ND", "VDD", "ND", "ND", "ND", "VDD",
                                     "ND", "VBP", "ND", "VDD"], order=["VDD", "ND", "VBP"])]
    pcell = an.multi_strip_cell(b, "ota2_p", "p", loads + pcas + pmir, bulk="VDD")
    cc = an.mim_cell(b, "ota2_cc", 70.65, "VBP", "OUT", n=1)
    return ncell, pcell, cc


def build_ota2():
    name = "gf180_ct_ota_tel16_cmfb"
    b = g.Block(name)
    ncell, pcell, cc = ota2(b)
    nets = {}
    placed = []

    def place(cell, x, y, pname, cmap=None):
        b.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, pname)
        for pn, segs in p.pins.items():
            nets.setdefault((cmap or {}).get(pn, pn), []).extend(segs)
        placed.append(p)
        return p

    x0 = round((SW + 2.4) / lg.PITCH) * lg.PITCH
    pn_ = place(ncell, x0, 0.0, "N")
    pp_ = place(pcell, x0, ncell.height + 3.0, "P")
    xm = x0 + max(ncell.width, pcell.width) + 4.0
    c1 = place(cc, xm, 0.0, "CCP", {"OUT": "OUTP"})
    c2 = place(cc, xm, cc.height + 3.0, "CCN", {"OUT": "OUTN"})
    width = xm + cc.width + 4.0 + SW
    height = max(ncell.height + 3.0 + pcell.height, 2 * cc.height + 3.0) + 10.0
    xs_vss, xs_vdd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
        nets.setdefault(net, []).append(("metal3", x - SW / 2, -1.0, x + SW / 2, height))
    ports = ["INP", "INN", "OUTP", "OUTN", "VCMREF", "VBN", "VNC", "VPC", "VBCM"]
    gx0 = (x0 + 1.04) % lg.PITCH
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (SW + 2.0)) / len(ports)
    pp = bl.ports_top(b, ports, [snap(SW + 2.0 + step * (k + 0.5)) for k in range(len(ports))], height)
    for n, pin in pp.items():
        nets.setdefault(n, []).append(pin)
    r = route.Router(gx0, -1.5, width, height + 0.5, px=lg.PITCH)
    for p, cell in ((c1, cc), (c2, cc)):
        k3, k4 = cell.keepout, cell.keepout4
        r.obstacle("metal3", p.x + k3[0], p.y + k3[1], p.x + k3[2], p.y + k3[3])
        r.obstacle("metal4", p.x + k4[0], p.y + k4[1], p.x + k4[2], p.y + k4[3])
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(b)
    return b, name, (width, height)


def tg_pair_seq(a1, g1, x, g2, a2, groups):
    """Two TGs (or commutator halves) sharing the middle node x: per group of four
    fingers a1 g1 x g2 a2 g2 x g1 a1, i.e. x-a1 on gate g1 and x-a2 on gate g2."""
    seq = [a1]
    for k in range(groups):
        seq += [g1, x, g2, a2, g2, x, g1, a1]
    return seq


def ota1(b):
    """Cells of OTA1 (gf180_inside_cascode_ota)."""
    st = {"straps": None}
    # NMOS: input pair (16 strips x 128 fingers, W10/L1) and the tail (128 fingers)
    pair = [dict(w=10.0, l=1.0, seq=pair_seq("D1P", "CIP", "D1N", "CIN", "TAIL", 16, start_b=(k % 2 == 1)),
                 gates={"CIP": ("t", 0), "CIN": ("t", 1)}, order=["TAIL", "D1P", "D1N"],
                 straps={"TAIL": 2, "D1P": 2, "D1N": 2}) for k in range(16)]
    tail = [dict(w=10.0, l=1.0, seq=dev_seq("TAIL", "VBN", "VSS", 128), order=["VSS", "TAIL"],
                 straps={"VSS": 3, "TAIL": 3})]
    nin = an.multi_strip_cell(b, "ota1_nin", "n", tail[:0] + pair[:8] + tail + pair[8:], bulk="VSS")
    # NMOS cascodes: 2 + 2 strips of 128 (nc_p nc_n nc_n nc_p)
    ncp = dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "VNC", "N1P", 128), order=["N1P", "OUTN"], straps={"N1P": 3, "OUTN": 3})
    ncn = dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "VNC", "N1N", 128), order=["N1N", "OUTP"], straps={"N1N": 3, "OUTP": 3})
    ncas = an.multi_strip_cell(b, "ota1_ncas", "n", [ncp, ncn, ncn, ncp], bulk="VSS")
    # N-side commutator (D1x -> N1x): NMOS halves (W20 m8 = 160 um: 16 fingers of 10 um per
    # device, 8 groups) and PMOS halves (W40 m8 = 320 um: 32 fingers, 16 groups)
    def comm(kind, ga, gb, groups, d_p, d_n, n_p, n_n):
        return [dict(w=10.0, l=0.28, seq=tg_pair_seq(n_p, ga, d_p, gb, n_n, groups),
                     gates={ga: ("t", 0), gb: ("t", 1)}, order=[d_p, n_p, n_n], straps={d_p: 2, n_p: 2, n_n: 2}),
                dict(w=10.0, l=0.28, seq=tg_pair_seq(n_n, ga, d_n, gb, n_p, groups),
                     gates={ga: ("t", 0), gb: ("t", 1)}, order=[d_n, n_n, n_p], straps={d_n: 2, n_n: 2, n_p: 2})]
    ntg = an.multi_strip_cell(b, "ota1_ntg", "n", comm("n", "CDA", "CDB", 8, "D1P", "D1N", "N1P", "N1N"), bulk="VSS")
    ptg = an.multi_strip_cell(b, "ota1_ptg", "p", comm("p", "NCDA", "NCDB", 16, "D1P", "D1N", "N1P", "N1N"), bulk="VDD")
    # P-side commutator (P1x -> P2x)
    nptg = an.multi_strip_cell(b, "ota1_nptg", "n", comm("n", "CDA", "CDB", 8, "P1P", "P1N", "P2P", "P2N"), bulk="VSS")
    pptg = an.multi_strip_cell(b, "ota1_pptg", "p", comm("p", "NCDA", "NCDB", 16, "P1P", "P1N", "P2P", "P2N"), bulk="VDD")
    # PMOS cascodes: 4 + 4 strips of 128
    pcp = dict(w=10.0, l=1.0, seq=dev_seq("OUTP", "VPC", "P2P", 128), order=["P2P", "OUTP"], straps={"P2P": 3, "OUTP": 3})
    pcn = dict(w=10.0, l=1.0, seq=dev_seq("OUTN", "VPC", "P2N", 128), order=["P2N", "OUTN"], straps={"P2N": 3, "OUTN": 3})
    pcas = an.multi_strip_cell(b, "ota1_pcas", "p", [pcp, pcn, pcn, pcp, pcp, pcn, pcn, pcp], bulk="VDD")
    # PMOS loads W10/L4 x 512 per side: 16 strips of 64 fingers, P1P / P1N interleaved
    pload = an.multi_strip_cell(b, "ota1_pload", "p", [
        dict(w=10.0, l=4.0, seq=pair_seq("P1P", "VBP", "P1N", "VBP", "VDD", 8, start_b=(k % 2 == 1)),
             order=["VDD", "P1P", "P1N"], straps={"VDD": 2, "P1P": 2, "P1N": 2}) for k in range(16)], bulk="VDD")
    # input chopper (four chop_tg): INP / INN -> CIP / CIN
    chn = an.multi_strip_cell(b, "ota1_chn", "n", comm("n", "CIA", "CIB", 8, "INP", "INN", "CIP", "CIN"), bulk="VSS")
    chp = an.multi_strip_cell(b, "ota1_chp", "p", comm("p", "NCIA", "NCIB", 16, "INP", "INN", "CIP", "CIN"), bulk="VDD")
    # CMFB (cmfb8: NMOS pairs L2 m2, tails m1; PMOS mirror m4)
    cmn = an.multi_strip_cell(b, "ota1_cmn", "n", [
        dict(w=10.0, l=2.0, seq=["ND", "OUTP", "NTA", "VCMREF", "VBP", "VCMREF", "NTA", "OUTP", "ND"],
             gates={"OUTP": ("t", 0), "VCMREF": ("t", 1)}, order=["NTA", "ND", "VBP"]),
        dict(w=10.0, l=2.0, seq=["ND", "OUTN", "NTB", "VCMREF", "VBP", "VCMREF", "NTB", "OUTN", "ND"],
             gates={"OUTN": ("t", 0), "VCMREF": ("t", 1)}, order=["NTB", "ND", "VBP"]),
        dict(w=10.0, l=2.0, seq=["NTA", "VBCM", "VSS", "VBCM", "NTB"], order=["VSS", "NTA", "NTB"])], bulk="VSS")
    cmp_ = an.multi_strip_cell(b, "ota1_cmp", "p", [
        dict(w=10.0, l=2.0, seq=["VDD", "ND", "ND", "ND", "VDD", "ND", "VBP", "ND", "VDD", "ND", "ND", "ND", "VDD",
                                 "ND", "VBP", "ND", "VDD"], order=["VDD", "ND", "VBP"])], bulk="VDD")
    cc = an.mim_cell(b, "ota1_cc", 70.65, "VBP", "OUT", n=1)
    return dict(nin=nin, ncas=ncas, ntg=ntg, ptg=ptg, nptg=nptg, pptg=pptg, pcas=pcas, pload=pload, chn=chn, chp=chp,
                cmn=cmn, cmp=cmp_, cc=cc)


HIGH = ["VSS", "TAIL", "D1P", "D1N", "N1P", "N1N", "OUTN", "OUTP", "P2P", "P2N", "P1P", "P1N", "VDD"]


def build_ota1():
    name = "gf180_inside_cascode_ota"
    b = g.Block(name)
    C = ota1(b)
    nets, placed = {}, []

    def place(cell, x, y, pname, cmap=None):
        b.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, pname)
        for pn, segs in p.pins.items():
            nets.setdefault((cmap or {}).get(pn, pn), []).extend(segs)
        placed.append(p)
        return p

    x0 = round((SW + 2.4) / lg.PITCH) * lg.PITCH
    # column A (NMOS world), bottom to top: input pair + tail, commutator halves, cascodes
    y = 0.0
    pa = [place(C["nin"], x0, y, "NIN")]
    y += C["nin"].height + 3.0
    pa.append(place(C["ntg"], x0, y, "NTG"))
    pa.append(place(C["ptg"], x0 + C["ntg"].width + 3.0, y, "PTG"))
    y += max(C["ntg"].height, C["ptg"].height) + 3.0
    pa.append(place(C["ncas"], x0, y, "NCAS"))
    ya_top = y + C["ncas"].height
    # column B (PMOS world), east of A, bottom to top: cascodes, commutator halves, loads
    xb = x0 + C["nin"].width + 6.0
    y = 0.0
    pb = [place(C["pcas"], xb, y, "PCAS")]
    y += C["pcas"].height + 3.0
    pb.append(place(C["nptg"], xb, y, "NPTG"))
    pb.append(place(C["pptg"], xb + C["nptg"].width + 3.0, y, "PPTG"))
    y += max(C["nptg"].height, C["pptg"].height) + 3.0
    pb.append(place(C["pload"], xb, y, "PLOAD"))
    yb_top = y + C["pload"].height
    # east: input chopper, CMFB, compensation MIMs
    xe = xb + max(C["pcas"].width, C["pload"].width) + 6.0
    y = 0.0
    pe = []
    for key in ("chn", "chp", "cmn", "cmp"):
        pe.append(place(C[key], xe, y, key.upper()))
        y += C[key].height + 3.0
    ccs = []
    for k, out in enumerate(("OUTP", "OUTN")):
        ccs.append(place(C["cc"], xe, y, f"CC{k}", {"OUT": out}))
        y += C["cc"].height + 3.0
    height = max(ya_top, yb_top, y) + 12.0
    width = xe + max(C[k].width for k in ("chn", "chp", "cmn", "cmp", "cc")) + 4.0 + SW
    # ---- high-current lanes (Metal3 bars over the stacked cells). Every narrow cell gets
    # one lane per net it carries inside its own x range; the full-width cells (input pair,
    # cascodes, loads) join the lanes of a net to each other through their straps.
    def spread(x1, x2, nets_here, per=1, w=1.2):
        out = {}
        k = per * len(nets_here)
        step = (x2 - x1) / k
        for m in range(k):
            n = nets_here[m % len(nets_here)]
            xx = x1 + (m + 0.5) * step - w / 2
            out.setdefault(n, []).append(round(xx / 0.005) * 0.005)
        return out

    def inner(p, free=5.0):
        """x range for a cell's lanes: inside its ring, the first `free` um left open so the
        router can still reach the gate pins that run along the strips"""
        return p.x + 2.2 + free, p.x + p.cell.width - 2.2

    def merge(*ds):
        out = {}
        for d in ds:
            for n, xs in d.items():
                out.setdefault(n, []).extend(xs)
        return out

    pd = {p.name: p for p in placed}
    xa1, xa2 = inner(pd["NIN"])
    la = merge(spread(*inner(pd["NTG"]), ["D1P", "N1P", "VSS", "N1N", "D1N"]),
               spread(*inner(pd["PTG"]), ["D1P", "N1P", "VDD", "N1N", "D1N"], per=2),
               spread(pd["PTG"].x + pd["PTG"].cell.width + 2.0, xa2,
                      ["VSS", "TAIL", "D1P", "OUTN", "N1P", "N1N", "OUTP", "D1N", "TAIL"], per=2))
    xb1, xb2 = inner(pd["PCAS"])
    lb = merge(spread(*inner(pd["NPTG"]), ["P1P", "P2P", "VSS", "P2N", "P1N"]),
               spread(*inner(pd["PPTG"]), ["P1P", "P2P", "VDD", "P2N", "P1N"], per=2),
               spread(pd["PPTG"].x + pd["PPTG"].cell.width + 2.0, xb2,
                      ["VDD", "P1P", "OUTP", "P2P", "P2N", "OUTN", "P1N", "VDD"], per=2))
    top_y = height - 8.0
    bars_a = bl.lanes(b, pa, la, extend={"OUTP": (0, top_y), "OUTN": (0, top_y)})
    bars_b = bl.lanes(b, pb, lb, extend={"OUTP": (0, top_y), "OUTN": (0, top_y)})
    trunk_vias = []
    # OUTP / OUTN trunks (Metal4) across both columns near the top, via3 on their lanes
    for k, n in enumerate(("OUTP", "OUTN")):
        yt = top_y - 2.5 - k * 3.0
        xs_all = [bx[1] for bx in bars_a.get(n, []) + bars_b.get(n, [])]
        b.box("metal4", min(xs_all), yt - 1.0, max(xs_all) + 1.2, yt + 1.0)
        for bx in bars_a.get(n, []) + bars_b.get(n, []):
            b.vias("via3", bx[1], yt - 1.0, bx[1] + 1.2, yt + 1.0)
            trunk_vias.append((bx[1], yt - 1.0, bx[1] + 1.2, yt + 1.0))
        nets.setdefault(n, []).append(("metal4", min(xs_all), yt - 1.0, max(xs_all) + 1.2, yt + 1.0))
    # the lanes replace the Metal2 strap pins of their nets inside the columns
    for n in set(HIGH):
        segs = nets.get(n, [])
        keep = [sg for sg in segs if not any(p.name in ("NIN", "NTG", "PTG", "NCAS", "PCAS", "NPTG", "PPTG", "PLOAD")
                                             and sg in p.pins.get(n, []) for p in placed)]
        nets[n] = keep + bars_a.get(n, []) + bars_b.get(n, [])
    # power straps west (VSS) / east (VDD) and ports on the top edge
    xs_vss, xs_vdd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, height)
        b.label("metal3", net, x, 2.0)
        nets.setdefault(net, []).append(("metal3", x - SW / 2, -1.0, x + SW / 2, height))
    ports = ["INP", "INN", "OUTP", "OUTN", "VCMREF", "VBN", "VNC", "VPC", "VBCM", "CIA", "NCIA", "CIB", "NCIB",
             "CDA", "NCDA", "CDB", "NCDB"]
    gx0 = 0.24
    snap = lambda v: gx0 + round((v - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (SW + 2.0)) / len(ports)
    pp = bl.ports_top(b, ports, [snap(SW + 2.0 + step * (k + 0.5)) for k in range(len(ports))], height)
    for n, pin in pp.items():
        nets.setdefault(n, []).append(pin)
    r = route.Router(gx0, -1.5, width, height + 0.5, px=lg.PITCH)
    for p in ccs:
        k3, k4 = C["cc"].keepout, C["cc"].keepout4
        r.obstacle("metal3", p.x + k3[0], p.y + k3[1], p.x + k3[2], p.y + k3[3])
        r.obstacle("metal4", p.x + k4[0], p.y + k4[1], p.x + k4[2], p.y + k4[3])
    for (lay, x1, y1, x2, y2) in [sg for n in ("OUTP", "OUTN") for sg in nets[n] if sg[0] == "metal4"]:
        pass
    for bx in [v for bars in (bars_a, bars_b) for n, segs in bars.items() for v in segs]:
        pass
    for n in list(nets):
        for sg in nets[n]:
            if sg[0] == "metal3" and (sg in bars_a.get(n, []) or sg in bars_b.get(n, [])):
                r.obstacle("metal3", *sg[1:], n)
    for p in placed:
        for bx in bl.cell_shapes(p, "via3"):
            r.via_keepout(*bx)
    for bx in trunk_vias:
        r.via_keepout(*bx)
    # via3 under the OUTP/OUTN trunks were drawn by this script: keep the router's vias off them
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(b)
    # name hints for the LVS net matcher: CIP / CIN are nets of this subcircuit (not
    # pins); without them it pairs D1P / D1N and P1P / P1N the wrong way round
    for n, hint in (("CIP", "CIP"), ("CIN", "CIN"), ("P1P", "OTA.CORE.P1P"), ("P1N", "OTA.CORE.P1N"),
                    ("D1P", "OTA.CORE.D1P"), ("D1N", "OTA.CORE.D1N")):
        lay, x1, y1, x2, y2 = [sg for sg in nets[n] if sg[0] in ("metal2", "metal3")][0]
        b.label(lay, hint, (x1 + x2) / 2, (y1 + y2) / 2)
    return b, name, (width, height)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    ap.add_argument("--only", nargs="+", default=["ota1", "ota2"])
    a = ap.parse_args()
    for which in a.only:
        b, name, (w, h) = {"ota2": build_ota2, "ota1": build_ota1}[which]()
        runs = os.path.join(HERE, "runs", name)
        os.makedirs(runs, exist_ok=True)
        print(f"{name}: {w:.1f} x {h:.1f} um")
        bl.check(b, name, [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Layout of the AFE (tracker E3): eeg_afe (gf180/tapeout/afe/eeg_afe.spice) in the AFE
region of the floorplan (1100 x 1447 um, core x 40..1140, y 100..1547). Top cell afe_top;
LVS against lvs/afe_top.spice.

Placement (local um; the differential axis at y = 723.5):
  - Cin arrays (eeg_cin, 636 pF per side) on the east 860.6 um, above and below the core
    band, both buses facing it: Cin_P (TOP = INP outer, BOT = WP), Cin_N mirrored.
  - core band (y 422..1025): the input chopper afe_tgin at the west (its electrode
    spines EP / EN on its west edge, for the pad straps), the core amplifier
    eeg_afe_core in the middle, and the output section in the east part: hold
    capacitors, CC, CFB, CPF, the Cpf trim, the output chopper, the CMFB, the reset and
    DC-path switches.
  - west corners: the offset-DAC halves offdac_p / offdac_n (offdac_lay.py), the clock
    driver eeg_afe_clk and its supply decoupling.
Hand-drawn wiring (the signal path is in series with the electrodes: tracker D6):
  - WP / WN from the input chopper's stripes into the Cin bottom-plate buses and the
    Metal3 planes under the arrays (w_entry: Metal3 / Metal4 / Metal5 plates over the
    chopper, a Metal5 sheet under it for WN);
  - the core's INP / INN Metal5 bars (its top / bottom edge) joined to the Cin top-plate
    buses along the core's width and on over the output section; the offset DAC's INP /
    INN stubs onto those bars;
  - WP / WN and INN taps for the output section, the P side's INP pins straight into the
    INP fill (fill_drop); the DC-path switches, two per side (sc_wiring), and their gate
    lines CDA2 / CDB2 from the east ports to the P side's switches, between AVSS shields;
  - AVSS / AVDD Metal5 rails from the east edge over the output section to the core's
    Metal4 supply rows over its tails (the core's 19 mA comes from the Ch-A side: the
    west of the band is the input chopper's).
Everything else: route.Router on Metal3 / Metal4.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/afe_lay.py [--drc] [--lvs]
"""
import argparse
import os
import time
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl
import route
import assemble as A
import fets as f
import afecore_lay as CORE
import afetg_lay as TG
from ota_lay import dev_seq

HERE = os.path.dirname(os.path.abspath(__file__))
AFE = os.path.join(g.REPO, "gf180", "tapeout", "afe")
TOP = "afe_top"
W, H = 1100.0, 1447.0
GRID = (0.24, 0.8, 0.0, route.P)
CIN_X = 239.4
EAST_X = 912.0                 # the output section starts here
HOLD_Y = 692.0                 # hold capacitors: above the top AVDD rail strip (Metal5 to 689.8)


def ring_seq(a, ga, x, gb, y, gc, z, gd, periods):
    """[a ga x gb y gc z gd a ...]: four TGs on a commutator ring of S/D nets"""
    seq = [a]
    for _ in range(periods):
        seq += [ga, x, gb, y, gc, z, gd, a]
    return seq


def section_cells(a):
    """Cells of the output section (east part of the band)."""
    C = {}
    C["hold"] = an.mim_cell(a, "afe_hold", 86.58, "TOP", "BOT")
    C["cc"] = an.mim_cell(a, "afe_cc", 70.65, "TOP", "BOT")
    C["cfb"] = an.mim_cell(a, "afe_cfb", 31.46, "TOP", "BOT")
    C["cpf"] = an.mim_cell(a, "afe_cpf", 30.92, "TOP", "BOT")
    C["m5"] = an.mim_cell(a, "afe_m5", 5.0, "TOP", "BOT")
    C["m717"] = an.mim_cell(a, "afe_m717", 7.17, "TOP", "BOT")
    C["m1023"] = an.mim_cell(a, "afe_m1023", 10.23, "TOP", "BOT")
    # output chopper: OUTP -CDA- OPI -CDB- OUTN -CDA- ONI -CDB- OUTP (XOP_A, XOP_B, XON_A,
    # XON_B); NMOS 16 periods (W 10 um fingers), PMOS 32
    st = lambda ga, gb, n: dict(w=10.0, l=0.28, seq=ring_seq("OUTP", ga, "OPI", gb, "OUTN", ga, "ONI", gb, n),
                                gates={ga: ("t", 0), gb: ("t", 1)}, order=["OUTP", "OPI", "OUTN", "ONI"],
                                straps={"OUTP": 2, "OPI": 2, "OUTN": 2, "ONI": 2})
    C["otg_n"] = an.multi_strip_cell(a, "afe_otg_n", "n", [st("CDA", "CDB", 8) for _ in range(2)], bulk="VSS")
    C["otg_p"] = an.multi_strip_cell(a, "afe_otg_p", "p", [st("NCDA", "NCDB", 8) for _ in range(4)], bulk="VDD")
    # CMFB (eeg_afe_cmfb at the amp level: OUTP = OPI, OUTN = ONI, VCMREF = VCM): pairs L2 m4,
    # tails m2, PMOS mirror m8
    pa = dict(w=10.0, l=2.0, seq=["ND", "OPI", "NTA", "VCM", "VBP", "VCM", "NTA", "OPI", "ND"],
              gates={"OPI": ("t", 0), "VCM": ("t", 1)}, order=["NTA", "ND", "VBP"])
    pb = dict(w=10.0, l=2.0, seq=["ND", "ONI", "NTB", "VCM", "VBP", "VCM", "NTB", "ONI", "ND"],
              gates={"ONI": ("t", 0), "VCM": ("t", 1)}, order=["NTB", "ND", "VBP"])
    tl = dict(w=10.0, l=2.0, seq=["NTA", "VBCM", "VSS", "VBCM", "NTB"], order=["VSS", "NTA", "NTB"])
    C["cmfb_n"] = an.multi_strip_cell(a, "afe_cmfb_n", "n", [pa, pb, pb, pa, tl, tl], bulk="VSS")
    pm = dict(w=10.0, l=2.0, seq=["VDD", "ND", "ND", "ND", "VDD", "ND", "VBP", "ND", "VDD", "ND", "ND", "ND", "VDD",
                                  "ND", "VBP", "ND", "VDD"], order=["VDD", "ND", "VBP"])
    C["cmfb_p"] = an.multi_strip_cell(a, "afe_cmfb_p", "p", [pm, pm], bulk="VDD")
    # reset switches (W1/L1) and the DC-path switched capacitors (W0.5/L0.28, gate pins CIA then
    # CIB, wired to SC_GATES)
    C["rstp"] = an.strip_cell(a, "afe_rstp", "n", 1.0, 1.0, ["INP", "RST", "ONI"], bulk="VSS")
    C["rstn"] = an.strip_cell(a, "afe_rstn", "n", 1.0, 1.0, ["INN", "RST", "OPI"], bulk="VSS")
    C["scp"] = an.strip_cell(a, "afe_scp", "n", 0.5, 0.28, ["INP", "CIA", "SCP", "CIB", "ONI"],
                             gates={"CIA": ("t", 0), "CIB": ("t", 1)}, bulk="VSS")
    C["scn"] = an.strip_cell(a, "afe_scn", "n", 0.5, 0.28, ["INN", "CIA", "SCN", "CIB", "OPI"],
                             gates={"CIA": ("t", 0), "CIB": ("t", 1)}, bulk="VSS")
    # the DC path's second branch, phases swapped (tracker B7): the same strip with the gates
    # exchanged, so that its pins and gate tracks sit where the first branch's do
    C["scp2"] = an.strip_cell(a, "afe_scp2", "n", 0.5, 0.28, ["INP", "CIB", "SCP2", "CIA", "ONI"],
                              gates={"CIB": ("t", 0), "CIA": ("t", 1)}, bulk="VSS")
    C["scn2"] = an.strip_cell(a, "afe_scn2", "n", 0.5, 0.28, ["INN", "CIB", "SCN2", "CIA", "OPI"],
                              gates={"CIB": ("t", 0), "CIA": ("t", 1)}, bulk="VSS")
    # Cpf trim logic: eeg_afe_tg (NMOS W1, PMOS W2, here two fingers each) and the inverters
    C["tg"] = lg.tg_cell(a, "afe_trim_tg", 2, 2, 0.5, 1.0, a="A", y="Y", gn="G", gp="GN")
    p, n = lg.inv_seq(1)
    C["inv"] = lg.cmos_cell(a, "afe_trim_inv", p, n, 2.5, 1.0, ["A", "Y"])
    return C


def gate_diodes(a, x, y, h):
    """Antenna diodes for the DC-path switch's gates (CDA2 / CDB2, 0.14 um2 each, reached by
    long Metal3 from the east ports: ANT.4): an N+ diffusion just above the cell (no diode
    marker, so the LVS sees a conductor while the antenna check counts its area), tied by
    Metal2 straight up from the gate pin (afe_scp / afe_scn pins CIA at x 1.51..3.11, CIB
    at x 2.31..3.91); the cell's guard ring is the substrate tap (DF.14)."""
    for (xa, xb), (wa, wb, wy) in (((0.4, 2.0), (1.51, 1.89, 4.21)), ((3.0, 4.6), (3.53, 3.91, 5.01))):
        d = (x + xa, y + h + 1.06, x + xb, y + h + 2.66)
        f.tap(a, "n", *d, well=False)
        a.vias("via1", *d)
        a.box("metal2", x + wa, y + wy, x + wb, d[3])


SC_STUB = 21.0                 # Metal3 stubs on the DC-path switch's pins: up to here above the cell
# the DC-path switches' gates (cell pins CIA / CIB) on the output-chopper phases: the input-
# chopper phases less the blanking window, so that no switch opens during an input-chopper
# edge (on CIA2 / CIB2 they sampled its transient: 1.6 mV of offset, 4.5 mV p-p ripple in the
# extracted layout, tracker B7)
SC_GATES = {"CIA": "CDA2", "CIB": "CDB2"}


def fill_drop(a, x, y, fill, net):
    """A Metal3 drop from a Metal2 pin (via2 at x, y) straight up into the input fill
    whose Metal5 starts at y fill (Metal3 / Metal4 / Metal5 via stack just above that)."""
    a.box("via2", x - 0.13, y - 0.13, x + 0.13, y + 0.13)
    a.wire("metal3", x - 0.19, y - 0.19, x + 0.19, fill + 1.4, net)
    a.via_stack("metal3", "metal5", x - 0.6, fill + 0.2, x + 0.6, fill + 1.4, net)


def sc_wiring(a, x, y, scn, sc, cap, fill=None):
    """The same wiring on both sides of the DC-path switched capacitor (cell sc at x, y,
    its MIM cap 2 um east): the middle node scn (SCP / SCN) to the MIM's top plate on
    Metal2 / Metal4, under a router keep-out; the gate lines (SC_GATES) and the two
    signal pins (ONI / OPI west of the gate stubs, INP / INN east) on Metal3 stubs straight
    up from their pins, which the router reaches at their tops (the P side's gate stubs are
    joined by hand: wiring()). In the first layout the
    router brought P side's CIB2 along under SCP's Metal4: 0.57 fF against 0.04 fF on the
    N side, an AFE output ripple of 39 mV p-p (tracker D6). fill: the P side's INP stub
    runs on up into the INP fill starting at this y (fill_drop), no router pin. Returns
    the router pins {net: [...]}."""
    xc = x + sc.width + 2.0                                   # the MIM cell
    s = sc.pins[scn][0]
    t = cap.pins["TOP"][0]
    a.box("metal2", x + s[3] - 0.5, y + s[2], x + sc.width + 1.2, y + s[4])
    a.vias_fit("via2", x + sc.width + 0.2, y + s[2] - 0.13, x + sc.width + 1.2, y + s[4] + 0.13)
    a.vias_fit("via3", x + sc.width + 0.2, y + s[2] - 0.13, x + sc.width + 1.2, y + s[4] + 0.13)
    a.box("metal4", x + sc.width + 0.2, y + s[2] - 0.13, xc + t[3], y + s[4] + 0.13)
    keep = (x + sc.width - 1.1, y - 1.0, xc + cap.width, y + t[4] + 0.6)
    for lay in ("metal3", "metal4"):
        a.manual.append((lay, keep, scn))
    gx0, px = GRID[0], GRID[1]
    pins, used = {}, []
    sig = [p for p in sc.pins if p not in (scn, "CIA", "CIB", "VSS")]          # INP / ONI or INN / OPI
    order = [(g_, n_, 0) for g_, n_ in SC_GATES.items()] + \
        [(p, p, d) for p, d in zip(sorted(sig, key=lambda p: sc.pins[p][0][2]), (-1, 1))]
    for pn, net, side in order:
        g_ = sc.pins[pn][0]
        if side == 0:                                     # gate pins: the column nearest the pin centre
            k = round((x + (g_[1] + g_[3]) / 2 - gx0) / px)
        else:                                             # signal pins: west / east of the gate stubs
            k = round(((min(used) - px if side < 0 else max(used) + px) - gx0) / px)
        while gx0 + k * px - 0.19 < x + g_[1] or any(abs(gx0 + k * px - u) < px - 1e-6 for u in used):
            k += 1
        xs = gx0 + k * px
        assert xs + 0.19 <= min(x + g_[3], keep[0]), f"no column on the {pn} pin"
        used.append(xs)
        yg = y + (g_[2] + g_[4]) / 2
        a.box("metal2", xs - 0.19, yg - 0.19, xs + 0.19, yg + 0.19)
        if side > 0 and fill is not None:
            fill_drop(a, xs, yg, fill, net)
            continue
        a.box("via2", xs - 0.13, yg - 0.13, xs + 0.13, yg + 0.13)
        a.wire("metal3", xs - 0.19, yg - 0.19, xs + 0.19, y + SC_STUB, net)
        pins[net] = [("metal3", xs - 0.19, y + SC_STUB - 1.5, xs + 0.19, y + SC_STUB)]
    return pins


def build():
    a = A.Assembly(TOP)
    nets = {}
    keep = []

    def conn(net, segs):
        nets.setdefault(net, []).extend(segs)

    def add(inst, power=("VDD", "VSS", "AVDD", "AVSS")):
        for n, segs in inst.pins.items():
            if "." in n or n in power:
                continue
            conn(n, segs)

    def cell_at(cell, x, y, name, cmap, mirror=False):
        a.place(cell.cell, x, y, mirror=mirror)
        p = bl.Placed(cell, x, y, mirror, name)
        for pn, segs in p.pins.items():
            net = cmap.get(pn, pn)
            if pn in ("VDD", "VSS") and isinstance(cell, lg.LogicCell):
                lay, x1, y1, x2, y2 = segs[0]
                a.box("metal2", x1 - 3.0, y1, x1 + 0.5, y2)
                pad = (x1 - 3.0, (y1 + y2) / 2 - 0.5, x1 - 1.6, (y1 + y2) / 2 + 0.5)
                a.vias("via2", *pad)
                a.manual.append(("metal3", pad, net))
                conn(net, [("metal3",) + pad])
                continue
            conn(net, segs)
        if hasattr(cell, "keepout"):
            k3, k4 = cell.keepout, cell.keepout4
            if mirror:
                k3 = (k3[0], -k3[3], k3[2], -k3[1])
                k4 = (k4[0], -k4[3], k4[2], -k4[1])
            keep.append(((x + k3[0], y + k3[1], x + k3[2], y + k3[3]), (x + k4[0], y + k4[1], x + k4[2], y + k4[3])))
        return p

    I = {}
    I["cinp"] = a.put("eeg_cin", CIN_X, 1024.8, name="CINP", nets={"TOP": "INP", "BOT": "WP"}, mim=True)
    I["cinn"] = a.put("eeg_cin", CIN_X, 422.2, mirror=True, name="CINN", nets={"TOP": "INN", "BOT": "WN"}, mim=True)
    I["core"] = a.put("eeg_afe_core", 196.0, 429.3, name="CORE", grid=GRID, nets={
        "OUTP": "OPI", "OUTN": "ONI", "VDD": "AVDD", "VSS": "AVSS"})
    I["tg"] = a.put("afe_tgin", 2.0, 483.5, name="TG", nets={
        "EP": "ELP", "EN": "ELN", "VDD": "AVDD", "VSS": "AVSS"})
    for k in ("core",):
        a.cover(I[k])
    add(I["core"])
    # the input chopper's bulk: the PMOS n-well bar (Metal3, wired by hand to offdac_p's AVDD
    # in w_entry), and the NMOS ring (Metal2, run east under the gate lanes and the n-well bar
    # to a Metal3 pad in the gap beside the core)
    rs = I["tg"].pins["AVSS"][0]
    xg2 = I["tg"].bbox[2]
    ym = (rs[2] + rs[4]) / 2
    a.box("metal2", rs[3] - 0.5, rs[2], xg2 + 2.0, rs[4])
    pad = (xg2 + 0.6, ym - 0.55, xg2 + 2.0, ym + 0.55)
    a.box("metal2", *pad)
    a.vias("via2", *pad)
    a.box("metal3", *pad)
    conn("AVSS", [("metal3",) + pad])
    for n in ("INP", "INN"):                 # the core's INP / INN stubs go straight into the buses
        nets.pop(n, None)

    # ---- output section
    C = section_cells(a)
    x0 = EAST_X
    # hold capacitors 2 x 2 above the supply rails, CC above them, CFB_P / CPF_P on top
    hx = [x0 + 1.0, x0 + 1.0 + C["hold"].width + 3.0]
    yh = HOLD_Y
    hold = [("OUTP", hx[0], yh), ("OUTN", hx[1], yh), ("OUTN", hx[0], yh + C["hold"].height + 3.0),
            ("OUTP", hx[1], yh + C["hold"].height + 3.0)]
    for k, (n, x, y) in enumerate(hold):
        cell_at(C["hold"], x, y, f"HOLD{k}", {"TOP": n, "BOT": "AVSS"})
    ycc = yh + 2 * (C["hold"].height + 3.0)
    cell_at(C["cc"], x0 + 1.0, ycc, "CCP", {"TOP": "VBP", "BOT": "OPI"})
    cell_at(C["cc"], x0 + 1.0 + C["cc"].width + 3.0, ycc, "CCN", {"TOP": "VBP", "BOT": "ONI"})
    ytop = ycc + C["cc"].height + 2.0
    # P side: the MIMs mirrored (the N side's mirror image): TOP plates (INP, WP) up against
    # the INP fill, BOT plates (ONI, OPI, the trim nodes) down towards CC (tracker D6: with
    # the BOT pins up under the INP fill and the router's INP along the row's bottom beside
    # ONI, INP-ONI came out 12 fF above INN-OPI)
    def flip(cell, x, name, cmap):
        return cell_at(cell, x, ytop + cell.height, name, cmap, mirror=True)
    flip(C["cfb"], x0 + 1.0, "CFBP", {"TOP": "INP", "BOT": "ONI"})
    flip(C["cpf"], x0 + 1.0 + C["cfb"].width + 3.0, "CPFP", {"TOP": "WP", "BOT": "OPI"})
    # Cpf trim MIMs, P side (top): bit 0 two in series through MP0
    sw_x = {}
    xt = x0 + 1.0 + C["cfb"].width + C["cpf"].width + 8.0
    for nm, cell, tp, bt in (("CTP0A", "m5", "WP", "MP0"), ("CTP0B", "m5", "MP0", "XP0"), ("CTP1", "m5", "WP", "XP1"),
                             ("CTP2", "m717", "WP", "XP2"), ("CTP3", "m1023", "WP", "XP3")):
        flip(C[cell], xt, nm, {"TOP": tp, "BOT": bt})
        xt += C[cell].width + 2.0
    sw_x["P"] = xt + 1.0
    # N side (bottom, TOP plates down against the INN fill): CFB_N, CPF_N, trim MIMs,
    # 11 um above the Cin_N buses (the INN fill runs on under them: wiring()), 12 router rows
    # above the first layout's 425 (the cells' Metal2 pins keep their phase on the rows)
    yb = 425.0 + 12 * GRID[3]
    cell_at(C["cfb"], x0 + 1.0, yb, "CFBN", {"TOP": "INN", "BOT": "OPI"})
    cell_at(C["cpf"], x0 + 1.0 + C["cfb"].width + 3.0, yb, "CPFN", {"TOP": "WN", "BOT": "ONI"})
    xt = x0 + 1.0 + C["cfb"].width + C["cpf"].width + 8.0
    for nm, cell, tp, bt in (("CTN0A", "m5", "WN", "MN0"), ("CTN0B", "m5", "MN0", "XN0"), ("CTN1", "m5", "WN", "XN1"),
                             ("CTN2", "m717", "WN", "XN2"), ("CTN3", "m1023", "WN", "XN3")):
        cell_at(C[cell], xt, yb, nm, {"TOP": tp, "BOT": bt})
        xt += C[cell].width + 2.0
    sw_x["N"] = xt + 1.0
    I["rows_pn"] = (ytop + max(C[k].height for k in ("cfb", "cpf", "m5", "m717", "m1023", "rstp", "scp")), yb)
    # INP is wired by hand into the INP fill over the P row (wiring(): from rows_pn[0] + 2):
    # CFB_P's top-plate bar by Metal5, the switches' INP pins by Metal3 drops (fill_drop)
    y_fill = I["rows_pn"][0] + 2.0
    a.box("metal5", x0 + 2.0, ytop + C["cfb"].height - 1.6, x0 + C["cfb"].width, y_fill + 0.6)
    # switches next to the buses: reset (INP-ONI / INN-OPI) and the DC path's two switched
    # capacitors (phase A then B, and the phases swapped, on the output-chopper phases
    # SC_GATES; each with its 54.5 fF MIM to AVSS)
    for side, y0_, (rst, sc, csc, scn) in (("P", ytop, ("rstp", "scp", "CSCP", "SCP")), ("N", yb, ("rstn", "scn", "CSCN", "SCN"))):
        x = sw_x[side]
        p1 = cell_at(C[rst], x, y0_, f"XRST{side}", {"VSS": "AVSS", "RST": "RST2"})
        if side == "P":                       # (west of the gate pin, on the INP pin's end)
            s = C[rst].pins["INP"][0]
            fill_drop(a, x + s[1] + 0.4, y0_ + (s[2] + s[4]) / 2, y_fill, "INP")
        x += C[rst].width + 2.0
        fill = y_fill if side == "P" else None
        for k, (sc_, csc_, scn_) in enumerate(((sc, csc, scn), (sc + "2", csc + "2", scn + "2"))):
            p2 = cell_at(C[sc_], x, y0_, f"XSC{side}{k + 1}", dict(SC_GATES, VSS="AVSS"))
            gate_diodes(a, x, y0_, C[sc_].height)
            cell_at(C["m5"], x + C[sc_].width + 2.0, y0_, csc_, {"TOP": scn_, "BOT": "AVSS"})
            for n, segs in sc_wiring(a, x, y0_, scn_, C[sc_], C["m5"], fill).items():
                pin = {v: k_ for k_, v in SC_GATES.items()}.get(n, n)
                nets[n] = [s for s in nets[n] if s not in p2.pins.get(pin, [])]
                if side == "P" and n in SC_GATES.values():     # joined by hand (wiring())
                    I.setdefault("sc_p_gates", {}).setdefault(n, []).extend(segs)
                else:
                    nets[n] += segs
            nets.pop(scn_)
            x += C[sc_].width + 2.0 + C["m5"].width + 2.0
    nets.pop("INP")
    I["sc_p_top"] = ytop + SC_STUB              # the P side's switch stubs end here (wiring())
    # the band between the rails: output chopper, CMFB, switches, trim logic
    S = bl.Shelves(a, x0 + 1.0, 527.0, W - x0 - 4.0, gap=2.0)

    def shelf(cell, name, cmap):
        p = S.place(cell, name)
        for pn, segs in p.pins.items():
            conn(cmap.get(pn, pn), segs)
        return p
    clk2 = {"CDA": "CDA2", "CDB": "CDB2", "NCDA": "NCDA2", "NCDB": "NCDB2"}
    shelf(C["otg_n"], "OTGN", dict(clk2, VSS="AVSS"))
    shelf(C["otg_p"], "OTGP", dict(clk2, VDD="AVDD"))
    shelf(C["cmfb_n"], "CMFBN", {"VSS": "AVSS"})
    shelf(C["cmfb_p"], "CMFBP", {"VDD": "AVDD"})
    S.newline()
    rows = bl.Rows(a, round((x0 + 4.0) / lg.PITCH) * lg.PITCH, S.y)
    for k in range(4):
        p = rows.add(0, C["inv"], f"XIB{k}")
        for pn, segs in p.pins.items():
            if pn not in ("VDD", "VSS"):
                conn({"A": f"CPF{k}", "Y": f"BN{k}"}[pn], segs)
    for side, o in (("P", "OPI"), ("N", "ONI")):
        for k in range(4):
            for kind, y, g1, g2 in (("O", o, f"CPF{k}", f"BN{k}"), ("V", "VCM", f"BN{k}", f"CPF{k}")):
                r = 0 if side == "P" else 1
                p = rows.add(r, C["tg"], f"XT{side}{kind}{k}")
                for pn, segs in p.pins.items():
                    if pn not in ("VDD", "VSS"):
                        conn({"A": f"X{side}{k}", "Y": y, "G": g1, "GN": g2}[pn], segs)
    rows.fill_all()
    merged = []                                       # rails of mirrored rows abut: one pad each
    for net, y1, y2 in sorted(rows.rails(), key=lambda t: t[1]):
        if merged and merged[-1][0] == net and y1 <= merged[-1][2] + 0.01:
            merged[-1] = (net, merged[-1][1], max(y2, merged[-1][2]))
        else:
            merged.append((net, y1, y2))
    for net, y1, y2 in merged:
        xr = rows.x0 - 3.0
        a.box("metal2", xr, y1, rows.x0 + 0.5, y2)
        pad = (xr, (y1 + y2) / 2 - 0.5, xr + 1.4, (y1 + y2) / 2 + 0.5)
        a.vias("via2", *pad)
        a.manual.append(("metal3", pad, "AVDD" if net == "VDD" else "AVSS"))
        conn("AVDD" if net == "VDD" else "AVSS", [("metal3",) + pad])
    I["section_top"] = rows.y0 + rows.height()
    for n, segs in corners(a, I).items():
        conn(n, segs)
    return a, nets, keep, I


# west corners: offset-DAC halves (offdac_lay.py), the clock driver eeg_afe_clk and the
# 100 ohm resistors of its supply (AVDD_CLK / AVSS_CLK)
OD_X = 0.8                      # offdac_n / offdac_p origin x (ports on the router columns)
OD_P_Y = 1100.0                 # offdac_p origin y, above the WP entry (w_entry)
CK_X, CK_Y = 14.0, 306.0        # eeg_afe_clk origin (its shapes from y CK_Y - 1)
OD_PORTS = ["VCM", "S", "PH"] + [f"M{k}" for k in range(10)] + [f"EN{k}" for k in range(4)]
OD_NET = dict({"VCM": "VCM", "S": "OFS", "PH": "OFPH"}, **{f"M{k}": f"OFM{k}" for k in range(10)},
              **{f"EN{k}": f"OFEN{k}" for k in range(4)})
CLK_WEST = ["CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CIA", "CIB", "CDA", "NCDA", "CDB", "NCDB",
            "RST", "OFPH"]
TG_JOG = {"CIA": 428.0, "NCIA": 433.0, "CIB": 438.0, "NCIB": 443.0}    # Metal4 jogs to the chopper's gates


def corners(a, I):
    """Place and wire the west corners; returns the router nets {net: [pins]}.

    Bottom-left: offdac_n on the bottom edge (its control ports are AFE ports there, its
    INN stub runs up into the INN bus east of the clock driver), eeg_afe_clk above it.
    The driver's four chopper gates go to the input chopper's gate lanes on wide hand-
    drawn Metal3 / Metal4 (16-33 pF each); its other ports and CIA / CIB go to the west
    edge (the chip routes them on). Its supply: the 105 pF decap under offdac_n's MIMs
    (straps AVDD_CLK / AVSS_CLK on offdac_n's top edge), joined to the driver's straps by
    hand (AVSS_CLK on Metal3, AVDD_CLK on Metal5 over the driver), and two 100 ohm
    resistors (ppolyf_u_1k, 2 x 20 um) to AVDD / AVSS beside the driver.
    Top-left: offdac_p above the WP entry (INP stub down onto the core's INP bar), its
    control ports routed to the west edge; its AVDD / AVSS straps run on to the top edge."""
    pins = {}
    tp, bp = I["cinp"].pin("INP", "metal5"), I["cinp"].pin("WP", "metal5")
    tn, bn = I["cinn"].pin("INN", "metal5"), I["cinn"].pin("WN", "metal5")
    odn = a.put("offdac_n", OD_X, 0.0, name="ODN", grid=GRID,
                nets={p: OD_NET[p] + "_N" for p in OD_PORTS})
    odp = a.put("offdac_p", OD_X, OD_P_Y, name="ODP", grid=GRID,
                nets={p: OD_NET[p] + "_P" for p in OD_PORTS})
    ck = a.put("eeg_afe_clk", CK_X, CK_Y, name="CLK", grid=GRID, nets={"VDD": "AVDD_CLK", "VSS": "AVSS_CLK"})
    I.update(odn=odn, odp=odp, clk=ck)
    a.cover(ck)
    for inst in (odn, odp):
        a.cover(inst)
    # INN / INP stubs of the offset DAC: Metal4 across the WN / WP entries (w_entry) onto
    # the core's INN / INP Metal5 bars along its bottom / top edge
    core = I["core"]
    for inst, n in ((odn, "INN"), (odp, "INP")):
        s = inst.pin(n, "metal3")
        xc = (s[1] + s[3]) / 2
        a.box("metal3", xc - 0.3, s[2], xc + 0.3, s[4])
        a.vias_fit("via3", xc - 0.3, s[2], xc + 0.3, s[4])
        if n == "INN":
            a.wire("metal4", xc - 0.6, s[2], xc + 0.6, core.bbox[1] + 3.6, n)
            a.vias_fit("via4", xc - 0.6, core.bbox[1] + 0.4, xc + 0.6, core.bbox[1] + 3.6)
        else:
            a.wire("metal4", xc - 0.6, core.bbox[3] - 3.6, xc + 0.6, s[4], n)
            a.vias_fit("via4", xc - 0.6, core.bbox[3] - 3.6, xc + 0.6, core.bbox[3] - 0.4)
        I["od_stub_" + n] = (xc - 0.6, xc + 0.6)
    # chopper gates: port stub -> 2 um Metal3 up -> Metal4 jog -> 1.2 um Metal3 into the lane
    for n, yj in TG_JOG.items():
        s = ck.pin(n, "metal3")
        xc = (s[1] + s[3]) / 2
        ln = I["tg"].pin(n, "metal3")
        xl = (ln[1] + ln[3]) / 2
        a.wire("metal3", xc - 0.19, s[2], xc + 0.19, s[4] + 1.2, n)
        a.wire("metal3", xc - 1.0, s[4] + 1.0, xc + 1.0, yj + 2.0, n)
        a.via_stack("metal3", "metal4", xc - 1.0, yj, xc + 1.0, yj + 2.0, n)
        a.wire("metal4", xc - 1.0, yj, xl + 0.6, yj + 2.0, n)
        a.via_stack("metal3", "metal4", xl - 0.6, yj, xl + 0.6, yj + 2.0, n)
        a.wire("metal3", xl - 0.6, yj, xl + 0.6, ln[4], n)
    # driver supply: AVSS_CLK straps joined on Metal3 under the driver's west edge;
    # AVDD_CLK up on Metal5 and over the driver to its east strap
    dvss, dvdd = ck.pin("AVSS_CLK", "metal3"), ck.pin("AVDD_CLK", "metal3")
    cvss = [p for p in odn.pins["AVSS_CLK"] if p[0] == "metal3"][0]
    cvdd = [p for p in odn.pins["AVDD_CLK"] if p[0] == "metal3"][0]
    ytop = odn.bbox[3]
    a.wire("metal3", cvss[1], ytop - 0.6, dvss[3], dvss[2] + 1.0, "AVSS_CLK")
    a.wire("metal3", cvdd[1], ytop - 0.6, cvdd[3], ytop + 6.4, "AVDD_CLK")
    a.via_stack("metal3", "metal5", cvdd[1], ytop + 2.4, cvdd[3], ytop + 6.4, "AVDD_CLK")
    ym = CK_Y + 50.0
    a.box("metal5", cvdd[1], ytop + 2.4, cvdd[3], ym + 6.0)
    a.box("metal5", cvdd[1], ym, dvdd[3], ym + 6.0)
    a.via_stack("metal3", "metal5", dvdd[1], ym, dvdd[3], ym + 6.0, "AVDD_CLK")
    # the two 100 ohm resistors (west end on the driver's supply, east end on AVDD / AVSS)
    rn = an.res_cell(a, "afe_rck_n", 2.0, 20.0, [("AVSS_CLK", "AVSS")], sub="AVSS")
    rp = an.res_cell(a, "afe_rck_p", 2.0, 20.0, [("AVDD_CLK", "AVDD")], sub="AVSS")
    I["rckp_top"] = CK_Y + 14.0 + rp.height
    for cell, x, y, nm in ((rn, 0.8, CK_Y + 14.0, "RCKN"), (rp, dvdd[3] + 8.0, CK_Y + 14.0, "RCKP")):
        a.place(cell.cell, x, y)
        p = bl.Placed(cell, x, y, False, nm)
        for n, segs in p.pins.items():
            pins.setdefault(n, []).extend(segs)
    pins.setdefault("AVSS_CLK", []).append(dvss)
    pins.setdefault("AVDD_CLK", []).append(dvdd)
    # supplies of the offset-DAC halves: their straps (offdac_p's run on to the top edge)
    for inst in (odn, odp):
        for n in ("AVDD", "AVSS"):
            s = [p for p in inst.pins[n] if p[0] == "metal3"][0]
            pins.setdefault(n, []).append(s)
            if inst is odp:
                a.wire("metal3", s[1], s[4] - 1.0, s[3], H, n)
    # the driver's other ports and CIA / CIB to the west edge; offdac_p's controls too
    for n in CLK_WEST:
        pins.setdefault(n, []).append(ck.pin(n, "metal3"))
    for p in OD_PORTS:
        n = OD_NET[p] + "_P"
        pins.setdefault(n, []).append(odp.pin(n, "metal3"))
    I["west_ports"] = [(CLK_WEST, ck.bbox[3] + 1.0, 2), ([OD_NET[p] + "_P" for p in OD_PORTS], odp.bbox[3] + 8.0, 3)]
    return pins


W_ROW = 15.0                    # pitch of the via rows in the W entries (under 30 um: MSLOT)


def w_entry(a, I, y_wn, y_wp):
    """WP / WN from the input chopper into the Metal3 planes under the Cin arrays
    (gf180lay.mim_array plane), on Metal3 / Metal4 / Metal5 with via rows between them:
      top: over the chopper's top and through the corner between the core and offdac_p
        (moved up to make room), up to 0.6 um from the Cin_P buses;
      bottom: under the chopper (above the clock driver's gate jogs), on Metal3 between
        the jogs, and through the corner between the core, the clock driver and offdac_n.
    The offset DAC's INP / INN stubs cross them on Metal4 (corners()); the input chopper's
    n-well bias (AVDD bar) goes up beside them to offdac_p's AVDD strap (Metal3 / Metal4).
    The WP / WN wiring is in series with the signal (tracker D6)."""
    tg, core, cinp, odp = I["tg"], I["core"], I["cinp"], I["odp"]
    bp, bn = cinp.pin("WP", "metal5"), I["cinn"].pin("WN", "metal5")
    xa = cinp.bbox[0]                                    # the arrays' west edge
    vb = tg.pin("AVDD", "metal3")
    sp = [p for p in odp.pins["AVDD"] if p[0] == "metal3"][0]
    y_tw = odp.bbox[1] - 6.6                             # top of the WP entry
    # chopper AVDD bar -> offdac_p's AVDD strap: Metal3 up beside the WP entry, Metal5 over
    # its top (the INP stub crosses on Metal4 below)
    yr1, yr2 = odp.bbox[1] - 5.4, odp.bbox[1] - 1.4
    a.wire("metal3", vb[1], vb[4] - 1.0, vb[3], yr2, "AVDD")
    a.via_stack("metal3", "metal5", vb[1], yr1, vb[3], yr2, "AVDD")
    a.box("metal5", vb[1], yr1, sp[3], yr2)
    a.via_stack("metal3", "metal5", sp[1], yr1, sp[3], yr2, "AVDD")
    a.wire("metal3", sp[1], yr1, sp[3], sp[2] + 1.0, "AVDD")
    stub = {n: (x1 - 0.3, x2 + 0.3) for n, (x1, x2) in (("WP", I["od_stub_INP"]), ("WN", I["od_stub_INN"]))}
    # the input chopper's own Metal3 / Metal4 reach a bit beyond its stripes (gate lanes)
    ext = {}
    for lay in ("metal3", "metal4"):
        li = tg.src.find_layer(*g.L[lay])
        bxs = [A.pya.DBox(*A._box_um(sh.bbox())).transformed(tg.trans) for sh in
               A.pya.Region(tg.srctop.begin_shapes_rec(li)).merged().each()]
        ext[lay] = (min(b.bottom for b in bxs), max(b.top for b in bxs))

    def plate(net, m3, m4, m5, holes=()):
        """Boxes per metal, via rows every W_ROW where Metal4 meets Metal3 / Metal5; holes:
        2 um openings in the Metal5 where no via rows break it up (MSLOT5.1)."""
        for lay, boxes in (("metal3", m3), ("metal4", m4)):
            for bx in boxes:
                a.wire(lay, *bx, net)
        um = lambda v: int(round(v * 1000))
        reg = lambda boxes: A.pya.Region([A.pya.Box(*[um(v) for v in bx]) for bx in boxes]).merged()
        m5r = reg(m5) - reg(holes)
        a.cell.shapes(a.li("metal5")).insert(m5r)
        merged = {"via3": reg(m3), "via4": m5r}
        for x1, y1, x2, y2 in m4:
            y = y1 + 1.0
            while y + 2.0 < y2 - 0.5:
                row = A.pya.Region(A.pya.Box(um(x1), um(y), um(x2), um(y + 2.0)))
                for via, other in merged.items():
                    for p in (other & row).merged().each():
                        b = p.bbox()
                        if b.width() >= 1000 and b.height() >= 1999:
                            a.vias_fit(via, b.left / 1000, b.bottom / 1000, b.right / 1000, b.top / 1000)
                y += W_ROW
    cuts = [(vb[1] - 0.3, vb[3] + 0.3)]
    # top: WP
    yc = core.bbox[3] + 0.6
    west, east = (5.0, vb[1] - 0.3), (vb[3] + 0.3, xa - 0.3)
    y3, y4 = ext["metal3"][1] + 0.6, ext["metal4"][1] + 0.6
    m4 = [(west[0], y4, west[1], y_tw)] + [(x1, yc, x2, y_tw) for x1, x2 in CORE.minus(east[0], east[1], [stub["WP"]])]
    m3 = [(west[0], y3, west[1], y_tw), (east[0], yc, xa + 0.6, y_tw)]
    xs5 = I["wp_stripes_x2"] + 0.6                       # east of the widened WP stripes
    m5 = [(5.0, y_wn, 27.0, bp[2] + 0.5), (5.0, bp[2], xa - 0.6, y_tw), (xs5, y_wn, core.bbox[0] - 0.6, bp[2] + 0.5),
          (core.bbox[0] - 1.0, yc, xa - 0.6, bp[2] + 0.5)]
    plate("WP", m3, m4, m5)
    # bottom: WN (the clock driver's gate jogs at TG_JOG, its 100 ohm resistor RCKP below)
    yj0, yj1 = min(TG_JOG.values()), max(TG_JOG.values()) + 2.0
    yw0 = I["rckp_top"] + 2.0
    x_lane = min(tg.pin(n, "metal3")[1] for n in TG_JOG) - 0.3      # the chopper's gate lanes, jogs
    y3, y4 = min(y_wp, ext["metal3"][0] - 0.6), min(y_wp, ext["metal4"][0] - 0.6)
    m4 = [(5.0, yj1 + 1.0, x_lane, y4)] + \
        [(x1, yw0, x2, yj0 - 0.6) for x1, x2 in CORE.minus(x_lane + 6.0, xa - 0.3, [stub["WN"]])]
    links = [(100.0 + k * (x_lane - 100.0 + 1.0) / 3, bn[4] + 0.8, 100.0 + (k + 1) * (x_lane - 100.0 + 1.0) / 3 - 1.0,
              yj1 + 1.0) for k in range(3)]                  # Metal3 between the jogs, strips under 30 um
    m3 = [(5.0, yj1 + 1.0, x_lane, y3)] + links + \
        [(100.0, bn[4] + 0.8, xa + 0.6, yj0 - 0.6), (x_lane + 6.0, yw0, xa + 0.6, core.bbox[1] - 0.6)]
    # Metal5: one sheet from the chopper's bottom edge down to the Cin_N bus, east to the
    # core (the WN stripes alone met only on the 5 um bus: 0.2 ohm, tracker D6), a row of
    # holes over the jogs (no via rows there)
    m5 = [(5.0, bn[2] - 0.5, core.bbox[0] - 0.6, y_wp), (x_lane + 6.0, yw0, xa - 0.6, bn[2] + 0.5),
          (vb[3] - 1.0, bn[4] - 0.5, xa - 0.6, core.bbox[1] - 0.6)]
    yh = (yj0 + yj1) / 2 - 1.0
    holes = [(x, yh, x + 2.0, yh + 2.0) for x in [17.0 + 25.0 * k for k in range(8)] if x + 2.0 < core.bbox[0] - 1.0]
    plate("WN", m3, m4, m5, holes)


EAST_PORTS_LO = ["VBN", "VBCM", "BLP", "BLN", "VCM"]
EAST_PORTS_OUT = ["OUTP", "OUTN"]         # on the rows of the ADC's INP / INN (adc_lay.WEST_PORTS)
# (CIA2 / CIB2 stay as ports for the chip's wiring; nothing inside uses them since the DC path
# runs on CDA2 / CDB2)
EAST_PORTS_HI = ["RST2", "CIA2", "CIB2", "CDA2", "NCDA2", "CDB2", "NCDB2", "CPF0", "CPF1", "CPF2", "CPF3"]


def wiring(a, I):
    """Hand-drawn wiring (see the module doc); returns {net: [router pins]}."""
    pins = {}
    cinp, cinn, core, tg = I["cinp"], I["cinn"], I["core"], I["tg"]
    tp, bp = cinp.pin("INP", "metal5"), cinp.pin("WP", "metal5")
    tn, bn = cinn.pin("INN", "metal5"), cinn.pin("WN", "metal5")
    # bus extensions to the west (WP / WN for the input chopper)
    a.wire("metal5", 5.0, bp[2], bp[1] + 1.0, bp[4], "WP")
    a.wire("metal5", 5.0, bn[2], bn[1] + 1.0, bn[4], "WN")
    # the input chopper's WP stripes up into the WP bus (past the WN stripes' ends they widen
    # to the whole lane period); the WN stripes end in a Metal5 sheet below the chopper
    # (w_entry)
    src, top = tg.src, tg.srctop
    li = src.find_layer(*g.L["metal5"])
    half = (TG.PERIOD_X - TG.STRIPE_GAP) / 2
    stripes = [A.pya.DBox(*A._box_um(sh.bbox())).transformed(tg.trans) for sh in top.shapes(li).each()]
    stripes = [b for b in stripes if b.height() > 300 and b.width() < TG.PERIOD_X / 2]   # (not the spines)
    wp = [b for b in stripes if abs(b.top - tg.bbox[3]) < 0.01]       # WP stripes reach the block's top
    wn = [b for b in stripes if abs(b.bottom - tg.bbox[1]) < 0.01]    # WN stripes its bottom
    y_wn, y_wp = max(b.top for b in wn) + 0.6, min(b.bottom for b in wp) - 0.6
    for b in wp:
        a.wire("metal5", b.center().x - half, y_wn, b.center().x + half, bp[4], "WP")
    I["wp_stripes_x2"] = max(b.center().x for b in wp) + half
    w_entry(a, I, y_wn, y_wp)
    # WP / WN taps for the output section: Metal4 from the inner bus into the Cin array's
    # bottom-plate island under the outer bus (gf180lay.mim_array feet)
    xt = W - 12.0
    a.wire("metal4", xt, tp[2] - 6.0, xt + 4.0, bp[4] - 0.3, "WP")
    pins["WP"] = [("metal4", xt, tp[2] - 6.0, xt + 4.0, tp[2] - 2.0)]
    a.wire("metal4", xt, bn[2] + 0.3, xt + 4.0, tn[4] + 6.0, "WN")
    pins["WN"] = [("metal4", xt, tn[4] + 2.0, xt + 4.0, tn[4] + 6.0)]
    # INN tap for the N side of the output section (CFB, reset and DC-path switches): Metal4
    # from the Cin array's top-plate jumper over the inner bus into the gap between the core
    # and the section (Metal3 there is the bottom-plate plane under the array); the P side's
    # INP pins are wired into the INP fill by hand (build())
    xi = EAST_X - 2.4
    a.wire("metal4", xi, tn[4] - 0.5, xi + 1.2, tn[4] + 6.0, "INN")
    pins["INN"] = [("metal4", xi, tn[4] + 2.0, xi + 1.2, tn[4] + 6.0)]
    # the core's INP / INN Metal5 bars (along its top / bottom edges) join the inner Cin buses
    # along the core's width (Metal5 over the gap, Metal4 under it with via4): the gate
    # wiring is in series with the signal (tracker D6)
    for n, bus, up in (("INP", tp, True), ("INN", tn, False)):
        x1, x2 = cinp.bbox[0], core.bbox[2] - 1.0             # (west of the arrays: the W entries)
        y1, y2 = (core.bbox[3] - 3.0, bus[2] + 3.0) if up else (bus[4] - 3.0, core.bbox[1] + 3.0)
        a.box("metal5", x1, y1, x2, y2)
        ya, yb_ = (core.bbox[3] + 0.3, bus[2] - 0.3) if up else (bus[4] + 0.3, core.bbox[1] - 0.3)
        a.wire("metal4", x1, ya, x2, yb_, n)
        a.vias_fit("via4", x1, ya, x2, yb_)
    # east of the core the Cin buses run over the output section: the INP / INN fills go on
    # over it (2 um clear of the section's Metal5; the east columns' current ran 150 um along
    # the 5 um bus), with no other net's Metal4 under them between the INP / INN and WP / WN
    # taps (a router obstacle: the amplifier inputs)
    for bus, (y1, y2), (k1, k2) in ((tp, (I["rows_pn"][0] + 2.0, tp[2] + 3.0), (I["rows_pn"][0] + 1.7, tp[2] - 0.3)),
                                    (tn, (tn[4] - 3.0, I["rows_pn"][1] - 1.0), (tn[4] + 0.3, I["rows_pn"][1] - 1.3))):
        a.box("metal5", core.bbox[2] - 2.0, y1, W - 1.0, y2)
        a.manual.append(("metal4", (xi + 1.8, k1, xt - 0.6, k2), None))
    # supply rails (Metal5) from the east edge over the output section to the core's supply
    # segments (Metal4, PWR_W tall, on the supply lanes of its tails: AVSS in the N column,
    # AVDD in the P column; the AVDD rails start between the columns, so the N column's
    # gate straps keep their Metal5)
    segs = {"AVSS": [], "AVDD": []}
    li4 = core.src.find_layer(*g.L["metal4"])
    rows4 = A.pya.Region()                            # (merged: the via3 arrays' own Metal4 lies inside)
    for sh in core.srctop.shapes(li4).each():
        lb = A.pya.DBox(*A._box_um(sh.bbox()))
        if abs(lb.height() - CORE.PWR_W) < 0.01 and lb.width() < 150:
            rows4.insert(sh.bbox())
    for p in rows4.merged().each():
        lb = A.pya.DBox(*A._box_um(p.bbox()))
        b = lb.transformed(core.trans)
        segs["AVSS" if lb.center().x < CORE.AVDD_RAIL_X0 else "AVDD"].append((b.left, b.bottom, b.right, b.top))
    xw0 = core.trans * A.pya.DPoint(CORE.AVDD_RAIL_X0, 0.0)

    def strips(net, grow):
        """Metal5 strips under 30 um (MSLOT5.1) over the rows of segments: [(y1, y2, segments)]"""
        out = []
        for y in sorted({bx[1] for bx in segs[net]}):
            row = [bx for bx in segs[net] if abs(bx[1] - y) < 0.01]
            y1, y2 = y - grow, row[0][3] + grow
            if out and y2 - out[-1][0] <= 29.0 and y1 <= out[-1][1] + 6.0:
                out[-1] = (out[-1][0], y2, out[-1][2] + row)
            else:
                out.append((y1, y2, row))
        return out
    xw = tg.bbox[2] + 0.6                             # AVSS west ends: over the gap beside the chopper
    vss_top = max(bx[3] for bx in segs["AVSS"])
    segs["AVDD"] = [bx for bx in segs["AVDD"] if bx[1] > vss_top + 4.0]
    rails = {"AVSS": strips("AVSS", CORE.RAIL_GROW["VSS"]), "AVDD": strips("AVDD", CORE.RAIL_GROW["VDD"])}
    for net, lst in rails.items():
        x_west = xw if net == "AVSS" else xw0.x
        for y1, y2, bl_ in lst:
            a.wire("metal5", x_west, y1, W, y2, net)
            for bx in bl_:
                a.vias_fit("via4", *bx)
        y1, y2, _ = lst[0]
        a.label("metal5", net, W - 1.0, (y1 + y2) / 2)
        # Metal4 pads under the rails for the router (the chopper's bulk, the section's cells)
        for x in ((xw + 0.6, W - 20.0) if net == "AVSS" else (W - 20.0,)):
            a.via_stack("metal4", "metal5", x, y1 + 1.0, x + 4.0, y2 - 1.0, net)
            pins.setdefault(net, []).append(("metal4", x, y1 + 1.0, x + 4.0, y2 - 1.0))
    I["rails"] = rails
    # ports on the east and west edges (Metal4 stubs on router rows)
    gx0, px, gy0, py = GRID
    sides = [(EAST_PORTS_LO, 470.0, 4, W - 3.0), (EAST_PORTS_HI, 642.0, 4, W - 3.0),
             (EAST_PORTS_OUT, 870.0, 8, W - 3.0)] + \
        [(names, y0, step, 0.0) for names, y0, step in I["west_ports"]]
    for names, y0, step, xa in sides:
        j0 = round((y0 - gy0) / py)
        for k, n in enumerate(names):
            y = gy0 + (j0 + step * k) * py
            box = (xa, y - 0.19, xa + 3.0, y + 0.19)
            a.box("metal4", *box)
            a.label("metal4", n, xa + 1.5, y)
            pins.setdefault(n, []).append(("metal4",) + box)
    # the DC path's gate lines (SC_GATES) to the P side's switches by hand: from their port
    # stubs up the east corridor beside the hold capacitors (the only way up) in the two
    # easternmost columns, an AVSS Metal3 shield west of them, then west over the switches on
    # two Metal4 rows above the stubs, between AVSS rows, down to the gate stubs. A gate line
    # rises at the end of each blanking window, and a coupling to WP / WN is a kick at the
    # input (gain 300) at the start of the held window: the router had run CDB2 40 um along
    # WP above the switches (3.3 fF against 0.1 fF to WN, a 3.9 mV spike at the start of
    # phase B, 4.5 mV p-p, tracker B7). The N side's gate stubs are the router's.
    k_e = int((W - 0.49 - gx0) / px)
    gates = sorted(SC_GATES.values())
    j0 = int((I["sc_p_top"] + 0.5 - gy0) / py) + 1           # the first row clear of the stubs' tops
    yrow = {n: gy0 + (j0 + len(gates) - k) * py for k, n in enumerate(gates)}
    ysh = (gy0 + j0 * py, gy0 + (j0 + len(gates) + 1) * py)
    stubs = I["sc_p_gates"]
    risers = []
    for k, n in enumerate(gates):
        y = pins[n][0][2] + 0.19                     # its port stub's row
        xr = gx0 + (k_e - k) * px
        a.box("via3", xr - 0.13, y - 0.13, xr + 0.13, y + 0.13)
        seg = (xr - 0.19, y - 0.19, xr + 0.19, yrow[n] + 0.19)
        a.wire("metal3", *seg, n)
        pins[n].append(("metal3",) + seg)            # (the port stub stays a pin: the router keeps clear)
        risers.append(y)
        a.wire("metal4", min(s[1] for s in stubs[n]), yrow[n] - 0.19, xr + 0.19, yrow[n] + 0.19, n)
        for s in stubs[n] + [("metal3",) + seg]:
            a.wire("metal3", s[1], s[4] - 0.38, s[3], yrow[n] + 0.19, n)
            xc = (s[1] + s[3]) / 2
            a.box("via3", xc - 0.13, yrow[n] - 0.13, xc + 0.13, yrow[n] + 0.13)
    xs = gx0 + (k_e - len(gates)) * px
    shield = (xs - 0.19, min(risers) - 1.0, xs + 0.19, ysh[1] + 0.19)
    a.wire("metal3", *shield, "AVSS")
    pins["AVSS"].append(("metal3",) + shield)
    xw = min(s[1] for n in gates for s in stubs[n]) - 0.6
    for y in ysh:
        a.wire("metal4", xw, y - 0.19, gx0 + k_e * px + 0.19, y + 0.19, "AVSS")
        a.box("via3", xs - 0.13, y - 0.13, xs + 0.13, y + 0.13)
    return pins


def route_all(a, nets, keep):
    t0 = time.time()
    r = route.Router(GRID[0], GRID[2], W, H, px=GRID[1], py=GRID[3])
    a.obstacles(r)
    for k3, k4 in keep:
        r.obstacle("metal3", *k3)
        r.obstacle("metal4", *k4)
    a.give(r)
    for n in nets:                                   # identical pins (e.g. a rail shared by two
        uniq = []                                    # mirrored rows) would starve each other
        for p_ in nets[n]:
            key = (p_[0],) + tuple(round(v, 3) for v in p_[1:])
            if key not in [(q[0],) + tuple(round(v, 3) for v in q[1:]) for q in uniq]:
                uniq.append(p_)
        nets[n] = uniq
    single = sorted(n for n, p in nets.items() if len(p) < 2)
    if single:
        print("single-pin nets:", single)
    failed = r.route({n: p for n, p in nets.items() if len(p) >= 2}, rounds=4)
    print(f"routed in {time.time() - t0:.0f} s")
    if failed:
        for n in failed:
            print("why", n, r.why.get(n))
        raise RuntimeError(f"unrouted {failed}")
    r.draw(a)


def labels(a, I):
    """Port labels on the top cell that wiring() does not set: the electrode spines, the
    offdac_n controls on the bottom edge, the corner supplies on the bottom / top edges."""
    for n, net in (("ELP", "ELP"), ("ELN", "ELN")):
        s = I["tg"].pin(net, "metal5")
        a.label("metal5", n, (s[1] + s[3]) / 2, (s[2] + s[4]) / 2)
    for p in OD_PORTS:
        n = OD_NET[p] + "_N"
        s = I["odn"].pin(n, "metal3")
        a.label("metal3", n, (s[1] + s[3]) / 2, s[2] + 0.5)
    for inst, yl in ((I["odn"], 1.0), (I["odp"], H - 1.0)):
        for n in ("AVDD", "AVSS"):
            s = [p for p in inst.pins[n] if p[0] == "metal3"][0]
            a.label("metal3", n, (s[1] + s[3]) / 2, yl)


NETLISTS = [os.path.join(AFE, "eeg_afe.spice"), os.path.join(AFE, "eeg_afe_clk.spice")] + \
    [os.path.join(HERE, "lvs", f"{n}.spice") for n in ("afe_tgin", "offdac_n", "offdac_p", "afe_top")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    args = ap.parse_args()
    runs = os.path.join(HERE, "runs", TOP)
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    a, nets, keep, I = build()
    for n, pins in wiring(a, I).items():
        nets.setdefault(n, []).extend(pins)
    route_all(a, nets, keep)
    labels(a, I)
    a.write(os.path.join(runs, "afe_route.gds"))
    bl.check(a, TOP, NETLISTS, runs, drc=args.drc, lvs=args.lvs, ties=[("AVSS_CLK", "AVSS")])


if __name__ == "__main__":
    main()

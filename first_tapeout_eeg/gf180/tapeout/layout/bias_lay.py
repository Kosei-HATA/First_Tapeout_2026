#!/usr/bin/env python3
"""Layout of eeg_bias (gf180/tapeout/bias/eeg_bias.spice, tracker E5): the master
current reference and the AFE / ADC bias, for the Ch-A column (about 150 um wide).

Cells, bottom to top (blocks.Shelves, 146.3 um wide at most):
  - the GP mirror: 296 PMOS fingers W10/L4 in ten guarded strips, two fingers per drain
    region; MP4 (the GP diode) and MP3 (G1) interleaved in the first strip
  - PMOS switches (W10/L0.5) of the AFE-tail and booster selects, the start-up PMOS
    (W1/L50 x 2) and the DAC2 reference PMOS (W1/L6.2 x 2)
  - the beta-multiplier NMOS (W10/L4: MN2 128 fingers, MN1 32), the NMOS diodes and
    mirrors (L1, L2) and the DAC2 reference NMOS (W1/L20)
  - one logic row: the three select decoders (NOR2, inverter, NAND2)
  - resistors: R0 (3.3 x 2), the four 1 kohm isolators, the cascode divider (the 129.25
    and 149.06 um legs in two series halves each, so the row stays narrow; LVS adds
    series resistors back up), the VCM divider
  - the filter and decoupling capacitors: MOS capacitor units of 28.6 x 44 um (PDK
    cap_nmos / cap_pmos pcells), which leave Metal3/Metal4 free for routing over them
Power: Metal3 straps on the west (VSS) and east (VDD) edges. Ports: Metal3 stubs on the
top edge. Routing: route.Router (Metal3/Metal4).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/bias_lay.py [--drc] [--lvs]
"""
import argparse
import os
import gf180lay as g
import logic as lg
import analog as an
import blocks as bl

HERE = os.path.dirname(os.path.abspath(__file__))
NETLIST = os.path.join(g.REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
PORTS = ["VBN", "VBCM", "BLP", "BLN", "VBN1", "VBCM1", "VNC1", "VPC1", "VBPC2", "VBNC2", "IDP", "IDN", "IQ",
         "ITST", "VCM", "VREFP", "VREFN", "IB1", "IB0", "BP1", "BP0", "BN1", "BN0"]
SW = 2.4           # power strap width
X0 = SW + 1.6      # cells start here (on the 0.8 um grid)
MAXW = 147.0
MAXF = 30          # fingers per W10/L4 strip


def mirror_seq(pairs, src="VDD", gate="GP"):
    """[src, gate, d, gate, src, ...] for a list of drain nets, one entry per finger pair"""
    seq = [src]
    for d in pairs:
        seq += [gate, d, gate, src]
    return seq


def build():
    b = g.Block("eeg_bias")
    nets = {}

    def conn(net, pins):
        nets.setdefault(net, []).extend(pins)

    def add(cell, name, newline=False, nets_map=None):
        p = S.place(cell, name, newline=newline)
        for n, pins in p.pins.items():
            conn((nets_map or {}).get(n, n), pins)
        return p

    S = bl.Shelves(b, X0, 0.0, MAXW, gap=1.6)
    # ---- GP mirror (PMOS W10/L4)
    units = [("NT", 48), ("TA", 8), ("TB", 8), ("TC", 16), ("NC", 8), ("BLN", 16), ("BNA", 16), ("BNB", 16),
             ("BNC", 16), ("ND", 16), ("NDA", 16), ("NDB", 16), ("NDC", 16), ("NA1", 40), ("NA2", 8), ("IQ", 8),
             ("ITST", 8)]
    pairs = []
    for n, k in units:
        pairs += [n] * (k // 2)
    first = ["GP", "G1"] * 4 + pairs[:MAXF // 2 - 8]          # MP4 / MP3 interleaved
    rest = pairs[MAXF // 2 - 8:]
    strips = [first] + [rest[i:i + MAXF // 2] for i in range(0, len(rest), MAXF // 2)]
    for k, pr in enumerate(strips):
        seq = mirror_seq(pr)
        order = ["VDD"] + list(dict.fromkeys(pr))
        add(an.strip_cell(b, f"bias_pm{k}", "p", 10.0, 4.0, seq, order=order), f"PM{k}")
    # ---- PMOS switches (W10/L0.5) and small PMOS
    swc = [("bias_sw1", ["TA", "GA", "NT", "GB", "TB"]), ("bias_sw2", ["TC", "GC", "NT", "GC", "TC"]),
           ("bias_sw3", ["BNA", "GPA", "BLN", "GPB", "BNB"]), ("bias_sw4", ["BNC", "GPC", "BLN"]),
           ("bias_sw5", ["NDA", "GNA", "ND", "GNB", "NDB"]), ("bias_sw6", ["NDC", "GNC", "ND"])]
    for name, seq in swc:   # XSWC is W 10 um in two fingers of 5 um (W is the total width)
        add(an.strip_cell(b, name, "p", 5.0 if name == "bias_sw2" else 10.0, 0.5, seq), name)
    add(an.strip_cell(b, "bias_su1", "p", 1.0, 50.0, ["VDD", "VSS", "SBM", "VSS", "SB"], order=["VDD", "SB"]), "SU1")
    add(an.strip_cell(b, "bias_md", "p", 1.0, 6.2, ["IDN", "GP", "VDD", "GP", "ND2"], order=["VDD", "IDN", "ND2"]), "MD")
    # ---- NMOS beta multiplier (W10/L4): MN2 128 fingers (S2 source), MN1 32 (diode)
    for k, nf in enumerate((26, 26, 26, 26, 24)):
        add(an.strip_cell(b, f"bias_mn2_{k}", "n", 10.0, 4.0, mirror_seq(["GP"] * (nf // 2), src="S2", gate="G1"),
                          order=["S2", "GP"]), f"MN2_{k}")
    for k in range(2):
        add(an.strip_cell(b, f"bias_mn1_{k}", "n", 10.0, 4.0, mirror_seq(["G1"] * 8, src="VSS", gate="G1"),
                          order=["VSS", "G1"]), f"MN1_{k}")
    # ---- NMOS diodes and mirrors
    seq = ["SB", "G1", "VSS"]
    for d, k in (("NT", 10), ("NA1", 6)):
        for j in range(k // 2):
            seq += [d, d, d, "VSS"]
    add(an.strip_cell(b, "bias_nl1", "n", 10.0, 1.0, seq, gates={n: ("t", 0) for n in ("G1", "NT", "NA1")},
                      order=["VSS", "SB", "NT", "NA1"]), "NL1")
    add(an.strip_cell(b, "bias_su3", "n", 2.0, 1.0, ["GP", "SB", "VSS"]), "SU3")
    seq = ["VSS"]
    for j in range(4):
        seq += ["ND", "ND", "ND", "VSS", "ND", "BLP", "ND", "VSS"]
    add(an.strip_cell(b, "bias_nl2a", "n", 10.0, 2.0, seq, order=["VSS", "ND", "BLP"]), "NL2A")
    seq = ["NC", "NC", "VSS", "NC", "NC", "NC", "VSS", "NA2", "NA2", "NA2", "VSS", "NA2", "NA2"]
    add(an.strip_cell(b, "bias_nl2b", "n", 10.0, 2.0, seq, gates={"NC": ("t", 0), "NA2": ("t", 0)},
                      order=["VSS", "NC", "NA2"]), "NL2B")
    add(an.strip_cell(b, "bias_nd2", "n", 1.0, 20.0, ["ND2", "ND2", "VSS", "ND2", "IDP"], order=["VSS", "ND2", "IDP"]),
        "ND2")
    # ---- logic row: the three decoders
    S.newline()
    y_logic = S.y
    rows = bl.Rows(b, X0, y_logic)
    p, n = lg.inv_seq(1)
    inv = lg.cmos_cell(b, "eeg_bias_inv", p, n, 2.0, 1.0, ["A", "Y"])
    p, n = lg.nor_seq(["A", "B"], 1)
    nor2 = lg.cmos_cell(b, "eeg_bias_nor2", p, n, 4.0, 1.0, ["A", "B", "Y"])
    p, n = lg.nand_seq(["A", "B"], 1)
    nand2 = lg.cmos_cell(b, "eeg_bias_nand2", p, n, 2.0, 2.0, ["A", "B", "Y"])
    for (a1, a0), (ga, gb, gc) in ((("IB1", "IB0"), ("GA", "GB", "GC")), (("BP1", "BP0"), ("GPA", "GPB", "GPC")),
                                   (("BN1", "BN0"), ("GNA", "GNB", "GNC"))):
        c = rows.add(0, nor2, f"XL{ga}")
        conn(a1, c.pins["A"]), conn(a0, c.pins["B"]), conn(ga, c.pins["Y"])
        c = rows.add(0, inv, f"XL{gb}")
        conn(a1, c.pins["A"]), conn(gb, c.pins["Y"])
        c = rows.add(0, nand2, f"XL{gc}")
        conn(a1, c.pins["A"]), conn(a0, c.pins["B"]), conn(gc, c.pins["Y"])
    S.y, S.h, S.x = y_logic + lg.H, 0.0, X0
    S.newline()
    S.y += 1.6
    # ---- resistors
    add(an.res_cell(b, "bias_r0", 3.3, 2.0, [("S2", "VSS")]), "R0")
    add(an.res_cell(b, "bias_riso", 1.8, 2.0, [("NT", "VBN"), ("NC", "VBCM"), ("NA1", "VBN1"), ("NA2", "VBCM1")]), "RISO")
    add(an.res_cell(b, "bias_rdiv", [64.625, 64.625, 19.99, 10.07, 19.99, 74.53, 74.53], 1.0,
                    [("VDD", "RM1"), ("RM1", "VNC1"), ("VNC1", "VBPC2"), ("VBPC2", "VPC1"), ("VPC1", "VBNC2"),
                     ("VBNC2", "RM2"), ("RM2", "VSS")]), "RDIV")
    add(an.res_cell(b, "bias_rvcm", 99.47, 1.0, [("VREFP", "VCM"), ("VCM", "VREFN")]), "RVCM")
    # ---- MOS capacitors (28.6 x 44 um units, eeg_bias.spice)
    S.newline()
    mcn = an.moscap_cell(b, "bias_mcn", "n", "G", "B")
    mcp = an.moscap_cell(b, "bias_mcp", "p", "G", "B")
    add(mcp, "CGP", nets_map={"G": "GP", "B": "VDD"})
    for node, n in (("VBN", 4), ("VBCM", 2), ("VBN1", 4), ("VBCM1", 2), ("VNC1", 2), ("VPC1", 2), ("VBPC2", 2),
                    ("VBNC2", 2)):
        for k in range(n):
            add(mcn, f"C{node}_{k}", nets_map={"G": node, "B": "VSS"})
    keep = []
    y_top = S.top_y() + 10.0
    width = X0 + MAXW + 1.0 + SW + 0.6
    # ---- power straps and ports
    xs_vss, xs_vdd = SW / 2 + 0.4, width - SW / 2 - 0.4
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        b.box("metal3", x - SW / 2, -1.0, x + SW / 2, y_top)
        b.label("metal3", net, x, 2.0)
        conn(net, [("metal3", x - SW / 2, -1.0, x + SW / 2, y_top)])
    # logic rails: Metal2 rails extended to both straps, via2 on each
    for net, a, c_ in rows.rails():
        if net == "VSS":
            b.box("metal2", xs_vss - SW / 2, a, X0 + 0.5, c_)
            b.vias("via2", xs_vss - SW / 2, a, xs_vss + SW / 2, c_)
        else:
            b.box("metal2", X0 + rows.width() - 0.5, a, xs_vdd + SW / 2, c_)
            b.vias("via2", xs_vdd - SW / 2, a, xs_vdd + SW / 2, c_)
    gx0 = (X0 + lg.GATE0) % lg.PITCH
    snap = lambda x: gx0 + round((x - gx0) / lg.PITCH) * lg.PITCH
    step = (width - 2 * (SW + 2.0)) / len(PORTS)
    ports = bl.ports_top(b, PORTS, [snap(SW + 2.0 + step * (k + 0.5)) for k in range(len(PORTS))], y_top)
    for n, pin in ports.items():
        conn(n, [pin])
    r = bl.route.Router(gx0, -1.5, width, y_top + 0.5, px=lg.PITCH)
    for n, pin in ports.items():
        r.obstacle(pin[0], *pin[1:], n)
    for net, x in (("VSS", xs_vss), ("VDD", xs_vdd)):
        r.obstacle("metal3", x - SW / 2, -1.0, x + SW / 2, y_top, net)
    for k in keep:
        r.obstacle("metal3", *k)
        r.obstacle("metal4", *k)
    failed = r.route(nets, rounds=6)
    if failed:
        for n in failed:
            for pin in nets[n]:
                if not r.access(pin, r.index[n]):
                    print("no access:", n, pin)
        raise RuntimeError(f"unrouted: {failed}")
    r.draw(b)
    return b, (width, y_top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--lvs", action="store_true")
    a = ap.parse_args()
    runs = os.path.join(HERE, "runs", "eeg_bias")
    os.makedirs(runs, exist_ok=True)
    os.chdir(runs)
    b, (w, h) = build()
    print(f"eeg_bias: {w:.1f} x {h:.1f} um")
    bl.check(b, "eeg_bias", [NETLIST], runs, drc=a.drc, lvs=a.lvs)


if __name__ == "__main__":
    main()

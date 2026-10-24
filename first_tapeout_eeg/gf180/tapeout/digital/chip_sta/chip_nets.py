#!/usr/bin/env python3
"""Chip-level parasitics of the digital interface nets, for the chip-level STA of the
two digital macros (tracker C3, chip_sta.tcl).

Reads the LVS database of the core (gf180/tapeout/layout/runs/chip_top/eeg_core.lvsdb,
flat layout netlist cross-referenced with the flat schematic eeg_core.spice) and, for
each net between the macros, the MCLK pad, the quantizer and the analog drivers:

  * the routed geometry outside the two macros (eeg_digital_top at x 3002..3442,
    y 542..1242; eeg_adc_dig at x 2298.4..2718.4, y 542..782); the inside parts are in
    the macros' timing models (LibreLane, extracted with their SPEF);
  * the ports: the macro pin (the net's shapes in a 2 um band inside the macro edge),
    the MCLK pad (the core edge, x >= 3550), analog gates (poly at the device) and
    analog drains (Metal1 at the device);
  * the effective resistance between the driver and each sink (KLayout RNetExtractor
    on the merged conductors, sheet values of pex_rin.py, "typ" and "high");
  * the wire capacitance: area and fringe to substrate (C_iso) and the sidewall
    coupling to the neighbours on the same layer (C_cpl, from the parallel run length
    within 0.6 um), magic's nominal coefficients of gf180mcuD.tech (aF/um^2, aF/um);
    C_min = C_iso (neighbours switching the same way), C_nom = C_iso + C_cpl,
    C_max = C_iso + 2 C_cpl (opposite switching);
  * the gate and diffusion load of the analog receivers (3.3 V devices: Cox 4.9 fF/um^2,
    overlap 0.3 fF/um per side; drain/source terminals 1.0 fF/um of width).

Writes build/nets.json, build/chip_dig_{min,nom,max}.spef (each net as a pi / T / star
network from the effective resistances, the wire capacitance split along the branches
in proportion to their resistance) and build/chip_dig.v (the top-level netlist: the
MCLK pad, both macros, a timing model of the quantizer and one output port per analog
receiver).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/chip_nets.py
"""
import json
import os
import sys
import time

import numpy as np
import klayout.db as kdb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "pex"))
import pex_rin as pr  # noqa: E402  (net_geometry, network, solve, COND, SHEET)

LVSDB = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "chip_top", "eeg_core.lvsdb")
BUILD = os.path.join(HERE, "build")

DIG_BOX = (3002.0, 542.0, 3442.0, 1242.0)        # eeg_digital_top (mirrored about x)
ADIG_BOX = (2298.4, 542.0, 2718.4, 782.0)        # eeg_adc_dig in adc_top (566, 0) + (1732.4, 542)
PAD_X = 3550.0                                   # MCLK: the core's east edge (pad pin at 3556)
BAND = 2.0                                       # macro pin band inside the edge (um)

# magic gf180mcuD.tech, nominal: area (aF/um^2), perimeter (aF/um), sidewall (aF/um, offset um)
CAPS = {"po": (110.67, 50.72, 11.098, -0.082), "m1": (29.304, 39.431, 40.512, -0.053),
        "m2": (15.016, 33.298, 46.736, 0.289), "m3": (10.094, 30.021, 70.675, 0.534),
        "m4": (7.602, 28.153, 77.388, 0.611), "m5": (5.798, 30.386, 114.86, 0.025)}
CPL_D = 0.6                                       # neighbour search distance for coupling (um)
COX, COV, CJ = 4.9, 0.3, 1.0                      # fF/um^2, fF/um per side, fF/um

# chip net -> (driver, [sinks]); "top:" / "adc:" = macro pin, "pad" = the MCLK pad,
# "q" = the quantizer's comparator outputs (driver of TH), "ana" = analog devices on the net
NETS = {"MCLK": ("pad", ["top:MCLK", "adc:MCLK"])}
for n in ("TH_CAPTURE", "DAC_LOAD", "DWA_EN", "ADC_RST_N"):
    NETS[n] = (f"top:{n}", [f"adc:{'RST_N' if n == 'ADC_RST_N' else n}"])
for k in range(5):
    NETS[f"CODE{k}"] = (f"adc:CODE[{k}]", [f"top:CODE[{k}]"])
for n in ("CMP_STROBE", "DAC_CLK", "CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP1", "CHOP_EN", "AFE_RST", "ADC_ZERO"):
    NETS[n] = (f"top:{'TEST_CFG[5]' if n == 'ADC_ZERO' else n}", ["ana"])
for k in range(31):
    NETS[f"SEL1_{k}"] = (f"adc:SEL1[{k}]", ["ana"])
    NETS[f"SEL2_{k}"] = (f"adc:SEL2[{k}]", ["ana"])
    NETS[f"TH{k}"] = ("q", [f"adc:TH[{k}]"])


def um(v):
    return int(round(v * 1000))


def box_region(b):
    return kdb.Region(kdb.Box(um(b[0]), um(b[1]), um(b[2]), um(b[3])))


def macro_of(spec):
    return DIG_BOX if spec.startswith("top:") else ADIG_BOX


def clip(geo, keep_out):
    """Geometry minus the macros' interiors (a BAND-wide strip inside each edge stays)."""
    cut = kdb.Region()
    for b in keep_out:
        cut += box_region((b[0] + BAND, b[1] + BAND, b[2] - BAND, b[3] - BAND))
    return {k: (r - cut).merged() for k, r in geo.items()}


def macro_port(geo, b):
    """The net's shapes in the strip inside the macro edge: [(layer key, polygon)]."""
    strip = box_region(b) - box_region((b[0] + BAND, b[1] + BAND, b[2] - BAND, b[3] - BAND))
    out = []
    for k in ("m4", "m3", "m2", "m1"):
        for p in (geo[k] & strip).merged().each():
            out.append((k, p))
    return out


def device_port(geo, ld, key, half=1.5):
    """Shapes of layer `key` of the net within +-half um of a layout device."""
    d = ld.trans.disp                          # micrometres (DCplxTrans)
    win = box_region((d.x - half, d.y - half, d.x + half, d.y + half))
    return [(key, p) for p in (geo[key] & win).merged().each()]


def wire_caps(lvs, geo, net):
    """C_iso and C_cpl (fF) of the clipped geometry."""
    c_iso = c_cpl = 0.0
    per = {}
    for k, (ca, cf, sw, off) in CAPS.items():
        r = geo[k]
        if r.is_empty():
            continue
        a = r.area() * 1e-6
        p = r.perimeter() * 1e-3
        ci = (a * ca + p * cf) * 1e-3
        # neighbours of other nets on the same layer near this net
        bb = r.bbox().enlarged(um(CPL_D), um(CPL_D))
        near = r.sized(um(CPL_D))
        allr = kdb.Region()
        for ln in pr.COND[k]:
            li = lvs.layer_of(lvs.layer_by_name(ln))
            allr += kdb.Region(lvs.internal_top_cell().begin_shapes_rec_touching(li, bb))
        others = (allr & near).merged() - r
        ep = r.separation_check(others, um(CPL_D), False, kdb.Region.Projection)
        cc = 0.0
        for e in ep.each():
            s = max(e.distance() * 1e-3, 0.28)
            cc += e.first.length() * 1e-3 * sw / (s + off) * 1e-3
        per[k] = {"area_um2": round(a, 2), "perim_um": round(p, 1), "c_iso_fF": round(ci, 2), "c_cpl_fF": round(cc, 2)}
        c_iso += ci
        c_cpl += cc
    return c_iso, c_cpl, per


def r_eff(n, els, a, b):
    if a == b:
        return 0.0
    p, _ = pr.solve(n, els, {a: 1.0, b: -1.0})
    return p


def main():
    os.makedirs(BUILD, exist_ok=True)
    t0 = time.time()
    lvs = kdb.LayoutVsSchematic()
    lvs.read(LVSDB)
    xref = lvs.xref()
    sc = next(lvs.reference.each_circuit_top_down())
    print(f"read {os.path.relpath(LVSDB, REPO)} in {time.time() - t0:.0f} s", flush=True)
    res = {}
    for name, (drv, sinks) in NETS.items():
        t = time.time()
        sn = sc.net_by_name(name)
        if sn is None:
            raise SystemExit(f"{name}: not in the schematic")
        ln = xref.other_net_for(sn)
        geo = pr.net_geometry(lvs, ln)
        geo = clip(geo, [DIG_BOX, ADIG_BOX])
        # analog devices on the net (schematic devices outside the two macros)
        ana_g, ana_d = [], []
        for term in sn.each_terminal():
            d = term.device()
            dn = d.expanded_name()
            if dn.startswith("DIG.") or dn.startswith("ADIG."):
                continue
            tname = d.device_class().terminal_definitions()[term.terminal_id()].name
            ld = xref.other_device_for(d)
            w, l = d.parameter("W"), d.parameter("L")
            if tname == "G":
                ana_g.append((dn, ld, w * l * COX + 2 * w * COV))
            elif tname in ("S", "D"):
                ana_d.append((dn, ld, w * CJ))
        # ports: driver first
        specs = []
        if drv == "pad":
            strip = box_region((PAD_X, 0.0, 3600.0, 3000.0))
            specs.append(("pad", [(k, p) for k in ("m2", "m3", "m4") for p in (geo[k] & strip).merged().each()], 0.0))
        elif drv == "q":
            specs.append(("q", [pp for _, ld, _ in ana_d for pp in device_port(geo, ld, "m1")], 0.0))
        else:
            specs.append((drv, macro_port(geo, macro_of(drv)), 0.0))
        for s in sinks:
            if s == "ana":
                # one port per receiving inverter / gate (P and N of a gate share a port)
                groups = {}
                for dn, ld, cg in ana_g:
                    key = dn.rsplit(".", 1)[0]
                    groups.setdefault(key, [[], 0.0])
                    groups[key][0] += device_port(geo, ld, "po")
                    groups[key][1] += cg
                for dn, ld, cj in ana_d:
                    key = dn.rsplit(".", 1)[0] + ":sd"
                    groups.setdefault(key, [[], 0.0])
                    groups[key][0] += device_port(geo, ld, "m1")
                    groups[key][1] += cj
                for key, (pp, c) in sorted(groups.items()):
                    specs.append((key, pp, c))
            else:
                specs.append((s, macro_port(geo, macro_of(s)), 0.0))
        for key, pp, _ in specs:
            if not pp:
                raise SystemExit(f"{name}: no port shapes for {key}")
        # R network: all port polygons, each port's polygons tied together
        ports, owner = [], []
        for i, (_, pp, _) in enumerate(specs):
            for q in pp:
                ports.append(q)
                owner.append(i)
        rr = {}
        for corner in ("typ", "high"):
            n, els, pn, _ = pr.network(geo, ports, corner)
            # tie each port's polygons with near-zero resistors
            extra = []
            for i in range(len(specs)):
                nodes = [pn[j] for j in range(len(ports)) if owner[j] == i]
                for x in nodes[1:]:
                    extra.append((nodes[0], x, 1e-6, "tie"))
            els2 = els + extra
            first = {i: pn[owner.index(i)] for i in range(len(specs))}
            m = len(specs)
            mat = [[r_eff(n, els2, first[i], first[j]) for j in range(m)] for i in range(m)]
            rr[corner] = mat
        c_iso, c_cpl, per = wire_caps(lvs, geo, ln)
        res[name] = {"driver": specs[0][0], "sinks": [s[0] for s in specs[1:]],
                     "sink_cap_fF": [round(s[2], 2) for s in specs[1:]],
                     "r_typ": [[round(v, 2) for v in row] for row in rr["typ"]],
                     "r_high": [[round(v, 2) for v in row] for row in rr["high"]],
                     "c_iso_fF": round(c_iso, 2), "c_cpl_fF": round(c_cpl, 2), "layers": per}
        print(f"{name}: {len(specs) - 1} sinks, R(drv->sink) {', '.join(f'{v:.0f}' for v in rr['typ'][0][1:])} ohm, "
              f"C_iso {c_iso:.1f} fF, C_cpl {c_cpl:.1f} fF, gates {sum(s[2] for s in specs[1:]):.1f} fF "
              f"({time.time() - t:.0f} s)", flush=True)
    with open(os.path.join(BUILD, "nets.json"), "w") as f:
        json.dump(res, f, indent=1)
    write_spef(res)
    write_verilog(res)
    write_quantizer_libs()
    print(f"done in {time.time() - t0:.0f} s")


# ---------------------------------------------------------------------------------------
# SPEF and top-level netlist
# ---------------------------------------------------------------------------------------
def pin_name(spec, net):
    """SPEF / Verilog name of a macro / pad / quantizer port spec (None: analog receiver)."""
    if spec == "pad":
        return "u_pad:Y"
    if spec == "q":
        return f"u_q:TH{net[2:]}"
    if spec.startswith("top:"):
        return "u_top:" + spec[4:]
    if spec.startswith("adc:"):
        return "u_adc:" + spec[4:]
    return None


def node_names(net, d, rm):
    """Node names of the driver and the sinks. Analog receivers: on CMP_STROBE the quantizer
    model's CK pin; elsewhere the receiver farthest from the driver is the top-level port
    (named after the net) and the others are internal nodes with their load."""
    names = [pin_name(d["driver"], net)]
    ana = [i for i, s in enumerate(d["sinks"]) if pin_name(s, net) is None]
    far = max(ana, key=lambda i: rm[0][i + 1]) if ana else None
    for i, s in enumerate(d["sinks"]):
        nm = pin_name(s, net)
        if nm is None:
            if i == far:
                nm = "u_q:CK" if net == "CMP_STROBE" else net
            else:
                nm = f"{net}:{101 + i}"
        names.append(nm)
    return names


def tree(rm):
    """Branches of the network from the driver: [(parent node, child node, R)] with node 0 =
    driver, 1..m-1 = sinks, m = Steiner point (3 ports); a star for more than 3 ports."""
    m = len(rm)
    if m == 2:
        return [(0, 1, rm[0][1])], 2
    if m == 3:
        rs = max((rm[0][1] + rm[0][2] - rm[1][2]) / 2.0, 0.0)
        return [(0, 3, rs), (3, 1, max(rm[0][1] - rs, 0.0)), (3, 2, max(rm[0][2] - rs, 0.0))], 4
    return [(0, i, rm[0][i]) for i in range(1, m)], m


def write_spef(res):
    for cname, kc in (("min", 0.0), ("nom", 1.0), ("max", 2.0)):
        rkey = "r_typ" if cname != "max" else "r_high"
        lines = ['*SPEF "IEEE 1481-1998"', '*DESIGN "chip_dig"', '*DATE "2026-10-24"', '*VENDOR "first_tapeout_eeg"',
                 '*PROGRAM "chip_nets.py"', '*VERSION "1"', '*DESIGN_FLOW "PIN_CAP NONE"', '*DIVIDER /',
                 '*DELIMITER :', '*BUS_DELIMITER [ ]', '*T_UNIT 1 NS', '*C_UNIT 1 FF', '*R_UNIT 1 OHM',
                 '*L_UNIT 1 HENRY', '']
        for net, d in res.items():
            rm = d[rkey]
            m = len(rm)
            names = node_names(net, d, rm)
            br, nn = tree(rm)
            node = {i: names[i] for i in range(m)}
            for i in range(m, nn):
                node[i] = f"{net}:{i}"
            cw = d["c_iso_fF"] + kc * d["c_cpl_fF"]
            rsum = sum(r for _, _, r in br) or 1.0
            cap = {i: 0.0 for i in range(nn)}
            for a, b, r in br:
                c = cw * r / rsum
                cap[a] += c / 2
                cap[b] += c / 2
            for i, cg in enumerate(d["sink_cap_fF"]):
                cap[i + 1] += cg
            lines.append(f"*D_NET {net} {sum(cap.values()):.4f}")
            lines.append("*CONN")
            for i in range(m):
                nm = node[i]
                if nm.split(":")[0] in ("u_pad", "u_q", "u_top", "u_adc"):
                    lines.append(f"*I {nm} {'O' if i == 0 else 'I'}")
                elif ":" not in nm:
                    lines.append(f"*P {nm} O")
            lines.append("*CAP")
            k = 1
            for i in range(nn):
                if cap[i] > 0:
                    lines.append(f"{k} {node[i]} {cap[i]:.4f}")
                    k += 1
            lines.append("*RES")
            for k, (a, b, r) in enumerate(br, 1):
                lines.append(f"{k} {node[a]} {node[b]} {max(r, 0.01):.3f}")
            lines.append("*END")
            lines.append("")
        with open(os.path.join(BUILD, f"chip_dig_{cname}.spef"), "w") as f:
            f.write("\n".join(lines))


def write_verilog(res):
    outs = [n for n, d in res.items() if n != "CMP_STROBE" and any(pin_name(s, n) is None for s in d["sinks"])]
    v = ["// chip_dig - digital interface of the chip for the chip-level STA (chip_nets.py):",
         "// the MCLK pad, eeg_digital_top and eeg_adc_dig (LibreLane timing models), a timing",
         "// model of the quantizer (CMP_STROBE -> TH) and one output port per net to analog receivers.",
         "module chip_dig (" + ", ".join(["MCLK_PAD"] + outs) + ");",
         "  input MCLK_PAD;"]
    v += [f"  output {o};" for o in outs]
    v += [f"  wire {n};" for n in res if n not in outs]
    v += ["  wire tc7, tc6, tc4, tc3, tc2, tc1, tc0;", ""]
    v.append("  gf180mcu_fd_io__bi_24t u_pad (.PAD(MCLK_PAD), .Y(MCLK), .A(1'b0), .OE(1'b0), .IE(1'b1), .CS(1'b0),"
             " .SL(1'b0), .PU(1'b0), .PD(1'b0));")
    conn = [f".{p}({p})" for p in ("MCLK", "TH_CAPTURE", "DAC_LOAD", "DWA_EN", "ADC_RST_N", "CMP_STROBE", "DAC_CLK",
                                     "CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP1", "CHOP_EN", "AFE_RST")]
    conn += [".CODE({CODE4, CODE3, CODE2, CODE1, CODE0})", ".TEST_CFG({tc7, tc6, ADC_ZERO, tc4, tc3, tc2, tc1, tc0})"]
    v.append("  eeg_digital_top u_top (" + ", ".join(conn) + ");")
    conn = [".MCLK(MCLK)", ".RST_N(ADC_RST_N)", ".TH_CAPTURE(TH_CAPTURE)", ".DAC_LOAD(DAC_LOAD)", ".DWA_EN(DWA_EN)",
            ".CODE({CODE4, CODE3, CODE2, CODE1, CODE0})",
            ".TH({" + ", ".join(f"TH{k}" for k in range(30, -1, -1)) + "})",
            ".SEL1({" + ", ".join(f"SEL1_{k}" for k in range(30, -1, -1)) + "})",
            ".SEL2({" + ", ".join(f"SEL2_{k}" for k in range(30, -1, -1)) + "})"]
    v.append("  eeg_adc_dig u_adc (" + ", ".join(conn) + ");")
    v.append("  eeg_quantizer_tm u_q (.CK(CMP_STROBE), " + ", ".join(f".TH{k}(TH{k})" for k in range(31)) + ");")
    v.append("endmodule")
    with open(os.path.join(BUILD, "chip_dig.v"), "w") as f:
        f.write("\n".join(v) + "\n")


# quantizer timing model: CMP_STROBE (CK) -> TH0..30, all TH settled (quantizer_check.py
# timing, documentation/gf180_quantizer_20261022.md: 0.5 ns strobe edge, 0.3 pF on each
# TH): typical 27 C 2.31 ns, ss -20 C 3.99 ns, ff 85 C 1.51..1.85 ns (1.51 for the ff
# corner: the earliest TH change). Slower strobe edges add half the 30-70 % slew beyond
# 0.2 ns (the receiving inverter), and TH loads beyond 0.3 pF add k_load per pF (the output
# inverters, W 4 / 2 um at L 0.28 um).
QTM = {"tt": (2.31, 1.8, 3.3, 27.0), "ss": (3.99, 2.5, 2.97, -20.0), "ff": (1.51, 1.2, 3.63, 85.0)}


def write_quantizer_libs():
    s_idx = [0.1, 0.5, 1.0, 2.0, 4.0, 8.0]
    c_idx = [0.05, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8]
    for corner, (d0, kl, vdd, temp) in QTM.items():
        def row(sl):
            return ", ".join(f"{d0 + 0.5 * max(sl - 0.2, 0.0) + kl * (c - 0.3):.4f}" for c in c_idx)
        dly = ", ".join(f'"{row(sl)}"' for sl in s_idx)
        tr = ", ".join('"' + ", ".join(f"{0.15 + 1.6 * c:.4f}" for c in c_idx) + '"' for _ in s_idx)
        idx = (f'index_1("{", ".join(map(str, s_idx))}"); index_2("{", ".join(map(str, c_idx))}");')
        L = [f"library (eeg_quantizer_tm_{corner}) {{", "  delay_model : table_lookup;", "  time_unit : \"1ns\";",
             "  voltage_unit : \"1V\";", "  current_unit : \"1mA\";", "  pulling_resistance_unit : \"1kohm\";",
             "  leakage_power_unit : \"1nW\";", "  capacitive_load_unit (1, pf);",
             "  input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;",
             "  output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;",
             "  slew_lower_threshold_pct_rise : 30; slew_lower_threshold_pct_fall : 30;",
             "  slew_upper_threshold_pct_rise : 70; slew_upper_threshold_pct_fall : 70;",
             f"  nom_process : 1; nom_voltage : {vdd}; nom_temperature : {temp};",
             "  lu_table_template (q_tm) { variable_1 : input_net_transition; variable_2 : total_output_net_capacitance; "
             + idx + " }",
             "  cell (eeg_quantizer_tm) {",
             "    pin (CK) { direction : input; capacitance : 0.0118; }"]
        for k in range(31):
            L += [f"    pin (TH{k}) {{ direction : output;",
                  "      timing () { related_pin : \"CK\"; timing_sense : non_unate; timing_type : combinational;",
                  f"        cell_rise (q_tm) {{ {idx} values({dly}); }}",
                  f"        cell_fall (q_tm) {{ {idx} values({dly}); }}",
                  f"        rise_transition (q_tm) {{ {idx} values({tr}); }}",
                  f"        fall_transition (q_tm) {{ {idx} values({tr}); }} }}",
                  "    }"]
        L += ["  }", "}"]
        with open(os.path.join(BUILD, f"eeg_quantizer_tm_{corner}.lib"), "w") as f:
            f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()

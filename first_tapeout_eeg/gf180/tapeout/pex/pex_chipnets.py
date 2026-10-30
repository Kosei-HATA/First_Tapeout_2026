#!/usr/bin/env python3
"""Chip-level models for the AFE power-on testbench (afe_startup.py): the extracted bias block
and reference filter, and lumped R / C models of the wiring between the blocks, from the
chip of 10/27 (sixth assembly, mask-identical rebuild; runs/chip_top/chip_top.gds, filled
chip_top_fill.gds, core LVS eeg_core.lvsdb). Results in runs/chipnets/ (README.md there). The
seventh assembly (10/29, the ADC's C1 and C2 x1.25) with EEG_PEX_REV=r7 (pex.py) in
runs/chipnets_r7/: rnet, caps, write and tables run again; blocks, verify, pad and afegrid are
r6's (eeg_bias, eeg_ref, the pad cell and afe_top did not change), their results copied. The ninth
(10/29, Metal3 under the AFE's AVSS jumpers) likewise with EEG_PEX_REV=r9 in runs/chipnets_r9/.

Steps (each saves its results, so later steps rerun alone):
  blocks  pex.py's extraction (magic: devices with the layout's geometry and every parasitic
          capacitance, nodes on the schematic names, ports in the schematic's order) of
          eeg_bias and eeg_ref, registered here as pex.BLOCKS entries; eeg_ref's LVS is run
          again on its GDS first (the GDS is newer than its LVS run of 10/23)
  verify  the extracted netlists in ngspice: eeg_bias at its operating point with the loads of
          sim/bias/bias_check.py (I0, VBN, VBCM, ... against the schematic), eeg_ref's DC drop
          with the reference loads of afe_startup.py
  pad     the asig_5p0 pad cell (padring GDS): resistance of its ASIG5V net from the bond pad
          to the ends of its eight Metal2 bars at the core edge (KLayout R extractor), and
          magic on the cell (ESD diodes, the bars' capacitance to the ring's rails)
  rnet    resistance of the chip-level wiring (shapes drawn in chip_top itself, not in a
          block, the padring or a decap unit) of AVDD, AVSS, VBN, VBCM, BLP, BLN, VCM, ELP,
          ELN, OUTP, OUTN, VREFP, VREFN, VREFP_PAD, VREFN_PAD from the core LVS database;
          ports where that wiring overlaps a block's shape of the same layer (block pins, pad
          bars, decap pins) or a chip-level via lands on a block's metal; reduced onto the
          ports (and the routes' junctions)
  caps    magic on windows of the chip GDS (pex_chipwin.py's method: the window flattened,
          extracted, nodes mapped through the core LVS database), each window filled, before
          the fill and with the blocks' shapes only (chip-level C = full - blocks). Unlike
          pex_chipwin.py: the metal fill goes onto the drawn layers (magic's tech treats the
          fill layers as non-electrical), magic's substrate node is AVSS (pex_chipwin.py folds
          it like fill), and the floating nodes are eliminated at once (sparse Schur complement)
  write   runs/chipnets/chipnets.spice (filled, typical), chipnets_nofill.spice,
          chipnets_highr.spice (high-corner metal R) and their *_afe_extra.spice
  tables  runs/chipnets/tables.md: the README's numbers
  afegrid an estimate of afe_top's own supply rails (east pins -> the tails' supply segments),
          which no extraction has (pex.py extracts C only)
  smoke   the models together (extracted afe_top, eeg_bias, eeg_ref, chipnets): power-on
          transient or (--op) operating point with the AFE held in reset; --rafe puts the
          afegrid estimate in series with afe_top's AVSS / AVDD, --rscale scales the model's R

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/pex_chipnets.py <step> [...]
       (blocks, verify, pad, rnet, caps, write, tables in this order; caps --jobs 2 runs two
       magic windows at a time)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pex  # noqa: E402

REPO = pex.REPO
LAYOUT = pex.LAYOUT
OUT = os.path.join(pex.RUNS, "chipnets" + pex.SUFFIX)    # EEG_PEX_REV: see pex.py
# the chip the models are of: r6 (no EEG_PEX_REV), r7 (EEG_PEX_REV=r7: the ADC's C1 and C2 x1.25),
# r9 (EEG_PEX_REV=r9: also the core's DVDD to its pads (r8) and Metal3 under the AFE's AVSS jumpers)
CHIP_LABEL = {"": "10/27, sixth assembly", "r7": "10/29, seventh assembly",
              "r9": "10/29, ninth assembly"}.get(pex.REV, pex.REV)
CHIP = os.path.join(LAYOUT, "runs", "chip_top")
GDS_NOFILL = os.path.join(CHIP, "chip_top.gds")
GDS_FILL = os.path.join(CHIP, "chip_top_fill.gds")
LVSDB = os.path.join(CHIP, "eeg_core.lvsdb")
PADRING = os.path.join(REPO, "gf180", "tapeout", "chip", "padring", "padring_1x0p5_20261023.gds.gz")
PADGEOM = os.path.join(REPO, "gf180", "tapeout", "chip", "padring", "pad_geometry.json")

# ----------------------------------------------------------------------------------
# blocks: eeg_bias and eeg_ref through pex.py
# ----------------------------------------------------------------------------------
REF_LVS = os.path.join(pex.RUNS, "eeg_ref_c", "lvs")
pex.BLOCKS.setdefault("eeg_bias", dict(gds="gds/eeg_bias.gds", lvsdb="runs/eeg_bias/eeg_bias.lvsdb",
                                       ports=("gf180/tapeout/bias/eeg_bias.spice", "eeg_bias"), dut="eeg_bias",
                                       sub="VSS"))
pex.BLOCKS.setdefault("eeg_ref", dict(gds="gds/eeg_ref.gds", lvsdb=os.path.join(REF_LVS, "eeg_ref.lvsdb"),
                                      ports=("gf180/tapeout/adc/eeg_ref.spice", "eeg_ref"), dut="eeg_ref",
                                      sub="VSS"))


def ref_lvs():
    """LVS of gds/eeg_ref.gds against eeg_ref.spice into runs/eeg_ref_c/lvs (the layout
    script's own run of 10/23 07:41 predates the GDS of 08:48)."""
    sys.path.insert(0, LAYOUT)
    import gf180lay as g
    os.makedirs(REF_LVS, exist_ok=True)
    cdl = os.path.join(REF_LVS, "eeg_ref.cdl")
    open(cdl, "w").write(g.to_cdl([os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")], "eeg_ref"))
    ok, lines = g.lvs(os.path.join(LAYOUT, "gds", "eeg_ref.gds"), cdl, "eeg_ref", REF_LVS)
    print("eeg_ref LVS:", "match" if ok else "MISMATCH", *lines, sep="\n  ")
    if not ok:
        raise RuntimeError("eeg_ref LVS mismatch")


def step_blocks(a):
    ref_lvs()
    for blk in ("eeg_bias", "eeg_ref"):
        t = time.time()
        pex.build(blk, a.cthresh)
        print(f"{blk}: {time.time() - t:.0f} s", flush=True)


# ----------------------------------------------------------------------------------
# verify: the extracted eeg_bias / eeg_ref in ngspice against their schematics
# ----------------------------------------------------------------------------------
BIAS_PEX = os.path.join(pex.RUNS, "eeg_bias_c", "eeg_bias_pex.spice")
REF_PEX = os.path.join(pex.RUNS, "eeg_ref_c", "eeg_ref_pex.spice")
REF_SCH = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")


def find_dev(text, nodes, model, mult):
    """Instance name of the device of `model` with M = mult whose drain / gate / source are
    `nodes` (drain and source either way round: magic does not keep the schematic's order)."""
    d, gt, s = nodes
    for ln in text.splitlines():
        t = ln.split()
        if len(t) > 5 and t[0][0] in "Xx" and t[5] == model and t[2] == gt and {t[1], t[3]} == {d, s}:
            m = next((x.split("=")[1] for x in t if x.upper().startswith("M=")), "1")
            if int(m) == mult:
                return t[0].lower()
    raise KeyError(f"no {model} {nodes} M={mult}")


def run_spice(d, deck, extra=None):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    for name, txt in (extra or {}).items():
        open(os.path.join(d, name), "w").write(txt)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    return {k: float(v) for k, v in re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}


def bias_op(variant, code, corner, temp, gmin=None):
    """bias_check.py's operating point (its loads and prints) on the schematic or the
    extracted eeg_bias; returns the printed values with MN1 / XSU3 under their schematic
    names."""
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "bias"))
    import bias_check as bc
    text, sch = bc.build(code, corner, temp)
    if variant == "pex":
        bias = open(BIAS_PEX).read()
        mn1 = find_dev(bias, ("G1", "G1", "VSS"), "nfet_03v3", 32)
        su3 = find_dev(bias, ("GP", "SB", "VSS"), "nfet_03v3", 1)
        text = text.replace("@m.xb.xmn1.", f"@m.xb.{mn1}.").replace("@m.xb.xsu3.", f"@m.xb.{su3}.")
    else:
        bias = sch
    if gmin:
        text = text.replace(".options sparse", f".options gmin={gmin:g} sparse")
    d = os.path.join(OUT, "verify", f"bias_{variant}_{corner}_{temp:g}_{code}" + (f"_gmin{gmin:g}" if gmin else ""))
    v = run_spice(d, text, {"bias.spice": bias})
    out = {}
    for k, x in v.items():
        k2 = re.sub(r"@m\.xb\.x\d+\.m0", lambda m: "@m.xb.xmn1.m0" if m.group(0) == f"@m.xb.{mn1}.m0" else
                    "@m.xb.xsu3.m0", k) if variant == "pex" else k
        out[k2] = x
    return out


REF_LOAD = 18.4e3          # afe_startup.py: the ADC's reference load (DAC1 and the ladder) VREFP-VREFN


def ref_dc(variant):
    """eeg_ref with the pads at 1.9 / 1.4 V, the ADC load (18.4 kohm) and the VCM divider of
    eeg_bias (two ppolyf_u_1k of 99.47 x 1 um) between VREFP and VREFN."""
    sub = REF_PEX if variant == "pex" else REF_SCH
    deck = f"""* eeg_ref {variant}: DC drop
.include {pex_afe_pdk()}/design.ngspice
.lib {pex_afe_pdk()}/sm141064.ngspice typical
.lib {pex_afe_pdk()}/sm141064.ngspice res_typical
.lib {pex_afe_pdk()}/sm141064.ngspice mimcap_typical
.lib {pex_afe_pdk()}/sm141064.ngspice cap_mim
.param moscap_corner=1
.include {os.path.join(REPO, 'gf180', 'tapeout', 'sim', 'moscap_lin.spice')}
.include {sub}
VP VREFP_PAD 0 1.9
VN VREFN_PAD 0 1.4
XREF VREFP_PAD VREFN_PAD VREFP VREFN 0 eeg_ref
RADC VREFP VREFN {REF_LOAD:g}
XRV1 VREFP VCM 0 ppolyf_u_1k r_length=99.47u r_width=1u
XRV2 VCM VREFN 0 ppolyf_u_1k r_length=99.47u r_width=1u
.control
set noaskquit
op
print v(vrefp) v(vrefn) i(vp) i(vn) v(vcm)
quit
.endc
.end
"""
    return run_spice(os.path.join(OUT, "verify", f"ref_{variant}"), deck)


def pex_afe_pdk():
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "afe"))
    import afe_noise
    return afe_noise.PDK


def step_verify(a):
    rows = []
    cases = [("typical", 27, c) for c in range(4)] + [(c, 27, 2) for c in ("ss", "ff", "sf", "fs")] + \
        [("typical", t, 2) for t in (-20, 85)]
    keys = [("I0 (uA)", "@m.xb.xmn1.m0[id]", 1e6), ("VBN (V)", "v(vbn)", 1), ("VBCM (V)", "v(vbcm)", 1),
            ("BLN (uA)", "i(vmbln)", 1e6), ("BLP (uA)", "i(vmblp)", 1e6), ("GP (V)", "v(xb.gp)", 1),
            ("IDD (uA)", "i(vdd)", -1e6), ("VBN1 (V)", "v(vbn1)", 1), ("VBCM1 (V)", "v(vbcm1)", 1),
            ("VNC1 (V)", "v(vnc1)", 1), ("VPC1 (V)", "v(vpc1)", 1), ("VBPC2 (V)", "v(vbpc2)", 1),
            ("VBNC2 (V)", "v(vbnc2)", 1), ("IDN (nA)", "i(vmidn)", 1e9), ("IDP (nA)", "i(vmidp)", 1e9),
            ("VCM (V)", "v(vcm)", 1), ("IQ (uA)", "i(vmiq)", 1e6), ("ITST (uA)", "i(vmitst)", 1e6),
            ("start-up (nA)", "@m.xb.xsu3.m0[id]", 1e9)]
    res = {}
    for corner, temp, code in cases:
        s = bias_op("sch", code, corner, temp)
        p = bias_op("pex", code, corner, temp)
        res[f"{corner}_{temp}_{code}"] = {"sch": s, "pex": p}
        i0s, i0p = abs(s["@m.xb.xmn1.m0[id]"]), abs(p["@m.xb.xmn1.m0[id]"])
        rows.append(f"| {corner} | {temp} | {code} | {i0s * 1e6:.3f} | {i0p * 1e6:.3f} | {(i0p / i0s - 1) * 100:+.3f} | "
                    f"{s['v(vbn)']:.4f} | {p['v(vbn)']:.4f} | {(p['v(vbn)'] - s['v(vbn)']) * 1e3:+.2f} | "
                    f"{s['v(vbcm)']:.4f} | {p['v(vbcm)']:.4f} | {(p['v(vbcm)'] - s['v(vbcm)']) * 1e3:+.2f} | "
                    f"{s['i(vmbln)'] * 1e6:.1f} / {p['i(vmbln)'] * 1e6:.1f} | {s['i(vmblp)'] * 1e6:.1f} / "
                    f"{p['i(vmblp)'] * 1e6:.1f} |")
        print(rows[-1], flush=True)
    g = bias_op("pex", 2, "typical", 27, gmin=1e-15)
    res["typical_27_2_gmin1e-15"] = {"pex": g}
    print("| corner | T | code | I0 sch (uA) | I0 pex (uA) | diff (%) | VBN sch | VBN pex | diff (mV) | VBCM sch | "
          "VBCM pex | diff (mV) | BLN sch / pex (uA) | BLP sch / pex (uA) |")
    print("\n".join(rows))
    t = res["typical_27_2"]
    print("typical, code 2, all printed values (sch / pex):")
    for lab, k, sc in keys:
        print(f"  {lab}: {abs(t['sch'][k]) * abs(sc):.4f} / {abs(t['pex'][k]) * abs(sc):.4f}"
              if "start" in lab else f"  {lab}: {t['sch'][k] * sc:.4f} / {t['pex'][k] * sc:.4f}")
    print(f"  pex with gmin 1e-15: I0 {abs(g['@m.xb.xmn1.m0[id]']) * 1e6:.4f} uA, VBN {g['v(vbn)']:.5f} V")
    ref = {v: ref_dc(v) for v in ("sch", "pex")}
    for v, r in ref.items():
        print(f"eeg_ref {v}: VREFP {r['v(vrefp)']:.5f} V (drop {(1.9 - r['v(vrefp)']) * 1e3:.3f} mV), VREFN "
              f"{r['v(vrefn)']:.5f} V (rise {(r['v(vrefn)'] - 1.4) * 1e3:.3f} mV), VREFP-VREFN "
              f"{(r['v(vrefp)'] - r['v(vrefn)']) * 1e3:.3f} mV, I {-r['i(vp)'] * 1e6:.3f} uA, VCM {r['v(vcm)']:.5f} V")
    res["ref"] = ref
    json.dump(res, open(os.path.join(OUT, "verify.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------
# resistance networks (KLayout's R extractor, as pex_rin.py)
# ----------------------------------------------------------------------------------
GDSL = {"m1": (34, 0), "v1": (35, 0), "m2": (36, 0), "v2": (38, 0), "m3": (42, 0), "v3": (40, 0),
        "m4": (46, 0), "v4": (41, 0), "m5": (81, 0)}
LVSL = {"m1": ["l13"], "m2": ["l15"], "m3": ["l17"], "m4": ["l20", "l25"], "m5": ["l23", "l26"],
        "v1": ["l14"], "v2": ["l16"], "v3": ["l19"], "v4": ["l22"]}
METALS = ("m1", "m2", "m3", "m4", "m5")
VIAS = {"v1": ("m1", "m2"), "v2": ("m2", "m3"), "v3": ("m3", "m4"), "v4": ("m4", "m5")}
# pex_rin.py's sheet and via resistances (magic's gf180mcuD tech): typical and the high corner
SHEET = {"typ": {"m1": 0.090, "m2": 0.090, "m3": 0.090, "m4": 0.090, "m5": 0.040, "via": 4.5},
         "high": {"m1": 0.104, "m2": 0.104, "m3": 0.104, "m4": 0.104, "m5": 0.049, "via": 15.0}}
CUT = 0.26 * 0.26


def network(geo, ports, corner="typ", tess=(), area=4.0):
    """R network of conductor / via regions geo {key: Region (dbu 1 nm)}; ports [(layer key,
    Polygon)]. Returns (node count, [(a, b, R)], {port index: node}, {node: (x, y) um},
    {node: layer key}). tess: conductors meshed by Tesselation (triangles of at most `area`
    um2), the others by SquareCounting (pex_rin.network with the mesh size as a parameter)."""
    import klayout.pex as kpex
    sh = SHEET[corner]
    keys = list(METALS) + list(VIAS)
    lid = {k: i for i, k in enumerate(keys)}
    tech = kpex.RExtractorTech()
    for k in METALS:
        c = kpex.RExtractorTechConductor()
        c.layer, c.resistance = lid[k], sh[k]
        if k in tess:
            c.algorithm = kpex.RExtractorTechConductor.Tesselation
            c.triangulation_max_area = area
        else:
            c.algorithm = kpex.RExtractorTechConductor.SquareCounting
        tech.add_conductor(c)
    for k, (lo, hi) in VIAS.items():
        v = kpex.RExtractorTechVia()
        v.cut_layer, v.bottom_conductor, v.top_conductor = lid[k], lid[lo], lid[hi]
        v.resistance = sh["via"] * CUT
        v.merge_distance = 0.2
        tech.add_via(v)
    pp, seq, cnt = {}, {}, {}
    for g, (k, poly) in enumerate(ports):
        li = lid[k]
        pp.setdefault(li, []).append(poly)
        seq[(li, cnt.get(li, 0))] = g
        cnt[li] = cnt.get(li, 0) + 1
    net = kpex.RNetExtractor(0.001).extract(tech, {lid[k]: r for k, r in geo.items() if k in lid and not r.is_empty()},
                                             {}, pp)
    nodes, loc, lay, port_node = {}, {}, {}, {}
    for nd in net.each_node():
        i = len(nodes)
        nodes[nd.object_id()] = i
        b = nd.location()
        loc[i] = ((b.left + b.right) / 2, (b.bottom + b.top) / 2)
        lay[i] = keys[nd.layer()] if nd.layer() < len(keys) else "?"
        if nd.type() == kpex.RNodeType.PolygonPort:
            port_node[seq[(nd.layer(), nd.port_index())]] = i
    els = [(nodes[e.a().object_id()], nodes[e.b().object_id()], e.resistance()) for e in net.each_element()]
    return len(nodes), els, port_node, loc, lay


def conductance(n, els, rep=None):
    """Sparse nodal conductance matrix (nodes merged by rep[i])."""
    from scipy.sparse import coo_matrix
    rep = rep if rep is not None else list(range(n))
    rows, cols, vals = [], [], []
    for a, b, r in els:
        a, b = rep[a], rep[b]
        if a == b:
            continue
        g = 1.0 / r if abs(r) > 1e-12 else 1e12
        rows += [a, b, a, b]
        cols += [a, b, b, a]
        vals += [g, g, -g, -g]
    return coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsc()


def kron(G, keep):
    """Schur complement of the conductance matrix G onto the node list keep (dense K x K)."""
    from scipy.sparse.linalg import splu
    n = G.shape[0]
    ks = set(keep)
    elim = np.array([i for i in range(n) if i not in ks], dtype=int)
    K = np.array(keep, dtype=int)
    GKK = G[K][:, K].toarray()
    if len(elim) == 0:
        return GKK
    GKE = G[K][:, elim]
    GEE = G[elim][:, elim].tocsc()
    X = splu(GEE).solve(GKE.T.toarray())
    return GKK - GKE @ X


def r_between(Gr, names, a, b):
    """Resistance between node groups a and b (each list tied) of a reduced network, the
    other nodes open."""
    idx = {nm: i for i, nm in enumerate(names)}
    ia, ib = [idx[x] for x in a], [idx[x] for x in b]
    rest = [i for i in range(len(names)) if i not in ia + ib]
    T = np.zeros((len(names), 2 + len(rest)))
    T[ia, 0] = 1
    T[ib, 1] = 1
    for c, i in enumerate(rest):
        T[i, 2 + c] = 1
    Gt = T.T @ Gr @ T
    sel = [0] + list(range(2, Gt.shape[0]))
    rhs = np.zeros(len(sel))
    rhs[0] = 1.0
    return float(np.linalg.solve(Gt[np.ix_(sel, sel)], rhs)[0])


# ----------------------------------------------------------------------------------
# pad: the asig_5p0 cell
# ----------------------------------------------------------------------------------
PAD_CELL = "gf180mcu_fd_io__asig_5p0"


def step_pad(a):
    """R of the pad cell's ASIG5V net from the bond pad (its opening, layer 37/0, on Metal5)
    to the eight Metal2 bars' ends at the core edge (tied), typical and high corner; and
    magic's extraction of the cell (ESD diodes and wiring capacitances of ASIG5V)."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(PADRING)
    c = ly.cell(PAD_CELL)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, c, []))
    regs = {k: l2n.make_layer(ly.find_layer(*v), k) for k, v in GDSL.items()}
    for v, (lo, hi) in VIAS.items():
        l2n.connect(regs[lo])
        l2n.connect(regs[lo], regs[v])
        l2n.connect(regs[v], regs[hi])
    l2n.connect(regs["m5"])
    l2n.extract_netlist()
    edge_y = c.bbox().top                     # the core edge (local y 350 um): only ASIG5V's bars reach it
    band = kdb.Region(kdb.Box(c.bbox().left, edge_y - 500, c.bbox().right, edge_y))
    ends = [p for p in (kdb.Region(c.begin_shapes_rec(ly.find_layer(36, 0))).merged() & band).each()]
    bars = [p.bbox() for p in ends]
    net = l2n.probe_net(regs["m2"], kdb.DPoint(bars[0].center().x / 1000, edge_y / 1000 - 0.1))
    geo = {k: l2n.shapes_of_net(net, regs[k], True).merged() for k in GDSL}
    opening = kdb.Region(c.begin_shapes_rec(ly.find_layer(37, 0))).merged()
    ports = [("m5", list(opening.each())[0])] + [("m2", p) for p in ends]
    res = {"bars": len(bars), "bar_width_um": bars[0].width() / 1000,
           "m2_area_um2": geo["m2"].area() * 1e-6}
    for corner in ("typ", "high"):
        for tess in ((), ("m2",)):
            n, els, pn, loc, lay = network(geo, ports, corner, tess)
            G = conductance(n, els)
            names = ["PAD"] + [f"B{k}" for k in range(len(ends))]
            Gr = kron(G, [pn[i] for i in range(len(ports))])
            r = r_between(Gr, names, ["PAD"], names[1:])
            key = f"{corner}_{'tess' if tess else 'square'}"
            res[key] = r
            print(f"asig_5p0 ASIG5V, bond pad -> bar ends ({corner}, {'Metal2 meshed' if tess else 'square counting'}): "
                  f"{r:.4f} ohm ({n} nodes)", flush=True)
    # magic: the cell flat, with its own labels (ASIG5V, DVDD, DVSS, VDD, VSS)
    d = os.path.join(OUT, "pad_magic")
    os.makedirs(d, exist_ok=True)
    out = kdb.Layout()
    out.dbu = ly.dbu
    oc = out.create_cell("asig")
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        r = kdb.Region(c.begin_shapes_rec(li)).merged()
        if not r.is_empty():
            oc.shapes(out.layer(info)).insert(r)
        for s in c.shapes(li).each():
            if s.is_text() and not s.text.string.startswith("&"):
                oc.shapes(out.layer(info)).insert(s.text)
    out.write(os.path.join(d, "asig.gds"))
    msp, dt = pex.run_magic(os.path.join(d, "asig.gds"), "asig", d, 0.01)
    diodes, caps = [], []
    for ln in open(msp):                       # (pex.read_magic has no diodes)
        t = ln.split()
        if t and t[0][0] in "Dd" and "ASIG5V" in t[1:3]:
            area = next(float(pex.spice_val(x.split("=")[1])) for x in t if x.startswith("area="))
            diodes.append((t[1], t[2], t[3], area))
        elif t and t[0][0] in "Cc":
            caps.append((t[1], t[2], pex.spice_val(t[3])))
    capd = defaultdict(float)
    for x, y, v in caps:
        if "ASIG5V" in (x, y):
            capd[y if x == "ASIG5V" else x] += v
    res["diodes"] = diodes
    res["caps"] = dict(capd)
    print(f"magic ({dt:.0f} s): ASIG5V diodes " + ", ".join(f"{m} {a1}-{a2} {ar * 1e12:.0f} um2" for a1, a2, m, ar in diodes))
    print("  ASIG5V wiring capacitance (fF): " + ", ".join(f"{k} {v * 1e15:.1f}" for k, v in sorted(capd.items())))
    json.dump(res, open(os.path.join(OUT, "pad.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------
# chip geometry: the chip-level part of a net and its ports
# ----------------------------------------------------------------------------------
BLOCK_SHORT = {"afe_top": "AFE", "adc_top": "ADC", "eeg_bias": "BIAS", "eeg_ref": "REF", "eeg_testmux": "TM",
               "eeg_digital_top": "DIG"}
SUPPLY_PADS = {"AVDD": ("A0", "A7", "A12"), "AVSS": ("A1", "A6", "A13")}
CHA_X = (1582.0, 1732.4)                # Ch-A: the analog decoupling units lie here


class Chip:
    """The core LVS database and the chip_top cell (pre-fill GDS: the fill adds no
    connection) with its instances."""

    def __init__(self):
        import klayout.db as kdb
        self.kdb = kdb
        t = time.time()
        self.lvs = kdb.LayoutVsSchematic()
        self.lvs.read(LVSDB)
        self.xref = self.lvs.xref()
        self.sc = next(self.lvs.reference.each_circuit_top_down())
        self.ly = kdb.Layout()
        self.ly.read(GDS_NOFILL)
        self.top = self.ly.top_cell()
        self.topr = {k: kdb.Region(self.top.shapes(self.ly.find_layer(*v))).merged() for k, v in GDSL.items()}
        self.insts = [(self.ly.cell(i.cell_index).name, i) for i in self.top.each_inst()]
        self.pads = {}
        for p in json.load(open(PADGEOM))["pads"]:
            m = re.match(r"(\w+)\\?\[(\d+)\\?\]", p["inst"])
            short = ({"analog": "A", "dvdd_pads": "DD", "dvss_pads": "DS", "bidir": "B"}.get(m.group(1), m.group(1))
                     + m.group(2)) if m else p["inst"]
            self.pads[short] = p
        print(f"chip: LVS database and GDS read in {time.time() - t:.0f} s", flush=True)

    def net_geo(self, name):
        """{layer key: Region} of the shapes of net `name` drawn in chip_top itself."""
        kdb = self.kdb
        ln = self.xref.other_net_for(self.sc.net_by_name(name))
        geo = {}
        for k, ls in LVSL.items():
            r = kdb.Region()
            for l in ls:
                r += self.lvs.shapes_of_net(ln, self.lvs.layer_by_name(l), True)
            geo[k] = r.merged() & self.topr[k]
        return geo

    def inst_region(self, inst, k, box):
        cell = self.ly.cell(inst.cell_index)
        tr = inst.cplx_trans
        return self.kdb.Region(cell.begin_shapes_rec_overlapping(self.ly.find_layer(*GDSL[k]),
                                                                 box.transformed(tr.inverted()))).transformed(tr).merged()

    def pad_of(self, b):
        c = b.center()
        for nm, p in self.pads.items():
            x1, y1, x2, y2 = p["bbox"]
            if x1 - 1 <= c.x <= x2 + 1 and y1 - 1 <= c.y <= y2 + 1:
                return nm
        return "?"

    def ports(self, geo, cluster=False):
        """[(group, layer key, Polygon, (x, y) um)]: where the chip-level shapes overlap a
        shape of the same layer in an instance. Groups: pads by name (A0 = analog[0], ...),
        blocks by short name (clusters of overlaps more than 50 um apart get the block edge
        they sit on as a suffix if cluster), analog decoupling units by row (DC<y>)."""
        out = []
        for iname, inst in self.insts:
            for k in list(METALS) + list(VIAS):
                if geo[k].is_empty():
                    continue
                box = geo[k].bbox() & inst.bbox()
                if box.empty():
                    continue
                found = []
                if k in VIAS:
                    # a chip-level via onto a block's metal (the router's via2 onto a Metal2
                    # pin): the port is the via's footprint on the chip-level metal
                    lo, hi = VIAS[k]
                    for side, other in ((lo, hi), (hi, lo)):
                        bare = geo[k] - geo[side]
                        if bare.is_empty():
                            continue
                        hit = (bare & self.inst_region(inst, side, box.enlarged(10, 10))) & geo[other]
                        found += [(p, other) for p in hit.merged().each()]
                else:
                    ov = (geo[k] & self.inst_region(inst, k, box.enlarged(10, 10))).merged()
                    found = [(p, k) for p in ov.each()]
                for p, lay_k in found:
                    b = p.bbox().to_dtype(0.001)
                    if iname == "padring":
                        grp = self.pad_of(b)
                    elif iname == "chip_decap":
                        ib = inst.dbbox()
                        grp = f"DC{ib.bottom:.0f}" if CHA_X[0] < ib.left < CHA_X[1] else "DDC"
                    else:
                        grp = BLOCK_SHORT.get(iname, iname)
                    out.append([grp, lay_k, p, (b.center().x, b.center().y), inst.dbbox()])
        if cluster:                       # separate pins of one block (VCM: the AFE's VCM, VCM_N, VCM_P)
            for grp in sorted({o[0] for o in out}):
                if not grp.isalpha() or grp == "DDC":
                    continue
                mem = [o for o in out if o[0] == grp]
                cl = []
                for o in mem:
                    for c in cl:
                        if any(abs(o[3][0] - q[3][0]) + abs(o[3][1] - q[3][1]) < 50.0 for q in c):
                            c.append(o)
                            break
                    else:
                        cl.append([o])
                if len(cl) > 1:
                    for c in cl:
                        ib = c[0][4]
                        x = sum(q[3][0] for q in c) / len(c)
                        y = sum(q[3][1] for q in c) / len(c)
                        d = {"W": x - ib.left, "E": ib.right - x, "S": y - ib.bottom, "N": ib.top - y}
                        for q in c:
                            q[0] = grp + "_" + min(d, key=d.get)
        return [(o[0], o[1], o[2], o[3]) for o in out]


# nets of the chip-level models: kind, port grouping
NETS = {"AVDD": "supply", "AVSS": "supply", "VBN": "wire", "VBCM": "wire", "BLP": "wire", "BLN": "wire",
        "VCM": "wire", "ELP": "strap", "ELN": "strap", "OUTP": "wire", "OUTN": "wire", "VREFP": "wire",
        "VREFN": "wire", "VREFP_PAD": "wire", "VREFN_PAD": "wire"}


def net_rnet(chip, name, corner="typ", tess=(), area=4.0):
    """Reduced R network of one net: ports (groups tied) and, for wires, the junctions of
    the route (nodes of degree 3 or more). Returns a dict for rnet.json."""
    from scipy.sparse.csgraph import connected_components
    kind = NETS[name]
    geo = chip.net_geo(name)
    ports = chip.ports(geo, cluster=(name == "VCM"))
    t = time.time()
    for ar in (area, area * 2.5, area * 6.25, None):   # KLayout's triangulation stops on some shapes
        try:
            n, els, pn, loc, lay = network(geo, [(k, p) for _, k, p, _ in ports], corner, tess if ar else (),
                                           ar or area)
            break
        except RuntimeError as e:
            print(f"  {name}: mesh of {'+'.join(tess)} at {ar} um2 failed ({str(e)[:60]}); retrying", flush=True)
    area_used = ar if tess else None
    groups = defaultdict(list)
    for i, (grp, k, p, c) in enumerate(ports):
        groups[grp].append(pn[i])

    def tie(gs):
        rep = list(range(n))
        for g, vs in gs.items():
            for v in vs[1:]:
                rep[v] = vs[0]
        return rep
    if kind == "supply":
        # pieces joined by chip-level metal only: a block's pins of different nets that the
        # LVS joins (the ADC's DVSS rail: DVSS and AVSS are one net through the substrate)
        # must not be tied
        ncomp, comp = connected_components(conductance(n, els) != 0, directed=False)
        keepc = {comp[v] for g in SUPPLY_PADS[name] for v in groups.get(g, [])}
    else:
        # a pin of a block joins the pieces that reach it (ELP: both pads' straps land on
        # the chopper's EP spine)
        rep0 = tie(groups)
        _, comp0 = connected_components(conductance(n, els, rep0) != 0, directed=False)
        comp = [comp0[rep0[i]] for i in range(n)]
        ncomp = len(set(comp))
        cnt = defaultdict(set)
        for g, vs in groups.items():
            for v in vs:
                cnt[comp[v]].add(g)
        keepc = {max(cnt, key=lambda c: len(cnt[c]))}
    dropped = sorted({g for g, vs in groups.items() if all(comp[v] not in keepc for v in vs)})
    groups = {g: [v for v in vs if comp[v] in keepc] for g, vs in groups.items() if g not in dropped}
    if kind == "supply":
        groups.pop("DDC", None)
    # tie each group's port nodes, then reduce onto groups (+ junctions for wires)
    rep = tie(groups)
    alive = [i for i in range(n) if comp[i] in keepc and rep[i] == i]
    idx = {v: j for j, v in enumerate(alive)}
    rep2 = [idx.get(rep[i], -1) for i in range(n)]
    els2 = [(a, b, r) for a, b, r in els if rep2[a] >= 0 and rep2[b] >= 0]
    Gm = conductance(len(alive), [(rep2[a], rep2[b], r) for a, b, r in els2])
    names = sorted(groups)
    keep = [idx[groups[g][0]] for g in names]
    locs = {g: (float(np.mean([loc[v][0] for v in groups[g]])), float(np.mean([loc[v][1] for v in groups[g]])))
            for g in names}
    if kind == "wire":                   # junctions: degree >= 3 in the fine network
        deg = defaultdict(set)
        for a, b, r in els2:
            ra, rb = rep2[a], rep2[b]
            if ra != rb:
                deg[ra].add(rb)
                deg[rb].add(ra)
        inv = {j: i for i, j in idx.items()}
        js = [j for j, s in deg.items() if len(s) >= 3 and j not in keep]
        for k, j in enumerate(js):
            names.append(f"J{k + 1}")
            keep.append(j)
            locs[f"J{k + 1}"] = tuple(float(v) for v in loc[inv[j]])
    Gr = kron(Gm, keep)
    if kind == "wire":
        names, Gr = clean_tree(names, Gr, locs)
    edges = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if Gr[i, j] < -1e-9:
                edges.append((names[i], names[j], -1.0 / Gr[i, j]))
    nports = {g: len(vs) for g, vs in groups.items()}       # (a decoupling row: its units)
    res = dict(net=name, kind=kind, names=names, locs=locs, G=Gr.tolist(), edges=edges, dropped=dropped, nports=nports,
               nodes=n, elements=len(els), components=int(ncomp), t=time.time() - t, corner=corner,
               tess=list(tess) if area_used else [], mesh_area=area_used,
               area={k: geo[k].area() * 1e-6 for k in METALS})
    print(f"{name}: {n} nodes, {len(els)} resistors, {ncomp} components ({time.time() - t:.0f} s); "
          f"ports {', '.join(g for g in names if not g.startswith('J'))}"
          + (f"; dropped (other components): {', '.join(dropped)}" if dropped else ""), flush=True)
    return res


R_MERGE = 1.0      # ohm: nodes this close (via arrays, pad plates, Metal5 stubs) become one


def clean_tree(names, Gr, locs):
    """A routed net's reduced network as a tree of ports and real junctions: nodes joined by
    less than R_MERGE are merged (the port's name kept), then non-port nodes of degree 2 or
    less are eliminated again, until every junction joins three branches."""
    names, Gr = list(names), np.array(Gr)
    while True:
        isport = [not x.startswith("J") for x in names]
        par = list(range(len(names)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if Gr[i, j] < -1.0 / R_MERGE:
                    a, b = find(i), find(j)
                    if a != b and not (isport[a] and isport[b]):
                        if isport[b]:
                            a, b = b, a
                        par[b] = a
        roots = sorted({find(i) for i in range(len(names))})
        if len(roots) < len(names):
            T = np.zeros((len(names), len(roots)))
            for i in range(len(names)):
                T[i, roots.index(find(i))] = 1
            Gr = T.T @ Gr @ T
            names = [names[r] for r in roots]
            continue
        deg = [(Gr[i] < -1e-9).sum() for i in range(len(names))]
        drop = [i for i in range(len(names)) if names[i].startswith("J") and deg[i] <= 2]
        if not drop:
            break
        keep = [i for i in range(len(names)) if i not in drop]
        Gk = Gr[np.ix_(keep, keep)] - Gr[np.ix_(keep, drop)] @ np.linalg.solve(Gr[np.ix_(drop, drop)],
                                                                               Gr[np.ix_(drop, keep)])
        names, Gr = [names[i] for i in keep], Gk
    # number the junctions in order
    ren = {}
    k = 0
    for x in names:
        if x.startswith("J"):
            k += 1
            ren[x] = f"J{k}"
    for x, y in ren.items():
        locs[y + "_"] = locs[x]
    for x, y in ren.items():
        locs[y] = locs.pop(y + "_")
    return [ren.get(x, x) for x in names], Gr


def supply_summary(r, rio):
    """Pad -> block resistances of a supply net from its reduced network (decoupling rows
    open); rio: the pad cell's bond pad -> bars resistance, added per pad."""
    names, Gr = r["names"], np.array(r["G"])
    pads = [g for g in names if g in SUPPLY_PADS[r["net"]]]
    # bond pads: the pad cell's resistance in series with each pad
    nn = len(names)
    Gb = np.zeros((nn + len(pads), nn + len(pads)))
    Gb[:nn, :nn] = Gr
    for k, p in enumerate(pads):
        i, j = names.index(p), nn + k
        g = 1.0 / rio
        Gb[i, i] += g
        Gb[j, j] += g
        Gb[i, j] -= g
        Gb[j, i] -= g
    bn = names + [p + "_bond" for p in pads]
    out = {}
    for blk in [g for g in ("AFE", "ADC", "BIAS", "TM", "REF") if g in names]:
        for p in pads:
            out[f"{p}->{blk}"] = r_between(Gr, names, [p], [blk])
            out[f"{p}_bond->{blk}"] = r_between(Gb, bn, [p + "_bond"], [blk])
        out[f"pads->{blk}"] = r_between(Gr, names, pads, [blk])
        out[f"bonds->{blk}"] = r_between(Gb, bn, [p + "_bond" for p in pads], [blk])
    return out


def step_rnet(a):
    chip = Chip()
    path = os.path.join(OUT, "rnet.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    for name in a.nets:
        kind = NETS[name]
        res[name] = net_rnet(chip, name)
        if kind in ("supply", "strap") and not a.no_tess:
            res[name + "@tess"] = net_rnet(chip, name, tess=("m5",) if kind == "supply" else ("m3", "m4", "m5"),
                                           area=a.area)
        res[name + "@high"] = net_rnet(chip, name, corner="high")
        json.dump(res, open(path, "w"), indent=1)
    pad = json.load(open(os.path.join(OUT, "pad.json")))
    for name in a.nets:
        r = res[name]
        if r["kind"] == "supply":
            for v in [v for v in ("", "@tess", "@high") if name + v in res]:
                s = supply_summary(res[name + v], pad["high_square" if v == "@high" else "typ_square"])
                print(f"{name}{v}: " + ", ".join(f"{k} {x:.3f}" for k, x in s.items() if "AFE" in k or "pads" in k
                                                  or "bonds" in k))
        else:
            print(f"{name}: " + ", ".join(f"{x}-{y} {v:.3f}" for x, y, v in r["edges"]))


# ----------------------------------------------------------------------------------
# caps: magic on windows of the chip
# ----------------------------------------------------------------------------------
# the channels around the AFE (die um; the AFE x 482..1582, y 542..1989), as unions of boxes,
# reaching 10..30 um into the blocks (their own shapes cancel in the difference below)
WINDOWS = {
    "south": [(376.0, 376.0, 2850.0, 552.0)],                      # south band: SB straps, bias block, VCM
    "cha": [(1572.0, 552.0, 1760.0, 2000.0)],                      # Ch-A: trunks, decoupling, the corridor
    "north": [(376.0, 1979.0, 1572.0, 2155.0), (1572.0, 2000.0, 1760.0, 2155.0)],   # eeg_ref, NB straps, VCM
    "west": [(376.0, 552.0, 514.0, 1979.0)],                       # west gap: electrode straps, WG verticals
}
# the PDK's metal fill (datatype 4): magic's gf180mcuD tech reads it as fillm1..fillm5, "not
# handled by extraction" (non-electrical), so the window takes it onto the drawn layers as
# floating metal. COMP and poly fill (22/4, 30/4) stay out (below Metal1; also ignored by magic).
FILL_MAP = {(34, 4): (34, 0), (36, 4): (36, 0), (42, 4): (42, 0), (46, 4): (46, 0), (81, 4): (81, 0)}
BLOCK_CELLS = ("afe_top", "adc_top", "eeg_bias", "eeg_ref", "eeg_testmux", "eeg_digital_top")
VARIANTS = {"fill": GDS_FILL, "nofill": GDS_NOFILL, "blocks": GDS_NOFILL}


def window_gds(variant, boxes, out):
    """Flat copy of the window: fill (filled chip, metal fill on the drawn layers), nofill
    (the chip before the fill), blocks (only the blocks' own shapes: what the block
    extractions already have)."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(VARIANTS[variant])
    top = ly.top_cell()
    win = kdb.Region()
    for b in boxes:
        win.insert(kdb.DBox(*b).to_itype(ly.dbu))
    win.merge()
    wb = win.bbox()
    acc = defaultdict(kdb.Region)
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        key = (info.layer, info.datatype)
        if variant == "blocks":
            r = kdb.Region()
            for inst in top.each_inst():
                if ly.cell(inst.cell_index).name in BLOCK_CELLS and inst.bbox().overlaps(wb):
                    tr = inst.cplx_trans
                    r += kdb.Region(ly.cell(inst.cell_index).begin_shapes_rec_overlapping(
                        li, wb.transformed(tr.inverted()))).transformed(tr)
        else:
            r = kdb.Region(top.begin_shapes_rec_overlapping(li, wb))
        if r.is_empty():
            continue
        if variant == "fill" and key in FILL_MAP:
            key = FILL_MAP[key]
        elif key[1] == 4 and key[0] in (22, 30):
            continue
        acc[key] += r & win
    w = kdb.Layout()
    w.dbu = ly.dbu
    wc = w.create_cell("win")
    for (l, d), r in acc.items():
        wc.shapes(w.layer(l, d)).insert(r.merged())
    w.write(out)


def fold_sparse(rcaps, keep):
    """pex.fold_floating for tens of thousands of floating nodes (the metal fill): the
    floating nodes eliminated at once, C_red = C_KK - C_KF C_FF^-1 C_FK on the nodal
    (Laplacian) capacitance matrix, which is the star-mesh transform done for all of them
    (exact for nodes with capacitors only). Returns [(a, b, F)] between kept nodes."""
    from scipy.sparse import coo_matrix, identity
    from scipy.sparse.linalg import splu
    names = sorted({x for a_, b_, _ in rcaps for x in (a_, b_)})
    idx = {n_: i for i, n_ in enumerate(names)}
    rows, cols, vals = [], [], []
    for a_, b_, c in rcaps:
        if a_ == b_:
            continue
        i, j, v = idx[a_], idx[b_], c * 1e15                 # fF
        rows += [i, j, i, j]
        cols += [i, j, j, i]
        vals += [v, v, -v, -v]
    n = len(names)
    L = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    K = np.array([i for i, x in enumerate(names) if x in keep], dtype=int)
    F = np.array([i for i, x in enumerate(names) if x not in keep], dtype=int)
    LKK = L[K][:, K].toarray()
    if len(F):
        LFF = (L[F][:, F] + 1e-9 * identity(len(F))).tocsc()  # (floating groups with no kept neighbour)
        LFK = L[F][:, K].toarray()
        LKK = LKK - L[K][:, F] @ splu(LFF).solve(LFK)
    out = []
    for a_ in range(len(K)):
        for b_ in range(a_ + 1, len(K)):
            c = -LKK[a_, b_] * 1e-15
            if abs(c) > 1e-21:
                out.append((names[K[a_]], names[K[b_]], c))
    return out, len(F)


def window_caps(name, variant):
    """magic on one window variant; capacitances on the chip's schematic net names, the
    substrate on AVSS, unknown nodes (fill) folded. Saved to caps_<name>_<variant>.json."""
    d = os.path.join(OUT, "win", f"{name}_{variant}")
    os.makedirs(d, exist_ok=True)
    gds = os.path.join(d, "win.gds")
    t = time.time()
    window_gds(variant, WINDOWS[name], gds)
    msp, dt = pex.run_magic(gds, "win", d, 0.01)
    top, mports, devs, caps = pex.read_magic(msp)
    nodes = set()
    for a_, b_, _ in caps:
        nodes.update((a_, b_))
    for _, nn, _, _ in devs:
        nodes.update(nn)
    nmap, miss = pex.map_nodes(sorted(nodes), pex.read_uses(d), top, LVSDB, pex.ext_unit(d, top))
    # magic names the substrate after one of its tiles (a substrate tap), which the LVS probe
    # does not find: without this it would be folded like fill, and every net's capacitance
    # to the substrate would turn into couplings to its neighbours
    sub = None
    for ln in open(os.path.join(d, "win.ext")):
        if ln.startswith("substrate "):
            sub = ln.split()[1].strip('"')
            break
    if sub is not None:
        nmap[sub] = "AVSS"
    ren = {n_: pex.sanitize(nmap.get(n_, n_)) for n_ in nodes}
    rcaps = [(ren[x], ren[y], c) for x, y, c in caps]
    keep = {ren[n_] for n_ in nmap}
    fcaps, nfl = fold_sparse(rcaps, keep)
    res = dict(window=name, variant=variant, caps=fcaps, folded=nfl, mapped=len(nmap), nodes=len(nodes),
               substrate=sub, magic_s=dt, devices=len(devs), total=sum(c for _, _, c in caps))
    json.dump(res, open(os.path.join(OUT, f"caps_{name}_{variant}.json"), "w"))
    print(f"window {name} {variant}: magic {dt:.0f} s, {len(nodes)} nodes, {len(nmap)} mapped, {nfl} folded, "
          f"{len(fcaps)} capacitors, substrate {sub} ({time.time() - t:.0f} s)", flush=True)
    return res


def step_caps(a):
    from concurrent.futures import ThreadPoolExecutor
    jobs = [(w, v) for w in a.windows for v in a.variants]
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: window_caps(*j), jobs))


def chip_caps(variant, windows=None):
    """Chip-level capacitances {(a, b) sorted: F}: the windows' extraction of the full chip
    (fill or nofill) less that of the blocks alone (the couplings inside the blocks, which
    their own extractions have, cancel; what the chip's shapes add stays, including the
    shielding they give the blocks' shapes)."""
    tot = defaultdict(float)
    for w in windows or WINDOWS:
        for v, sgn in ((variant, 1.0), ("blocks", -1.0)):
            for x, y, c in json.load(open(os.path.join(OUT, f"caps_{w}_{v}.json")))["caps"]:
                if x != y:
                    tot[(x, y) if x < y else (y, x)] += sgn * c
    return tot


# ----------------------------------------------------------------------------------
# write: the SPICE models
# ----------------------------------------------------------------------------------
MODELED = [n for n in NETS]
# chip nets that switch in the AFE testbench (afe_startup.py's node names), coupled to the
# modeled nets by 1 fF or more: ports of the model; every other net the modeled nets couple to
# is static there (trims, test-mux selects, other bias lines, the ATP line, supplies of other
# blocks) and its capacitance goes to the nearest AVSS node
AGGR = {"NCDB": "NCDB", "RSTA": "RST", "OFPH": "OFPH", "CDA": "CDA", "CDB": "CDB", "NCDA": "NCDA",
        "CIA": "CIA", "CIB": "CIB", "CHOP": "CHOP", "CHOP_OUT": "CHOP_OUT", "CHOP_BLANK": "CHOP_BLANK",
        "AFE_RST": "AFE_RST"}
AGGR_MIN = 1e-15
# afe_top's ports among the modeled nets (couplings of the chip wiring to the AFE's inner nets
# go into the AFE subcircuit at these pins: chipnets_afe_extra.spice)
AFE_PIN = {"BLN": "BLN", "BLP": "BLP", "VBN": "VBN", "VBCM": "VBCM", "VCM": "VCM", "OUTP": "OUTP", "OUTN": "OUTN",
           "ELP": "ELP", "ELN": "ELN"}
PAD_NET = {"A0": "AVDD", "A7": "AVDD", "A12": "AVDD", "A1": "AVSS", "A6": "AVSS", "A13": "AVSS", "A2": "ELP",
           "A3": "ELP", "A4": "ELN", "A5": "ELN", "A9": "VCM", "A10": "VREFP_PAD", "A11": "VREFN_PAD"}
DC_GROUPS = 5            # decoupling rows lumped into this many groups along the Ch-A trunks
G_PRUNE = 1e-4           # supply networks: conductances below this fraction of a node's total dropped


def node_name(net, grp):
    if grp in PAD_NET:
        return f"{net}_E{grp[1:]}"                 # core edge of the pad (bond pad: _P<k>)
    if net == "VCM" and grp.startswith("AFE_"):
        return {"AFE_E": "VCM_AFE", "AFE_S": "VCMN_AFE", "AFE_W": "VCMP_AFE"}[grp]
    return f"{net}_{grp}"


def in_window(pt, w, tol=12.0):
    return any(x1 - tol <= pt[0] <= x2 + tol and y1 - tol <= pt[1] <= y2 + tol for x1, y1, x2, y2 in WINDOWS[w])


def window_dist(pt, w):
    return min(max(x1 - pt[0], 0, pt[0] - x2) + max(y1 - pt[1], 0, pt[1] - y2) for x1, y1, x2, y2 in WINDOWS[w])


class Model:
    """The lumped model: resistors and capacitors on named nodes."""

    def __init__(self, rnet, corner):
        self.R, self.C, self.extra = [], defaultdict(float), defaultdict(float)
        self.nodes = {}                       # net -> {node: (x, y), weight}
        self.dcap = {}                        # group -> (AVDD node, AVSS node, units)
        for net in MODELED:
            # typical: the electrode straps with their sheets meshed (pex_rin.py's choice for planes),
            # the rest by square counting (the supplies' mesh moved them by under 1 %)
            sfx = "@high" if corner == "high" else ("@tess" if NETS[net] == "strap" else "")
            r = rnet[net + sfx]
            if r["kind"] == "supply":
                self.supply(net, r)
            else:
                self.tree(net, r)

    def tree(self, net, r):
        names, locs = r["names"], r["locs"]
        wsum = defaultdict(float)
        tot = sum(R for _, _, R in r["edges"]) or 1.0
        for a_, b_, R in r["edges"]:
            self.R.append((node_name(net, a_), node_name(net, b_), R))
            wsum[a_] += R / 2 / tot
            wsum[b_] += R / 2 / tot
        self.nodes[net] = {node_name(net, g): (tuple(locs[g]), wsum.get(g, 0.0)) for g in names}

    def supply(self, net, r):
        names, Gr, locs = list(r["names"]), np.array(r["G"]), r["locs"]
        rows = sorted([g for g in names if g.startswith("DC")], key=lambda g: int(g[2:]))
        k = len(rows)
        grp = [rows[i * k // DC_GROUPS:(i + 1) * k // DC_GROUPS] for i in range(DC_GROUPS)]
        reps = [g[len(g) // 2] for g in grp]
        units = {f"DC{i + 1}": sum(r["nports"][x] for x in g) for i, g in enumerate(grp)}
        drop = [names.index(x) for x in rows if x not in reps]
        keep = [i for i in range(len(names)) if i not in drop]
        Gk = Gr[np.ix_(keep, keep)] - Gr[np.ix_(keep, drop)] @ np.linalg.solve(Gr[np.ix_(drop, drop)],
                                                                               Gr[np.ix_(drop, keep)])
        kn = [names[i] for i in keep]
        ren = {x: f"DC{reps.index(x) + 1}" for x in reps}
        kn = [ren.get(x, x) for x in kn]
        loc = {ren.get(x, x): tuple(locs[x]) for x in names if x in ren or x in kn}
        for i in range(len(kn)):
            for j in range(i + 1, len(kn)):
                g = -Gk[i, j]
                if g > G_PRUNE * min(Gk[i, i], Gk[j, j]):
                    self.R.append((node_name(net, kn[i]), node_name(net, kn[j]), 1.0 / g))
        self.nodes[net] = {node_name(net, x): (loc[x], 1.0 / len(kn)) for x in kn}
        for x, u in units.items():
            d = self.dcap.setdefault(x, [None, None, u])
            d[0 if net == "AVDD" else 1] = node_name(net, x)
        self.supply_r = getattr(self, "supply_r", {})
        self.supply_r[net] = (kn, Gk)

    def near(self, net, pt, within=None):
        nd = self.nodes[net]
        cand = [n_ for n_ in nd if within is None or n_ in within] or list(nd)
        return min(cand, key=lambda n_: (nd[n_][0][0] - pt[0]) ** 2 + (nd[n_][0][1] - pt[1]) ** 2)

    def share(self, net, w):
        """{node: fraction} of net's capacitance in window w: its nodes there by their pi
        weights (all equal for a supply), else the node nearest to the window."""
        nd = self.nodes[net]
        ins = {n_: max(v[1], 1e-6) for n_, v in nd.items() if in_window(v[0], w)}
        if not ins:
            n_ = min(nd, key=lambda m: window_dist(nd[m][0], w))
            return {n_: 1.0}
        s = sum(ins.values())
        return {n_: v / s for n_, v in ins.items()}

    def add_c(self, a_, b_, c):
        if a_ != b_:
            self.C[(a_, b_) if a_ < b_ else (b_, a_)] += c

    def place(self, caps_by_window, aggr):
        """Each window's chip-level capacitances onto the model's nodes."""
        for w, cc in caps_by_window.items():
            for (x, y), c in cc.items():
                for a_, b_ in ((x, y), (y, x)):
                    if a_ not in self.nodes:
                        continue
                    if b_ in self.nodes:
                        if a_ > b_:
                            continue                    # pairs of modeled nets: once, both sides
                        sa, sb = self.share(a_, w), self.share(b_, w)
                        for na, f in sa.items():         # each side's pieces to the other's nearest node
                            self.add_c(na, self.near(b_, self.nodes[a_][na][0], sb), 0.5 * f * c)
                        for nb, f in sb.items():
                            self.add_c(nb, self.near(a_, self.nodes[b_][nb][0], sa), 0.5 * f * c)
                    elif b_ in aggr:
                        for na, f in self.share(a_, w).items():
                            self.add_c(na, AGGR[b_], f * c)
                    elif b_.startswith("AFE.") and a_ in AFE_PIN:
                        self.extra[(AFE_PIN[a_], b_[4:])] += c
                    else:                               # static: AC ground at the nearest AVSS node
                        for na, f in self.share(a_, w).items():
                            self.add_c(na, self.near("AVSS", self.nodes[a_][na][0]), f * c)

    def spice(self, name, title):
        """The subcircuit text: ports, resistors, decoupling units, pads, capacitors."""
        ports = []
        for pad_, net in PAD_NET.items():
            ports.append(f"{net}_P{pad_[1:]}")
        blocks = sorted({n_ for net in MODELED for n_ in self.nodes[net] if not re.search(r"_(J\d+|E\d+|DC\d+)$", n_)})
        ports += blocks + ["DVDD", "DVSS"] + sorted({n_ for k in self.C for n_ in k if n_ in AGGR.values()})
        L = [f"* {title}", f".subckt {name} " + " ".join(ports)]
        L.append("* pads (asig_5p0): bond pad <net>_P<k> -> core edge <net>_E<k> (pad cell R, ESD diodes, wiring C)")
        for pad_, net in PAD_NET.items():
            L.append(f"XPAD{pad_[1:]} {net}_P{pad_[1:]} {net}_E{pad_[1:]} DVDD DVSS pad_asig5p0")
        L.append("* chip-level wiring resistance")
        for k, (a_, b_, R) in enumerate(self.R):
            L.append(f"R{k} {a_} {b_} {R:.6g}")
        L.append("* AVDD-AVSS decoupling: cap_nmos_03v3 units of 28.6 x 44 um in groups along the Ch-A trunks")
        for g, (vd, vs, u) in sorted(self.dcap.items()):
            for j in range(u):
                L.append(f"XDC{g[2:]}_{j} {vd} {vs} cap_nmos_03v3 c_length=28.6u c_width=44u")
        L.append("* chip-level wiring capacitance (magic, windows of the chip less the blocks' own)")
        k = 0
        neg = [(x, c) for x, c in self.C.items() if c <= -5e-18]
        if neg:
            L.append("* left out (negative: the chip's shapes shielding a block's own coupling): " +
                     ", ".join(f"{a_}-{b_} {c * 1e15:.2f} fF" for (a_, b_), c in neg))
        for (a_, b_), c in sorted(self.C.items()):
            if c >= 5e-18:
                L.append(f"C{k} {a_} {b_} {c:.4e}")
                k += 1
        L.append(f".ends {name}")
        return "\n".join(L) + "\n"


def pad_subckt(pad):
    d = pad["caps"]
    cdv = d.get("DVDD", 0) + d.get("VDD", 0)
    cds = d.get("DVSS", 0) + d.get("VSS", 0)
    nd = sum(1 for x in pad["diodes"] if x[2] == "diode_nd2ps_06v0")
    npw = sum(1 for x in pad["diodes"] if x[2] == "diode_pd2nw_06v0")
    return f"""* gf180mcu_fd_io__asig_5p0 (pex_chipnets.py pad): PAD = bond pad, CORE = the ends of its
* eight Metal2 bars at the core edge. R bond pad -> bars {pad['typ_square']:.4f} ohm typical ({pad['high_square']:.4f} ohm high
* corner), split around the ESD diodes ({nd} x N+/Psub to DVSS, {npw} x P+/Nwell to DVDD, each 3 x 50 um:
* area 150 um2, perimeter 106 um) and the bars' capacitance to the pad ring's rails (DVDD and VDD
* {cdv * 1e15:.0f} fF, DVSS and VSS {cds * 1e15:.0f} fF; the ring's VDD / VSS are DVDD / DVSS). Needs the PDK's
* diode models: .lib <PDK>/sm141064.ngspice diode_typical
.subckt pad_asig5p0 PAD CORE DVDD DVSS
RIO1 PAD M {pad['typ_square'] / 2:.5g}
RIO2 M CORE {pad['typ_square'] / 2:.5g}
DNS DVSS M diode_nd2ps_06v0 area={nd * 150e-12:.4g} pj={nd * 106e-6:.4g}
DPW M DVDD diode_pd2nw_06v0 area={npw * 150e-12:.4g} pj={npw * 106e-6:.4g}
CDV M DVDD {cdv:.4e}
CDS M DVSS {cds:.4e}
.ends pad_asig5p0
"""


def build_model(variant, corner="typ"):
    rnet = json.load(open(os.path.join(OUT, "rnet.json")))
    m = Model(rnet, corner)
    cbw = {w: chip_caps(variant, [w]) for w in WINDOWS}
    tot = defaultdict(float)
    for cc in cbw.values():
        for (x, y), c in cc.items():
            if x in MODELED and y in AGGR:
                tot[y] += c
            elif y in MODELED and x in AGGR:
                tot[x] += c
    aggr = {k for k, v in tot.items() if v >= AGGR_MIN}
    m.place(cbw, aggr)
    return m, cbw


def step_write(a):
    pad = json.load(open(os.path.join(OUT, "pad.json")))
    for variant, corner, fname in (("fill", "typ", "chipnets.spice"), ("nofill", "typ", "chipnets_nofill.spice"),
                                   ("fill", "high", "chipnets_highr.spice")):
        m, cbw = build_model(variant, corner)
        title = (f"chipnets: chip-level wiring of the GF180 EEG chip ({CHIP_LABEL}), "
                 f"{'filled chip' if variant == 'fill' else 'chip before the fill'}, "
                 f"{'typical' if corner == 'typ' else 'high'} metal resistance (pex_chipnets.py; README.md)")
        txt = (HEADER + pad_subckt(pad) + "\n" + m.spice("chipnets", title))
        open(os.path.join(OUT, fname), "w").write(txt)
        ex = [f"* couplings of the chip wiring to afe_top's inner nets ({variant}): lines for inside afe_top",
              "* (e.g. pex_afe.dut_text(variant, extra=open(this file).read())); pins are afe_top's ports"]
        for k, ((pin, inner), c) in enumerate(sorted(m.extra.items())):
            if abs(c) >= 5e-18:
                ex.append(f"CCHIP{k} {pin} {inner} {c:.4e}")
        open(os.path.join(OUT, fname.replace(".spice", "_afe_extra.spice")), "w").write("\n".join(ex) + "\n")
        print(f"wrote {fname}: {len(m.R)} resistors, {len(m.C)} capacitors, "
              f"{sum(u for _, _, u in m.dcap.values())} decoupling units", flush=True)


HEADER = """* Node names (all die-level nets of the chip that the AFE testbench needs):
*   <net>_P<k>   bond pad of analog pad analog[k] (asig_5p0; pad cell inside: pad_asig5p0)
*                AVDD: P0 (west, y 1759), P7 (west, y 772), P12 (north, x 1256)
*                AVSS: P1 (west, y 1618), P6 (west, y 913), P13 (north, x 1386)
*                ELP: P2, P3 (west); ELN: P4, P5 (west); VCM: P9; VREFP_PAD: P10; VREFN_PAD: P11 (north)
*   <net>_AFE    afe_top's pin (AVDD / AVSS: its east-edge rails, tied; ELP / ELN: the chopper's spines;
*                VCM_AFE = afe_top VCM (east edge), VCMN_AFE = VCM_N (south edge), VCMP_AFE = VCM_P (west edge))
*   <net>_BIAS   eeg_bias's pin (AVDD_BIAS / AVSS_BIAS = its VDD / VSS), <net>_ADC adc_top (eeg_adc), <net>_TM
*                the test multiplexer, <net>_REF eeg_ref (VREFP_REF / VREFN_REF its outputs,
*                VREFP_PAD_REF / VREFN_PAD_REF its pad inputs, AVSS_REF its VSS)
*   internal: <net>_E<k> core edge of a pad, <net>_J<n> route junctions, AVDD_DC<g> / AVSS_DC<g>
*   decoupling groups (Ch-A, south to north)
*   DVDD, DVSS   the pad ring's rails (ESD diodes and the pads' bar capacitance)
*   NCDB, RST, OFPH, ...  switching nets of the AFE (afe_startup.py's node names: RST = the chip's
*                RSTA) that couple to the modeled nets
* Static nets the modeled nets couple to (trims, other bias lines, test-mux selects, ATP) are AC
* ground here: their capacitance goes to the nearest AVSS node.
* Needs: .lib <PDK>/sm141064.ngspice diode_typical (pad ESD diodes) and cap_nmos_03v3 (moscap_lin.spice
* or the PDK's moscap section).
"""


# ----------------------------------------------------------------------------------
# afegrid: afe_top's own supply rails (an estimate; the block extraction has no R)
# ----------------------------------------------------------------------------------
AFE_LVSDB = os.path.join(LAYOUT, "runs", "afe_top", "afe_top.lvsdb")


def step_afegrid(a):
    """Resistance inside afe_top from its east-edge supply pins to the core's Metal4 supply
    segments over the tails (afecore_lay PWR_W = 6 um rows; AVSS in the NMOS column): the whole
    net's geometry (afe_top.lvsdb), the east-edge Metal5 pieces tied as the source, each segment
    a sink taking current in proportion to its length (the tail fingers under it). Prints the
    current-weighted mean (the drop seen by the tails per A) and the spread."""
    import klayout.db as kdb
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import spsolve
    lvs = kdb.LayoutVsSchematic()
    lvs.read(AFE_LVSDB)
    xref = lvs.xref()
    sc = next(lvs.reference.each_circuit_top_down())
    res = {}
    for net in ("AVSS", "AVDD"):
        ln = xref.other_net_for(sc.net_by_name(net))
        g = {}
        for k, ls in LVSL.items():
            r = kdb.Region()
            for l in ls:
                r += lvs.shapes_of_net(ln, lvs.layer_by_name(l), True)
            g[k] = r.merged()
        segs = [p for p in g["m4"].each() if abs(p.bbox().height() - 6000) < 20 and p.bbox().width() < 150000]
        src = list((g["m5"] & kdb.Region(kdb.Box(1099000, 0, 1100000, 1447000))).merged().each())
        n, els, pn, loc, lay = network(g, [("m5", p) for p in src] + [("m4", p) for p in segs])
        rep = list(range(n))
        for i in range(1, len(src)):
            rep[pn[i]] = pn[0]
        G = conductance(n, els, rep)
        _, comp = connected_components(G != 0, directed=False)
        wsum = sum(p.bbox().width() for p in segs)
        I = np.zeros(n)
        for j, p in enumerate(segs):
            I[pn[len(src) + j]] -= p.bbox().width() / wsum
        I[pn[0]] += 1.0
        keep = [i for i in range(n) if rep[i] == i and i != pn[0] and comp[i] == comp[pn[0]]]
        V = np.zeros(n)
        V[keep] = spsolve(G[keep][:, keep].tocsc(), I[keep])
        vs = -np.array([V[pn[len(src) + j]] for j in range(len(segs))])
        w = np.array([p.bbox().width() for p in segs]) / wsum
        res[net] = dict(mean=float((vs * w).sum()), min=float(vs.min()), max=float(vs.max()), segments=len(segs))
        print(f"afe_top {net}: east pins -> {len(segs)} core supply segments: {res[net]['mean']:.3f} ohm "
              f"(current-weighted; {res[net]['min']:.3f} .. {res[net]['max']:.3f})", flush=True)
    json.dump(res, open(os.path.join(OUT, "afegrid.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------
# tables: the numbers of the README
# ----------------------------------------------------------------------------------
def transfer(r, rio, blocks):
    """Supply net with its bond pads ideal: {(i, j): V at block i per A drawn at block j}
    (the pad cells' R in series with each pad), and the pads' share of a block's current."""
    names, Gr = r["names"], np.array(r["G"])
    pads = [g for g in names if g in SUPPLY_PADS[r["net"]]]
    G = Gr.copy()
    for p in pads:
        G[names.index(p), names.index(p)] += 1.0 / rio      # bond pad grounded through R_io
    Z = np.linalg.inv(G)
    out = {(i, j): Z[names.index(i), names.index(j)] for i in blocks for j in blocks}
    share = {}
    for j in blocks:
        v = Z[:, names.index(j)]
        share[j] = {p: v[names.index(p)] / rio for p in pads}
    return out, share


def step_tables(a):
    rn = json.load(open(os.path.join(OUT, "rnet.json")))
    pad = json.load(open(os.path.join(OUT, "pad.json")))
    L = []
    rio, rioh = pad["typ_square"], pad["high_square"]
    L.append(f"pad cell asig_5p0, bond pad -> core-edge bar ends: {rio:.4f} ohm typical ({pad['typ_tess']:.4f} with "
             f"Metal2 meshed), {rioh:.4f} ohm high corner")
    L.append("\n### supply\n")
    L.append("| | AVDD | AVSS |\n|---|---|---|")
    S = {n_: supply_summary(rn[n_], rio) for n_ in ("AVDD", "AVSS")}
    SH = {n_: supply_summary(rn[n_ + "@high"], rioh) for n_ in ("AVDD", "AVSS")}
    ST = {n_: supply_summary(rn[n_ + "@tess"], rio) for n_ in ("AVDD", "AVSS")}
    pads = {n_: SUPPLY_PADS[n_] for n_ in S}
    L.append("| each pad alone, core edge -> AFE (ohm) | " + " | ".join(
        ", ".join(f"{p} {S[n_][f'{p}->AFE']:.3f}" for p in pads[n_]) for n_ in ("AVDD", "AVSS")) + " |")
    L.append("| each pad alone, bond pad -> AFE (ohm) | " + " | ".join(
        ", ".join(f"{p} {S[n_][f'{p}_bond->AFE']:.3f}" for p in pads[n_]) for n_ in ("AVDD", "AVSS")) + " |")
    for blk in ("AFE", "ADC", "BIAS"):
        L.append(f"| 3 pads, core edge -> {blk} (ohm) | " + " | ".join(f"{S[n_][f'pads->{blk}']:.3f}" for n_ in S) + " |")
        L.append(f"| 3 bond pads -> {blk} (ohm) | " + " | ".join(f"{S[n_][f'bonds->{blk}']:.3f}" for n_ in S) + " |")
    L.append("| 3 bond pads -> AFE, high corner (ohm) | " + " | ".join(f"{SH[n_]['bonds->AFE']:.3f}" for n_ in S) + " |")
    L.append("| 3 pads, core edge -> AFE, Metal5 meshed (ohm) | " + " | ".join(
        f"{ST[n_]['pads->AFE']:.3f}" + ("" if rn[n_ + "@tess"]["tess"] else " (mesh failed: square)") for n_ in S) + " |")
    TR = {n_: transfer(rn[n_], rio, ["AFE", "ADC", "BIAS"]) for n_ in S}
    for j in ("AFE", "ADC", "BIAS"):
        L.append(f"| AFE pin per A drawn at {j} (mV/mA) | " + " | ".join(f"{TR[n_][0][('AFE', j)]:.3f}" for n_ in S) + " |")
    L.append("| pads' share of the AFE's current | " + " | ".join(
        ", ".join(f"{p} {TR[n_][1]['AFE'][p] * 100:.0f} %" for p in pads[n_]) for n_ in S) + " |")
    L.append("| star equivalent bond pad -> AFE, per pad (ohm) | " + " | ".join(
        ", ".join(f"{p} {TR[n_][0][('AFE', 'AFE')] / TR[n_][1]['AFE'][p]:.2f}" for p in pads[n_]) for n_ in S) + " |")
    # decoupling: R from the AFE pins to the decoupling rows (pads open)
    for n_ in S:
        r = rn[n_]
        names, Gr = r["names"], np.array(r["G"])
        rows = sorted([g for g in names if g.startswith("DC")], key=lambda g: int(g[2:]))
        rr = [r_between(Gr, names, ["AFE"], [x]) for x in rows]
        L.append(f"| {n_}: AFE pins -> decoupling rows (ohm), nearest / farthest / all rows tied | "
                 f"{min(rr):.3f} / {max(rr):.3f} / {r_between(Gr, names, ['AFE'], rows):.3f} | |")
    # capacitances
    cc = {v: chip_caps(v) for v in ("fill", "nofill")}
    adj = {v: defaultdict(lambda: defaultdict(float)) for v in cc}
    for v, c in cc.items():
        for (x, y), val in c.items():
            adj[v][x][y] += val
            adj[v][y][x] += val
    L.append(f"\nAVDD-AVSS wiring capacitance (chip level): {adj['fill']['AVDD']['AVSS'] * 1e12:.2f} pF filled, "
             f"{adj['nofill']['AVDD']['AVSS'] * 1e12:.2f} pF before the fill")
    L.append("\n### capacitance of the chip-level wiring per net (fF)\n")
    L.append("| net | total filled | total no fill | fill | to AVSS | to AVDD | largest couplings (filled) |")
    L.append("|---|---|---|---|---|---|---|")
    for n_ in [x for x in MODELED if x not in ("AVDD", "AVSS")]:
        f_, nf = sum(adj["fill"][n_].values()), sum(adj["nofill"][n_].values())
        big = sorted(((k, v) for k, v in adj["fill"][n_].items() if k not in ("AVDD", "AVSS")), key=lambda kv: -kv[1])[:6]
        L.append(f"| {n_} | {f_ * 1e15:.1f} | {nf * 1e15:.1f} | {(f_ / nf - 1) * 100:+.1f} % | "
                 f"{adj['fill'][n_]['AVSS'] * 1e15:.1f} | {adj['fill'][n_]['AVDD'] * 1e15:.1f} | "
                 + ", ".join(f"{k} {v * 1e15:.1f}" for k, v in big) + " |")
    # resistances of the routed nets
    L.append("\n### resistance of the routed nets (ohm, typical; high corner in brackets)\n")
    for n_ in [x for x in MODELED if x not in ("AVDD", "AVSS")]:
        k = n_ + ("@tess" if NETS[n_] == "strap" else "")
        L.append(f"- {n_}: " + ", ".join(f"{x}-{y} {v:.3f}" for x, y, v in rn[k]["edges"]) + " ["
                 + ", ".join(f"{v:.3f}" for _, _, v in rn[n_ + "@high"]["edges"]) + "]")
    txt = "\n".join(L) + "\n"
    open(os.path.join(OUT, "tables.md"), "w").write(txt)
    print(txt)


# ----------------------------------------------------------------------------------
# smoke: the models together in a power-on transient (afe_startup.py's power mode, simplified)
# ----------------------------------------------------------------------------------
def subckt_ports(path, name):
    txt = re.sub(r"\n\+", " ", open(path).read())
    return re.search(rf"^\.subckt {name} (.*)$", txt, re.M | re.I).group(1).split()


def smoke_deck(a, model, extra):
    """afe_top (pex, W / T wiring R inside, the chopper's part of E in the source resistors),
    eeg_bias and eeg_ref extracted, the chip model between them; supplies ideal at the bond
    pads (ramp 0 -> 3.3 V in --tramp), the AFE held in reset (RESET_N low)."""
    import pex_afe as P
    afe = P.dut_text("pex", extra=open(extra).read(), rin=P.RIN_EXTRACTED)
    rn = json.load(open(os.path.join(OUT, "rnet.json")))
    straps = {n_: 1.0 / sum(1.0 / R for _, _, R in rn[n_ + "@tess"]["edges"]) for n_ in ("ELP", "ELN")}
    e = [max(P.RIN_EXTRACTED["E"][k] - STRAP_RIN[k], 0.0) for k in range(2)]   # the chopper's part of E
    conn = {"VCM": "VCM_AFE", "VCM_N": "VCMN_AFE", "VCM_P": "VCMP_AFE", "AVDD": "AVDD_AFEI", "AVSS": "AVSS_AFEI",
            "ELP": "ELP_AFE", "ELN": "ELN_AFE", "OUTP": "OUTP_AFE", "OUTN": "OUTN_AFE", "VBN": "VBN_AFE",
            "VBCM": "VBCM_AFE", "BLP": "BLP_AFE", "BLN": "BLN_AFE", "RST2": "RST", "CIA2": "CIA", "CIB2": "CIB",
            "CDA2": "CDA", "NCDA2": "NCDA", "CDB2": "CDB", "NCDB2": "NCDB", "OFPH_N": "OFPH", "OFPH_P": "OFPH"}
    for k in range(4):
        conn[f"CPF{k}"] = "VDDX" if (8 >> k) & 1 else "0"
    xdut = "XDUT " + " ".join(conn.get(p, "0" if re.match(r"OF(S|M\d|EN\d)_[NP]$", p) else p) for p in P.ports()) + \
        " afe_top"
    cp = subckt_ports(model, "chipnets")
    ext = {"DVDD": "VDDX", "DVSS": "0"}
    for p in cp:
        if re.match(r"AVDD_P\d+$", p):
            ext[p] = "VDDX"
        elif re.match(r"AVSS_P\d+$", p):
            ext[p] = "0"
        elif re.match(r"EL[PN]_P\d+$", p):
            ext[p] = p[:3] + "X"
    xchip = "XCHIP " + " ".join(ext.get(p, p) for p in cp) + " chipnets"
    sv = ("v(vddx) v(avdd_afe) v(avss_afe) v(avdd_bias) v(avss_bias) v(vbn_bias) v(vbn_afe) v(vbcm_afe) v(vcm_p9) "
          "v(vcm_afe) v(vcm_bias) v(vrefp_ref) v(vrefn_ref) v(vrefp_adc) v(vrefn_adc) v(elp_afe) v(eln_afe) i(vdd)")
    an = (f"tran 10n {a.tstop:.6e} 0 {min(10e-6, a.tstop / 2000):.3e} uic\nwrdata tr.csv {sv}" if not a.op else
          f"op\nprint {sv}")
    return f"""* chipnets smoke test: power-on, AFE in reset, extracted afe_top / eeg_bias / eeg_ref with the chip model
{P.head()}.lib {P.PDK}/sm141064.ngspice diode_typical
.include {REF_PEX}
.include {BIAS_PEX}
.include {model}
{afe}
.temp 27
.options sparse reltol=1e-5 vntol=1e-8 abstol=1e-12 bypass=0
VDD VDDX 0 DC 3.3 PWL(0 0 {a.tramp:.6e} 3.3)
VREFPX VREFP_PAD_P10 0 DC 1.9 PWL(0 0 {a.tramp:.6e} 1.9)
VREFNX VREFN_PAD_P11 0 DC 1.4 PWL(0 0 {a.tramp:.6e} 1.4)
CVCM VCM_P9 0 {a.cvcm:g}
{xchip}
RAFEVDD AVDD_AFE AVDD_AFEI {max(a.rafe[1], 1e-6):g}
RAFEVSS AVSS_AFEI AVSS_AFE {max(a.rafe[0], 1e-6):g}
XREF VREFP_PAD_REF VREFN_PAD_REF VREFP_REF VREFN_REF AVSS_REF eeg_ref
RADC VREFP_ADC VREFN_ADC 18.4k
XB VBN_BIAS VBCM_BIAS BLP_BIAS BLN_BIAS VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM_BIAS VREFP_BIAS VREFN_BIAS
+ IB1 IB0 BP1 BP0 BN1 BN0 AVDD_BIAS AVSS_BIAS eeg_bias
XDQ IQ IQ AVSS_BIAS AVSS_BIAS nfet_03v3 W=4u L=2u nf=1 m=8
VITST ITST AVSS_BIAS 0
EIB1 IB1 0 VDDX 0 1
VIB0 IB0 0 0
VBP1 BP1 0 0
EBP0 BP0 0 VDDX 0 1
VBN1 BN1 0 0
EBN0 BN0 0 VDDX 0 1
IADC AVDD_ADC AVSS_ADC DC {a.iadc:g} PWL(0 0 {a.tramp:.6e} {a.iadc:g})
ECHEN CHOP_EN 0 VDDX 0 1
VCHOP CHOP 0 0
VCHOPO CHOP_OUT 0 0
VBLK CHOP_BLANK 0 0
EAFERST AFE_RST 0 VDDX 0 1
VSRC SRC 0 DC 0
EP SRC_P VCM_P9 SRC 0 0.5
EN SRC_N VCM_P9 SRC 0 -0.5
RSP SRC_P ELPX {100 + e[0]:g}
RSN SRC_N ELNX {100 + e[1]:g}
EVG VG 0 VCM_ADC 0 1
RLOADP OUTP_ADC VG {P.RIN:g}
RLOADN OUTN_ADC VG {P.RIN:g}
{xdut}
.control
set noaskquit
{an}
quit
.endc
.end
""", straps


# the pad straps' share of RIN_EXTRACTED's E (pex_rin.py, region "pad straps", sixth chip): with
# chipnets, which has the straps (and the pads), only the rest of E (the chopper) stays in series
STRAP_RIN = (0.039, 0.059)


def step_smoke(a):
    model = os.path.join(OUT, "chipnets.spice")
    extra = os.path.join(OUT, "chipnets_afe_extra.spice")
    tag = ""
    if a.rscale != 1.0:            # every resistance of the model scaled (1e-4: an ideal chip-level wiring)
        txt = open(model).read()
        txt = re.sub(r"^(R\w+ \S+ \S+ )([0-9.eE+-]+)$", lambda m: m.group(1) + f"{float(m.group(2)) * a.rscale:.6g}",
                     txt, flags=re.M)
        model = os.path.join(OUT, "smoke", f"chipnets_r{a.rscale:g}.spice")
        os.makedirs(os.path.dirname(model), exist_ok=True)
        open(model, "w").write(txt)
        tag = f"_r{a.rscale:g}"
    if any(a.rafe):
        tag += f"_rafe{a.rafe[0]:g}_{a.rafe[1]:g}"
    deck, straps = smoke_deck(a, model, extra)
    d = os.path.join(OUT, "smoke", ("op" if a.op else f"power_{a.tstop * 1e3:g}ms") + f"_iadc{a.iadc * 1e3:g}mA{tag}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    cols = ["vddx", "avdd_afe", "avss_afe", "avdd_bias", "avss_bias", "vbn_bias", "vbn_afe", "vbcm_afe", "vcm_p9",
            "vcm_afe", "vcm_bias", "vrefp_ref", "vrefn_ref", "vrefp_adc", "vrefn_adc", "elp_afe", "eln_afe", "idd"]
    if a.op:
        pv = {k.lower(): float(x_) for k, x_ in re.findall(r"^(\S+) = ([-0-9.e+]+)", r.stdout, re.M)}
        v = {c: pv["i(vdd)" if c == "idd" else f"v({c})"] for c in cols}
        x = np.array([[0.0]])
    else:
        x = np.loadtxt(os.path.join(d, "tr.csv"))
        v = {c: x[-1, 2 * k + 1] for k, c in enumerate(cols)}
    print(f"smoke ({time.time() - t:.0f} s, {d}): at {x[-1, 0] * 1e3:.2f} ms: IDD {-v['idd'] * 1e3:.3f} mA, "
          f"AFE supply {v['avdd_afe'] - v['avss_afe']:.4f} V (AVDD -{(3.3 - v['avdd_afe']) * 1e3:.1f} mV, AVSS "
          f"+{v['avss_afe'] * 1e3:.1f} mV), bias supply {v['avdd_bias'] - v['avss_bias']:.4f} V, VBN bias/AFE "
          f"{v['vbn_bias']:.4f} / {v['vbn_afe']:.4f} V (AFE rel. its AVSS {v['vbn_afe'] - v['avss_afe']:.4f}), "
          f"VCM pad / bias / AFE {v['vcm_p9']:.4f} / {v['vcm_bias']:.4f} / {v['vcm_afe']:.4f} V, VREF at eeg_ref "
          f"{(v['vrefp_ref'] - v['vrefn_ref']) * 1e3:.2f} mV, at the ADC {(v['vrefp_adc'] - v['vrefn_adc']) * 1e3:.2f} mV",
          flush=True)
    json.dump(dict(v=v, t=float(x[-1, 0]), straps=straps), open(os.path.join(d, "result.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["blocks", "verify", "pad", "rnet", "caps", "write", "tables", "afegrid", "smoke"])
    ap.add_argument("--tstop", type=float, default=3e-3, help="smoke: stop time (s)")
    ap.add_argument("--tramp", type=float, default=1e-3, help="smoke: supply ramp (s)")
    ap.add_argument("--cvcm", type=float, default=10e-9, help="smoke: off-chip VCM capacitor (F)")
    ap.add_argument("--iadc", type=float, default=0.0, help="smoke: ADC supply current AVDD_ADC -> AVSS_ADC (A)")
    ap.add_argument("--op", action="store_true", help="smoke: DC operating point at 3.3 V instead of the transient")
    ap.add_argument("--rafe", nargs=2, type=float, default=[0.0, 0.0],
                    help="smoke: afe_top's own AVSS / AVDD rails (east pins -> tails), lumped in series (ohm)")
    ap.add_argument("--rscale", type=float, default=1.0, help="smoke: scale every resistance of the model (1e-4: ideal wiring)")
    ap.add_argument("--windows", nargs="+", default=list(WINDOWS))
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--jobs", type=int, default=2, help="caps: magic runs at a time")
    ap.add_argument("--cthresh", type=float, default=0.01)
    ap.add_argument("--nets", nargs="+", default=list(NETS))
    ap.add_argument("--area", type=float, default=4.0, help="rnet: largest triangle (um2) of the meshed conductors")
    ap.add_argument("--no-tess", action="store_true", help="rnet: square counting only")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    {"blocks": step_blocks, "verify": step_verify, "pad": step_pad, "rnet": step_rnet, "caps": step_caps, "write": step_write, "tables": step_tables, "afegrid": step_afegrid, "smoke": step_smoke}[a.step](a)


if __name__ == "__main__":
    main()

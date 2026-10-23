#!/usr/bin/env python3
"""Parasitic capacitance extraction of the critical blocks (tracker D6,
documentation/gf180_pex_20261023.md).

Flow, per block:
  1. magic 8.3 (the template's nix shell, the gf180mcuD tech of the template PDK, the
     PDK of the layout and precheck) extracts the block GDS flat: the devices and every
     parasitic capacitance to the substrate and between nets above `--cthresh` fF
     (ext2spice; coupling within the tech's 8 um side halo). Device capacitances (gate,
     junction) stay in the BSIM models (ad/as/pd/ps from the layout), as the tech file
     intends, so nothing is counted twice.
  2. The magic node names are mapped to the schematic net names through the block's
     KLayout LVS database (layout/runs/<block>/<block>.lvsdb, the run that matched): a
     name such as "eeg_afe_core_0/m3_43288_59236#" is a point on a layer in cell-local
     units (5 nm here; the scale line of the .ext); the 'use' records transform it to the top cell,
     where the LVS layout netlist is probed and cross-referenced to the schematic net
     (here INN; nets of subcircuits come out as CORE.SN, CLK.PH0, ...).
  3. The DUT for ngspice: a subcircuit with the ports (names and order) of the block's
     schematic wrapper, the extracted devices (MIM renamed to the simulation model
     cap_mim_2f0ff), the capacitances between the schematic nets, and the floating nodes
     (dummy poly, isolated diffusion or metal: capacitors only) folded into their
     neighbours by the star-mesh transform, which is exact for a node with capacitors
     only. Two files: <block>_pex.spice (devices and capacitances) and
     <block>_dev.spice (the same devices without the parasitic capacitances), so that the
     layout's device geometry (finger width, junction areas) and the wiring can be told
     apart in the comparisons.
  4. A capacitance table per schematic net (total, to the supplies, the largest
     couplings), <block>_caps.txt.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/pex.py <block> [--cthresh 0.01] [--skip-magic]
"""
import argparse
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

import klayout.db as kdb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
LAYOUT = os.path.join(REPO, "gf180", "tapeout", "layout")
RUNS = os.path.join(HERE, "runs")
NIX_DIR = "/Users/noah/Codings/ws_gf180/eeg_padring"
MAGIC_TECH = ("/Users/noah/Codings/ws_gf180/gf180mcu-project-template/gf180mcu/gf180mcuD/"
              "libs.tech/magic/gf180mcuD.tech")
# .ext coordinates: lscale centimicrons per unit, from the "scale rscale cscale lscale"
# line (magic picks the grid per extraction: 0.5 for afe_top and adc_top, 1 for adc_rdac)
# KLayout LVS layers (PDK gf180mcu.lvs, read from the lvsdb connectivity) for a magic plane
# prefix: metal1..5 (l25 / l26: Metal4 / Metal5 inside the MIM marker), poly, diffusions, wells
# (not the well-derived layers for the active plane: a p-diffusion node inside an n-well
# would be taken for the well's net)
LVS_LAYERS = {"m1": ["l13"], "m2": ["l15"], "m3": ["l17"], "m4": ["l20", "l25"], "m5": ["l23", "l26"],
              "a": ["l12", "l9", "l10", "l11"], "w": ["l6"]}
ALL_LAYERS = [l for k, v in LVS_LAYERS.items() if k != "w" for l in v]
MODELS = {"cap_mim_2f0_m4m5_noshield": "cap_mim_2f0ff"}
# magic puts the MIM region on the Metal4 plane as the top plate's type, so the area and
# fringe capacitance of that region to the substrate lands on the top plate; physically the
# Metal4 bottom plate under it faces the substrate and shields the top plate. build() moves
# it to the bottom plate: per MIM, Metal4 area 7.602 aF/um2 and fringe 29.04 aF/um (the
# values of magic's .ext for a lone cap_mim cell: 87.15 fF for a 99.7 um square)
MIM_AREA, MIM_FRINGE = 7.602e-18, 29.04e-18
SUPPLIES = ("AVDD", "AVSS", "DVDD", "DVSS", "AVDD_CLK", "AVSS_CLK", "VDD", "VSS")
# block: GDS, lvsdb, the netlist and subcircuit whose ports (names, order) the DUT takes, the
# DUT name, magic uses deleted before the extraction, a prefix taken off the schematic names
BLOCKS = {
    "afe_top": dict(gds="gds/afe_top.gds", lvsdb="runs/afe_top/afe_top.lvsdb",
                    ports=("gf180/tapeout/layout/lvs/afe_top.spice", "afe_top"), dut="afe_top", sub="AVSS"),
    # the ADC without its digital block (eeg_adc_dig, a LibreLane macro of standard cells): the
    # analog part eeg_adc with the ports of gf180/tapeout/adc/eeg_adc.spice, SEL1 / SEL2 / TH
    # ending at the macro's pins
    "adc_top": dict(gds="gds/adc_top.gds", lvsdb="runs/adc_top/adc_top.lvsdb",
                    ports=("gf180/tapeout/adc/eeg_adc.spice", "eeg_adc"), dut="eeg_adc",
                    drop=("eeg_adc_dig_0",), strip="ADC.", sub="AVSS"),
    # blocks for the bench checks of DAC1 (dac1_check.py) and the OTA1 chopper (ota1_edge.py)
    "adc_rdac": dict(gds="gds/adc_rdac.gds", lvsdb="runs/adc_rdac/adc_rdac.lvsdb",
                     ports=("gf180/tapeout/layout/lvs/adc_rdac.spice", "adc_rdac"), dut="adc_rdac", sub="AVSS"),
    # the quantizer alone (its input coupling, D6 item 7): DVSS joins AVSS through the
    # substrate taps (as in its LVS), so the DUT's DVSS port stays open
    "eeg_quantizer": dict(gds="gds/eeg_quantizer.gds", lvsdb="runs/eeg_quantizer/eeg_quantizer.lvsdb",
                          ports=("gf180/tapeout/adc/eeg_quantizer.spice", "eeg_quantizer"), dut="eeg_quantizer",
                          sub="AVSS"),
    "gf180_inside_cascode_ota": dict(gds="gds/gf180_inside_cascode_ota.gds",
                                     lvsdb="runs/gf180_inside_cascode_ota/gf180_inside_cascode_ota.lvsdb",
                                     ports=("gf180/tapeout/adc/eeg_adc_otas.spice", "gf180_inside_cascode_ota"),
                                     dut="gf180_inside_cascode_ota", sub="VSS"),
}


# ----------------------------------------------------------------------------------
# magic
# ----------------------------------------------------------------------------------
def run_magic(gds, top, outdir, cthresh, drop_uses=()):
    """Flat extraction with parasitic capacitances (cthresh in fF). drop_uses: magic use ids
    (cell_n) of the top cell deleted before the extraction (e.g. a digital macro)."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".ext"):
            os.remove(os.path.join(outdir, f))
    drops = "".join(f"select cell {c}\ndelete\n" for c in drop_uses)
    tcl = f"""tech load {MAGIC_TECH}
drc off
crashbackups stop
gds read {gds}
load {top}
{drops}select top cell
extract do local
extract all
ext2spice hierarchy off
ext2spice format ngspice
ext2spice cthresh {cthresh}
ext2spice merge conservative
ext2spice subcircuit top on
ext2spice global off
ext2spice scale off
ext2spice -o {top}_magic.spice
quit -noprompt
"""
    open(os.path.join(outdir, "ext.tcl"), "w").write(tcl)
    t = time.time()
    r = subprocess.run(["nix-shell", os.path.join(NIX_DIR, "shell.nix"), "--run", "magic -dnull -noconsole ext.tcl"],
                       cwd=outdir, capture_output=True, text=True)
    open(os.path.join(outdir, "magic.log"), "w").write(r.stdout + r.stderr)
    out = os.path.join(outdir, f"{top}_magic.spice")
    if not os.path.exists(out):
        raise RuntimeError(f"magic wrote no netlist; see {outdir}/magic.log")
    return out, time.time() - t


# ----------------------------------------------------------------------------------
# netlists
# ----------------------------------------------------------------------------------
def spice_val(s):
    m = re.match(r"^([-+0-9.eE]+)([a-zA-Z]*)$", s)
    k = {"": 1, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "a": 1e-18}[m.group(2).lower()[:1]]
    return float(m.group(1)) * k


def read_magic(path):
    """magic's flat netlist -> (top, ports, devices [(name, nodes, model, params)], caps [(a, b, F)])."""
    lines, cur = [], ""
    for raw in open(path):
        raw = raw.rstrip("\n")
        if raw.startswith("+"):
            cur += " " + raw[1:]
            continue
        if cur:
            lines.append(cur)
        cur = raw
    lines.append(cur)
    top, ports, devs, caps = None, [], [], []
    for ln in lines:
        t = ln.split()
        if not t or t[0].startswith("*"):
            continue
        if t[0].lower() == ".subckt":
            top, ports = t[1], t[2:]
        elif t[0][0] in "Xx":
            k = next((i for i, w in enumerate(t) if "=" in w), len(t))
            devs.append((t[0], t[1:k - 1], t[k - 1], t[k:]))
        elif t[0][0] in "Cc":
            caps.append((t[1], t[2], spice_val(t[3])))
        elif t[0].lower() == ".ends":
            pass
        else:
            raise ValueError(f"unexpected line in {path}: {ln[:80]}")
    return top, ports, devs, caps


def wrapper_ports(path, top):
    """Port names of `.subckt top` in a schematic netlist (continuation lines joined)."""
    txt = re.sub(r"\n\+", " ", open(path).read())
    m = re.search(rf"^\.subckt\s+{top}\s+(.*)$", txt, re.M | re.I)
    return m.group(1).split()


# ----------------------------------------------------------------------------------
# magic node -> schematic net
# ----------------------------------------------------------------------------------
def ext_unit(outdir, top):
    """um per coordinate unit of the extraction (the scale line of the top cell's .ext)."""
    for ln in open(os.path.join(outdir, f"{top}.ext")):
        if ln.startswith("scale "):
            return float(ln.split()[3]) * 0.01
    raise ValueError(f"no scale line in {top}.ext")


def read_uses(outdir):
    """{cell: {use id: (child cell, (a, b, c, d, e, f))}} from the .ext files."""
    uses = {}
    for f in os.listdir(outdir):
        if not f.endswith(".ext"):
            continue
        cell = f[:-4]
        d = {}
        for ln in open(os.path.join(outdir, f)):
            if ln.startswith("use "):
                t = ln.split()
                if len(t) != 9:
                    raise ValueError(f"array use not handled: {ln.strip()}")
                d[t[2]] = (t[1], tuple(int(v) for v in t[3:9]))
        uses[cell] = d
    return uses


NODE_RX = re.compile(r"^([a-z]+[0-9]?)_(n?\d+)_(n?\d+)#$")


def node_point(name, uses, top, unit, d=0.4):
    """(plane prefix, x um, y um) of a magic node name in top-cell coordinates, or None.
    The name is the lower-left corner of one of the node's tiles in its cell; the point is
    moved d units (2 or 4 nm) into that tile before the transforms (a mirrored use turns
    the corner into another one)."""
    parts = name.split("/")
    m = NODE_RX.match(parts[-1])
    if not m:
        return None
    pre, xs, ys = m.groups()
    x, y = (int(v.replace("n", "-")) + d for v in (xs, ys))
    chain, cell = [], top
    for u in parts[:-1]:
        if u not in uses.get(cell, {}):
            return None
        cell, tr = uses[cell][u]
        chain.append(tr)
    for a, b, c, d, e, f in reversed(chain):
        x, y = a * x + b * y + c, d * x + e * y + f
    return pre, x * unit, y * unit


def map_nodes(nodes, uses, top, lvsdb, unit):
    """{magic node: schematic net name} for the nodes that the LVS database resolves."""
    lvs = kdb.LayoutVsSchematic()
    lvs.read(lvsdb)
    xref = lvs.xref()
    regions = {l: lvs.layer_by_name(l) for l in ALL_LAYERS}
    out, miss = {}, []
    for n in nodes:
        p = node_point(n, uses, top, unit)
        if p is None:
            continue
        pre, x, y = p
        net = None
        for l in LVS_LAYERS.get(pre, ALL_LAYERS):
            net = lvs.probe_net(regions[l], kdb.DPoint(x, y))
            if net is not None:
                break
        if net is None:
            miss.append(n)
            continue
        sn = xref.other_net_for(net)
        if sn is not None:
            out[n] = sn.expanded_name()
        else:
            out[n] = "LAYOUT." + net.expanded_name()
    return out, miss


# ----------------------------------------------------------------------------------
# DUT netlist
# ----------------------------------------------------------------------------------
def sanitize(n):
    return re.sub(r"[^A-Za-z0-9_.]", "_", n)


def fold_floating(caps, keep):
    """Star-mesh elimination of the nodes that only have capacitors (not in `keep`)."""
    adj = defaultdict(lambda: defaultdict(float))
    for a, b, c in caps:
        if a != b:
            adj[a][b] += c
            adj[b][a] += c
    floating = [n for n in adj if n not in keep]
    for f in floating:
        nb = adj.pop(f)
        tot = sum(nb.values())
        for k in nb:
            del adj[k][f]
        ks = list(nb)
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                c = nb[a] * nb[b] / tot
                adj[a][b] += c
                adj[b][a] += c
    out = []
    for a in adj:
        for b, c in adj[a].items():
            if a < b and c > 0:
                out.append((a, b, c))
    return out, len(floating)


def mim_substrate(devs, caps, sub):
    """Move each MIM's area/fringe capacitance to the substrate net `sub` from its top
    plate (first terminal in magic's netlist) to its bottom plate (see MIM_AREA)."""
    agg = defaultdict(float)
    for a, b, c in caps:
        agg[(a, b) if a < b else (b, a)] += c
    moved = 0.0
    key = lambda a, b: (a, b) if a < b else (b, a)
    for _, nn, model, par in devs:
        if model != "cap_mim_2f0_m4m5_noshield":
            continue
        p = dict(w.split("=") for w in par)
        w, l = spice_val(p["c_width"]) * 1e6, spice_val(p["c_length"]) * 1e6
        c = MIM_AREA * w * l + MIM_FRINGE * 2 * (w + l)
        top, bot = nn[0], nn[1]
        if top == sub:
            continue
        c = min(c, agg.get(key(top, sub), 0.0))
        agg[key(top, sub)] -= c
        if bot != sub:
            agg[key(bot, sub)] += c
        moved += c
    return [(a, b, c) for (a, b), c in agg.items() if c > 0], moved


def build(block, cthresh=0.01, skip_magic=False):
    cfg = BLOCKS[block]
    outdir = os.path.join(RUNS, f"{block}_c")
    gds = os.path.join(LAYOUT, cfg["gds"])
    dut = cfg["dut"]
    if skip_magic:
        msp = os.path.join(outdir, f"{block}_magic.spice")
    else:
        msp, dt = run_magic(gds, block, outdir, cthresh, cfg.get("drop", ()))
        print(f"magic: {dt:.0f} s")
    top, mports, devs, caps = read_magic(msp)
    caps, moved = mim_substrate(devs, caps, cfg["sub"])
    print(f"MIM substrate capacitance moved from the top to the bottom plates: {moved * 1e12:.2f} pF")
    nodes = set(mports)
    for _, nn, _, _ in devs:
        nodes.update(nn)
    for a, b, _ in caps:
        nodes.update((a, b))
    uses = read_uses(outdir)
    t = time.time()
    nmap, miss = map_nodes(sorted(nodes), uses, top, os.path.join(LAYOUT, cfg["lvsdb"]), ext_unit(outdir, top))
    print(f"mapped {len(nmap)} of {len(nodes)} nodes in {time.time() - t:.0f} s ({len(miss)} not found in the LVS layout)")
    for p in mports:  # ports keep their labels
        nmap[p] = p
    strip = cfg.get("strip", "")
    ren = {n: sanitize(nmap.get(n, n)[len(strip):] if strip and nmap.get(n, n).startswith(strip)
                       else nmap.get(n, n)) for n in nodes}
    # several magic nodes on one schematic net: allowed for ports (joined outside, e.g. AVDD
    # pieces), reported otherwise
    groups = defaultdict(list)
    for n, s in ren.items():
        groups[s].append(n)
    multi = {s: v for s, v in groups.items() if len(v) > 1}
    wports = wrapper_ports(os.path.join(REPO, cfg["ports"][0]), cfg["ports"][1])
    devnodes = set()
    rdevs = []
    for name, nn, model, par in devs:
        nn = [ren[n] for n in nn]
        devnodes.update(nn)
        rdevs.append((name, nn, MODELS.get(model, model), par))
    rcaps = [(ren[a], ren[b], c) for a, b, c in caps]
    keep = devnodes | set(wports)
    fcaps, nfl = fold_floating(rcaps, keep)
    missing_ports = [p for p in wports if p not in devnodes and p not in {a for a, _, _ in fcaps} | {b for _, b, _ in fcaps}]
    hdr = (f"* {dut}: magic flat extraction of {os.path.relpath(gds, REPO)} (cthresh {cthresh} fF), nodes on the\n"
           f"* schematic net names of {cfg['lvsdb']} (gf180/tapeout/pex/pex.py). {len(rdevs)} devices,\n"
           f"* {len(fcaps)} capacitors ({sum(c for _, _, c in fcaps) * 1e12:.1f} pF), {nfl} floating nodes folded.\n")
    body = [f"{name} {' '.join(nn)} {model} {' '.join(par)}" for name, nn, model, par in rdevs]

    def write(path, with_caps):
        with open(path, "w") as fo:
            fo.write(hdr + ("" if with_caps else "* devices only (no parasitic capacitances)\n"))
            fo.write(f".subckt {dut} " + " ".join(wports) + "\n")
            for ln in body:
                fo.write(ln + "\n")
            if with_caps:
                for i, (a, b, c) in enumerate(sorted(fcaps)):
                    fo.write(f"CP{i} {a} {b} {c:.6e}\n")
            fo.write(f".ends {dut}\n")
    write(os.path.join(outdir, f"{dut}_pex.spice"), True)
    write(os.path.join(outdir, f"{dut}_dev.spice"), False)
    cap_table(fcaps, os.path.join(outdir, f"{block}_caps.txt"))
    print(f"{block}: {len(rdevs)} devices, {len(fcaps)} capacitors, {nfl} floating nodes folded; "
          f"ports missing from the extraction: {missing_ports}")
    mp = {s: v for s, v in multi.items() if s not in wports}
    if mp:
        print(f"  internal schematic nets on several magic nodes (joined): {len(mp)}, e.g. "
              + ", ".join(f"{s} ({len(v)})" for s, v in list(mp.items())[:8]))
    unm = sorted({ren[n] for n in nodes if n not in nmap})
    print(f"  unmapped nodes kept with magic names: {len(unm)}")
    return outdir


def cap_table(caps, path):
    """Per net: total parasitic C, the part to the supplies, the five largest couplings."""
    adj = defaultdict(lambda: defaultdict(float))
    for a, b, c in caps:
        adj[a][b] += c
        adj[b][a] += c
    with open(path, "w") as fo:
        fo.write("# net  total_fF  to_supplies_fF  largest couplings (fF)\n")
        for n in sorted(adj, key=lambda k: -sum(adj[k].values())):
            tot = sum(adj[n].values())
            sup = sum(v for k, v in adj[n].items() if k in SUPPLIES)
            big = sorted(((v, k) for k, v in adj[n].items()), reverse=True)[:5]
            fo.write(f"{n} {tot * 1e15:.2f} {sup * 1e15:.2f} " + " ".join(f"{k}:{v * 1e15:.2f}" for v, k in big) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("block", choices=sorted(BLOCKS))
    ap.add_argument("--cthresh", type=float, default=0.01, help="smallest capacitance kept by ext2spice (fF)")
    ap.add_argument("--skip-magic", action="store_true", help="reuse the magic netlist of an earlier run")
    a = ap.parse_args()
    build(a.block, a.cthresh, a.skip_magic)


if __name__ == "__main__":
    sys.exit(main())

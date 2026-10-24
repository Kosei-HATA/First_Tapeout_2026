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
     cap_mim_2f0ff), the capacitances between the schematic nets (what magic gives a MIM
     top plate down to the conductors under it moved to the bottom plate, which lies
     between them: mim_shield), and the floating nodes
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
# magic puts the MIM region on the Metal4 plane as the top plate's type, so the capacitance
# of that region down to the conductors under it (Metal3 ... wells) and to the substrate
# lands on the top plate; physically the Metal4 bottom plate lies under the whole top plate,
# faces them and shields the top plate. build() moves it to the bottom plate (mim_shield):
# top plates (LVS layer l67, fusetop) and bottom plates (l66 / l25 / l20) from the lvsdb,
# per lower LVS layer, top down (an upper one shields the lower ones), magic's area (aF/um2)
# and edge (aF/um, for the conductor under a 0.2 um band outside the plate edge)
# capacitances from the Metal4 plane (gf180mcuD.tech, defaultoverlap / defaultsideoverlap
# allm4, which includes *mimcap); what no conductor covers faces the substrate
# (defaultareacap / defaultperimeter allm4: 86.8 fF for a lone 99.7 um cap_mim, magic's
# .ext of the cell 87.15 fF)
MIM_TOP, MIM_BOT = "l67", ("l66", "l25", "l20")
MIM_UNDER = [(("l17",), 59.027, 47.871), (("l15",), 20.238, 36.563), (("l13",), 12.212, 32.104),
             (("l12",), 8.557, 29.407), (("l9", "l10", "l11"), 8.148, 29.065), (("l6",), 7.602, 28.153)]
MIM_SUB, MIM_BAND = (7.602, 28.153), 0.2
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
    # OTA2 alone, for its open-loop AC with the stage-2 load (viz_data.py ota)
    "gf180_ct_ota_tel16_cmfb": dict(gds="gds/gf180_ct_ota_tel16_cmfb.gds",
                                    lvsdb="runs/gf180_ct_ota_tel16_cmfb/gf180_ct_ota_tel16_cmfb.lvsdb",
                                    ports=("gf180/tapeout/adc/eeg_adc_otas.spice", "gf180_ct_ota_tel16_cmfb"),
                                    dut="gf180_ct_ota_tel16_cmfb", sub="VSS"),
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
    regions = {l: lvs.layer_by_name(l) for v in LVS_LAYERS.values() for l in v}
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


def mim_shield(caps, lvsdb, sub, rename):
    """Move the capacitance that magic gives a MIM top plate down to the conductors under it
    and to the substrate net `sub` to its bottom plate (see MIM_TOP). caps (a, b, F) on the
    schematic names; rename() turns an LVS net name into one. A conductor of the top plate's
    own net under it (nothing in magic) faces the bottom plate: added. Returns the caps,
    {(top, bottom): F moved or added}, the total wanted and the part magic did not have."""
    lvs = kdb.LayoutVsSchematic()
    lvs.read(lvsdb)
    xref = lvs.xref()
    dbu = lvs.internal_layout().dbu
    cell = lvs.internal_top_cell()

    def region(names):
        r = kdb.Region()
        for l in names:
            r += kdb.Region(cell.begin_shapes_rec(lvs.layer_of(lvs.layer_by_name(l))))
        return r

    def inside(poly):  # a point inside a polygon: the centre of one of its trapezoids
        pts = list(poly.decompose_trapezoids()[0].each_point())
        return kdb.DPoint(sum(p.x for p in pts) / len(pts) * dbu, sum(p.y for p in pts) / len(pts) * dbu)

    def net_at(names, pt):
        for l in names:
            n = lvs.probe_net(lvs.layer_by_name(l), pt)
            if n is not None:
                s = xref.other_net_for(n)
                return rename(s.expanded_name() if s is not None else "LAYOUT." + n.expanded_name())
        return None

    tops = region([MIM_TOP]).merged()
    band = int(round(MIM_BAND / dbu))
    zone = tops.sized(band)
    under = [(names, ca, ce, (region(names) & zone).merged()) for names, ca, ce in MIM_UNDER]
    want = defaultdict(float)  # (top, bottom, conductor under) -> F
    for p in tops.each():
        plate = kdb.Region(p)
        edge = plate.sized(band) - plate
        pt = inside(p)
        t, b = net_at([MIM_TOP], pt), net_at(MIM_BOT, pt)
        if t is None or b is None:
            continue
        cov_a, cov_e = kdb.Region(), kdb.Region()
        for names, ca, ce, r in under:
            a, e = (r & plate) - cov_a, (r & edge) - cov_e
            for q in a.each():
                want[(t, b, net_at(names, inside(q)))] += ca * q.area() * dbu ** 2 * 1e-18
            for q in e.each():
                want[(t, b, net_at(names, inside(q)))] += ce * q.area() * dbu ** 2 / MIM_BAND * 1e-18
            cov_a += a
            cov_e += e
        want[(t, b, sub)] += (MIM_SUB[0] * (plate - cov_a).area() * dbu ** 2
                              + MIM_SUB[1] * (edge - cov_e).area() * dbu ** 2 / MIM_BAND) * 1e-18
    key = lambda a, b: (a, b) if a < b else (b, a)
    agg = defaultdict(float)
    for a, b, c in caps:
        if a != b:
            agg[key(a, b)] += c
    moved, total, left = defaultdict(float), 0.0, 0.0
    for (t, b, x), c in want.items():
        if x is None or t == b:
            continue
        total += c
        if x != t:
            have = agg.get(key(t, x), 0.0)
            left += max(c - have, 0.0)
            c = min(c, have)
            agg[key(t, x)] -= c
        if x != b:
            agg[key(b, x)] += c
        moved[(t, b)] += c
    return [(a, b, c) for (a, b), c in agg.items() if c > 0], moved, total, left


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
    rename = lambda s: sanitize(s[len(strip):] if strip and s.startswith(strip) else s)
    ren = {n: rename(nmap.get(n, n)) for n in nodes}
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
    rcaps, moved, total, left = mim_shield(rcaps, os.path.join(LAYOUT, cfg["lvsdb"]), ren.get(cfg["sub"], cfg["sub"]),
                                           rename)
    print(f"MIM top plates: {total * 1e12:.2f} pF down to the conductors under them and the substrate "
          f"taken to the bottom plates ({left * 1e12:.2f} pF of it not on the top plate in magic's netlist)")
    for (t, b), c in sorted(moved.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {t} -> {b}: {c * 1e12:.3f} pF")
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

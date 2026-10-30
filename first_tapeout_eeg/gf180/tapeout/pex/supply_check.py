#!/usr/bin/env python3
"""Supply connections of the chip from its GDS alone: no schematic, no LVS and none of the
chip-level labels (tracker E7; written 10/29, after the core's DVDD turned out to reach no pad
in r0..r7). It checks what chip_lay.connect_check() and the two full-chip LVS assume, from
other sources:

  - the supply pads: DVDD / DVSS by their IO cell (gf180mcu_fd_io__dvdd / __dvss), AVDD /
    AVSS by the floorplan's pad table (gf180/tapeout/chip/padring/pad_coordinates.csv); each
    bond pad (pad_geometry.json, from the template's pad ring run) probed on Metal5
  - the nets: Metal1..5 / Via1..4 of the GDS (KLayout LayoutToNetlist, hierarchical)
  - the blocks' supply pins: the digital macros' power pins from their LEF (LibreLane), the
    other blocks' from the labels of their own GDS (what their block LVS checked)
  - the resistance of the chip-level wiring (shapes drawn in chip_top itself) from where it
    meets the supply's pads to where it meets each block (pex_chipnets.network(): KLayout's
    R extractor with the PDK's sheet resistances); the pad cells' own resistance and the pad
    ring's rails are not in it

usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/supply_check.py [chip_top.gds]
       (default: gf180/tapeout/layout/runs/chip_top/chip_top.gds)
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pex_chipnets as PC  # noqa: E402  (network, conductance, kron, r_between, layer keys)

import klayout.db as kdb  # noqa: E402

PADCSV = os.path.join(PC.REPO, "gf180", "tapeout", "chip", "padring", "pad_coordinates.csv")
GDSDIR = os.path.join(PC.LAYOUT, "gds")
LABEL_LAYER = {34: "m1", 36: "m2", 42: "m3", 46: "m4", 81: "m5"}       # label datatype 10
SUPPLIES = ("DVDD", "DVSS", "AVDD", "AVSS")
# each block's supply pins by the block's own names -> the chip's supply (adc_top's block LVS
# renamed its DVSS label to AVSS, the substrate joining them: either supply is accepted there)
BLOCK_PINS = {"afe_top": {"AVDD": "AVDD", "AVSS": "AVSS"},
              "adc_top": {"AVDD": "AVDD", "DVDD": "DVDD", "AVSS": ("AVSS", "DVSS")},
              "eeg_bias": {"VDD": "AVDD", "VSS": "AVSS"}, "eeg_ref": {"VSS": "AVSS"},
              "eeg_testmux": {"AVDD": "AVDD", "AVSS": "AVSS"}}
# LibreLane macros: LEF, instance path from the top cell; power pins -> the chip's supply
MACROS = {"eeg_digital_top": ("eeg_digital_top.lef", ("eeg_digital_top",)),
          "eeg_adc_dig": ("eeg_adc_dig.lef", ("adc_top", "eeg_adc_dig"))}
MACRO_PINS = {"VDD": "DVDD", "VSS": "DVSS"}
SHORT = {"afe_top": "AFE", "adc_top": "ADC", "eeg_bias": "BIAS", "eeg_ref": "REF", "eeg_testmux": "TM",
         "eeg_digital_top": "DIG", "chip_decap": "DECAP"}


def extract(path):
    ly = kdb.Layout()
    ly.read(path)
    top = ly.top_cell()
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, top, []))
    keys = ("m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4", "m5")
    R = {k: l2n.make_layer(ly.find_layer(*PC.GDSL[k]), k) for k in keys}
    for k in keys:
        l2n.connect(R[k])
    for lo, hi in zip(keys, keys[1:]):
        l2n.connect(R[lo], R[hi])
    l2n.extract_netlist()
    return ly, top, l2n, R


def top_net(l2n, R, lay, x, y):
    """The top-level net at (x, y) um on layer lay (followed up through subcircuit pins), or
    None (no shape, or a net that does not leave its cell)."""
    path = []
    net = l2n.probe_net(R[lay], kdb.DPoint(x, y), path)
    while net is not None and path:
        sc = path.pop()
        pins = list(net.each_pin())
        net = sc.net_for_pin(pins[0].pin_id()) if pins else None
    return net


def lef_pins(lef):
    """{pin: [(layer key, x1, y1, x2, y2)]} of a LEF macro's VDD / VSS pins (um)."""
    out, pin, lay = {}, None, None
    for line in open(lef):
        w = line.split()
        if w[:1] == ["PIN"]:
            pin = w[1] if w[1] in MACRO_PINS else None
        elif w[:1] == ["END"] and pin and w[1:2] == [pin]:
            pin = None
        elif pin and w[:1] == ["LAYER"]:
            lay = {"Metal1": "m1", "Metal2": "m2", "Metal3": "m3", "Metal4": "m4", "Metal5": "m5"}.get(w[1])
        elif pin and lay and w[:1] == ["RECT"]:
            out.setdefault(pin, []).append((lay,) + tuple(float(v) for v in w[1:5]))
    return out


def inst_trans(ly, top, names):
    """DCplxTrans of the (first) instance path names[0] / names[1] / ... from the top cell."""
    t, cell = kdb.DCplxTrans(), top
    for nm in names:
        inst = next(i for i in cell.each_inst() if i.cell.name == nm)
        t = t * inst.dcplx_trans
        cell = inst.cell
    return t


def block_labels(name):
    """[(label, layer key, x, y)] of the supply labels in a block's own GDS (block um)."""
    ly = kdb.Layout()
    ly.read(os.path.join(GDSDIR, f"{name}.gds"))
    top = ly.top_cell()
    out = []
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        if info.datatype != 10 or info.layer not in LABEL_LAYER:
            continue
        for sh in top.shapes(li).each(kdb.Shapes.STexts):
            if sh.text.string in BLOCK_PINS[name]:
                d = sh.text.trans.disp
                out.append((sh.text.string, LABEL_LAYER[info.layer], d.x * ly.dbu, d.y * ly.dbu))
    return out


def supply_pads():
    """{supply: [(pad name, (x, y) bond pad centre, bbox)]}."""
    sig = {row["inst"]: row["signal"] for row in csv.DictReader(open(PADCSV))}
    out = defaultdict(list)
    for p in json.load(open(PC.PADGEOM))["pads"]:
        name = re.sub(r"\.pad$", "", p["inst"].replace("\\", ""))
        cell = p["cell"].replace("gf180mcu_fd_io__", "")
        s = {"dvdd": "DVDD", "dvss": "DVSS"}.get(cell)
        if cell == "asig_5p0":
            s = next((x for x in ("AVDD", "AVSS") if sig.get(name, "").startswith(x)), None)
        if s:
            out[s].append((name, tuple(p["bond_center"]), p["bbox"]))
    return out


def net_ports(ly, top, l2n, R, net, pads):
    """The chip-level shapes of a net ({layer key: Region}) and its ports [(group, layer key,
    Polygon)] where they meet an instance's shapes (pex_chipnets.Chip.ports): pads by name,
    blocks by SHORT, the decoupling units as DECAP."""
    geo = {k: l2n.shapes_of_net(net, R[k], False).merged() for k in R}
    out = []
    for inst in top.each_inst():
        cell = inst.cell
        tr = inst.cplx_trans

        def reg(k, box):
            return kdb.Region(cell.begin_shapes_rec_overlapping(ly.find_layer(*PC.GDSL[k]),
                                                                box.transformed(tr.inverted()))).transformed(tr).merged()
        for k in list(PC.METALS) + list(PC.VIAS):
            if geo[k].is_empty():
                continue
            box = geo[k].bbox() & inst.bbox()
            if box.empty():
                continue
            found = []
            if k in PC.VIAS:              # a chip-level via onto the instance's metal
                lo, hi = PC.VIAS[k]
                for side, other in ((lo, hi), (hi, lo)):
                    bare = geo[k] - geo[side]
                    if not bare.is_empty():
                        hit = (bare & reg(side, box.enlarged(10, 10))) & geo[other]
                        found += [(p, other) for p in hit.merged().each()]
            else:
                found = [(p, k) for p in (geo[k] & reg(k, box.enlarged(10, 10))).merged().each()]
            for p, lk in found:
                c = p.bbox().center().to_dtype(ly.dbu)
                if cell.name == "padring":
                    grp = next((nm for nm, _, bb in pads if bb[0] - 1 <= c.x <= bb[2] + 1 and bb[1] - 1 <= c.y <= bb[3] + 1),
                               "padring")
                else:
                    grp = SHORT.get(cell.name, cell.name)
                out.append((grp, lk, p))
    return geo, out


def resistances(geo, ports, sources):
    """R from the ports of the source pads (tied) to each other group; inf where the chip-level
    wiring does not join them."""
    from scipy.sparse.csgraph import connected_components
    n, els, pn, loc, lay = PC.network(geo, [(k, p) for _, k, p in ports])
    groups = defaultdict(list)
    for i, (grp, _, _) in enumerate(ports):
        groups[grp].append(pn[i])
    G = PC.conductance(n, els)
    _, comp = connected_components(G != 0, directed=False)
    src = [v for g in sources for v in groups.get(g, [])]
    out = {}
    for g, vs in sorted(groups.items()):
        if g in sources:
            continue
        cs = {comp[v] for v in vs} & {comp[s] for s in src}
        if not cs:
            out[g] = float("inf")
            continue
        # the components that join the group to the pads (floating pieces make G singular)
        sub = [i for i in range(n) if comp[i] in cs]
        idx = {v: j for j, v in enumerate(sub)}
        Gs = G[sub][:, sub].tocsc()
        a = [idx[v] for v in src if comp[v] in cs]
        b = [idx[v] for v in vs if comp[v] in cs]
        keep = sorted(set(a) | set(b))
        Gr = PC.kron(Gs, keep)
        names = [str(v) for v in keep]
        out[g] = PC.r_between(Gr, names, [str(v) for v in a], [str(v) for v in b])
    return out


# the analog supplies' DC currents (A) at the chip's operating point (gf180_realistic_eval_20261028.md:
# the AFE at AFE_IBIAS 3, the ADC, the bias block), for the split over the pads; the analog pad
# cell: bond pad -> its eight Metal2 bars 1.27 ohm (pex_chipnets pad), bars 8 x 2.54 um
LOADS = {"AVDD": {"AFE": 21.53e-3, "ADC": 4.7e-3, "BIAS": 0.95e-3},
         "AVSS": {"AFE": 21.53e-3, "ADC": 4.7e-3, "BIAS": 0.95e-3}}
R_PAD = 1.27
PAD_LIMIT = 8 * 2.54 * 0.67e-3           # A: the bars at the tech LEF's 0.67 mA/um (Metal2)


def pad_split(geo, ports, sources, loads):
    """Each source pad's share of the loads' currents: the chip-level wiring, each pad's own
    cell (R_PAD) to the supply outside; returns {pad: A}."""
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import spsolve
    n, els, pn, loc, lay = PC.network(geo, [(k, p) for _, k, p in ports])
    groups = defaultdict(list)
    for i, (grp, _, _) in enumerate(ports):
        groups[grp].append(pn[i])
    rep = list(range(n + 1))                 # node n: the supply outside the chip
    for vs in groups.values():
        for v in vs[1:]:
            rep[v] = vs[0]
    els = els + [(groups[g][0], n, R_PAD) for g in sources]
    G = PC.conductance(n + 1, els, rep)
    _, comp = connected_components(G != 0, directed=False)
    keep = [i for i in range(n) if comp[i] == comp[n] and rep[i] == i]
    idx = {v: j for j, v in enumerate(keep)}
    Gk = G[keep][:, keep].tocsc()
    rhs = np.zeros(len(keep))
    for g, amps in loads.items():
        if g in groups and comp[rep[groups[g][0]]] == comp[n]:
            rhs[idx[rep[groups[g][0]]]] += amps
    v = spsolve(Gk, rhs)
    return {g: float(v[idx[rep[groups[g][0]]]] / R_PAD) for g in sources}


def main(path=None):
    """The check of the chip GDS `path` (default: the command line's, else the chip's
    chip_top.gds); returns the problems (empty: ok)."""
    path = path or (sys.argv[1] if len(sys.argv) > 1 else PC.GDS_NOFILL)
    ly, top, l2n, R = extract(path)
    pads = supply_pads()
    nets, bad = {}, []
    print(f"supply check of {path} (GDS only)")
    for s in SUPPLIES:
        found = defaultdict(list)
        for name, (x, y), _ in pads[s]:
            net = top_net(l2n, R, "m5", x, y)
            found[net.expanded_name() if net else None].append(name)
        print(f"== {s}: {len(pads[s])} pads on {len(found)} net(s): " +
              "; ".join(f"{k}: {', '.join(v)}" for k, v in found.items()))
        if None in found or len(found) != 1:
            bad.append(f"{s}: pads on {len(found)} nets")
        nets[s] = next(iter(found))
    by_net = defaultdict(list)
    for s, n in nets.items():
        by_net[n].append(s)
    bad += [f"{' and '.join(v)} on one net {k}" for k, v in by_net.items() if len(v) > 1]
    # the blocks' supply pins
    for name, (lef, ipath) in MACROS.items():
        t = inst_trans(ly, top, ipath)
        for pin, rects in lef_pins(os.path.join(GDSDIR, lef)).items():
            want = MACRO_PINS[pin]
            got = defaultdict(int)
            for k, x1, y1, x2, y2 in rects:
                c = t * kdb.DPoint((x1 + x2) / 2, (y1 + y2) / 2)
                net = top_net(l2n, R, k, c.x, c.y)
                got[next((s for s, nn in nets.items() if net and nn == net.expanded_name()), "no supply pad")] += 1
            ok = set(got) == {want}
            print(f"   {name} {pin} (LEF, {len(rects)} shapes): " + ", ".join(f"{v} on {k}" for k, v in got.items())
                  + ("" if ok else f"   <-- should be {want}"))
            if not ok:
                bad.append(f"{name} {pin}: {dict(got)}")
    for name, pins in BLOCK_PINS.items():
        t = inst_trans(ly, top, (name,))
        for lab, k, x, y in block_labels(name):
            c = t * kdb.DPoint(x, y)
            net = top_net(l2n, R, k, c.x, c.y)
            s = next((s for s, nn in nets.items() if net and nn == net.expanded_name()), "no supply pad")
            want = pins[lab] if isinstance(pins[lab], tuple) else (pins[lab],)
            print(f"   {name} {lab} (its label at {c.x:.1f}, {c.y:.1f}): on {s}" + ("" if s in want else f"   <-- should be {'/'.join(want)}"))
            if s not in want:
                bad.append(f"{name} {lab}: on {s}")
    # resistance of the chip-level wiring, the supply's pads to each block
    for s in SUPPLIES:
        net = next(n for n in l2n.netlist().circuit_by_name(top.name).each_net() if n.expanded_name() == nets[s])
        geo, ports = net_ports(ly, top, l2n, R, net, pads[s])
        srcs = sorted({g for g, _, _ in ports if g in {p[0] for p in pads[s]}})
        r = resistances(geo, ports, srcs)
        blocks = {g: v for g, v in r.items() if g in SHORT.values()}
        print(f"   {s} chip-level wiring from {', '.join(srcs) or 'no pad'}: " +
              ", ".join(f"{g} {v:.3f} ohm" if np.isfinite(v) else f"{g} NOT JOINED" for g, v in sorted(blocks.items())))
        bad += [f"{s}: {g} not joined to its pads by the chip-level wiring" for g, v in blocks.items() if not np.isfinite(v)]
        if s in LOADS:
            sp = pad_split(geo, ports, srcs, LOADS[s])
            tot = sum(LOADS[s].values())
            print(f"   {s} pad currents ({tot * 1e3:.1f} mA; limit {PAD_LIMIT * 1e3:.1f} mA per pad, its Metal2 bars): " +
                  ", ".join(f"{g} {a * 1e3:.2f} mA ({a / PAD_LIMIT:.0%})" for g, a in sorted(sp.items())))
    print("result:", "ok" if not bad else f"{len(bad)} problems")
    for b in bad:
        print("  " + b)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)

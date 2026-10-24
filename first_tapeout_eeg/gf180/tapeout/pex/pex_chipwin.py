#!/usr/bin/env python3
"""Chip-level wiring of a few nets (tracker D4 / D6): magic's capacitances in a window of the
filled chip, on the chip's schematic net names.

The window of runs/chip_top/chip_top_fill.gds (die coordinates, all layers, flattened; the
dummy fill included) is extracted flat with magic as pex.py does for a block; the node names
are mapped through the chip core's LVS database (runs/chip_top/eeg_core.lvsdb, the same
coordinates); nodes the database does not know (dummy fill, shapes the window cuts off from
their net) are folded into their neighbours (star-mesh, exact for capacitor-only nodes).
Shapes that cross the window's edge lose the part outside, so the window is drawn with a
margin of more than magic's 8 um coupling halo around the nets of interest.

Output: per net of interest, the total, the part to the supplies and every coupling above
--min fF, and a SPICE fragment (<name>_cw.spice) of these capacitors for a testbench.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/pex_chipwin.py --box x1 y1 x2 y2 --nets OUTP OUTN
       [--name outpn] [--min 0.05]
"""
import argparse
import os
from collections import defaultdict

import klayout.db as kdb

import pex

LAYOUT = pex.LAYOUT
GDS = os.path.join(LAYOUT, "runs", "chip_top", "chip_top_fill.gds")
LVSDB = os.path.join(LAYOUT, "runs", "chip_top", "eeg_core.lvsdb")


def window_gds(src, box, out):
    """Flat copy of every layer of the top cell inside box (um)."""
    ly = kdb.Layout()
    ly.read(src)
    top = ly.top_cell()
    b = kdb.DBox(*box).to_itype(ly.dbu)
    w = kdb.Layout()
    w.dbu = ly.dbu
    wc = w.create_cell("win")
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        r = (kdb.Region(top.begin_shapes_rec_overlapping(li, b)) & kdb.Region(b)).merged()
        if not r.is_empty():
            wc.shapes(w.layer(info)).insert(r)
    w.write(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", nargs=4, type=float, required=True, help="x1 y1 x2 y2 (um, die)")
    ap.add_argument("--nets", nargs="+", required=True)
    ap.add_argument("--name", default="win")
    ap.add_argument("--min", type=float, default=0.05, help="smallest coupling listed (fF)")
    ap.add_argument("--gds", default=GDS)
    a = ap.parse_args()
    outdir = os.path.join(pex.RUNS, f"chipwin_{a.name}")
    os.makedirs(outdir, exist_ok=True)
    gds = os.path.join(outdir, "win.gds")
    window_gds(a.gds, a.box, gds)
    msp, dt = pex.run_magic(gds, "win", outdir, 0.01)
    print(f"magic: {dt:.0f} s")
    top, mports, devs, caps = pex.read_magic(msp)
    nodes = set()
    for a_, b_, _ in caps:
        nodes.update((a_, b_))
    for _, nn, _, _ in devs:
        nodes.update(nn)
    nmap, miss = pex.map_nodes(sorted(nodes), pex.read_uses(outdir), top, LVSDB, pex.ext_unit(outdir, top))
    print(f"mapped {len(nmap)} of {len(nodes)} nodes ({len(miss)} not in the LVS layout: fill, cut shapes)")
    ren = {n: pex.sanitize(nmap.get(n, n)) for n in nodes}
    rcaps = [(ren[x], ren[y], c) for x, y, c in caps]
    keep = {ren[n] for n in nmap}
    fcaps, nfl = pex.fold_floating(rcaps, keep)
    print(f"{len(fcaps)} capacitors after folding {nfl} floating nodes")
    adj = defaultdict(lambda: defaultdict(float))
    for x, y, c in fcaps:
        if x != y:
            adj[x][y] += c
            adj[y][x] += c
    lines = [f"* {a.name}: chip-level capacitances of {' '.join(a.nets)} in the window {a.box} um of "
             f"{os.path.relpath(a.gds, pex.REPO)} (pex_chipwin.py)"]
    k = 0
    done = set()
    for n in a.nets:
        tot = sum(adj[n].values())
        sup = sum(v for m, v in adj[n].items() if m in pex.SUPPLIES)
        print(f"{n}: total {tot * 1e15:.2f} fF, to supplies {sup * 1e15:.2f} fF")
        for m, v in sorted(adj[n].items(), key=lambda kv: -kv[1]):
            if v * 1e15 >= a.min:
                print(f"   {m}: {v * 1e15:.3f} fF")
            pair = tuple(sorted((n, m)))
            if pair not in done:
                done.add(pair)
                lines.append(f"CW{k} {n} {m} {v:.6e}")
                k += 1
    open(os.path.join(outdir, f"{a.name}_cw.spice"), "w").write("\n".join(lines) + "\n")
    print(f"wrote {os.path.join(outdir, a.name + '_cw.spice')}")


if __name__ == "__main__":
    main()

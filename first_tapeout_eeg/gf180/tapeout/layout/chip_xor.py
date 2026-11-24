#!/usr/bin/env python3
"""XOR of two chip GDS files, layer by layer, flat (tracker E7; requirement VER-08 for the 14th chip).

Every layer (and every text layer: label strings and positions) of the two top cells is flattened and compared. The
differences are split by a list of named regions (die um) inside which a difference is expected; whatever differs
outside all of them is reported shape by shape (bounding boxes) and makes the check fail.

usage: gf180/tools/venv310/bin/python chip_xor.py A.gds B.gds [--top chip_top] [--region NAME:x1,y1,x2,y2 ...]
       [--log FILE] [--raster x1,y1,x2,y2,pixel --json FILE]
Exit status 0 when nothing differs outside the regions.
"""
import argparse
import sys
import time

import klayout.db as kdb


def flat(ly, top, li):
    r = kdb.Region(top.begin_shapes_rec(li))
    r.merged_semantics = True
    return r


def texts(ly, top, li):
    out = set()
    it = top.begin_shapes_rec(li)
    while not it.at_end():
        sh = it.shape()
        if sh.is_text():
            t = sh.text.transformed(it.trans())
            out.add((t.string, t.x, t.y))
        it.next()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--top", default="chip_top")
    ap.add_argument("--region", action="append", default=[], help="NAME:x1,y1,x2,y2 (die um), repeatable")
    ap.add_argument("--log")
    ap.add_argument("--raster", help="x1,y1,x2,y2,pixel (um): also the differing area per pixel of every layer -> --json")
    ap.add_argument("--json", help="the per-layer results (and the raster) as JSON")
    args = ap.parse_args()
    out = open(args.log, "w") if args.log else None

    def say(*s):
        line = " ".join(str(x) for x in s)
        print(line)
        if out:
            out.write(line + "\n")
            out.flush()
    t0 = time.time()
    L = []
    for p in (args.a, args.b):
        ly = kdb.Layout()
        ly.read(p)
        L.append((ly, ly.cell(args.top)))
    dbu = L[0][0].dbu
    assert abs(L[1][0].dbu - dbu) < 1e-12
    regions = []
    for spec in args.region:
        name, box = spec.split(":", 1)
        x1, y1, x2, y2 = (float(v) for v in box.split(","))
        regions.append((name, kdb.Region(kdb.Box(round(x1 / dbu), round(y1 / dbu), round(x2 / dbu), round(y2 / dbu)))))
    say(f"A: {args.a}")
    say(f"B: {args.b}")
    for name, r in regions:
        b = r.bbox()
        say(f"region {name}: x {b.left * dbu:.3f}..{b.right * dbu:.3f} y {b.bottom * dbu:.3f}..{b.top * dbu:.3f}")
    allr = kdb.Region()
    for _, r in regions:
        allr += r
    allr.merge()
    infos = {}
    for ly, _ in L:
        for li in ly.layer_indexes():
            i = ly.get_info(li)
            infos[(i.layer, i.datatype)] = True
    bad = 0
    same = 0
    js = {"a": args.a, "b": args.b, "regions": {n: [v * dbu for v in (r.bbox().left, r.bbox().bottom, r.bbox().right,
                                                                        r.bbox().top)] for n, r in regions},
          "layers": {}}
    if args.raster:
        rx1, ry1, rx2, ry2, rp = (float(v) for v in args.raster.split(","))
        nx, ny = int(round((rx2 - rx1) / rp)), int(round((ry2 - ry1) / rp))
        js["raster"] = {"box": [rx1, ry1, rx2, ry2], "pixel": rp, "nx": nx, "ny": ny}
    for key in sorted(infos):
        lis = [ly.find_layer(*key) for ly, _ in L]
        ra = flat(L[0][0], L[0][1], lis[0]) if lis[0] is not None else kdb.Region()
        rb = flat(L[1][0], L[1][1], lis[1]) if lis[1] is not None else kdb.Region()
        ta = texts(L[0][0], L[0][1], lis[0]) if lis[0] is not None else set()
        tb = texts(L[1][0], L[1][1], lis[1]) if lis[1] is not None else set()
        x = ra ^ rb
        tdiff = ta ^ tb
        lk = f"{key[0]}/{key[1]}"
        js["layers"][lk] = {"a_shapes": ra.count(), "b_shapes": rb.count(), "diff_um2": x.area() * dbu * dbu,
                            "texts_differ": len(tdiff)}
        if x.is_empty() and not tdiff:
            same += 1
            continue
        if args.raster and not x.is_empty():
            # differing area (um2) per pixel, rows from the bottom; only nonzero pixels kept
            ras = x.rasterize(kdb.Point(round(rx1 / dbu), round(ry1 / dbu)),
                              kdb.Vector(round(rp / dbu), round(rp / dbu)), nx, ny)
            js["layers"][lk]["raster"] = [[i, j, ras[j][i] * dbu * dbu] for j in range(ny) for i in range(nx)
                                         if ras[j][i] > 0]
        parts = []
        for name, r in regions:
            xi = x & r
            if not xi.is_empty():
                parts.append(f"{name} {xi.count()} shapes {xi.area() * dbu * dbu:.3f} um2")
        xo = x - allr
        tout = [t for t in tdiff if not allr.interacting(kdb.Region(kdb.Box(t[1] - 1, t[2] - 1, t[1] + 1, t[2] + 1))).count()]
        say(f"{key[0]}/{key[1]}: A {ra.count()} / B {rb.count()} shapes; differs: " + ("; ".join(parts) or "-") +
            (f"; texts {len(tdiff)} ({len(tout)} outside the regions)" if tdiff else ""))
        js["layers"][lk]["outside_um2"] = xo.area() * dbu * dbu
        js["layers"][lk]["outside_boxes"] = [[p.bbox().left * dbu, p.bbox().bottom * dbu, p.bbox().right * dbu,
                                              p.bbox().top * dbu] for k, p in enumerate(xo.each()) if k < 50]
        if not xo.is_empty() or tout:
            bad += 1
            say(f"  OUTSIDE the regions: {xo.count()} shapes, {xo.area() * dbu * dbu:.3f} um2")
            for k, p in enumerate(xo.each()):
                if k >= 20:
                    say("  ...")
                    break
                b = p.bbox()
                say(f"    x {b.left * dbu:.3f}..{b.right * dbu:.3f} y {b.bottom * dbu:.3f}..{b.top * dbu:.3f}")
            for t in sorted(tout)[:20]:
                say(f"    text {t[0]} at ({t[1] * dbu:.3f}, {t[2] * dbu:.3f})")
    say(f"layers the same: {same}; layers that differ outside the regions: {bad} ({time.time() - t0:.0f} s)")
    if args.json:
        import json
        js["same"], js["differ_outside"] = same, bad
        with open(args.json, "w") as f:
            json.dump(js, f)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

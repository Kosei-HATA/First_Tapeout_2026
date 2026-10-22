#!/usr/bin/env python3
"""PNG of a GDS with the PDK layer colours (KLayout's LayoutView, no GUI).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/layout/render.py <gds> <png> [--width 1600]
       [--box x1 y1 x2 y2]   (um; default: the whole top cell)
"""
import argparse
import os
import klayout.lay as lay
import klayout.db as db

LYP = ("/Users/noah/Codings/ws_gf180/gf180mcu-project-template/gf180mcu/gf180mcuD/libs.tech/klayout/"
       "tech/gf180mcu.lyp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("png")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--box", type=float, nargs=4, default=None)
    a = ap.parse_args()
    v = lay.LayoutView()
    v.load_layout(a.gds, True)
    v.load_layer_props(LYP)
    v.max_hier()
    bb = db.DBox(*a.box) if a.box else v.cellview(0).cell.dbbox().enlarged(2.0, 2.0)
    h = max(100, int(a.width * bb.height() / max(bb.width(), 1e-9)))
    v.resize(a.width, h)
    v.zoom_box(bb)
    v.save_image(a.png, a.width, h)
    print(f"wrote {a.png} ({a.width} x {h})")


if __name__ == "__main__":
    main()

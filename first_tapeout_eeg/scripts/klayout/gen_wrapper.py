#!/usr/bin/env python3
"""Caravan wrapper integration for eeg_afe_top, sky130A.

    scripts/klayout/.venv/bin/python scripts/klayout/gen_wrapper.py

Reads the test6 wrapper GDS (caravel analog user_analog_project_wrapper,
2920x3520 um user area), strips the example project, instances the
verified eeg_afe_top macro MIRRORED about the vertical axis at (PX,PY)
(local (x,y) -> (PX-x, PY+y); the macro's west-side pins then face the
wrapper's east-edge GPIO stubs and the north analog pads), and routes
every macro pin to its pad/stub per caravel_pinmap.md.

Template surgery (all scripted + verified, no hand edits):
- the user_analog_proj_example instance is removed;
- the EXAMPLE's wiring nets are removed: io_out[11/12/15/16] and
  gpio_analog[3]/[7] thin L-wires, and the vssd1 distribution (full-width
  m3 bar y957..981 + east/west m4 verticals + the example's four io_oeb
  pulldown resistors) — the bar blocks any macro placement and only fed
  the example's pulldowns.  Nets are identified by union-find over the
  wrapper cell's own metal, seeded from label positions.
- KEPT (padframe/power): all pads and boundary stubs, the vdda1/vssa1/
  vccd1 power buses, the six north clamp resistors (vssa1<->io_clamp_*,
  io_analog[4]<->io_clamp_high[0]).

Deck conventions: only */5 texts are labels for the sky130.lvs deck — the
template's (70,16) pad labels are invisible, so every net I connect gets a
new (70,5)/(72,5) label.  The stock deck DOES extract res_generic_m3.

Routing: all long flights on m5 (2.0 wide, pitch >= 3.6); the macro uses
m5 itself — every route is checked against the macro's m5 inventory
(mirrored): OUTP/OUTN riser regions x 2526..2530 / 2526..2539 (y 977..
1374.25), VDD18 riser x 2472..2474 (y 959..2663), VCM_REF riser x
1617..1619, VSS riser x 1577..1579, RST run y 883..885 (x 1577..2524),
RST riser x 2522..2524 (y 847.4..885), north trunks y 2661..2675 (x
1502..2474).  Stub approaches (m4) cross m5 dives freely; m3 pads merge
the 0.56-wide GPIO stubs.

All coordinates in um.  See klayout_common.py / README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klayout_common import kdb, u

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WRAPPER_GDS = os.path.join(PROJECT, "source", "trials", "20260820", "test6",
                           "gds", "user_analog_project_wrapper.gds")
MACRO_GDS = os.path.join(PROJECT, "GDSII", "eeg_afe_top.gds")
OUT_GDS = os.path.join(PROJECT, "GDSII", "user_analog_project_wrapper.gds")

PX, PY = 2078.0, 890.0     # mirrored macro placement: (x,y) -> (PX-x, PY+y)

# text layers the LVS deck reads
M3L, M4L, M5L = (70, 5), (71, 5), (72, 5)
M3, M4, M5 = (70, 20), (71, 20), (72, 20)
VIA3, VIA4 = (70, 44), (71, 44)


class W:
    """Thin wrapper over the padframe layout: box/via/label on the top cell."""

    def __init__(self, ly, top):
        self.ly, self.top = ly, top

    def box(self, spec, x0, y0, x1, y1):
        self.top.shapes(self.ly.layer(*spec)).insert(
            kdb.Box(u(x0), u(y0), u(x1), u(y1)))

    def via(self, spec, x, y):
        s = 0.1 if spec == VIA3 else 0.4
        self.box(spec, x - s, y - s, x + s, y + s)

    def label(self, spec, text, x, y):
        self.top.shapes(self.ly.layer(*spec)).insert(kdb.Text(text, u(x), u(y)))

    def m4pad(self, x, y, w=1.24):
        self.box(M4, x - w / 2, y - w / 2, x + w / 2, y + w / 2)

    def m5pad(self, x, y, w=1.5):
        self.box(M5, x - w / 2, y - w / 2, x + w / 2, y + w / 2)

    def stack_m4(self, x, y, w4=1.24, w5=1.6):
        """m4 pad + via4 + m5 pad (lands an m5 route on m4 metal)."""
        self.m4pad(x, y, w4)
        self.via(VIA4, x, y)
        self.m5pad(x, y, w5)

    def stack_m3(self, x, y, w3=1.2):
        """m3 pad + via3 + m4 pad (lands an m4 route on an m3 stub)."""
        self.box(M3, x - w3 / 2, y - 0.5, x + w3 / 2, y + 0.5)
        self.via(VIA3, x, y)
        self.m4pad(x, y)

    def h5(self, y, x0, x1): self.box(M5, x0, y - 1.0, x1, y + 1.0)
    def v5(self, x, y0, y1): self.box(M5, x - 1.0, y0, x + 1.0, y1)
    def h4(self, y, x0, x1): self.box(M4, x0, y - 0.3, x1, y + 0.3)
    def v4m(self, x, y0, y1): self.box(M4, x - 0.3, y0, x + 0.3, y1)


# ----------------------------------------------------------------------------
# example-content removal
# ----------------------------------------------------------------------------
TRACE_LAYERS = [(68, 20), (68, 44), (69, 20), (69, 44), (70, 20), (70, 44),
                (71, 20), (71, 44), (72, 20)]
MARKER_LAYERS = [(70, 13), (70, 16), (71, 16), (72, 16)]  # ride along + deleted
TEXT_LAYERS = [(68, 5), (69, 5), (70, 5), (71, 5), (72, 5),
               (69, 16), (70, 16), (71, 16), (72, 16)]


def remove_nets(w, seed_points, what):
    """Delete every shape/text belonging to a net containing a seed point.

    Per-layer shapes are merged first (Region.merged handles same-layer
    area/edge touch), then union-find links layers through vias (sized(1)
    overlap -> edge touch counts).  Deletion matches live shapes against
    doomed merged polygons per layer; texts die if their point lands on a
    doomed polygon.  Prints what died."""
    top = w.top
    # merged polygons per traced layer
    polys = []          # (spec, polygon)
    for spec in TRACE_LAYERS + MARKER_LAYERS:
        li = w.ly.layer(*spec)
        r = kdb.Region(top.shapes(li)).merged()
        for p in r.each():
            polys.append((spec, p))
    parent = list(range(len(polys)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    from collections import defaultdict
    CELL = 100000
    grid = defaultdict(list)
    for i, (spec, p) in enumerate(polys):
        bb = p.bbox()
        for gx in range(bb.left // CELL, bb.right // CELL + 1):
            for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
                grid[(gx, gy)].append(i)
    CONSEC = [((68, 20), (68, 44)), ((68, 44), (69, 20)), ((69, 20), (69, 44)),
              ((69, 44), (70, 20)), ((70, 20), (70, 44)), ((70, 44), (71, 20)),
              ((71, 20), (71, 44)), ((71, 44), (72, 20))]
    for sa, sb in CONSEC:
        for i, (spec, p) in enumerate(polys):
            if spec != sa:
                continue
            bb = p.bbox()
            seen = set()
            for gx in range(bb.left // CELL, bb.right // CELL + 1):
                for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
                    for j in grid.get((gx, gy), ()):
                        if j in seen or polys[j][0] != sb:
                            continue
                        seen.add(j)
                        if not (kdb.Region(polys[i][1]).sized(1) &
                                kdb.Region(polys[j][1]).sized(1)).is_empty():
                            union(i, j)
    # markers/label-boxes ride along with the metal they overlap
    for i, (spec, p) in enumerate(polys):
        if spec not in MARKER_LAYERS:
            continue
        bb = p.bbox()
        for gx in range(bb.left // CELL, bb.right // CELL + 1):
            for gy in range(bb.bottom // CELL, bb.top // CELL + 1):
                for j in grid.get((gx, gy), ()):
                    if polys[j][0] in MARKER_LAYERS:
                        continue
                    if not (kdb.Region(polys[i][1]).sized(1) &
                            kdb.Region(polys[j][1]).sized(1)).is_empty():
                        union(i, j)
    doomed = set()
    for x, y in seed_points:
        pt = kdb.Point(u(x), u(y))
        for i, (spec, p) in enumerate(polys):
            if spec in MARKER_LAYERS:
                continue
            if p.bbox().contains(pt) and p.inside(pt):
                doomed.add(find(i))
    doomed_regions = defaultdict(list)
    for i, (spec, p) in enumerate(polys):
        if find(i) in doomed:
            doomed_regions[spec].append(p)
    # texts on doomed nets
    lost = []
    for spec in TEXT_LAYERS:
        li = w.ly.layer(*spec)
        for s in list(top.shapes(li).each()):
            b = s.bbox()
            if s.is_text():
                pt = kdb.Point((b.left + b.right) // 2, (b.bottom + b.top) // 2)
                hit = any(p.inside(pt) for p in doomed_regions.get(
                    (70, 20), []) + doomed_regions.get((71, 20), []) +
                    doomed_regions.get((72, 20), []) +
                    doomed_regions.get((69, 20), []) +
                    doomed_regions.get((68, 20), []))
            else:
                hit = False
                for pspec, p in doomed_regions.items():
                    if pspec[0] == spec[0] and not (
                            kdb.Region(p).sized(1) &
                            kdb.Region(kdb.Box(b)).sized(1)).is_empty():
                        hit = True
                        break
            if hit:
                lost.append(s.text_string if s.is_text() else f"<rect {spec}>")
                s.delete()
    # delete doomed shapes: any live shape intersecting a doomed merged
    # polygon of the same layer goes (merged polygons fully contain their
    # contributors, so this is exact)
    n = 0
    for spec in TRACE_LAYERS + MARKER_LAYERS:
        if spec not in doomed_regions:
            continue
        doomed_r = kdb.Region()
        for p in doomed_regions[spec]:
            doomed_r.insert(p)
        li = w.ly.layer(*spec)
        for s in list(top.shapes(li).each()):
            if s.is_text():
                continue
            if not (doomed_r & kdb.Region(kdb.Box(s.bbox())).sized(1)
                    ).is_empty():
                s.delete()
                n += 1
    print(f"remove[{what}]: {n} shapes, texts/rects: {sorted(set(lost))}")


def main():
    ly = kdb.Layout()
    ly.read(WRAPPER_GDS)
    top = ly.cell("user_analog_project_wrapper")
    w = W(ly, top)

    # ---- strip the example project ---------------------------------------
    for inst in list(top.each_inst()):
        print("removing instance:", ly.cell(inst.cell_index).name,
              "at", inst.trans)
        inst.delete()

    # ---- remove the example's wiring nets + its vssd1 distribution --------
    remove_nets(w, [(1000.0, 969.0)], "vssd1 m3 bar")
    remove_nets(w, [(75.0, 2312.2)], "vssd1 west vertical + west oeb pulldowns")
    remove_nets(w, [(2875.0, 1500.0)], "vssd1 east vertical + east oeb pulldowns")
    remove_nets(w, [(1709.0, 2102.1)], "io_out[16] wire")
    remove_nets(w, [(1705.1, 2318.2)], "io_out[15] wire")
    remove_nets(w, [(1700.1, 2558.0)], "gpio_analog[7] wire")
    remove_nets(w, [(2667.75, 2026.75)], "gpio_analog[3] wire")
    remove_nets(w, [(2687.15, 2272.5)], "io_out[11] wire")
    remove_nets(w, [(2697.75, 2494.6)], "io_out[12] wire")

    # ---- restore the template's boundary stubs removed with the example ---
    # The mpw_precheck XOR check compares the BOUNDARY BAND (x<0 / x>2920)
    # against the golden template: every net the surgery removed must keep
    # its pad-boundary stub there.  Restored as plain m3 — boundary segments
    # only (the example's long L-wires crossing the macro would merge with
    # macro m3), no labels, so the LVS deck never sees them.
    for x0, y0, x1, y1 in (
            (2920.0, 957.15, 2924.0, 981.15),      # vssd1 bar boundary segment
            (2920.0, 2026.48, 2924.0, 2027.04),    # io_out[16] stub (E)
            (2920.0, 2272.23, 2924.0, 2272.79),    # io_out[12] stub (E)
            (2920.0, 2278.14, 2924.0, 2278.70),    # io_out[11] stub (E)
            (2920.0, 2494.34, 2924.0, 2494.90),    # gpio_analog[3] stub (E)
            (2920.0, 2500.25, 2924.0, 2500.81),    # io_oeb[12] stub (E)
            (-4.0, 2095.88, 88.47, 2096.44),       # gpio_analog[3] west strip
            (-4.0, 2101.79, 2.4, 2102.35),         # io_out[16] west stub
            (-4.0, 2311.99, 88.56, 2312.55),       # gpio_analog west strip
            (-4.0, 2317.90, 2.4, 2318.46),         # io_out[15] west stub
            (-4.0, 2557.65, 2.4, 2558.21)):        # gpio_analog[7] west stub
        w.box(M3, x0, y0, x1, y1)

    # ---- place the macro (mirrored about the vertical axis) ---------------
    opt = kdb.LoadLayoutOptions()
    opt.cell_conflict_resolution = kdb.LoadLayoutOptions.SkipNewCell
    ly.read(MACRO_GDS, opt)
    macro = ly.cell("eeg_afe_top")
    top.insert(kdb.CellInstArray(macro.cell_index(),
                                 kdb.Trans(2, True, u(PX), u(PY))))
    print(f"macro placed mirrored at ({PX},{PY}); abs bbox "
          f"x {PX-1078.3:.1f}..{PX+764.2:.1f}, y {PY-790.2:.1f}..{PY+1784.95:.1f}")

    # =======================================================================
    # power: macro m5 trunks (mirrored) -> the template's vdda1/vssa1 buses
    # =======================================================================
    # VDD18 trunk abs x 1627..2474, y 2660.95..2662.95: extend east to 2489
    # (staying 3 um west of VN's north run at 2492..2494), then north at
    # x=2488 to the vdda1 m4 bus's full-width part (x 1813..2813, y
    # 2976..3008.8) — stack there (the y2700..2976 part only reaches x
    # 2780..2813!).
    w.box(M5, 2474.0, 2660.95, 2489.0, 2662.95)  # trunk extension
    w.v5(2488.0, 2662.0, 2992.0)
    w.m5pad(2488.0, 2992.0, 2.0)
    w.box(M4, 2486.0, 2990.0, 2490.0, 2994.0)   # 4x4 pad on the vdda1 bus
    w.via(VIA4, 2488.0, 2992.0)
    # VSS trunk abs x 1502..1579, y 2672.95..2674.95 -> vssa1 m4 bus
    w.v5(1540.0, 2673.0, 3437.0)
    w.m5pad(1540.0, 3437.0, 2.0)
    w.box(M4, 1538.0, 3435.0, 1542.0, 3439.0)   # 4x4 pad on the vssa1 bus
    w.via(VIA4, 1540.0, 3437.0)

    # =======================================================================
    # analog pads (all m5 north runs; stacks down to the pads' m3)
    # =======================================================================
    def stack_pad(x, y):
        """m5 -> m4 -> m3 stack onto an analog pad's m3."""
        w.m4pad(x, y, 1.5)
        w.via(VIA4, x, y)
        w.via(VIA3, x, y)

    # VCM_REF trunk abs x 1607..1619, y 2666.95..2668.95 -> io_analog[2].
    # m5 north at x=1613, via4 down, m4 east at y=3501 (south of the pad row,
    # clear of VP's m5 west jog at y3490 and pad[4]'s m4), m4 north at
    # x=2339.5 into the pad row, via3 onto pad [2]'s m3.
    w.v5(1613.0, 2668.0, 3501.71)
    w.m4pad(1613.0, 3501.0, 1.5)
    w.via(VIA4, 1613.0, 3501.0)
    w.h4(3501.0, 1612.9, 2339.8)
    w.v4m(2339.5, 3501.0, 3518.5)
    w.via(VIA3, 2339.5, 3518.0)
    # VP pin (2518,1608.25) -> io_analog[3]: m5 north at x=2518, west at
    # y3490, north at x=2085 into the pad row, stack onto pad [3].  Run
    # starts at the pin pad's bottom edge and the jog ends at the run's
    # east edge (no sub-1.6 nubs at the junctions).
    w.stack_m4(2518.0, 1608.25)
    w.v5(2518.0, 1607.45, 3490.0)
    w.h5(3490.0, 2084.0, 2519.0)
    w.v5(2085.0, 3490.0, 3514.9)
    w.m5pad(2085.0, 3514.15, 1.5)
    w.m4pad(2085.0, 3514.15, 1.5)
    w.via(VIA4, 2085.0, 3514.15)
    w.via(VIA3, 2085.0, 3514.15)
    # VN pin (2493,1608.25) -> io_analog[4]: north at x=2493 (3 um east of
    # the VDD18 run at x2487..2489, west of VP's run at x2517..2519), west
    # at y3484 (below VP's y3489..3491 west jog), dive at x=1790 into
    # io_analog[4]'s m5 stubs (x1759.6..1796.8, y3065.4..3250).
    w.stack_m4(2493.0, 1608.25)
    w.v5(2493.0, 1607.45, 3484.0)
    w.h5(3484.0, 1789.0, 2494.0)
    w.v5(1790.0, 3070.0, 3484.0)
    # ELP pin (2840,931) -> io_analog[0] (NE corner pad).  Jogs start/end at
    # the run/pad edges; the final jog extends 0.71 past the stack's via4.
    w.stack_m4(2840.0, 931.0)
    w.h5(931.0, 2833.0, 2840.8)
    w.v5(2834.0, 931.0, 3402.4)
    w.h5(3402.4, 2833.0, 2918.71)
    stack_pad(2918.0, 3402.4)
    # ELN pin (2840,811) -> io_analog[1]
    w.stack_m4(2840.0, 811.0)
    w.h5(811.0, 2827.0, 2840.8)
    w.v5(2828.0, 811.0, 3517.75)
    w.h5(3517.75, 2827.0, 2846.21)
    stack_pad(2845.5, 3517.75)

    # m4 eastbound to the east-edge stub at (2918, ystub): direct below the
    # wall (y<1293) or when the channel starts EAST of it, else the proven
    # 3-layer crossing at x=2700/2790.
    def east_stub(xc, ystub):
        w.m4pad(xc, ystub)
        w.via(VIA4, xc, ystub)
        if ystub > 1293.0 and xc < 2700.0:
            w.h4(ystub, xc, 2700.62)
            w.m4pad(2700.0, ystub)
            w.via(VIA4, 2700.0, ystub)
            w.m5pad(2700.0, ystub, 1.42)
            w.h5(ystub, 2699.0, 2791.0)
            w.m4pad(2790.0, ystub)
            w.via(VIA4, 2790.0, ystub)
            w.m5pad(2790.0, ystub, 1.42)
            w.h4(ystub, 2789.38, 2918.3)
        else:
            w.h4(ystub, xc, 2918.3)
        w.stack_m3(2918.0, ystub)

    # =======================================================================
    # digital: PHI set 1 (input chopper), io_in[5..8]
    # =======================================================================
    # the 4 m4 lanes (y 906.7..910.3, pitch 1.0) end at x=2479: extend each
    # east to its jog x, then fan out to y 911/915/919/923 via staggered
    # jogs (no jog crosses a lane extension or fan-out run), then via4
    # stacks.  in0's stack can NOT sit on its lane (a macro m4 wire topping
    # at y906.3 leaves only 0.11 to the pad, and in1's extension is 0.11
    # above it): in0 extends furthest east (2516.3) and jogs up at x=2516,
    # east of in3's h4 end (2514.59); that column is m4-free (nearest macro
    # m4: x2517.7 at y<=905.3, x2539.7 at y<=916.9).
    w.box(M4, 2479.0, 908.7, 2497.3, 909.3)    # in1 (NPHII) -> jog
    w.box(M4, 2479.0, 909.7, 2491.3, 910.3)    # in2 (PHIBI) -> jog
    w.box(M4, 2479.0, 910.7, 2485.3, 911.3)    # in3 (NPHIBI) -> jog
    w.box(M4, 2479.0, 907.7, 2516.3, 908.3)    # in0 (PHII) -> jog at x=2516
    # (macro clock lanes moved +1 um for the chopper PHI/INN coupling fix)
    w.v4m(2485.0, 911.0, 919.0)                # in3 jogs first; jogs rise over
    w.v4m(2491.0, 910.0, 915.0)                # nothing (all lanes stay below)
    w.v4m(2497.0, 909.0, 911.0)
    w.v4m(2516.0, 908.0, 923.0)
    w.h4(919.0, 2485.0, 2514.59)
    w.h4(915.0, 2491.0, 2508.59)
    w.h4(911.0, 2497.0, 2502.59)
    for x, y in ((2502.0, 911.0), (2508.0, 915.0), (2514.0, 919.0),
                 (2516.0, 923.0)):
        w.m4pad(x, y, 1.18)
        w.via(VIA4, x, y)
        w.m5pad(x, y, 1.42)
    # NPHII (flight 911) dives south to io_in[6] (y464.05): flight ends at
    # the dive.  PHII (flight 923) dives to io_in[5] (y240.76) at x=2605 —
    # east of every flight end (see the up-channel notes below), reaching it
    # via an m4 mini-hop under the two up-channels.
    w.h5(911.0, 2501.29, 2530.0)               # NPHII flight east
    w.v5(2530.0, 463.34, 912.0)                # dive (bottom encloses the via4)
    east_stub(2530.0, 464.05)
    # PHIBI (915) -> io_in[7] (1364.16) and NPHIBI (919) -> io_in[8]
    # (1586.27): channels north in the PHI-2 channel band (x2596.8/2600.5,
    # east of all PHI-2 flight ends).  Order matters: NPHIBI's channel
    # (bottom 918.5) sits WEST of PHIBI's (bottom 914.5) — NPHIBI's flight
    # (918..920) ends before PHIBI's channel, and PHIBI's flight (914..916)
    # passes under NPHIBI's channel bottom — no crossings.
    w.h5(919.0, 2513.29, 2597.8)               # NPHIBI flight east
    w.v5(2596.8, 918.5, 1586.98)               # channel north to io_in[8]
    east_stub(2596.8, 1586.27)
    w.h5(915.0, 2507.29, 2601.5)               # PHIBI flight east
    w.v5(2600.5, 914.5, 1364.87)               # channel north to io_in[7]
    east_stub(2600.5, 1364.16)
    # PHII (923) -> io_in[5] (240.76): flight east to 2593.3, m4 mini-hop
    # under both up-channels, continue to the dive at x=2605, dive south.
    # (the mini-hop stack carries an m5pad: a bare via4 at the flight end
    # would be half-uncovered.)
    w.h5(923.0, 2515.29, 2594.01)
    w.m4pad(2593.3, 923.0)
    w.via(VIA4, 2593.3, 923.0)
    w.m5pad(2593.3, 923.0, 1.42)
    w.h4(923.0, 2592.68, 2604.52)
    w.m4pad(2603.9, 923.0)
    w.via(VIA4, 2603.9, 923.0)
    w.m5pad(2603.9, 923.0, 1.42)
    w.h5(923.0, 2603.19, 2606.0)
    w.v5(2605.0, 240.05, 924.0)                # dive (bottom encloses the via4)
    east_stub(2605.0, 240.76)

    # =======================================================================
    # digital: PHI set 2 (output chopper), io_in[9..12]
    # =======================================================================
    # The 4 m4 lanes (y 969.7..973.3, pitch 1.0) span x 1711.41..2479.  East
    # of the lane ends is the PGA's mirrored m4 thicket (interdigitated macro
    # nets spanning y 946.7..964.62 up to x2506.3 and y ..978.59 up to
    # x2543.3).  Verified-free m4 space: in4's corridor (x 2509.4..2510.6)
    # and the band at/above lane height from x2479 to ~2537 (the thicket's
    # fingers stop at y964.62; the next macro m4 starts at y979.41).
    # in4 keeps the proven south jog to y942.  in5/6/7 jog down from their
    # lane ends at staggered x (east of in4's corridor, so no jog crosses a
    # lane extension) to via4 stacks AT flight level, then fly east on m5.
    # Flight levels 966.6/970.4/974.3 keep >=1.6 m5 spacing between
    # neighbours and stay below the OUTP/OUTN m5 risers (y>=977).
    w.box(M4, 2479.0, 969.7, 2510.3, 970.3)    # in4 (PHIM) extension
    w.box(M4, 2479.0, 970.7, 2511.7, 971.3)    # in5 (NPHIM)
    w.box(M4, 2479.0, 971.7, 2514.9, 972.3)    # in6 (PHIBM)
    w.box(M4, 2479.0, 972.7, 2518.1, 973.3)    # in7 (NPHIBM)
    w.v4m(2510.0, 942.0, 970.0)                # in4 jog down (proven corridor)
    w.v4m(2511.4, 966.6, 971.0)                # in5 jog down to flight level
    w.v4m(2514.6, 970.4, 972.0)                # in6
    w.v4m(2517.8, 973.0, 974.3)                # in7 (highest lane, shortest jog)
    for x, y in ((2510.0, 942.0), (2511.4, 966.6), (2514.6, 970.4),
                 (2517.8, 974.3)):
        w.m4pad(x, y, 1.18)
        w.via(VIA4, x, y)
        w.m5pad(x, y, 1.42)
    # All four stubs (io_in[9..12], y1812.38..2488.71) are ABOVE the flights:
    # channels north in the band x2581..2594.1 (east of every PHI-2 flight
    # end, west of the shifted S runs at 2611+).  Channels run west->east
    # with DESCENDING flight height: an up-channel may not rise through a
    # higher flight's level inside that flight's x-span, so the highest
    # flight (NPHIBM) gets the westmost channel.  Each flight ends at its
    # channel; bottoms overlap the flight by 0.5, tops enclose the via4.
    for (xs, ys, xc, ystub) in ((2517.8, 974.3, 2582.0, 2488.71),
                                (2514.6, 970.4, 2585.7, 2266.6),
                                (2511.4, 966.6, 2589.4, 2044.49),
                                (2510.0, 942.0, 2593.1, 1812.38)):
        w.h5(ys, xs - 0.71, xc + 1.0)          # flight east (from the stack pad)
        w.v5(xc, ys - 0.5, ystub + 0.71)       # channel north
        east_stub(xc, ystub)

    # =======================================================================
    # digital: CLK16 -> io_in[13]; NCLK16 -> io_in[14] via the west highway
    # =======================================================================
    # pins: macro m4 pads at (2770,2512.15)/(2766.8,2510.05).  The two pin
    # stacks are only 1.43 um apart corner-to-corner, so CLK16 first hops
    # NORTH to y2514 (its flight bottom then clears NCLK16's jog top by
    # >=1.6 euclidean) and NCLK16's south jog is narrowed so its east edge
    # aligns with its pad's east edge (2767.6).  The ELP/ELN m5 north runs
    # (x2827..2829 / x2833..2835, y811..3517.75) wall off a straight m5
    # flight — hop down to m4 at x=2820, cross under them, back up at
    # x=2845.  CLK16 then continues NORTH to io_in[13] (y2935.82).
    w.stack_m4(2770.0, 2512.15)
    w.stack_m4(2766.8, 2510.05)
    w.v5(2770.0, 2512.15, 2514.0)              # CLK16 hop north (m5.2 corner)
    w.h5(2514.0, 2769.0, 2821.0)
    w.m4pad(2820.0, 2514.0)
    w.via(VIA4, 2820.0, 2514.0)
    w.m5pad(2820.0, 2514.0, 1.42)
    w.h4(2514.0, 2819.38, 2845.62)
    w.m4pad(2845.0, 2514.0)
    w.via(VIA4, 2845.0, 2514.0)
    w.m5pad(2845.0, 2514.0, 1.42)
    w.h5(2514.0, 2844.29, 2897.0)
    w.v5(2896.0, 2515.0, 2936.53)              # run north to io_in[13]
    east_stub(2896.0, 2935.82)
    # NCLK16 jog (narrowed: east edge = pad east edge, westward extension so
    # the north run at x2764 clears CLK16's hop at x2769..2771 by 4 um),
    # then north to the west highway lane y2698.
    w.box(M5, 2763.5, 2506.0, 2767.6, 2510.85)
    w.v5(2764.0, 2506.0, 2698.71)              # run north (top encloses via4)

    # =======================================================================
    # digital: S8/S16/S32/S64 -> io_in[15..18] via the west highway
    # =======================================================================
    # pin m4 pads at (2638,852)/(2634,850.8)/(2630,849.6)/(2647.5,840).
    # m5 verticals down from each pin, west jogs (heights DESCENDING with
    # pin x so no jog crosses a vertical), north runs at x 2630/2624/2618/
    # 2612 (shifted +16 east vs the old runs to clear the PHI channel band),
    # then up to the west-highway lanes (y2694.4/2690.8/2687.2/2683.6).
    w.stack_m4(2638.0, 852.0)                  # S8
    w.stack_m4(2634.0, 850.8)                  # S16
    w.stack_m4(2630.0, 849.6)                  # S32
    w.stack_m4(2647.5, 840.0)                  # S64
    w.v5(2630.0, 710.8, 850.4)                 # run tops align with the 1.6
    w.v5(2634.0, 707.2, 851.6)                 # pin-stack m5 pads (no nubs)
    w.v5(2638.0, 703.6, 852.8)
    w.v5(2647.5, 700.0, 840.8)
    w.h5(710.8, 2629.0, 2631.0)                # S32 jog -> run x2630
    w.h5(707.2, 2623.0, 2635.0)                # S16 -> x2624
    w.h5(703.6, 2617.0, 2639.0)                # S8  -> x2618
    w.h5(700.0, 2611.0, 2648.5)                # S64 -> x2612
    w.v5(2630.0, 710.8, 2695.11)               # S32 north run -> lane y2694.4
    w.v5(2624.0, 707.2, 2691.51)               # S16 -> y2690.8
    w.v5(2618.0, 703.6, 2687.91)               # S8  -> y2687.2
    w.v5(2612.0, 700.0, 2684.31)               # S64 -> y2683.6

    # =======================================================================
    # digital: BIT/NBIT -> io_out[19]/[20] via the west highway
    # =======================================================================
    # BIT pin (2503,1620.65): north run (dodges the VP/VN/VDD18/RST runs and
    # the OUT risers) to lane y2680.  NBIT pin (2653,2384.79): north run to
    # lane y2676.4.
    w.stack_m4(2503.0, 1620.65)
    w.v5(2503.0, 1619.85, 2680.71)
    w.stack_m4(2653.0, 2384.79)
    w.v5(2653.0, 2385.59, 2677.11)

    # =======================================================================
    # west highway: 7 m4 lanes at y2676.4..2698 (pitch 3.6) under the vdda1
    # m4 riser (which starts at y2700.78), m5 dives at staggered x to the
    # west-edge stubs (m3, x-4..2.4), m4 to the stub, stack_m3 at (1.8,y).
    # =======================================================================
    for (xr, ylane, xd, ystub, name) in (
            (2764.0, 2698.0, 4.0, 2540.20, "io_in[14]"),    # NCLK16
            (2618.0, 2687.2, 16.0, 2324.09, "io_in[15]"),   # S8
            (2624.0, 2690.8, 12.0, 2107.98, "io_in[16]"),   # S16
            (2630.0, 2694.4, 8.0, 1891.87, "io_in[17]"),    # S32
            (2612.0, 2683.6, 20.0, 1675.76, "io_in[18]"),   # S64
            (2503.0, 2680.0, 24.0, 1453.74, "io_out[19]"),  # BIT
            (2653.0, 2676.4, 28.0, 1238.63, "io_out[20]")): # NBIT
        w.m4pad(xr, ylane)                      # stack down to the lane
        w.via(VIA4, xr, ylane)
        w.h4(ylane, xd - 0.62, xr + 0.62)       # the lane itself
        w.m4pad(xd, ylane)                      # stack up for the dive
        w.via(VIA4, xd, ylane)
        w.m5pad(xd, ylane, 1.42)
        w.v5(xd, ystub - 0.71, ylane + 0.71)    # dive (bottom encloses the via4)
        w.m4pad(xd, ystub)
        w.via(VIA4, xd, ystub)
        w.h4(ystub, 1.8, xd + 0.62)             # m4 west to the stub
        w.stack_m3(1.8, ystub)
        w.label(M3L, name, 2.0, ystub)

    # =======================================================================
    # labels (deck reads */5 texts only!)
    # =======================================================================
    for text, x, y in (("io_analog[0]", 2918.0, 3402.4),
                       ("io_analog[1]", 2845.5, 3517.75),
                       ("io_analog[2]", 2339.5, 3517.75),
                       ("io_analog[3]", 2079.5, 3517.75)):
        w.label(M3L, text, x, y)
    w.label(M5L, "io_analog[4]", 1790.0, 3070.0)
    for name, y in (("io_in[5]", 240.76), ("io_in[6]", 464.05),
                    ("io_in[7]", 1364.16), ("io_in[8]", 1586.27),
                    ("io_in[9]", 1812.38), ("io_in[10]", 2044.49),
                    ("io_in[11]", 2266.6), ("io_in[12]", 2488.71),
                    ("io_in[13]", 2935.82)):
        w.label(M3L, name, 2918.5, y)
    # clamp nets (the six template resistors ride on these)
    for name, x, y in (("io_clamp_low[0]", 1627.0, 3515.0),
                       ("io_clamp_high[0]", 1639.5, 3515.0),
                       ("io_clamp_low[1]", 1118.5, 3510.0),
                       ("io_clamp_high[1]", 1131.0, 3510.0),
                       ("io_clamp_low[2]", 860.0, 3510.0),
                       ("io_clamp_high[2]", 872.5, 3510.0)):
        w.label(M3L, name, x, y)

    # prune cells not reachable from the wrapper (the stripped example cell
    # would otherwise remain as a second top cell, which the DRC/LVS decks
    # reject)
    reachable = set()

    def walk(cell):
        if cell.cell_index() in reachable:
            return
        reachable.add(cell.cell_index())
        for inst in cell.each_inst():
            walk(ly.cell(inst.cell_index))

    walk(top)
    for cell in list(ly.each_cell()):
        if cell.cell_index() not in reachable:
            print("pruning orphan cell:", cell.name)
            ly.delete_cell(cell.cell_index())

    ly.write(OUT_GDS)
    print("wrote", OUT_GDS)


if __name__ == "__main__":
    main()

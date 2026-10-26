#!/usr/bin/env python3
"""GF180 Half Height (wafer.space 1x0.5) floorplan, 2026-10-22.

Die/core from the wafer.space template (librelane/slots/slot_1x0p5.yaml):
DIE 3932 x 2531 um, CORE [442, 442, 3490, 2089] = 3048 x 1647 um.

Pads: the decided assignment (2026-10-22; AVDD/AVSS x3, ELP/ELN x2).
Positions are from the padring run /Users/noah/Codings/ws_gf180/eeg_padring/
librelane/runs/RUN_2026-10-22_14-47-04 (pad_coordinates.csv there). LibreLane places each
PAD_* list in increasing coordinate order: west/east from south to north,
south/north from west to east. Pad cells are 75 x 350 um at 26 um from the
die edge; pad pitch is 141 um on west/east and 129 um on south/north.
The wafer.space ID/marker/logo cells sit in the corner-cell areas, outside
the core, so the core has no reserve for them.

Block areas (low/high, mm2) come from documentation/gf180_area_estimate_20261021.md
(DAC2 as a MOS current-steering DAC with stage 2 scaled x10, 2026-10-22). The script
checks containment/overlap of blocks, pads and the corner cells, prints the placement
table and writes documentation/figures/gf180/plan_20261022/gf180_floorplan_20261022.svg.

Run: python3 gf180/floorplan_half_height.py
"""
import os

DIE_W, DIE_H = 3932.0, 2531.0
CX, CY = 442.0, 442.0  # core origin in die coordinates
CORE_W, CORE_H = 3048.0, 1647.0
RING = 40.0  # core power ring + spacing kept free on every side
YC = CORE_H / 2  # differential mirror axis (core-local)

# Pad ring geometry (die coordinates, um), measured in RUN_2026-10-22_14-47-04
PAD_EDGE = 26.0      # pad cells start 26 um from the die edge
PAD_DEPTH = 350.0    # pad cell depth (towards the core)
PAD_W = 75.0         # pad cell width along the edge
CORNER = 355.0       # corner cell size
WE_FIRST, WE_PITCH = 490.0, 141.0   # west/east pad centre y: bottom pad, pitch
SN_FIRST, SN_PITCH = 482.5, 129.0   # south/north pad centre x: west pad, pitch
BOND_OFFSET = 32.0   # bond pad centre from the outer edge of the pad cell

# (name, kind, [x0, y0, x1, y1] core-local um, need low/high mm2 or None)
BLOCKS = [
    ("AFE", "afe", [40, 100, 1040, 1547], (1.187, 1.691)),
    ("Ch-A: bias/VCM/ref, chop drivers", "svc", [1040, 100, 1190, 1547], (0.055, 0.170)),
    ("ADC", "adc", [1190, 100, 2490, 1547], (1.385, 1.966)),
    ("Isolation (guard rings)", "iso", [2490, 40, 2560, 1547], None),
    ("Digital", "dig", [2560, 787, 3008, 1547], (0.250, 0.400)),
    ("Spare", "spare", [2560, 40, 3008, 787], None),
    ("S-ch: bias", "chan", [40, 40, 2490, 100], None),
    # north channel split (decided 2026-10-22): west part carries VREFP/VREFN/VCM
    # from the north-west pads to the top of Ch-A, east part clocks/controls
    ("N-ch W: refs VREFP/VREFN/VCM (shielded)", "chan", [40, 1547, 1190, 1607], None),
    ("N-ch E: clocks/controls (shielded)", "chan", [1190, 1547, 3008, 1607], None),
]
# suggested internal arrangement (drawn only, mirrored about YC)
SUB = [
    ("in-TG + DC servo", [40, 100, 140, 1547]),
    ("Cin_P 636p", [140, 1130, 1040, 1547]),
    ("AFE core MOS, Cf/Cpf/CC", [140, 517, 1040, 1130]),
    ("Cin_N 636p", [140, 100, 1040, 517]),
    ("C1_P 680p", [1190, 1212, 2490, 1547]),
    ("RIN/DAC1 | OTA1 | DAC2+C2 | OTA2 | quantizer | DWA/drivers",
     [1190, 435, 2490, 1212]),
    ("C1_N 680p", [1190, 100, 2490, 435]),
]

# wafer.space ID/marker/logo cells (die coordinates, from the padring run);
# all lie inside the corner-cell areas
MARKS = [
    ("qrcode_id", "SW", [26.0, 26.0, 168.8, 168.8]),
    ("project_id", "SW", [175.6, 26.0, 371.1, 85.5]),
    ("shuttle_id", "SW", [26.0, 175.6, 85.5, 371.1]),
    ("marker", "NE", [3651.0, 2250.0, 3896.0, 2495.0]),
    ("logo", "NW", [26.0, 2361.75, 169.25, 2505.0]),
]
CORNERS = {
    "SW": [PAD_EDGE, PAD_EDGE, PAD_EDGE + CORNER, PAD_EDGE + CORNER],
    "SE": [DIE_W - PAD_EDGE - CORNER, PAD_EDGE, DIE_W - PAD_EDGE, PAD_EDGE + CORNER],
    "NW": [PAD_EDGE, DIE_H - PAD_EDGE - CORNER, PAD_EDGE + CORNER, DIE_H - PAD_EDGE],
    "NE": [DIE_W - PAD_EDGE - CORNER, DIE_H - PAD_EDGE - CORNER, DIE_W - PAD_EDGE,
           DIE_H - PAD_EDGE],
}

# Pads per edge in slot_1x0p5.yaml order = increasing coordinate
# (west/east: bottom to top; south/north: west to east). Decided 2026-10-22.
WEST = [("vss_pads[0]", "pwr", "VSS"), ("vdd_pads[0]", "pwr", "VDD"),
        ("analog[7]", "ana", "AVDD"), ("analog[6]", "ana", "AVSS"),
        ("analog[5]", "ana", "ELN"), ("analog[4]", "ana", "ELN"),
        ("analog[3]", "ana", "ELP"), ("analog[2]", "ana", "ELP"),
        ("analog[1]", "ana", "AVSS"), ("analog[0]", "ana", "AVDD"),
        ("dvss_pads[6]", "pwr", "DVSS"), ("dvdd_pads[6]", "pwr", "DVDD")]
EAST = ([("dvss_pads[2]", "pwr", "DVSS"), ("dvdd_pads[2]", "pwr", "DVDD")]
        + [(f"bidir[{i}]", "dio", s) for i, s in zip(
            range(18, 26), ["MCLK", "RESET_N", "SCLK", "CS_N", "MOSI", "MISO",
                            "DRDY_N", "RAW_DATA"])]
        + [("dvss_pads[3]", "pwr", "DVSS"), ("dvdd_pads[3]", "pwr", "DVDD")])
SOUTH = ([("clk_pad", "in", ""), ("rst_n_pad", "in", "")]
         + [(f"bidir[{i}]", "io", "") for i in (0, 1)]
         + [("dvss_pads[0]", "pwr", "DVSS"), ("dvdd_pads[0]", "pwr", "DVDD")]
         + [(f"bidir[{i}]", "io", "") for i in range(2, 14)]
         + [("dvss_pads[1]", "pwr", "DVSS"), ("dvdd_pads[1]", "pwr", "DVDD")]
         + [(f"bidir[{i}]", "io", "") for i in range(14, 18)])
NORTH = ([("analog[8]", "ana", "ATP"), ("analog[9]", "ana", "VCM"),
          ("analog[10]", "ana", "VREFP"), ("analog[11]", "ana", "VREFN")]
         + [("dvss_pads[5]", "pwr", "DVSS"), ("dvdd_pads[5]", "pwr", "DVDD")]
         + [("analog[12]", "ana", "AVDD"), ("analog[13]", "ana", "AVSS")]
         + [(f"bidir[{i}]", "io", "") for i in range(39, 29, -1)]
         + [("dvss_pads[4]", "pwr", "DVSS"), ("dvdd_pads[4]", "pwr", "DVDD")]
         + [(f"bidir[{i}]", "io", "") for i in range(29, 26, -1)]
         + [("bidir[26]", "dio", "RAW_CLK")])

COLORS = {"afe": "#cfe8cf", "svc": "#fff2b3", "adc": "#e3d7f2", "iso": "#d9d9d9",
          "dig": "#cfe0f5", "spare": "#ffffff", "mark": "#f6d5e0", "chan": "#eeeeee",
          "ana": "#f28e2b", "in": "#9ecae1", "io": "#bdbdbd", "dio": "#4e79a7",
          "pwr": "#7f7f7f", "corner": "#ececec"}


def area(r):
    return (r[2] - r[0]) * (r[3] - r[1]) / 1e6


def overlaps(ra, rb):
    return min(ra[2], rb[2]) > max(ra[0], rb[0]) and min(ra[3], rb[3]) > max(ra[1], rb[1])


def inside(r, box):
    return box[0] <= r[0] < r[2] <= box[2] and box[1] <= r[1] < r[3] <= box[3]


def pads(edge, n_list):
    """Pad cell rectangles (die coords) at the measured positions."""
    out = []
    for i, p in enumerate(n_list):
        if edge in ("S", "N"):
            c = SN_FIRST + SN_PITCH * i
            y0 = PAD_EDGE if edge == "S" else DIE_H - PAD_EDGE - PAD_DEPTH
            out.append((p, [c - PAD_W / 2, y0, c + PAD_W / 2, y0 + PAD_DEPTH]))
        else:
            c = WE_FIRST + WE_PITCH * i
            x0 = DIE_W - PAD_EDGE - PAD_DEPTH if edge == "E" else PAD_EDGE
            out.append((p, [x0, c - PAD_W / 2, x0 + PAD_DEPTH, c + PAD_W / 2]))
    return out


def all_pads():
    return [(edge, p, r) for edge, lst in (("W", WEST), ("E", EAST), ("S", SOUTH), ("N", NORTH))
            for p, r in pads(edge, lst)]


def check():
    # blocks: inside the core minus the ring keep-out, no overlaps
    inner = [RING, RING, CORE_W - RING, CORE_H - RING]
    for name, _, r, _ in BLOCKS:
        assert inside(r, inner), name
    for i, (a, _, ra, _) in enumerate(BLOCKS):
        for b, _, rb, _ in BLOCKS[i + 1:]:
            assert not overlaps(ra, rb), f"{a} overlaps {b}"
    # pads: 12/12/24/24, inside the die, outside the core, no overlaps with
    # each other or with the corner cells
    assert (len(WEST), len(EAST), len(SOUTH), len(NORTH)) == (12, 12, 24, 24)
    core = [CX, CY, CX + CORE_W, CY + CORE_H]
    die = [0.0, 0.0, DIE_W, DIE_H]
    plist = all_pads()
    for edge, (pname, _, _), r in plist:
        assert inside(r, die), pname
        assert not overlaps(r, core), f"{pname} intrudes into the core"
        for cname, cr in CORNERS.items():
            assert not overlaps(r, cr), f"{pname} overlaps corner {cname}"
    for i, (_, (a, _, _), ra) in enumerate(plist):
        for _, (b, _, _), rb in plist[i + 1:]:
            assert not overlaps(ra, rb), f"{a} overlaps {b}"
    # analog pads: 8 west + 6 north; AVDD/AVSS x3, ELP/ELN x2, others x1;
    # west pads mirror-symmetric about the axis
    sig = {(e, p[0]): p[2] for e, p, _ in plist}
    ana = [p[2] for e, p, _ in plist if p[1] == "ana"]
    assert len(ana) == 14
    assert {s: ana.count(s) for s in set(ana)} == {
        "AVDD": 3, "AVSS": 3, "ELP": 2, "ELN": 2, "ATP": 1, "VCM": 1, "VREFP": 1, "VREFN": 1}
    # the north AVDD/AVSS pads sit above the east half of the AFE
    afe = next(r for _, k, r, _ in BLOCKS if k == "afe")
    for e, p, r in plist:
        if e == "N" and p[2] in ("AVDD", "AVSS"):
            xc = (r[0] + r[2]) / 2
            assert CX + (afe[0] + afe[2]) / 2 < xc < CX + afe[2], (p, xc)
    west = [(p[2], (r[1] + r[3]) / 2) for e, p, r in plist if e == "W" and p[1] == "ana"]
    axis = CY + YC
    for s, y in west:
        mirror = [s2 for s2, y2 in west if abs((y2 - axis) + (y - axis)) < 1e-6]
        assert mirror and mirror[0] in (s, {"ELP": "ELN", "ELN": "ELP"}.get(s)), (s, y)
    # ID/marker/logo cells: inside the corner-cell areas, outside the core
    for name, corner, r in MARKS:
        assert inside(r, CORNERS[corner]), name
        assert not overlaps(r, core), name
    return sig


def table():
    print("| block | x (um, core) | y (um, core) | box (mm2) | need low-high (mm2) | mid | high |")
    print("|---|---|---|---|---|---|---|")
    spare = sum(area(r) for _, k, r, _ in BLOCKS if k == "spare")
    short_high = 0.0
    for name, kind, r, need in BLOCKS:
        if kind in ("spare", "chan", "iso"):
            continue
        a = area(r)
        lo, hi = need
        mid = (lo + hi) / 2
        short_high += max(0.0, hi - a)
        print(f"| {name} | {r[0]:.0f}-{r[2]:.0f} | {r[1]:.0f}-{r[3]:.0f} | {a:.3f} | "
              f"{lo:.3f}-{hi:.3f} | {'OK' if mid <= a else 'short'} | "
              f"{'OK' if hi <= a else f'short {hi - a:.2f}'} |")
    used = sum(area(r) for _, k, r, _ in BLOCKS if k != "spare")
    print(f"\ncore {CORE_W*CORE_H/1e6:.2f} mm2; boxes incl. channels {used:.2f} mm2; "
          f"spare {spare:.3f} mm2; high-case shortfall {short_high:.3f} mm2 "
          f"(net {short_high - spare:+.3f} mm2 after using spare)")
    print("\nanalog pads (bond pad centre, die um):")
    for edge, (pname, kind, s), r in all_pads():
        if kind != "ana":
            continue
        if edge == "W":
            print(f"  W {pname:11} {s:6} ({r[0] + BOND_OFFSET:.1f}, {(r[1] + r[3]) / 2:.1f})")
        else:
            print(f"  N {pname:11} {s:6} ({(r[0] + r[2]) / 2:.1f}, {r[3] - BOND_OFFSET:.1f})")


def svg(path, s=0.25):
    def R(r, fill, stroke="#333", sw=1.0, dash=None, op=1.0):
        x0, y0, x1, y1 = r
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<rect x="{x0*s:.1f}" y="{(DIE_H-y1)*s:.1f}" width="{(x1-x0)*s:.1f}" '
                f'height="{(y1-y0)*s:.1f}" fill="{fill}" fill-opacity="{op}" '
                f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def T(x, y, txt, size=11, anchor="middle", rot=0, color="#111"):
        tr = f' transform="rotate({rot} {x*s:.1f} {(DIE_H-y)*s:.1f})"' if rot else ""
        return (f'<text x="{x*s:.1f}" y="{(DIE_H-y)*s:.1f}" font-size="{size}" '
                f'font-family="Helvetica, Arial, sans-serif" text-anchor="{anchor}" '
                f'fill="{color}"{tr}>{txt}</text>')

    def core(r):
        return [r[0] + CX, r[1] + CY, r[2] + CX, r[3] + CY]

    W, H = DIE_W * s, DIE_H * s
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H+70:.0f}" '
          f'viewBox="0 0 {W:.0f} {H+70:.0f}">',
          '<rect width="100%" height="100%" fill="#ffffff"/>',
          R([0, 0, DIE_W, DIE_H], "#fafafa", sw=1.5),
          R([CX, CY, CX + CORE_W, CY + CORE_H], "#ffffff", sw=1.5)]
    for name, kind, r, need in BLOCKS:
        dash = "6,4" if kind == "spare" else None
        el.append(R(core(r), COLORS[kind], dash=dash))
    for name, r in SUB:
        el.append(R(core(r), "none", stroke="#555", sw=0.6, dash="3,3"))
        cx, cy = (r[0] + r[2]) / 2 + CX, (r[1] + r[3]) / 2 + CY
        rot = -90 if (r[2] - r[0]) < 160 else 0
        dy = 60 if (r[1] < YC < r[3] and not rot) else -15  # keep clear of the axis
        el.append(T(cx, cy + dy, name, 9, rot=rot, color="#444"))
    for name, kind, r, need in BLOCKS:
        cx, cy = (r[0] + r[2]) / 2 + CX, (r[1] + r[3]) / 2 + CY
        if kind == "chan":
            el.append(T(cx, cy - 12, name, 9))
        elif kind == "iso":
            el.append(T(cx, cy, "isolation", 9, rot=-90))
        elif kind == "svc":
            el.append(T(cx + 10, cy + 380, name, 9, rot=-90))
        elif kind in ("afe", "adc"):
            el.append(T(cx, r[3] + CY - 70, f"{name}  {area(r):.2f} mm2", 13))
        elif kind == "spare":
            el.append(T(cx, cy, name.strip(), 10))
            el.append(T(cx, cy - 60, f"{area(r):.2f} mm2", 9))
        else:
            el.append(T(cx, cy, name.strip(), 10))
            if need:
                el.append(T(cx, cy - 60, f"{area(r):.2f} mm2", 9))
    # mirror axis
    el.append(f'<line x1="{(CX+40)*s:.1f}" y1="{(DIE_H-CY-YC)*s:.1f}" '
              f'x2="{(CX+2490)*s:.1f}" y2="{(DIE_H-CY-YC)*s:.1f}" stroke="#c0392b" '
              f'stroke-width="0.8" stroke-dasharray="8,4"/>')
    # corner cells with the wafer.space ID/marker/logo cells
    for cname, cr in CORNERS.items():
        el.append(R(cr, COLORS["corner"], stroke="#999", sw=0.5))
    for name, _, r in MARKS:
        el.append(R(r, COLORS["mark"], stroke="#b0577a", sw=0.6))
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        rot = -90 if (r[3] - r[1]) > 1.5 * (r[2] - r[0]) else 0
        el.append(T(cx, cy - 10, name, 7, rot=rot, color="#6b2a45"))
    for edge, (pname, kind, sig), r in all_pads():
        el.append(R(r, COLORS[kind], stroke="#222", sw=0.5))
        if sig:
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            el.append(T(cx, cy - 15, sig, 8, rot=-90 if edge in ("S", "N") else 0,
                        color="#000"))
    # signal flow
    el.append(T(CX + 1150, CY + YC + 20, "&#8594;", 22, color="#c0392b"))
    el.append(T(CX + 2525, CY + YC + 270, "&#8594;", 22, color="#c0392b"))
    legend = [("ana", "analog pad (asig_5p0)"), ("dio", "digital I/O used"),
              ("io", "unused bidir"), ("in", "input-only (unused)"),
              ("pwr", "DVDD/DVSS ring"), ("mark", "ID/marker/logo (corners)")]
    for i, (k, txt) in enumerate(legend):
        x = 14 + i * 162
        el.append(f'<rect x="{x}" y="{H+18}" width="14" height="14" fill="{COLORS[k]}" '
                  f'stroke="#222" stroke-width="0.5"/>')
        el.append(f'<text x="{x+19}" y="{H+30}" font-size="10.5" '
                  f'font-family="Helvetica, Arial, sans-serif">{txt}</text>')
    el.append(f'<text x="14" y="{H+58}" font-size="11" font-family="Helvetica, Arial, '
              f'sans-serif" fill="#555">wafer.space 1x0.5: die 3932 x 2531 um, core '
              f'3048 x 1647 um. Pads at measured positions (padring run '
              f'RUN_2026-10-22_14-47-04). Red dashed line = differential mirror axis.</text>')
    el.append("</svg>")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(el))


def main():
    check()
    table()
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "documentation", "figures", "gf180", "plan_20261022",
                       "gf180_floorplan_20261022.svg")
    svg(os.path.normpath(out))
    print(f"\nwrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()

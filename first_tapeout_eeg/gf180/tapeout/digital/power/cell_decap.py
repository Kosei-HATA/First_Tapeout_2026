#!/usr/bin/env python3
"""The digital macros' own VDD-VSS capacitance, for the chip-level supply-noise deck
(gf180/tapeout/pex/digital_noise.py, its MACRO_C; written 11/25 for the 14th chip's macro).

  - The cells: every cell type of the macro's final netlist from the PDK's transistor netlist
    (libs.ref/<library>/spice) in ngspice AC (typical, 27 C, VDD 3.3 V, 1 MHz): the current into VDD
    (VNW on VDD, VPW and VSS on ground) once with every input at VSS and once at VDD (an input is
    driven by a cell whose on-transistor ties it to one rail), averaged, times the instances of that
    type. Outputs are left to the cell. Fill, end cap and tie cells hold no device.
  - The n-well junction: the macro's NWELL (21/0) merged, its area and perimeter as one
    diode_nw2ps_06v0 at 3.3 V reverse (the cells' netlists do not hold the well-substrate diode).

The 11/8 numbers in digital_noise.py (eeg_digital_top 92.4 pF of cells, of it 35 pF fillcap, + 25 pF of
n-well; eeg_adc_dig 25.6 + 8 pF) came from this method by hand; the script reproduces the cells' part.

usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/power/cell_decap.py [--rev r13|r14]
       writes build/cell_decap_<rev>.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import current_profile as CP  # noqa: E402  (netlist(), PDK)

TAPEOUT = os.path.dirname(os.path.dirname(HERE))
GDS = os.path.join(TAPEOUT, "layout", "gds")
NGSPICE = "/opt/homebrew/bin/ngspice"
FREQ = 1e6
VDD = 3.3
# per chip version: macro -> (cell library track, final netlist, GDS)
REVS = {"r13": {"eeg_digital_top": (9, os.path.join(GDS, "eeg_digital_top.nl.v"), os.path.join(GDS, "eeg_digital_top.gds")),
                "eeg_adc_dig": (7, os.path.join(GDS, "eeg_adc_dig.nl.v"), os.path.join(GDS, "eeg_adc_dig.gds"))},
        "r14": {"eeg_digital_top": (9, os.path.join(GDS, "r14", "eeg_digital_top.nl.v"),
                                    os.path.join(GDS, "r14", "eeg_digital_top.gds"))}}


def cells(t):
    """{cell: (ports, {pin: I/O/P/G})} of the PDK's transistor netlist of track t; and the file"""
    path = f"{CP.PDK}/libs.ref/gf180mcu_fd_sc_mcu{t}t5v0/spice/gf180mcu_fd_sc_mcu{t}t5v0.spice"
    out, cur = {}, None
    for ln in open(path):
        m = re.match(r"\.SUBCKT\s+(\S+)\s+(.*)$", ln, re.I)
        if m:
            cur = m.group(1)
            out[cur] = (m.group(2).split(), {}, [])
        elif cur and ln.startswith("*.PININFO"):
            for tok in ln.split()[1:]:
                p, k = tok.split(":")
                out[cur][1][p] = k
        elif cur and re.match(r"\.ENDS", ln, re.I):
            cur = None
        elif cur and ln.strip() and ln[0] in "XxDdMmCc":
            out[cur][2].append(ln)
    return out, path


def nwell(gds):
    """merged NWELL (21/0) of the macro's GDS: area (m^2), perimeter (m)"""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(gds)
    top = ly.top_cells()
    assert len(top) == 1, [c.name for c in top]
    reg = kdb.Region(top[0].begin_shapes_rec(ly.layer(21, 0)))
    reg.merge()
    return reg.area() * (ly.dbu * 1e-6) ** 2, reg.perimeter() * ly.dbu * 1e-6


def main(rev):
    res = {}
    for macro, (t, nl, gds) in REVS[rev].items():
        lib, libpath = cells(t)
        count = Counter(c for c, _, _ in CP.netlist(nl))
        L = ["* cell_decap.py: VDD-VSS capacitance per cell type, inputs low (L) / high (H)",
             f".include {CP.PDK}/libs.tech/ngspice/design.ngspice",
             f".lib {CP.PDK}/libs.tech/ngspice/sm141064.ngspice typical",
             f".lib {CP.PDK}/libs.tech/ngspice/sm141064.ngspice diode_typical",
             f".include {libpath}"]
        kinds = sorted(c for c in count if lib[c][2])         # cells holding a device
        for k, c in enumerate(kinds):
            ports, info, _ = lib[c]
            for lv in "LH":
                sup = f"v{lv.lower()}{k}"
                conn = []
                for p in ports:
                    kind = info.get(p, "I")
                    if p in ("VDD", "VNW"):
                        conn.append(sup)
                    elif p in ("VSS", "VPW"):
                        conn.append("0")
                    elif kind == "I":
                        conn.append("0" if lv == "L" else sup)
                    else:
                        conn.append(f"o{lv.lower()}{k}_{p}")
                L.append(f"V{lv}{k} {sup} 0 DC {VDD} AC 1\nX{lv}{k} {' '.join(conn)} {c}")
        a, p = nwell(gds)
        L.append(f"VNW vnw 0 DC {VDD} AC 1\nDNW 0 vnw diode_nw2ps_06v0 area={a:.6e} pj={p:.6e}")
        L.append(".control\nac lin 1 {0:g} {0:g}".format(FREQ))
        names = [f"{lv}{k}" for k in range(len(kinds)) for lv in "LH"] + ["NW"]
        for n in names:
            L.append(f"let c{n.lower()} = -imag(i(v{n.lower()}))/(2*pi*{FREQ:g})\nprint c{n.lower()}")
        L.append(".endc\n.end\n")
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "decap.spice"), "w").write("\n".join(L))
            r = subprocess.run([NGSPICE, "-b", "decap.spice"], cwd=d, capture_output=True, text=True)
        val = {m.group(1).upper(): float(m.group(2))
               for m in re.finditer(r"^c(\w+)\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)}
        missing = [n for n in names if n not in val]
        assert not missing, (missing[:5], r.stdout[-2000:], r.stderr[-2000:])
        per = {c: (val[f"L{k}"] + val[f"H{k}"]) / 2 for k, c in enumerate(kinds)}
        tot = sum(per[c] * count[c] for c in kinds)
        fill = sum(per[c] * count[c] for c in kinds if "fillcap" in c)
        res[macro] = {"cells": int(sum(count.values())), "cell_types_with_devices": len(kinds),
                      "C_cells_pF": tot * 1e12, "C_fillcap_pF": fill * 1e12,
                      "nwell_area_um2": a * 1e12, "nwell_perimeter_um": p * 1e6, "C_nwell_pF": val["NW"] * 1e12,
                      "C_total_pF": (tot + val["NW"]) * 1e12,
                      "per_type_fF": {c: [val[f"L{k}"] * 1e15, val[f"H{k}"] * 1e15, count[c]] for k, c in enumerate(kinds)}}
        x = res[macro]
        print(f"{rev} {macro}: {x['cells']} cells ({len(kinds)} types with devices): cells {x['C_cells_pF']:.1f} pF "
              f"(fillcap {x['C_fillcap_pF']:.1f}), n-well {x['nwell_area_um2']:.0f} um2 / {x['nwell_perimeter_um']:.0f} um "
              f"-> {x['C_nwell_pF']:.1f} pF; total {x['C_total_pF']:.1f} pF")
    out = os.path.join(CP.BUILD, f"cell_decap_{rev}.json")
    json.dump(res, open(out, "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rev", default="r14", choices=tuple(REVS))
    main(ap.parse_args().rev)

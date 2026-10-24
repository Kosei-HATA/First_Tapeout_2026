#!/usr/bin/env python3
"""Pairwise coupling of the digital control nets on the chip (tracker C3, chip_sta).

For the nets from the digital blocks to the analog blocks (the long control bus to the
AFE, the bias and the test multiplexer, and the ADC's strobes), the routed geometry
outside the two macros (as in chip_nets.py) and, for every pair, the sidewall coupling
on the same layer (parallel run within 0.6 um, magic's coefficients). Writes
build/xtalk.json: per net the ground capacitance (area + fringe, fF), the receivers
(analog devices with a gate on the net) and the coupling to every other net (fF).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/xtalk.py
"""
import json
import os
import sys
import time

import klayout.db as kdb

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chip_nets as cn  # noqa: E402

NETS = (["CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CHOP1", "ADC_ZERO", "CMP_STROBE", "DAC_CLK", "OFS"]
        + [f"OFM{k}" for k in range(10)] + [f"OFEN{k}" for k in range(4)] + [f"TC{k}" for k in range(5)]
        + ["IB0", "IB1", "BP0", "BP1", "BN0", "BN1"] + [f"CPF{k}" for k in range(4)])


def main():
    t0 = time.time()
    lvs = kdb.LayoutVsSchematic()
    lvs.read(cn.LVSDB)
    xref = lvs.xref()
    sc = next(lvs.reference.each_circuit_top_down())
    geo, info = {}, {}
    for n in NETS:
        sn = sc.net_by_name(n)
        ln = xref.other_net_for(sn)
        g = cn.clip(cn.pr.net_geometry(lvs, ln), [cn.DIG_BOX, cn.ADIG_BOX])
        geo[n] = g
        c_iso = 0.0
        for k, (ca, cf, _, _) in cn.CAPS.items():
            if not g[k].is_empty():
                c_iso += (g[k].area() * 1e-6 * ca + g[k].perimeter() * 1e-3 * cf) * 1e-3
        rx = []
        for term in sn.each_terminal():
            d = term.device()
            dn = d.expanded_name()
            if dn.startswith("DIG.") or dn.startswith("ADIG."):
                continue
            if d.device_class().terminal_definitions()[term.terminal_id()].name == "G":
                rx.append(f"{dn} {d.device_class().name} W={d.parameter('W'):.2f}")
        info[n] = {"c_iso_fF": round(c_iso, 2), "receivers": rx, "cpl_fF": {}}
    for i, a in enumerate(NETS):
        for b in NETS[i + 1:]:
            c = 0.0
            for k, (_, _, sw, off) in cn.CAPS.items():
                ra, rb = geo[a][k], geo[b][k]
                if ra.is_empty() or rb.is_empty():
                    continue
                if not ra.bbox().enlarged(cn.um(cn.CPL_D), cn.um(cn.CPL_D)).overlaps(rb.bbox()):
                    continue
                for e in ra.separation_check(rb, cn.um(cn.CPL_D), False, kdb.Region.Projection).each():
                    s = max(e.distance() * 1e-3, 0.28)
                    c += e.first.length() * 1e-3 * sw / (s + off) * 1e-3
            if c > 0.5:
                info[a]["cpl_fF"][b] = round(c, 2)
                info[b]["cpl_fF"][a] = round(c, 2)
    with open(os.path.join(cn.BUILD, "xtalk.json"), "w") as f:
        json.dump(info, f, indent=1)
    for n in NETS:
        top = sorted(info[n]["cpl_fF"].items(), key=lambda kv: -kv[1])[:4]
        tot = info[n]["c_iso_fF"] + sum(info[n]["cpl_fF"].values())
        print(f"{n:10s} C_iso {info[n]['c_iso_fF']:7.1f} fF, coupling to the bus {sum(info[n]['cpl_fF'].values()):7.1f} fF "
              f"(total {tot:7.1f}); largest: " + ", ".join(f"{k} {v:.0f}" for k, v in top)
              + f"; receivers: {len(info[n]['receivers'])} gates", flush=True)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The SOFT_RESET paths of the r14 macro (requirement VER-05), from run_sta_r14.sh's reports: for every corner, the
worst setup and hold slack of the paths through the clear / preset arcs of the flip-flops rst_n drives (its assertion,
the pins' fall), by where they end: the register the endpoint flip-flop holds (its Q net keeps the RTL name; the
module prefix gives the group) or an output port. The FIFO's memory and the flip-flops rst_n itself clears are false
paths (eeg_digital_top_r14.sdc), so they do not appear.

usage: soft_paths.py <run tag>        writes runs/<tag>/sta_r14/soft_paths.json and prints a table
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORNERS = [f"{rc}_{pv}" for pv in ("ss_125C_3v00", "tt_025C_3v30", "ff_n40C_3v60") for rc in ("max", "nom", "min")]
GROUPS = [("CIC", r"^\\?u_cic\."), ("clock generator", r"^\\?u_clkgen\."), ("CHOP1", r"^\\?u_chop1\."),
          ("RAW", r"^\\?u_raw\."), ("overload detector", r"^\\?u_ovl\."), ("rst_n, soft_cnt", r"^\\?(rst_n|soft_cnt)"),
          ("timing and data path (top)", r".")]


def q_names(nl):
    txt = open(nl).read()
    out = {}
    for m in re.finditer(r"\n\s*(\w+__\w+)\s+(\S+)\s*\((.*?)\);", txt, re.S):
        pins = dict((p, n.strip()) for p, n in re.findall(r"\.(\w+)\(([^()]*)\)", m.group(3)))
        if "Q" in pins:
            out[m.group(2)] = pins["Q"]
    return out


def ends(path):
    """[(endpoint, slack)] of a report_checks -format end file."""
    out = []
    for line in open(path):
        m = re.match(r"(\S+?)(?:/(\w+))? \(([^)]*)\)\s+\S+\s+\S+\s+(-?[\d.]+)", line.strip())
        if m:
            out.append((m.group(1), m.group(2), m.group(3), float(m.group(4))))
    return out


def group(q):
    for g, rx in GROUPS:
        if re.search(rx, q):
            return g
    return "?"


def main():
    tag = sys.argv[1]
    run = os.path.join(HERE, "runs", tag)
    qn = q_names(os.path.join(run, "final", "nl", "eeg_digital_top.nl.v"))
    res = {}
    for c in CORNERS:
        d = os.path.join(run, "sta_r14", "arcs_on", c)
        row = {}
        for inst, pin, kind, sl in ends(os.path.join(d, "soft_ends.rpt")):
            if kind in ("out", "output"):
                g = "output ports"
            else:
                g = group(qn.get(inst, "?"))
            row.setdefault(g, {"n": 0, "worst": 1e9})
            row[g]["n"] += 1
            row[g]["worst"] = min(row[g]["worst"], sl)
        # the hold side: the worst of report_checks -path_delay min (5 groups printed)
        holds = [float(x) for x in re.findall(r"(-?[\d.]+)\s+slack \((?:MET|VIOLATED)\)",
                                              open(os.path.join(d, "soft_hold.rpt")).read())]
        res[c] = {"setup_by_group": row, "hold_worst": min(holds) if holds else None}
    out = os.path.join(run, "sta_r14", "soft_paths.json")
    json.dump(res, open(out, "w"), indent=1)
    groups = sorted({g for c in res for g in res[c]["setup_by_group"]})
    print("| corner | " + " | ".join(groups) + " | hold worst |")
    print("|---|" + "---|" * (len(groups) + 1))
    for c in CORNERS:
        r = res[c]["setup_by_group"]
        print(f"| {c} | " + " | ".join(f"{r[g]['worst']:+.3f} ({r[g]['n']})" if g in r else "-" for g in groups) +
              f" | {res[c]['hold_worst']:+.3f} |")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

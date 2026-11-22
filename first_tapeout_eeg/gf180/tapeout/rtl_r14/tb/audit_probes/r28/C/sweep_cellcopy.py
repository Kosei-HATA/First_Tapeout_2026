#!/usr/bin/env python3
"""Audit round 28 (C): a class of single edits the earlier sweeps did not list: one cell of fsm_spec's SEQ or SPI table
replaced by the content of another cell (the same event in another state, or another event of the same state), and
one branch of a cell replaced by a branch of another cell with the same guard variables available. Each edited table
goes through run_checks(); an edit that passes is compared with the original by the signature of sweep_split.py.
Usage: sweep_cellcopy.py <sweep_split.py> <spec dir> <SEQ|SPI> <out>"""
import copy, os, sys
split_py, spec_dir, mach, out = sys.argv[1:5]
src = open(split_py).read().split("def edits():")[0]
sys.argv = [sys.argv[0], spec_dir, mach, out]
exec(compile(src, "sweep_split_head", "exec"))

def edits():
    keys = sorted(ORIG, key=str)
    for key in keys:
        s, e = key
        for k2 in keys:
            if k2 == key or (k2[0] != s and k2[1] != e):
                continue
            if ORIG[k2] == ORIG[key]:
                continue
            yield f"{key} := {k2}", ("cell", key, copy.deepcopy(ORIG[k2]))
        # one branch replaced by a branch of another cell of the same event (its guard kept)
        cell = ORIG[key]
        if isinstance(cell, list):
            for i, b in enumerate(cell):
                for k2 in keys:
                    c2 = ORIG[k2]
                    if k2 == key or k2[1] != e or not isinstance(c2, list):
                        continue
                    for b2 in c2:
                        if (b2["actions"], b2["next"]) != (b["actions"], b["next"]):
                            yield (f"{key} [{b['guard']}] := actions/next of {k2} [{b2['guard']}]",
                                   ("br", key, i, F.B(b["guard"], list(b2["actions"]), b2["next"])))

n = npass = 0
res = []
seen = set()
for desc, e in edits():
    t = copy.deepcopy(ORIG)
    if e[0] == "cell":
        t[e[1]] = e[2]
    else:
        t[e[1]][e[2]] = e[3]
    sig = repr(sorted((str(k), repr(v)) for k, v in t.items()))
    if sig in seen:
        continue
    seen.add(sig)
    n += 1
    M["table"] = t
    try:
        rep = F.check_tables(M) + F.check_vocab(M)
        if not rep:
            rep += (F.check_seq_branches() + F.check_seq_commands()) if mach == "SEQ" else F.check_spi_props()[0]
        if not rep:
            rep, _ = F.run_checks(verbose=False)
    except Exception as ex:   # noqa: BLE001
        rep = [f"CRASH {type(ex).__name__}: {ex}"]
    M["table"] = ORIG
    if not rep:
        npass += 1
        eq = SIG(t) == BASE
        res.append(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {desc}")
    elif any(str(r).startswith("CRASH") for r in rep):
        res.append(f"CRASH {desc}: {rep[0]}")
with open(out, "w") as fo:
    fo.write(f"{mach}: {n} distinct edits, {npass} pass the check\n" + "\n".join(res) + "\n")
print(f"{mach}: {n} edits, {npass} pass")

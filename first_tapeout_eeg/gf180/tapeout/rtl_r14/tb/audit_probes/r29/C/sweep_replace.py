#!/usr/bin/env python3
"""Audit round 29 (C): single edits that replace one action of a branch by another action of the machine (the classic
sweep drops and adds separately), and that move one action from a branch to the other branches of its cell.
Usage: sweep_replace.py <spec dir> <SEQ|SPI> <out>"""
import copy, os, sys
spec_dir, mach, out = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_split.py")).read()
src = src.split("def edits():")[0]
sys.argv = [sys.argv[0], spec_dir, mach, out]
exec(compile(src, "sweep_split_head", "exec"))

def edits():
    for key in sorted(ORIG, key=str):
        cell = ORIG[key]
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            for a in b["actions"]:
                for c in ACTS:
                    if c not in b["actions"]:
                        acts = [c if x == a else x for x in b["actions"]]
                        yield f"{key} [{b['guard']}] {a} -> {c}", ("rep", key, i, acts)
                for j, b2 in enumerate(cell):
                    if j != i and a not in b2["actions"]:
                        yield f"{key} [{b['guard']}] {a} moved to branch [{b2['guard']}]", ("mv", key, i, j, a)

n = npass = 0
res = []
for desc, e in edits():
    n += 1
    t = copy.deepcopy(ORIG)
    if e[0] == "rep":
        _, key, i, acts = e
        b = t[key][i]
        t[key][i] = F.B(b["guard"], acts, b["next"])
    else:
        _, key, i, j, a = e
        b, b2 = t[key][i], t[key][j]
        t[key][i] = F.B(b["guard"], [x for x in b["actions"] if x != a], b["next"])
        t[key][j] = F.B(b2["guard"], b2["actions"] + [a], b2["next"])
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
        res.append(f"PASS {'EQUIV' if SIG(t) == BASE else 'NOT-EQUIV'} {desc}")
    elif any(str(r).startswith("CRASH") for r in rep):
        res.append(f"CRASH {desc}: {rep[0]}")
with open(out, "w") as fo:
    fo.write(f"{mach}: {n} edits, {npass} pass the check\n" + "\n".join(res) + "\n")
print(f"{mach}: {n} edits, {npass} pass")

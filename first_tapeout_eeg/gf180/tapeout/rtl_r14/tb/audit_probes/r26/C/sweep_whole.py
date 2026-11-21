#!/usr/bin/env python3
"""Audit round 26 (C): the classic single edits of fsm_spec's tables, independently of the earlier rounds' sweeps:
every cell to IGN / IMP; every branch: each action dropped, each action of the machine added, the next state changed to
every state and to None, the branch removed, the branch refused with CFG_ERR or STATE_ERR (actions replaced, next None);
every guard replaced by its negation; SEQ_PRIORITY: every element moved to every position. Equivalence of an edit that
passes as in sweep_split.py. Usage: sweep_whole.py <spec dir> <SEQ|SPI> <out>"""
import copy
import os
import sys

spec_dir, mach, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_split.py")).read()
src = src.split("def edits():")[0]                  # the setup, the caches and the signatures of sweep_split.py
sys.argv = [sys.argv[0], spec_dir, mach, out]
exec(compile(src, "sweep_split_head", "exec"))


def edits():
    for key in sorted(ORIG, key=str):
        cell = ORIG[key]
        for alt in (F.IGN, F.IMP):
            if cell != alt:
                yield f"{key} -> {alt}", ("cell", key, alt)
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            for a in b["actions"]:
                yield f"{key} [{b['guard']}] drop {a}", ("br", key, i, [x for x in b["actions"] if x != a], b["next"], b["guard"])
            for a in ACTS:
                if a not in b["actions"]:
                    yield f"{key} [{b['guard']}] add {a}", ("br", key, i, b["actions"] + [a], b["next"], b["guard"])
            for n in STATES + [None]:
                if n != b["next"]:
                    yield f"{key} [{b['guard']}] next {n}", ("br", key, i, list(b["actions"]), n, b["guard"])
            if len(cell) > 1:
                yield f"{key} [{b['guard']}] removed", ("del", key, i)
            for fl in ("CFG_ERR", "STATE_ERR") if mach == "SEQ" else ("FRAME_ERR", "ADDR_ERR", "STATE_ERR", "CRC_ERR"):
                if b["actions"] != [fl] and fl in ACTS:
                    yield f"{key} [{b['guard']}] refused with {fl}", ("br", key, i, [fl], None, b["guard"])
            if b["guard"] != F.ALWAYS:
                yield f"{key} [{b['guard']}] guard negated", ("br", key, i, list(b["actions"]), b["next"], f"not ({b['guard']})")
    if mach == "SEQ":
        for i, e in enumerate(F.SEQ_PRIORITY):
            for j in range(len(F.SEQ_PRIORITY)):
                if j != i:
                    p = list(F.SEQ_PRIORITY)
                    p.insert(j, p.pop(i))
                    yield f"SEQ_PRIORITY {e} to position {j}: {p}", ("prio", p)


PRIO = list(F.SEQ_PRIORITY)
n = npass = 0
res = []
for desc, e in edits():
    n += 1
    t = copy.deepcopy(ORIG)
    if e[0] == "cell":
        t[e[1]] = e[2]
    elif e[0] == "br":
        _, key, i, acts, nxt, g = e
        t[key][i] = F.B(g, acts, nxt)
    elif e[0] == "del":
        _, key, i = e
        del t[key][i]
    elif e[0] == "prio":
        F.SEQ_PRIORITY[:] = e[1]
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
    F.SEQ_PRIORITY[:] = PRIO
with open(out, "w") as fo:
    fo.write(f"{mach}: {n} edits, {npass} pass the check\n" + "\n".join(res) + "\n")
print(f"{mach}: {n} edits, {npass} pass")

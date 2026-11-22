#!/usr/bin/env python3
"""Audit round 29 (C): a new class of single edits of fsm_spec's tables: a condition rewritten consistently in every
guard of one cell (so the cell's branches stay complementary: the edit is one coherent "rewrite of a guard"), and in
every guard of the whole table (one condition replaced everywhere: by 1, by 0, by its negation, by another condition,
two conditions exchanged). Each edit through the same checks as sweep_split.py; a passing edit compared with the
original table (seq_resolve / spi_walk signatures). Usage: sweep_cellguard.py <spec dir> <SEQ|SPI> <out>"""
import copy, os, re, sys
spec_dir, mach, out = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_split.py")).read()
src = src.split("def edits():")[0]
sys.argv = [sys.argv[0], spec_dir, mach, out]
exec(compile(src, "sweep_split_head", "exec"))

def subst(g, c, rep):
    return re.sub(r"\b%s\b" % re.escape(c), "(" + rep + ")", g)

def swap(g, a, b):
    g2 = re.sub(r"\b%s\b" % re.escape(a), "\x00", g)
    g2 = re.sub(r"\b%s\b" % re.escape(b), "(" + a + ")", g2)
    return g2.replace("\x00", "(" + b + ")")

def variants(c):
    yield "1", "1"
    yield "0", "0"
    yield f"not {c}", f"not {c}"
    for d in ALLC:
        if d != c:
            yield d, d
            yield f"not {d}", f"not {d}"
            yield f"{c} and {d}", f"{c} and {d}"
            yield f"{c} or {d}", f"{c} or {d}"

def edits():
    for key in sorted(ORIG, key=str):
        cell = ORIG[key]
        if not isinstance(cell, list):
            continue
        used = sorted({v for b in cell for v in F.guard_vars(b["guard"])})
        for c in used:
            for nm, rep in variants(c):
                yield f"{key}: {c} -> {nm} in every guard of the cell", ("cell", key, c, rep)
    for c in ALLC:
        for nm, rep in variants(c):
            yield f"whole table: {c} -> {nm} in every guard", ("all", c, rep)
    for i, a in enumerate(ALLC):
        for b in ALLC[i + 1:]:
            yield f"whole table: {a} <-> {b}", ("swap", a, b)

def apply(t, e):
    if e[0] == "cell":
        _, key, c, rep = e
        t[key] = [F.B(subst(b["guard"], c, rep), b["actions"], b["next"]) for b in t[key]]
    else:
        for key, cell in t.items():
            if isinstance(cell, list):
                if e[0] == "all":
                    t[key] = [F.B(subst(b["guard"], e[1], e[2]), b["actions"], b["next"]) for b in cell]
                else:
                    t[key] = [F.B(swap(b["guard"], e[1], e[2]), b["actions"], b["next"]) for b in cell]

n = npass = 0
res = []
seen = set()
for desc, spec in edits():
    t = copy.deepcopy(ORIG)
    apply(t, spec)
    key_ = repr(sorted((str(k), repr(v)) for k, v in t.items()))
    if key_ in seen or t == ORIG:
        continue
    seen.add(key_)
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
print(f"{mach}: {n} distinct edits, {npass} pass")

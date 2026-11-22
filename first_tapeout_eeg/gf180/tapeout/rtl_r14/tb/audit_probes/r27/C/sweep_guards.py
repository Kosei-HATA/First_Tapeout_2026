#!/usr/bin/env python3
"""Audit round 27 (C): single edits inside the guards of fsm_spec's SEQ and SPI tables (a class the earlier sweeps
did not list): each condition occurrence replaced by every other condition of the machine, by 1, by 0, or negated;
each 'not' dropped; each 'and' / 'or' exchanged. Equivalence of an edit that passes as in sweep_split.py.
Usage: sweep_guards.py <spec dir> <SEQ|SPI> <out>"""
import copy, os, re, sys
spec_dir, mach, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_split.py")).read()
src = src.split("def edits():")[0]
sys.argv = [sys.argv[0], spec_dir, mach, out]
exec(compile(src, "sweep_split_head", "exec"))
TOK = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")


def guard_edits(g):
    seen = set()
    for m in TOK.finditer(g):
        w = m.group(0)
        a, b = g[:m.start()], g[m.end():]
        if w in ALLC:
            for r in [c for c in ALLC if c != w] + ["1", "0", f"(not {w})"]:
                yield f"{w}->{r}@{m.start()}", a + r + b
        elif w == "not":
            yield f"drop not@{m.start()}", a + b.lstrip()
        elif w in ("and", "or"):
            yield f"{w}->{'or' if w == 'and' else 'and'}@{m.start()}", a + ("or" if w == "and" else "and") + b
    if g == F.ALWAYS:
        for c in ALLC:
            yield f"1->{c}", c
            yield f"1->not {c}", f"not {c}"


def edits():
    for key in sorted(ORIG, key=str):
        cell = ORIG[key]
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            for d, ng in guard_edits(b["guard"]):
                yield f"{key} branch {i} [{b['guard']}] {d}: [{ng}]", (key, i, ng)


n = npass = 0
res = []
for desc, (key, i, ng) in edits():
    n += 1
    t = copy.deepcopy(ORIG)
    t[key][i]["guard"] = ng
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
    fo.write(f"{mach}: {n} edits, {npass} pass the check\n" + "\n".join(res) + "\n")
print(f"{mach}: {n} edits, {npass} pass")

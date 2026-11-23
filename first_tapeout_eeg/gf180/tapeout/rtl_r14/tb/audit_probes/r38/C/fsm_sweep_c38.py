#!/usr/bin/env python3
"""audit 38, auditor C: single edits of fsm_spec's SEQ and SPI tables in classes the earlier sweeps did not make:
  litsub  one literal occurrence of a guard replaced by another condition the event may use, or by its negation, or
          negated in place (round 37's class replaced the whole guard by one literal, or dropped a conjunct)
  opswap  one 'and' <-> 'or' of a guard
  bswap   the outcomes (actions, next state) of two branches of one cell exchanged, the guards kept
  cswap   the cells of two events of one state exchanged (same-kind events: two commands, or BIT <-> BYTE)
Each edit: fsm_sweep3's early-stop checks, then run_checks; a passing edit is compared with the original by the
behaviour signatures (fsm_sweep_sig.py). Usage: <spec dir> <out> [part npart]"""
import copy, os, re, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
PART, NPART = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, 1)
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "fsm_sweep3.py")).read().replace("\nmain()\n", "\n")
sys.argv = ["x", SPEC, "/dev/null"]
g = {"__file__": os.path.join(HERE, "fsm_sweep3.py"), "__name__": "s3"}
exec(compile(src, "fsm_sweep3.py", "exec"), g)
F, B, IGN, IMP, ALWAYS = g["F"], g["B"], g["IGN"], g["IMP"], g["ALWAYS"]
KW = {"not", "and", "or"}

def conds_for(M, s, e):
    return g["seq_conds"](s, e) if M is F.SEQ else g["spi_conds"](s, e)

def tokens(gd):
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*", gd)
            if m.group(0) not in KW]

def guard_edits(gd, conds):
    out = set()
    for s0, s1, name in tokens(gd):
        pre = gd[:s0]
        if pre.endswith("not "):
            out.add(pre[:-4] + gd[s0:])                     # the 'not' before it removed
        else:
            out.add(pre + "not " + gd[s0:])                 # negated in place
        for c in conds:
            if c != name:
                out.add(pre + c + gd[s1:])
                out.add(pre + "not " + c + gd[s1:])
    out.discard(gd)
    return sorted(out)

def op_edits(gd):
    out = set()
    for m in re.finditer(r" (and|or) ", gd):
        out.add(gd[:m.start()] + (" or " if m.group(1) == "and" else " and ") + gd[m.end():])
    return sorted(out)

def edits(M):
    t = M["table"]
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list):
            continue
        conds = conds_for(M, *key)
        for i, b in enumerate(cell):
            gd = b["guard"]
            if gd == ALWAYS:
                continue
            for g2 in guard_edits(gd, conds):
                yield (f"litsub {key}#{i} [{gd}] -> [{g2}]", lambda tt, k=key, i=i, g2=g2: tt[k][i].__setitem__("guard", g2))
            for g2 in op_edits(gd):
                yield (f"opswap {key}#{i} [{gd}] -> [{g2}]", lambda tt, k=key, i=i, g2=g2: tt[k][i].__setitem__("guard", g2))
        for i in range(len(cell)):
            for j in range(i + 1, len(cell)):
                def sw(tt, k=key, i=i, j=j):
                    a, b = tt[k][i], tt[k][j]
                    a["actions"], b["actions"] = b["actions"], a["actions"]
                    a["next"], b["next"] = b["next"], a["next"]
                yield (f"bswap {key}#{i}<->#{j}", sw)
    states = [x[0] for x in M["states"]]
    evs = [x[0] for x in M["events"]]
    groups = [list(F.SEQ_COMMANDS)] if M is F.SEQ else [["BIT", "BYTE"]]
    for s in states:
        for grp in groups:
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    e1, e2 = grp[i], grp[j]
                    if (s, e1) in t and (s, e2) in t and t[(s, e1)] != t[(s, e2)]:
                        def cs(tt, s=s, e1=e1, e2=e2):
                            tt[(s, e1)], tt[(s, e2)] = tt[(s, e2)], tt[(s, e1)]
                        yield (f"cswap {s}: {e1}<->{e2}", cs)

def main():
    t0 = time.time()
    assert not g["full_checks"]()
    sig0 = {"SEQ": g["seq_sig"](), "SPI": g["spi_sig"]()}
    fo = open(OUT, "w")
    tried = npass = nneq = idx = 0
    def judge(label, M):
        nonlocal npass, nneq
        if g["checks_fast"]():
            return
        if g["full_checks"]():
            return
        s = g["seq_sig"]() if M is F.SEQ else g["spi_sig"]()
        eq = s == sig0[M["name"]]
        npass += 1; nneq += (not eq)
        diff = [] if eq else [k for k in s if s[k] != sig0[M["name"]].get(k)][:2]
        fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {M['name']} {label}" + ("" if eq else f" e.g. {diff}") + "\n"); fo.flush()
    for M in (F.SEQ, F.SPI):
        g["SPI_FIRST"] = M is F.SPI
        for label, ap in edits(M):
            idx += 1
            if idx % NPART != PART:
                continue
            orig = M["table"]; M["table"] = copy.deepcopy(orig)
            try:
                ap(M["table"]); judge(label, M)
            except Exception as ex:
                fo.write(f"EXC {M['name']} {label}: {ex!r}\n")
            finally:
                M["table"] = orig; tried += 1
            if tried % 200 == 0:
                fo.write(f"# {tried} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

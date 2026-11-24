#!/usr/bin/env python3
"""audit42 C: single edits of fsm_spec's SEQ and SPI tables in classes the earlier sweeps (rounds 32-38) did not make:
  amove   one action moved from one branch of a cell to another branch of the same cell (a misplaced action)
  xmove   one action moved from a branch to the branch with the same guard (or the only branch) of the same event's
          cell in another state
  nswap   the next states of two branches of two different cells of the same event exchanged (a crossed transition)
  gcopy   a branch's guard replaced by the guard of a branch of the same event's cell in another state
Each edit: fsm_sweep3's early-stop checks, then run_checks; a passing edit is compared with the original by the
behaviour signatures (fsm_sweep_sig.py). Usage: <spec dir> <out>"""
import copy, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "fsm_sweep3.py")).read().replace("\nmain()\n", "\n")
sys.argv = ["x", SPEC, "/dev/null"]
g = {"__file__": os.path.join(HERE, "fsm_sweep3.py"), "__name__": "s3"}
exec(compile(src, "fsm_sweep3.py", "exec"), g)
F = g["F"]

def edits(M):
    t = M["table"]
    keys = [k for k in sorted(t, key=str) if isinstance(t[k], list)]
    for key in keys:
        cell = t[key]
        for i, b in enumerate(cell):
            for a in b["actions"]:
                for j in range(len(cell)):
                    if j != i and a not in cell[j]["actions"]:
                        def mv(tt, k=key, i=i, j=j, a=a):
                            tt[k][i]["actions"].remove(a); tt[k][j]["actions"].append(a)
                        yield (f"[amove] {key}#{i} -{a} -> #{j}", mv)
                for key2 in keys:
                    if key2 == key or key2[1] != key[1]:
                        continue
                    c2 = t[key2]
                    for j, b2 in enumerate(c2):
                        if (b2["guard"] == b["guard"] or len(c2) == 1) and a not in b2["actions"]:
                            def xm(tt, k=key, i=i, k2=key2, j=j, a=a):
                                tt[k][i]["actions"].remove(a); tt[k2][j]["actions"].append(a)
                            yield (f"[xmove] {key}#{i} -{a} -> {key2}#{j}", xm)
            for key2 in keys:
                if key2 <= key or key2[1] != key[1]:
                    continue
                for j, b2 in enumerate(t[key2]):
                    if b2["next"] != b["next"]:
                        def ns(tt, k=key, i=i, k2=key2, j=j):
                            tt[k][i]["next"], tt[k2][j]["next"] = tt[k2][j]["next"], tt[k][i]["next"]
                        yield (f"[nswap] {key}#{i} <-> {key2}#{j} next", ns)
                    if b2["guard"] != b["guard"]:
                        def gc(tt, k=key, i=i, k2=key2, j=j):
                            tt[k][i]["guard"] = tt[k2][j]["guard"]
                        yield (f"[gcopy] {key}#{i} guard := {key2}#{j}'s [{b2['guard']}]", gc)

def main():
    t0 = time.time()
    assert not g["full_checks"]()
    sig0 = {"SEQ": g["seq_sig"](), "SPI": g["spi_sig"]()}
    fo = open(OUT, "w")
    tried = npass = nneq = 0
    for M in (F.SEQ, F.SPI):
        g["SPI_FIRST"] = M is F.SPI
        for label, ap in edits(M):
            orig = M["table"]; M["table"] = copy.deepcopy(orig)
            try:
                ap(M["table"])
                if not g["checks_fast"]() and not g["full_checks"]():
                    s = g["seq_sig"]() if M is F.SEQ else g["spi_sig"]()
                    eq = s == sig0[M["name"]]
                    npass += 1; nneq += (not eq)
                    diff = [] if eq else [k for k in s if s[k] != sig0[M["name"]].get(k)][:2]
                    fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {M['name']} {label}" + ("" if eq else f" e.g. {diff}") + "\n")
                    fo.flush()
            except Exception as ex:
                fo.write(f"EXC {M['name']} {label}: {ex!r}\n")
            finally:
                M["table"] = orig; tried += 1
            if tried % 500 == 0:
                fo.write(f"# {tried} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

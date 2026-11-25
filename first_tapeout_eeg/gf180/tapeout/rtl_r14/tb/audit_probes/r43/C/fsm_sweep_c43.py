#!/usr/bin/env python3
"""audit43 C: single edits of fsm_spec's SEQ and SPI tables in classes rounds 32-42 did not make:
  bswap   the outcomes (actions and next state) of two branches of one cell exchanged (an inverted condition)
  aswap   only the actions of two branches of one cell exchanged
  nswapi  only the next states of two branches of one cell exchanged
  gswap   the guards of two branches of one cell exchanged (differs from bswap in cells of three branches)
  xevent  a cell replaced by the cell of another event in the same state (e.g. (RUN, APPLY) := (RUN, APPLY_NR))
  eswap   the cells of two events of one state exchanged
Each edit: fsm_sweep3's early-stop checks, then run_checks; a passing edit is compared with the original by the
behaviour signatures (fsm_sweep_sig.py). Usage: <spec dir> <out>"""
import copy, os, sys, time, itertools
SPEC, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "fsm_sweep3.py")).read().replace("\nmain()\n", "\n")
sys.argv = ["x", SPEC, "/dev/null"]
g = {"__file__": os.path.join(HERE, "fsm_sweep3.py"), "__name__": "s3"}
exec(compile(src, "fsm_sweep3.py", "exec"), g)
F = g["F"]

def edits(M):
    t = M["table"]
    keys = sorted(t, key=str)
    events = sorted({k[1] for k in keys})
    for key in keys:
        cell = t[key]
        if isinstance(cell, list) and len(cell) >= 2:
            for i, j in itertools.combinations(range(len(cell)), 2):
                def bs(tt, k=key, i=i, j=j):
                    a, b = tt[k][i], tt[k][j]
                    a["actions"], b["actions"] = b["actions"], a["actions"]; a["next"], b["next"] = b["next"], a["next"]
                yield (f"[bswap] {key}#{i}<->#{j}", bs)
                if cell[i]["actions"] != cell[j]["actions"]:
                    def asw(tt, k=key, i=i, j=j):
                        a, b = tt[k][i], tt[k][j]; a["actions"], b["actions"] = b["actions"], a["actions"]
                    yield (f"[aswap] {key}#{i}<->#{j}", asw)
                if cell[i]["next"] != cell[j]["next"]:
                    def nsw(tt, k=key, i=i, j=j):
                        a, b = tt[k][i], tt[k][j]; a["next"], b["next"] = b["next"], a["next"]
                    yield (f"[nswapi] {key}#{i}<->#{j}", nsw)
                if len(cell) >= 3:
                    def gsw(tt, k=key, i=i, j=j):
                        a, b = tt[k][i], tt[k][j]; a["guard"], b["guard"] = b["guard"], a["guard"]
                    yield (f"[gswap] {key}#{i}<->#{j}", gsw)
    states = sorted({k[0] for k in keys})
    for s in states:
        evs = [e for e in events if (s, e) in t]
        for e1 in evs:
            for e2 in evs:
                if e1 == e2 or t[(s, e1)] == t[(s, e2)]:
                    continue
                def xe(tt, s=s, e1=e1, e2=e2):
                    tt[(s, e1)] = copy.deepcopy(tt[(s, e2)])
                yield (f"[xevent] ({s},{e1}) := ({s},{e2})", xe)
                if e1 < e2:
                    def es(tt, s=s, e1=e1, e2=e2):
                        tt[(s, e1)], tt[(s, e2)] = tt[(s, e2)], tt[(s, e1)]
                    yield (f"[eswap] ({s},{e1}) <-> ({s},{e2})", es)

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
            if tried % 200 == 0:
                fo.write(f"# {tried} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

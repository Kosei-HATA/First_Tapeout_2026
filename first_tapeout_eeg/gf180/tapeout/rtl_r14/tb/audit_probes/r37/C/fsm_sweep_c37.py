#!/usr/bin/env python3
"""audit 37, auditor C: single edits of fsm_spec's SEQ and SPI tables (the classes the brief names): add / remove /
replace one action, change one next state, refuse a branch (CFG_ERR or STATE_ERR; SPI: each flag), rewrite a guard
(negation, ALWAYS, one literal, one conjunct dropped), IGN <-> IMP and a cell to IGN / IMP / a no-op branch, and one
event moved in SEQ_PRIORITY. Each edit: fsm_sweep3's early-stop checks, then run_checks; a passing edit is compared with
the original by behaviour signatures (fsm_sweep_sig.py). Usage: <spec dir> <out> [part npart]"""
import copy, os, sys, time, itertools
SPEC, OUT = sys.argv[1], sys.argv[2]
PART, NPART = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, 1)
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "fsm_sweep3.py")).read().replace("\nmain()\n", "\n")
sys.argv = ["x", SPEC, "/dev/null"]
g = {"__file__": os.path.join(HERE, "fsm_sweep3.py"), "__name__": "s3"}
exec(compile(src, "fsm_sweep3.py", "exec"), g)
F, B, IGN, IMP, ALWAYS = g["F"], g["B"], g["IGN"], g["IMP"], g["ALWAYS"]

def conds_for(M, s, e):
    return g["seq_conds"](s, e) if M is F.SEQ else g["spi_conds"](s, e)

def edits(M):
    t = M["table"]
    acts = sorted(M["actions"])
    names = [x[0] for x in M["states"]]
    flags = ["CFG_ERR", "STATE_ERR"] if M is F.SEQ else ["FRAME_ERR", "CRC_ERR", "ADDR_ERR", "STATE_ERR"]
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list):
            other = IMP if cell == IGN else IGN
            yield (f"{key} {cell} -> {other}", lambda tt, k=key, o=other: tt.__setitem__(k, o))
            yield (f"{key} {cell} -> [no-op branch]", lambda tt, k=key: tt.__setitem__(k, [B(ALWAYS, [])]))
            continue
        yield (f"{key} -> IGN", lambda tt, k=key: tt.__setitem__(k, IGN))
        yield (f"{key} -> IMP", lambda tt, k=key: tt.__setitem__(k, IMP))
        for i, b in enumerate(cell):
            for a in acts:
                if a not in b["actions"]:
                    yield (f"{key}#{i} +{a}", lambda tt, k=key, i=i, a=a: tt[k][i]["actions"].append(a))
            for a in b["actions"]:
                yield (f"{key}#{i} -{a}", lambda tt, k=key, i=i, a=a: tt[k][i]["actions"].remove(a))
                for a2 in acts:
                    if a2 != a and a2 not in b["actions"]:
                        def rep(tt, k=key, i=i, a=a, a2=a2):
                            l = tt[k][i]["actions"]; l[l.index(a)] = a2
                        yield (f"{key}#{i} {a}->{a2}", rep)
            for n in names + [None]:
                if n != b["next"]:
                    yield (f"{key}#{i} next {b['next']}->{n}", lambda tt, k=key, i=i, n=n: tt[k][i].__setitem__("next", n))
            for fl in flags:
                if b["actions"] != [fl] or b["next"] is not None:
                    def refuse(tt, k=key, i=i, fl=fl):
                        tt[k][i]["actions"] = [fl]; tt[k][i]["next"] = None
                    yield (f"{key}#{i} refused with {fl}", refuse)
            gd = b["guard"]
            gs = set()
            if gd != ALWAYS:
                gs |= {f"not ({gd})", ALWAYS}
            for c in conds_for(M, *key):
                gs |= {c, f"not {c}"}
            if " and " in gd and "(" not in gd:
                parts = [p.strip() for p in gd.split(" and ")]
                for j in range(len(parts)):
                    gs.add(" and ".join(parts[:j] + parts[j + 1:]))
            gs.discard(gd)
            for g2 in sorted(gs):
                yield (f"{key}#{i} guard [{gd}] -> [{g2}]", lambda tt, k=key, i=i, g2=g2: tt[k][i].__setitem__("guard", g2))

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
            if tried % 500 == 0:
                fo.write(f"# {tried} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    orig_p = list(F.SEQ_PRIORITY)
    for i, x in enumerate(orig_p):
        for j in range(len(orig_p)):
            if j == i:
                continue
            idx += 1
            if idx % NPART != PART:
                continue
            l = orig_p[:i] + orig_p[i + 1:]; l.insert(j, x)
            F.SEQ_PRIORITY[:] = l
            try:
                judge(f"SEQ_PRIORITY move {x} to {j}: {l}", F.SEQ)
            except Exception as ex:
                fo.write(f"EXC prio {l}: {ex!r}\n")
            finally:
                F.SEQ_PRIORITY[:] = orig_p; tried += 1
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

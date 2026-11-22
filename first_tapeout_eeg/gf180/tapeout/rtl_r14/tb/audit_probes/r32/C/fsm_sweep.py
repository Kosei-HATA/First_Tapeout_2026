#!/usr/bin/env python3
"""Single-edit sweep of fsm_spec.SEQ / SPI tables and SEQ_PRIORITY through the spec checks (early stop), then an
equivalence test of every edit that passes. Usage: fsm_sweep.py <spec dir> <out file> [seq|spi|prio|all]"""
import copy, itertools, os, sys, time
SPEC = sys.argv[1]
OUT = sys.argv[2]
WHAT = sys.argv[3] if len(sys.argv) > 3 else "all"
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import fsm_spec as F

B, IGN, IMP, ALWAYS = F.B, F.IGN, F.IMP, F.ALWAYS

def checks_fast():
    """run_checks, in early-stop order: the first non-empty report ends it"""
    r = F.check_tables(F.SEQ) + F.check_tables(F.SPI)
    if r: return r
    well = True
    for fn in (lambda: F.check_vocab(F.SEQ), lambda: F.check_vocab(F.SPI), F.check_seq_columns,
               F.check_seq_commands, F.check_seq_branches,
               lambda: F.check_graph(F.SEQ, ["IDLE", "RUN"], ("RST",)) + F.check_graph(F.SPI, ["IDLE"], ()),
               lambda: F.check_seq_ticks()[0], lambda: F.check_spi_props()[0], lambda: F.check_spi_frames()[0],
               lambda: F.check_fifo()[0], lambda: F.check_timing()[0]):
        r = fn()
        if r: return r
    return []

def full_checks():
    return F.run_checks(verbose=False)[0]

SEQ_NAMES = [s[0] for s in F.SEQ_STATES]
SPI_NAMES = [s[0] for s in F.SPI_STATES]

def seq_sig():
    out = {}
    timed = {x[0] for x in F.SEQ_STATES if x[4]}
    for s in SEQ_NAMES:
        cases = F.seq_tick_cases(s, timed) if s != "RESET" else []
        cases = cases + [["RST"], ["RST", "OUT"], ["OUT"], ["REL"]] + [[c] for c in F.SEQ_COMMANDS]
        for present in cases:
            if not all(F.seq_possible(s, e) for e in present):
                continue
            for vals in itertools.product((0, 1), repeat=len(F.SEQ_CONDS)):
                env = dict(zip(F.SEQ_CONDS, vals))
                try:
                    nxt, acts = F.seq_tick(s, list(present), env)
                except Exception as ex:
                    nxt, acts = "EXC", [repr(ex)]
                out[(s, tuple(present), vals)] = (nxt, tuple(sorted(acts)))
    return out

def spi_sig():
    out = {}
    for kind, crc_en, env, nbytes, extra in F.spi_frame_cases():
        tr = []
        try:
            r = F.spi_walk(nbytes, extra, env, trace=tr)
        except Exception as ex:
            r = ("EXC", repr(ex))
        key = (kind, crc_en, tuple(sorted(env.items())), nbytes, extra)
        out[key] = (None if r is None else r[1], tuple((e, tuple(sorted(a))) for e, a in tr))
    return out

def guards(conds):
    g = {ALWAYS}
    for c in conds:
        g |= {c, f"not {c}"}
    for c, d in itertools.combinations(conds, 2):
        g |= {f"{c} and {d}", f"{c} and not {d}", f"not {c} and {d}", f"not {c} and not {d}", f"{c} or {d}",
              f"not ({c} and {d})", f"{c} or not {d}", f"not {c} or {d}"}
    return sorted(g)

def edits(M, names, actions, conds_for):
    t = M["table"]
    for key in sorted(t, key=str):
        cell = t[key]
        s, e = key
        if isinstance(cell, list):
            yield (f"{key} -> IGN", lambda tt, k=key: tt.__setitem__(k, IGN))
            yield (f"{key} -> IMP", lambda tt, k=key: tt.__setitem__(k, IMP))
            for i, b in enumerate(cell):
                if len(cell) > 1:
                    yield (f"{key}#{i} removed", lambda tt, k=key, i=i: tt[k].pop(i))
                for a in b["actions"]:
                    yield (f"{key}#{i} -{a}", lambda tt, k=key, i=i, a=a: tt[k][i]["actions"].remove(a))
                    for a2 in actions:
                        if a2 not in b["actions"]:
                            yield (f"{key}#{i} {a}->{a2}", lambda tt, k=key, i=i, a=a, a2=a2:
                                   tt[k][i]["actions"].__setitem__(tt[k][i]["actions"].index(a), a2))
                for a2 in actions:
                    if a2 not in b["actions"]:
                        yield (f"{key}#{i} +{a2}", lambda tt, k=key, i=i, a2=a2: tt[k][i]["actions"].append(a2))
                for n in names + [None]:
                    if n != b["next"]:
                        yield (f"{key}#{i} next {b['next']}->{n}", lambda tt, k=key, i=i, n=n: tt[k][i].__setitem__("next", n))
                for fl in ("CFG_ERR", "STATE_ERR", "FRAME_ERR", "ADDR_ERR"):
                    if fl in actions and b["actions"] != [fl]:
                        yield (f"{key}#{i} refused {fl}", lambda tt, k=key, i=i, fl=fl: tt[k].__setitem__(i, B(tt[k][i]["guard"], [fl])))
                for g in guards(conds_for(s, e)):
                    if g != b["guard"]:
                        yield (f"{key}#{i} guard [{b['guard']}]->[{g}]", lambda tt, k=key, i=i, g=g: tt[k][i].__setitem__("guard", g))
            if len(cell) == 2:
                yield (f"{key} branches swapped next", lambda tt, k=key: (lambda a, b_: (a.__setitem__("next", b_["next"]), b_.__setitem__("next", a["next"])))(*[dict(x) for x in tt[k]]) )
        elif cell == IGN:
            yield (f"{key} IGN -> IMP", lambda tt, k=key: tt.__setitem__(k, IMP))
            for fl in ("CFG_ERR", "STATE_ERR", "FRAME_ERR", "ADDR_ERR"):
                if fl in actions:
                    yield (f"{key} IGN -> {fl}", lambda tt, k=key, fl=fl: tt.__setitem__(k, [B(ALWAYS, [fl])]))
            for n in names:
                if n != s:
                    yield (f"{key} IGN -> next {n}", lambda tt, k=key, n=n: tt.__setitem__(k, [B(ALWAYS, [], n)]))
        elif cell == IMP:
            yield (f"{key} IMP -> IGN", lambda tt, k=key: tt.__setitem__(k, IGN))

def seq_conds(s, e):
    return list(F.SEQ_CONDS)

def spi_conds(s, e):
    if e == "CSR":
        cell = F.SPI["table"].get((s, e))
        vs = set()
        if isinstance(cell, list):
            for b in cell:
                vs |= set(F.guard_vars(b["guard"]))
        return sorted(vs | {"mid", "crc_en"})
    allowed = F.SPI_EVENT_CONDS.get(e)
    return sorted(allowed) if allowed else []

def main():
    t0 = time.time()
    assert not full_checks(), "the unmutated spec has violations"
    sig0 = {"SEQ": seq_sig(), "SPI": spi_sig()}
    res = {"tried": 0, "pass": []}
    fo = open(OUT, "w")
    def one(M, label, apply):
        orig = M["table"]
        M["table"] = copy.deepcopy(orig)
        try:
            apply(M["table"])
            rep = checks_fast()
            if not rep:
                rep2 = full_checks()
                if rep2:
                    fo.write(f"FASTSTOP-DIFF {M['name']} {label}: full check found {rep2[0][:100]}\n")
                    return
                s = seq_sig() if M is F.SEQ else spi_sig()
                eq = (s == sig0[M["name"]])
                diff = [] if eq else [k for k in s if s[k] != sig0[M["name"]].get(k)][:3]
                res["pass"].append((M["name"], label, eq))
                fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {M['name']} {label}" + ("" if eq else f" e.g. {diff[:2]}") + "\n")
                fo.flush()
        except Exception as ex:
            fo.write(f"EXC {M['name']} {label}: {ex!r}\n")
        finally:
            M["table"] = orig
            res["tried"] += 1
    if WHAT in ("seq", "all"):
        for label, ap in edits(F.SEQ, SEQ_NAMES, list(F.SEQ_ACTIONS), seq_conds):
            one(F.SEQ, label, ap)
        fo.write(f"# SEQ done: {res['tried']} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    n_seq = res["tried"]
    if WHAT in ("spi", "all"):
        for label, ap in edits(F.SPI, SPI_NAMES, list(F.SPI_ACTIONS), spi_conds):
            one(F.SPI, label, ap)
        fo.write(f"# SPI done: {res['tried'] - n_seq} edits, {time.time() - t0:.0f} s\n"); fo.flush()
    if WHAT in ("prio", "all"):
        orig = list(F.SEQ_PRIORITY)
        n0 = res["tried"]
        for i, x in enumerate(orig):
            for j in range(len(orig)):
                if j == i: continue
                p = orig[:i] + orig[i + 1:]
                p.insert(j, x)
                F.SEQ_PRIORITY[:] = p
                try:
                    rep = checks_fast()
                    if not rep and not full_checks():
                        eq = seq_sig() == sig0["SEQ"]
                        res["pass"].append(("PRIO", str(p), eq))
                        fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} PRIO {p}\n")
                finally:
                    F.SEQ_PRIORITY[:] = orig
                    res["tried"] += 1
        fo.write(f"# PRIO done: {res['tried'] - n0} moves\n")
    neq = [p for p in res["pass"] if not p[2]]
    fo.write(f"# total {res['tried']} edits, {len(res['pass'])} pass the checks, {len(neq)} of them not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

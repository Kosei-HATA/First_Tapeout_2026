#!/usr/bin/env python3
"""New single-edit classes of fsm_spec (audit 33, C) not in the round-32 sweep: real branch swaps (next, actions, guard;
the round-32 tool's 'branches swapped next' edited a copy, a no-op), branch order reversed, 3-literal guard rewrites,
SEQ_STATES attribute edits (AFE_RST, timer, parent, code), TIMING edits, SAMPLE_BYTES edits.
Each edit runs fsm_spec.run_checks; a passing edit is compared with the original by seq_sig / spi_sig.
Usage: fsm_sweep2.py <spec dir> <out file>"""
import copy, itertools, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm_sweep_sig.py")).read())   # kept beside it (round 36)

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

def table_edits(M, conds_for):
    t = M["table"]
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list) or len(cell) < 2:
            continue
        n = len(cell)
        for i, j in itertools.combinations(range(n), 2):
            for fld in ("next", "actions", "guard"):
                def ap(tt, k=key, i=i, j=j, fld=fld):
                    a, b = tt[k][i], tt[k][j]
                    a[fld], b[fld] = copy.deepcopy(b[fld]), copy.deepcopy(a[fld])
                yield (f"{key} #{i}<->#{j} {fld} swapped", ap)
        yield (f"{key} branch order reversed", lambda tt, k=key: tt[k].reverse())
        s, e = key
        cs = conds_for(s, e)
        for i, b in enumerate(cell):
            for c1, c2, c3 in itertools.combinations(cs, 3):
                for n1, n2, n3 in itertools.product(("", "not "), repeat=3):
                    g = f"{n1}{c1} and {n2}{c2} and {n3}{c3}"
                    if g != b["guard"]:
                        yield (f"{key}#{i} guard -> [{g}]", lambda tt, k=key, i=i, g=g: tt[k][i].__setitem__("guard", g))
            for c1, c2, c3 in itertools.permutations(cs, 3):
                for g in (f"{c1} and ({c2} or {c3})", f"{c1} or ({c2} and {c3})", f"not ({c1} and {c2}) and {c3}",
                          f"({c1} and {c2}) or not {c3}"):
                    if g != b["guard"]:
                        yield (f"{key}#{i} guard -> [{g}]", lambda tt, k=key, i=i, g=g: tt[k][i].__setitem__("guard", g))

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
    assert not full_checks()
    sig0 = {"SEQ": seq_sig(), "SPI": spi_sig()}
    fo = open(OUT, "w")
    tried = npass = nneq = 0
    def judge(label, M):
        nonlocal npass, nneq
        if checks_fast():
            return
        rep = full_checks()
        if rep:
            return
        s = seq_sig() if M is F.SEQ else spi_sig()
        eq = s == sig0[M["name"]]
        npass += 1; nneq += (not eq)
        diff = [] if eq else [k for k in s if s[k] != sig0[M["name"]].get(k)][:2]
        fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {M['name']} {label}" + ("" if eq else f" e.g. {diff}") + "\n"); fo.flush()
    for M, cf in ((F.SEQ, seq_conds), (F.SPI, spi_conds)):
        n0 = tried
        for label, ap in table_edits(M, cf):
            orig = M["table"]; M["table"] = copy.deepcopy(orig)
            try:
                ap(M["table"]); judge(label, M)
            except Exception as ex:
                fo.write(f"EXC {M['name']} {label}: {ex!r}\n")
            finally:
                M["table"] = orig; tried += 1
        fo.write(f"# {M['name']} table edits: {tried - n0}, {time.time() - t0:.0f} s\n"); fo.flush()
    # SEQ_STATES attributes
    n0 = tried
    orig_states = copy.deepcopy(F.SEQ_STATES)
    timers = sorted({s[4] for s in orig_states if s[4]})
    parents = [None, "ACTIVE", "AFE_ON"]
    codes = [s[1] for s in orig_states]
    def st_edit(label, idx, pos, val):
        nonlocal tried
        F.SEQ_STATES[:] = copy.deepcopy(orig_states)
        r = list(F.SEQ_STATES[idx]); r[pos] = val; F.SEQ_STATES[idx] = tuple(r)
        try:
            judge(label, F.SEQ)
        except Exception as ex:
            fo.write(f"EXC SEQ_STATES {label}: {ex!r}\n")
        finally:
            F.SEQ_STATES[:] = copy.deepcopy(orig_states); tried += 1
    for idx, s in enumerate(orig_states):
        st_edit(f"SEQ_STATES {s[0]} AFE_RST {s[3]}->{1 - s[3]}", idx, 3, 1 - s[3])
        for tm in [None] + timers:
            if tm != s[4]:
                st_edit(f"SEQ_STATES {s[0]} timer {s[4]}->{tm}", idx, 4, tm)
        for p in parents:
            if p != s[2]:
                st_edit(f"SEQ_STATES {s[0]} parent {s[2]}->{p}", idx, 2, p)
        for c in codes + [9, 15]:
            if c != s[1]:
                st_edit(f"SEQ_STATES {s[0]} code {s[1]}->{c}", idx, 1, c)
    fo.write(f"# SEQ_STATES edits: {tried - n0}\n")
    # TIMING
    n0 = tried
    if hasattr(F, "TIMING"):
        orig_t = copy.deepcopy(F.TIMING)
        def leaves(d, path=()):
            if isinstance(d, dict):
                for k, v in d.items():
                    yield from leaves(v, path + (k,))
            elif isinstance(d, (tuple, list)):
                for i, v in enumerate(d):
                    yield from leaves(v, path + (i,))
            elif isinstance(d, (int, float)) and not isinstance(d, bool):
                yield path, d
        def setp(d, path, v):
            for k in path[:-1]:
                d = d[k]
            if isinstance(d, tuple):
                raise TypeError("tuple")
            d[path[-1]] = v
        def set_path(root, path, v):
            # rebuild tuples on the way
            if len(path) == 1:
                if isinstance(root, tuple):
                    l = list(root); l[path[0]] = v; return tuple(l)
                root[path[0]] = v; return root
            child = set_path(root[path[0]], path[1:], v)
            if isinstance(root, tuple):
                l = list(root); l[path[0]] = child; return tuple(l)
            root[path[0]] = child; return root
        for path, v in list(leaves(orig_t)):
            cands = {v * 2, v / 2 if isinstance(v, float) else v // 2, v + 1, v - 1} - {v}
            for nv in cands:
                F.TIMING.clear(); F.TIMING.update(set_path(copy.deepcopy(orig_t), path, nv))
                try:
                    judge(f"TIMING {path} {v}->{nv}", F.SEQ)
                except Exception as ex:
                    fo.write(f"EXC TIMING {path}: {ex!r}\n")
                finally:
                    F.TIMING.clear(); F.TIMING.update(copy.deepcopy(orig_t)); tried += 1
    fo.write(f"# TIMING edits: {tried - n0}\n")
    n0 = tried
    orig_sb = copy.deepcopy(F.SAMPLE_BYTES)
    for i, (ident, lab, nb) in enumerate(orig_sb):
        for nv in (nb - 1, nb + 1):
            if nv < 1: continue
            F.SAMPLE_BYTES[:] = copy.deepcopy(orig_sb); F.SAMPLE_BYTES[i] = (ident, lab, nv)
            try:
                judge(f"SAMPLE_BYTES {ident} {nb}->{nv}", F.SPI)
            except Exception as ex:
                fo.write(f"EXC SAMPLE_BYTES {ident}: {ex!r}\n")
            finally:
                F.SAMPLE_BYTES[:] = copy.deepcopy(orig_sb); tried += 1
    fo.write(f"# SAMPLE_BYTES edits: {tried - n0}\n")
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} of them not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()

main()

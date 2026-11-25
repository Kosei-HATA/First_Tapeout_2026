#!/usr/bin/env python3
"""audit 44, auditor C: single edits of fsm_spec's tables in classes the earlier sweeps (rounds 32-43) did not make:
  code    SEQ_STATES: two states' STATE codes exchanged (36), or one state's code moved to an unused value 9..15 (63)
  sorder  SPI_STATES: two adjacent rows exchanged (the order of the state list)
  eorder  SEQ_EVENTS / SPI_EVENTS: two adjacent events exchanged
  corder  SEQ_COMMANDS: two adjacent commands exchanged; one command removed
  cdel    SEQ_CONDS / SPI_CONDS / SEQ_ACTIONS / SPI_ACTIONS: one entry removed (the table then names an undefined word)
  poss    seq_possible / spi_possible: one (state, event) made possible or impossible against the function
Each edit runs fsm_spec.run_checks, then regmap.check (the STATE field follows the codes), then both self-tests' clean
runs are implied (an edit is only reported if both checks pass). A passing edit is compared with the original by the
behaviour signatures of the earlier rounds (fsm_sweep_sig.py: seq_sig / spi_sig) and, for the codes, by the code map.
Usage: fsm_sweep_c44.py <spec dir> <out file>"""
import copy, io, contextlib, itertools, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
import regmap as R
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm_sweep_sig.py")).read())


def checks():
    with contextlib.redirect_stdout(io.StringIO()):
        a = F.run_checks(verbose=False)[0]
        if a:
            return a
        return R.check(verbose=False)


def edits():
    st = F.SEQ_STATES
    idx = [k for k, x in enumerate(st) if x[1] is not None]
    for i, j in itertools.combinations(idx, 2):
        def ap(i=i, j=j):
            a, b = st[i], st[j]
            st[i] = (a[0], b[1]) + a[2:]
            st[j] = (b[0], a[1]) + b[2:]
            return lambda: (st.__setitem__(i, a), st.__setitem__(j, b))
        yield f"[code] {st[i][0]} {st[i][1]} <-> {st[j][0]} {st[j][1]}", ap
    for i in idx:
        for v in range(9, 16):
            def ap(i=i, v=v):
                a = st[i]
                st[i] = (a[0], v) + a[2:]
                return lambda: st.__setitem__(i, a)
            yield f"[code] {st[i][0]} {st[i][1]} -> {v}", ap
    for L, nm in ((F.SPI_STATES, "SPI_STATES"), (F.SEQ_EVENTS, "SEQ_EVENTS"), (F.SPI_EVENTS, "SPI_EVENTS"),
                  (F.SEQ_COMMANDS, "SEQ_COMMANDS"), (F.SEQ_STATES, "SEQ_STATES")):
        for k in range(len(L) - 1):
            def ap(L=L, k=k):
                L[k], L[k + 1] = L[k + 1], L[k]
                return lambda: L.__setitem__(slice(k, k + 2), [L[k + 1], L[k]])
            yield f"[order] {nm} rows {k} <-> {k + 1}", ap
    for k in range(len(F.SEQ_COMMANDS)):
        def ap(k=k):
            old = list(F.SEQ_COMMANDS)
            del F.SEQ_COMMANDS[k]
            return lambda: F.SEQ_COMMANDS.__setitem__(slice(None), old)
        yield f"[corder] SEQ_COMMANDS drop {F.SEQ_COMMANDS[k]}", ap
    for D, nm in ((F.SEQ_CONDS, "SEQ_CONDS"), (F.SPI_CONDS, "SPI_CONDS"), (F.SEQ_ACTIONS, "SEQ_ACTIONS"),
                  (F.SPI_ACTIONS, "SPI_ACTIONS")):
        for key in list(D):
            def ap(D=D, key=key):
                old = dict(D)
                del D[key]
                def undo():
                    D.clear(); D.update(old)
                return undo
            yield f"[cdel] {nm} drop {key}", ap
    for M, fnm in ((F.SEQ, "seq_possible"), (F.SPI, "spi_possible")):
        names = [x[0] for x in M["states"]]
        evs = [e for e, _ in M["events"]]
        orig = M["possible"]
        for s in names:
            for e in evs:
                def ap(M=M, s=s, e=e, orig=orig):
                    M["possible"] = lambda s2, e2, s=s, e=e: (not orig(s2, e2)) if (s2, e2) == (s, e) else orig(s2, e2)
                    g = globals_of(M)
                    return lambda: M.__setitem__("possible", orig)
                yield f"[poss] {fnm}({s}, {e}) flipped to {not orig(s, e)}", ap


def globals_of(M):
    return None


def main():
    t0 = time.time()
    assert not checks(), "the unmutated specification fails"
    sig0 = (seq_sig(), spi_sig())
    codes0 = {x[0]: x[1] for x in F.SEQ_STATES}
    n = npass = 0
    with open(OUT, "w") as fo:
        for label, ap in edits():
            n += 1
            undo = ap()
            try:
                rep = checks()
            except Exception as ex:
                rep = [f"exception {ex!r}"]
            if not rep:
                npass += 1
                try:
                    s1 = (seq_sig(), spi_sig())
                    eq = s1 == sig0
                except Exception as ex:
                    eq = f"sig exception {ex!r}"
                codes1 = {x[0]: x[1] for x in F.SEQ_STATES}
                fo.write(f"PASS {label}: behaviour {'same' if eq is True else 'DIFFERENT' if eq is False else eq}; "
                         f"codes {'same' if codes1 == codes0 else 'CHANGED'}\n")
            else:
                fo.write(f"caught {label}: {rep[0][:150]}\n")
            fo.flush()
            undo()
        assert not checks(), "the specification was not restored"
        fo.write(f"# {n} edits, {npass} pass both checks, {time.time() - t0:.0f} s\n")


main()

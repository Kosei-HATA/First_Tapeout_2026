#!/usr/bin/env python3
"""Audit 45, auditor C: single edits of fsm_spec's SEQ and SPI tables and SEQ_PRIORITY through fsm_spec's checks.
Classes (per branch): drop / add / replace one action, change the next state (every state and None), refuse (the
branch's actions -> one refusal flag, staying); (per cell) IGN <-> IMP, a list -> IGN or IMP, IGN -> one action;
(per cell with >= 2 branches) two branches' guards swapped, one condition name renamed to another in the whole cell;
(SEQ_PRIORITY) every element moved to every position. A passing edit is compared with the original by a behaviour
signature (every state x event set x condition values for SEQ; every frame case's action trace for SPI).
usage: fsm_sweep45.py <spec dir> <out file> [classes,comma separated]"""
import copy, itertools, os, sys, time
SPEC, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F  # noqa: E402
IGN, IMP, ALWAYS, B = F.IGN, F.IMP, F.ALWAYS, F.B

SEQ_NAMES = [s[0] for s in F.SEQ_STATES]
SPI_NAMES = [s[0] for s in F.SPI_STATES]


def seq_sig():
    out = {}
    timed = {x[0] for x in F.SEQ_STATES if x[4]}
    for s in SEQ_NAMES:
        cases = F.seq_tick_cases(s, timed) if s != "RESET" else []
        cases = cases + [["RST"], ["RST", "OUT"], ["OUT"], ["REL"]] + [[c] for c in F.SEQ_COMMANDS]
        for present in cases:
            for vals in itertools.product((0, 1), repeat=len(F.SEQ_CONDS)):
                env = dict(zip(F.SEQ_CONDS, vals))
                try:
                    nxt, acts = F.seq_tick(s, list(present), env)
                except Exception as ex:   # noqa: BLE001
                    nxt, acts = "EXC", [type(ex).__name__]
                out[(s, tuple(present), vals)] = (nxt, tuple(sorted(acts)))
    return out


def spi_sig():
    out = {}
    for kind, crc_en, env, nbytes, extra in F.spi_frame_cases():
        tr = []
        try:
            r = F.spi_walk(nbytes, extra, env, trace=tr)
        except Exception as ex:   # noqa: BLE001
            r = ("EXC", type(ex).__name__)
        out[(kind, crc_en, tuple(sorted(env.items())), nbytes, extra)] = (None if r is None else r[1],
                                                                          tuple((e, tuple(a)) for e, a in tr))
    return out


def fast_checks():
    r = F.check_tables(F.SEQ) + F.check_tables(F.SPI)
    if r:
        return r
    for fn in (lambda: F.check_vocab(F.SEQ), lambda: F.check_vocab(F.SPI), F.check_seq_columns,
               F.check_seq_commands, F.check_seq_branches,
               lambda: F.check_graph(F.SEQ, ["IDLE", "RUN"], ("RST",)) + F.check_graph(F.SPI, ["IDLE"], ()),
               lambda: F.check_seq_ticks()[0], lambda: F.check_spi_props()[0], lambda: F.check_spi_frames()[0],
               lambda: F.check_fifo()[0], lambda: F.check_timing()[0]):
        r = fn()
        if r:
            return r
    return F.run_checks(verbose=False)[0]          # the whole check (doc blocks included) for a passing edit


SEQ0 = copy.deepcopy(F.SEQ["table"])
SPI0 = copy.deepcopy(F.SPI["table"])
PRIO0 = list(F.SEQ_PRIORITY)
assert not F.run_checks(verbose=False)[0], "the unedited spec must pass"
SIG_SEQ0, SIG_SPI0 = seq_sig(), spi_sig()


def edits():
    for mach, T0, names, vocab, refusals in (("SEQ", SEQ0, SEQ_NAMES, sorted(F.SEQ_ACTIONS), ("CFG_ERR", "STATE_ERR")),
                                             ("SPI", SPI0, SPI_NAMES, sorted(F.SPI_ACTIONS),
                                              ("FRAME_ERR", "ADDR_ERR", "STATE_ERR", "CRC_ERR"))):
        conds = sorted(F.SEQ_CONDS if mach == "SEQ" else F.SPI_CONDS)
        for key in sorted(T0, key=lambda k: (names.index(k[0]), k[1])):
            cell = T0[key]
            tag = f"{mach} {key[0]}/{key[1]}"
            if isinstance(cell, list):
                for bi, b in enumerate(cell):
                    bt = f"{tag}#{bi}[{b['guard']}]"
                    for a in b["actions"]:
                        yield "drop", mach, key, (bi, "actions", [x for x in b["actions"] if x != a]), f"{bt} drop {a}"
                    for x in vocab:
                        if x not in b["actions"]:
                            yield "add", mach, key, (bi, "actions", b["actions"] + [x]), f"{bt} add {x}"
                    for a in b["actions"]:
                        for x in vocab:
                            if x not in b["actions"]:
                                yield "repl", mach, key, (bi, "actions", [x if y == a else y for y in b["actions"]]), \
                                    f"{bt} {a}->{x}"
                    for s in names + [None]:
                        if s != b["next"]:
                            yield "next", mach, key, (bi, "next", s), f"{bt} next {b['next']}->{s}"
                    for r in refusals:
                        if b["actions"] != [r] or b["next"] is not None:
                            yield "refuse", mach, key, (bi, "refuse", r), f"{bt} refused with {r}"
                yield "cell", mach, key, ("cell", IGN), f"{tag} -> IGN"
                yield "cell", mach, key, ("cell", IMP), f"{tag} -> IMP"
                if len(cell) >= 2:
                    for i, j in itertools.combinations(range(len(cell)), 2):
                        yield "gswap", mach, key, ("gswap", i, j), f"{tag} guards of #{i} and #{j} swapped"
                    used = sorted({v for b in cell for v in F.guard_vars(b["guard"])})
                    for v in used:
                        for w in conds:
                            if w not in used:
                                yield "grename", mach, key, ("grename", v, w), f"{tag} condition {v} -> {w}"
            else:
                yield "cell", mach, key, ("cell", IMP if cell == IGN else IGN), f"{tag} {('IGN' if cell == IGN else 'IMP')} swapped"
                for x in vocab:
                    yield "cellact", mach, key, ("cell", [B(ALWAYS, [x])]), f"{tag} {('IGN' if cell == IGN else 'IMP')} -> [{x}]"
    for e in PRIO0:
        for pos in range(len(PRIO0)):
            p = [x for x in PRIO0 if x != e]
            p.insert(pos, e)
            if p != PRIO0:
                yield "prio", "PRIO", None, ("prio", p), f"SEQ_PRIORITY {e} to position {pos}: {p}"


def apply(mach, key, spec):
    if mach == "PRIO":
        F.SEQ_PRIORITY[:] = spec[1]
        return
    T = copy.deepcopy(SEQ0 if mach == "SEQ" else SPI0)
    if spec[0] == "cell":
        T[key] = spec[1]
    elif spec[0] == "gswap":
        i, j = spec[1], spec[2]
        T[key][i]["guard"], T[key][j]["guard"] = T[key][j]["guard"], T[key][i]["guard"]
    elif spec[0] == "grename":
        import re
        for b in T[key]:
            b["guard"] = re.sub(rf"\b{spec[1]}\b", spec[2], b["guard"])
    else:
        bi, field, val = spec
        if field == "refuse":
            T[key][bi]["actions"], T[key][bi]["next"] = [val], None
        else:
            T[key][bi][field] = val
    (F.SEQ if mach == "SEQ" else F.SPI)["table"] = T


def restore():
    F.SEQ["table"], F.SPI["table"] = SEQ0, SPI0
    F.SEQ_PRIORITY[:] = PRIO0


t0 = time.time()
n = npass = 0
with open(OUT, "w") as fo:
    for cls, mach, key, spec, txt in edits():
        if ONLY and cls not in ONLY:
            continue
        n += 1
        try:
            apply(mach, key, spec)
            try:
                r = fast_checks()
            except Exception as ex:   # noqa: BLE001
                r = [f"EXCEPTION {type(ex).__name__}: {ex}"]
            if not r:
                npass += 1
                same = (seq_sig() == SIG_SEQ0) and (spi_sig() == SIG_SPI0)
                fo.write(f"PASS {'EQUIV' if same else 'NOT-EQUIV'} [{cls}] {txt}\n")
                fo.flush()
        finally:
            restore()
    fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")
print(f"{n} edits, {npass} pass, {time.time() - t0:.0f} s")

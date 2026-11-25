"""Single edits of fsm_spec's SEQ and SPI tables (and SEQ_PRIORITY) through run_checks(); passing edits are compared
with the original by a behaviour signature (SEQ: seq_resolve over every state, tick case and condition value; SPI:
pick() of every cell and condition value, and spi_walk of the frame cases)."""
import copy, itertools, sys, os, io, contextlib, time
SPEC = sys.argv[1]
OUT = sys.argv[2]
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import fsm_spec as FS

B, ALWAYS, IGN, IMP = FS.B, FS.ALWAYS, FS.IGN, FS.IMP
ORIG = {"SEQ": copy.deepcopy(FS.SEQ["table"]), "SPI": copy.deepcopy(FS.SPI["table"])}
ORIG_PRIO = list(FS.SEQ_PRIORITY)

def run():
    # the checks of run_checks in its order, stopping at the first that reports (an edit passes only if none does);
    # check_doc_blocks reads the requirements' markers only (no table), run once at the start
    F = FS
    steps = (lambda: F.check_tables(F.SEQ) + F.check_tables(F.SPI),
             lambda: F.check_vocab(F.SEQ) + F.check_vocab(F.SPI) + F.check_seq_columns(),
             F.check_seq_commands, F.check_seq_branches,
             lambda: F.check_graph(F.SEQ, ["IDLE", "RUN"], ("RST",)) + F.check_graph(F.SPI, ["IDLE"], ()),
             lambda: F.check_seq_ticks()[0], lambda: F.check_spi_props()[0], lambda: F.check_spi_frames()[0],
             lambda: F.check_fifo()[0], lambda: F.check_timing()[0])
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            for st in steps:
                r = st()
                if r:
                    return r
        except Exception as ex:                     # a crash is no pass
            return ["CRASH " + repr(ex)[:100]]
    return []

def seq_sig():
    timed = {x[0] for x in FS.SEQ_STATES if x[4]}
    sig = {}
    for s in (x[0] for x in FS.SEQ_STATES):
        cases = FS.seq_tick_cases(s, timed) + [["RST"], ["RST", "OUT"], ["REL"]]
        for ev in cases:
            for vals in itertools.product((0, 1), repeat=len(FS.SEQ_CONDS)):
                env = dict(zip(FS.SEQ_CONDS, vals))
                try:
                    r = FS.seq_resolve(s, ev, env)
                    sig[(s, tuple(ev), vals)] = (r[0], tuple(sorted(r[1])))
                except Exception as ex:
                    sig[(s, tuple(ev), vals)] = ("ERR", repr(ex)[:40])
    return sig

def spi_sig():
    sig = {}
    t = FS.SPI["table"]
    names = sorted(FS.SPI_CONDS)
    for key in sorted(ORIG["SPI"]):
        cell = t.get(key)
        for vals in itertools.product((0, 1), repeat=len(names)):
            env = dict(zip(names, vals))
            b = FS.pick(cell, env)
            sig[(key, vals)] = b if not isinstance(b, dict) else (tuple(b["actions"]), b["next"])
    return sig

base_seq, base_spi = seq_sig(), spi_sig()

def actions_vocab(M):
    return sorted(FS.SEQ_ACTIONS if M == "SEQ" else FS.SPI_ACTIONS)

def states_of(M):
    return [s[0] for s in (FS.SEQ_STATES if M == "SEQ" else FS.SPI_STATES)]

def conds_of(M):
    return sorted(FS.SEQ_CONDS if M == "SEQ" else FS.SPI_CONDS)

def edits():
    for M in ("SEQ", "SPI"):
        T = ORIG[M]
        acts = actions_vocab(M)
        sts = states_of(M) + [None]
        conds = conds_of(M)
        refuse = ["CFG_ERR", "STATE_ERR"] if M == "SEQ" else ["FRAME_ERR", "STATE_ERR", "ADDR_ERR", "CRC_ERR"]
        for key in sorted(T, key=str):
            cell = T[key]
            if cell in (IGN, IMP) or cell is None:
                yield (M, key, f"{cell} -> {'IMP' if cell == IGN else 'IGN'}", lambda t, k=key, c=cell: t.__setitem__(k, IMP if c == IGN else IGN))
                if cell == IGN:
                    for a in acts:
                        yield (M, key, f"IGN -> [{a}]", lambda t, k=key, a=a: t.__setitem__(k, [B(ALWAYS, [a])]))
                    for s in states_of(M):
                        yield (M, key, f"IGN -> next {s}", lambda t, k=key, s=s: t.__setitem__(k, [B(ALWAYS, [], s)]))
                continue
            yield (M, key, "cell -> IGN", lambda t, k=key: t.__setitem__(k, IGN))
            yield (M, key, "cell -> IMP", lambda t, k=key: t.__setitem__(k, IMP))
            for i, b in enumerate(cell):
                for a in b["actions"]:
                    yield (M, key, f"br{i} remove {a}", lambda t, k=key, i=i, a=a: t[k][i].__setitem__("actions", [x for x in t[k][i]["actions"] if x != a]))
                    for a2 in acts:
                        if a2 not in b["actions"]:
                            yield (M, key, f"br{i} replace {a}->{a2}", lambda t, k=key, i=i, a=a, a2=a2: t[k][i].__setitem__("actions", [a2 if x == a else x for x in t[k][i]["actions"]]))
                for a2 in acts:
                    if a2 not in b["actions"]:
                        yield (M, key, f"br{i} add {a2}", lambda t, k=key, i=i, a2=a2: t[k][i].__setitem__("actions", t[k][i]["actions"] + [a2]))
                for s in sts:
                    if s != b["next"]:
                        yield (M, key, f"br{i} next {b['next']}->{s}", lambda t, k=key, i=i, s=s: t[k][i].__setitem__("next", s))
                for r in refuse:
                    yield (M, key, f"br{i} refuse {r}", lambda t, k=key, i=i, r=r: t[k].__setitem__(i, B(t[k][i]["guard"], [r])))
                g = b["guard"]
                alts = ["1", f"not ({g})"] + [f"({g}) and {c}" for c in conds] + [f"({g}) and not {c}" for c in conds] \
                       + [f"({g}) or {c}" for c in conds] + [f"({g}) or not {c}" for c in conds]
                for g2 in alts:
                    yield (M, key, f"br{i} guard {g!r}->{g2!r}", lambda t, k=key, i=i, g2=g2: t[k][i].__setitem__("guard", g2))
                for j in range(i + 1, len(cell)):
                    yield (M, key, f"swap guards br{i}/br{j}", lambda t, k=key, i=i, j=j: (lambda gi, gj: (t[k][i].__setitem__("guard", gj), t[k][j].__setitem__("guard", gi)))(t[k][i]["guard"], t[k][j]["guard"]))
            if len(cell) == 2:                      # rewrite the pair (g, not g) to (g', not g')
                for c1 in conds:
                    for g2 in (c1,) + tuple(f"{c1} {op} {n}{c2}" for c2 in conds if c2 != c1 for op in ("and", "or") for n in ("", "not ")):
                        yield (M, key, f"pair guard -> {g2!r}", lambda t, k=key, g2=g2: (t[k][0].__setitem__("guard", g2), t[k][1].__setitem__("guard", f"not ({g2})")))
            if len(cell) >= 2:                      # a branch dropped, its guard merged into the next
                for i in range(len(cell)):
                    j = (i + 1) % len(cell)
                    yield (M, key, f"merge br{i} into br{j}", lambda t, k=key, i=i, j=j: (t[k][j].__setitem__("guard", f"({t[k][j]['guard']}) or ({t[k][i]['guard']})"), t[k].pop(i)))

prio_edits = []
for i in range(len(ORIG_PRIO)):
    for j in range(len(ORIG_PRIO)):
        if i != j:
            p = list(ORIG_PRIO); e = p.pop(i); p.insert(j, e)
            if p != ORIG_PRIO and p not in [x[1] for x in prio_edits]:
                prio_edits.append((f"SEQ_PRIORITY {ORIG_PRIO} -> {p}", p))

t0 = time.time()
n = npass = 0
with open(OUT, "w") as fo:
    rep0 = run()
    fo.write(f"baseline: {len(rep0)} violations\n")
    SKIP = ("add", "replace", "next")              # the classes round 45's auditor C ran (2,507 + 1,243 edits)
    for M, key, desc, fn in edits():
        if desc.startswith("br") and desc.split()[1] in SKIP:
            continue
        FS.SEQ["table"] = copy.deepcopy(ORIG["SEQ"]); FS.SPI["table"] = copy.deepcopy(ORIG["SPI"])
        tbl = FS.SEQ["table"] if M == "SEQ" else FS.SPI["table"]
        try:
            fn(tbl)
        except Exception as ex:
            fo.write(f"SKIP {M} {key} {desc}: {ex!r}\n"); continue
        if tbl == ORIG[M]:
            continue                                # a no-op edit (the table unchanged)
        n += 1
        rep = run()
        if not rep:
            npass += 1
            eq = (seq_sig() == base_seq) if M == "SEQ" else (spi_sig() == base_spi)
            fo.write(f"PASS {'equivalent' if eq else 'NOT-EQUIVALENT'} {M} {key} {desc}\n"); fo.flush()
    FS.SEQ["table"] = copy.deepcopy(ORIG["SEQ"]); FS.SPI["table"] = copy.deepcopy(ORIG["SPI"])
    for desc, p in prio_edits:
        FS.SEQ_PRIORITY[:] = p
        n += 1
        rep = run()
        if not rep:
            npass += 1
            eq = seq_sig() == base_seq
            fo.write(f"PASS {'equivalent' if eq else 'NOT-EQUIVALENT'} PRIO {desc}\n"); fo.flush()
    FS.SEQ_PRIORITY[:] = ORIG_PRIO
    fo.write(f"done: {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")

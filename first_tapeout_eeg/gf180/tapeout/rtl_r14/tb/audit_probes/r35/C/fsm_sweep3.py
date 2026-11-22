#!/usr/bin/env python3
"""Audit 35, auditor C: single-edit classes of fsm_spec's tables not in the round-32 / 33 sweeps:
  ins   a new branch inserted into a cell (first or last), guard = one literal or a two-literal conjunction of the
        conditions the event may use, outcome = a flag alone, nothing, or the outcome of another branch of the cell
        (or of the same event's cell in another state)
  copy  a cell replaced by the cell of the same event in another state (SEQ and SPI)
  comp  a branch's next state set to a composite (ACTIVE, AFE_ON, FRAME)
  dup   a cell's branch duplicated in front of itself with one literal of its guard dropped
  sb    SAMPLE_BYTES: two entries swapped
  prio  SEQ_PRIORITY / SEQ_COMMANDS: an entry removed or doubled
Each edit runs the checks (early stop, then fsm_spec.run_checks); a passing edit is compared with the original by the
behaviour signature (seq_sig / spi_sig: every state, event set and condition value). Usage: <spec dir> <out file>"""
import copy, itertools, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3].split(",") if len(sys.argv) > 3 else None
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm_sweep_sig.py")).read())
B, IGN, IMP, ALWAYS = F.B, F.IGN, F.IMP, F.ALWAYS


SPI_FIRST = False


def checks_fast():
    if SPI_FIRST:                                   # an SPI edit: its own checks first (early stop sooner)
        for fn in (lambda: F.check_tables(F.SPI), lambda: F.check_vocab(F.SPI),
                   lambda: F.check_graph(F.SPI, ["IDLE"], ()), lambda: F.check_spi_props()[0]):
            r = fn()
            if r:
                return r
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
    return []


def full_checks():
    return F.run_checks(verbose=False)[0]


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


def small_guards(conds):
    g = []
    for c in conds:
        g += [c, f"not {c}"]
    for c, d in itertools.combinations(conds, 2):
        for nc, nd in itertools.product(("", "not "), repeat=2):
            g.append(f"{nc}{c} and {nd}{d}")
    return g


def flags_of(M):
    return sorted(a for a in M["actions"] if a in F.FLAGS)


def outcomes(M, key):
    """(actions, next) outcomes to give an inserted branch"""
    s, e = key
    out = {((), None)}
    for fl in flags_of(M):
        out.add(((fl,), None))
    for (s2, e2), cell in M["table"].items():
        if e2 == e and isinstance(cell, list):
            for b in cell:
                out.add((tuple(b["actions"]), b["next"]))
    return sorted(out, key=str)


def ins_edits(M, conds_for):
    t = M["table"]
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list):
            continue
        s, e = key
        for g in small_guards(conds_for(s, e)):
            for acts, nxt in outcomes(M, key):
                for pos in (0, len(cell)):
                    def ap(tt, k=key, g=g, acts=acts, nxt=nxt, pos=pos):
                        tt[k].insert(pos, B(g, list(acts), nxt))
                    yield (f"{key} insert@{pos} [{g}] {list(acts)} -> {nxt}", ap)


def copy_edits(M):
    t = M["table"]
    names = [x[0] for x in M["states"]]
    for key in sorted(t, key=str):
        s, e = key
        for s2 in names:
            if s2 == s or (s2, e) not in t:
                continue
            if t[(s2, e)] == t[key]:
                continue
            def ap(tt, k=key, src=(s2, e)):
                tt[k] = copy.deepcopy(tt[src])
            yield (f"{key} := cell of {(s2, e)}", ap)


def comp_edits(M):
    t = M["table"]
    comps = sorted(M["composites"])
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            for c in comps:
                def ap(tt, k=key, i=i, c=c):
                    tt[k][i]["next"] = c
                yield (f"{key}#{i} next {b['next']} -> composite {c}", ap)


def dup_edits(M):
    t = M["table"]
    for key in sorted(t, key=str):
        cell = t[key]
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            g = b["guard"]
            parts = [p.strip() for p in g.split(" and ")] if " and " in g and "(" not in g else []
            for j in range(len(parts)):
                g2 = " and ".join(parts[:j] + parts[j + 1:])
                def ap(tt, k=key, i=i, g2=g2):
                    nb = copy.deepcopy(tt[k][i]); nb["guard"] = g2
                    tt[k].insert(i, nb)
                yield (f"{key}#{i} duplicated in front with guard [{g2}]", ap)


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
        if full_checks():
            return
        s = seq_sig() if M is F.SEQ else spi_sig()
        eq = s == sig0[M["name"]]
        npass += 1
        nneq += (not eq)
        diff = [] if eq else [k for k in s if s[k] != sig0[M["name"]].get(k)][:2]
        fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {M['name']} {label}" + ("" if eq else f" e.g. {diff}") + "\n")
        fo.flush()

    def table_run(M, gen, tag):
        nonlocal tried
        n0 = tried
        for label, ap in gen:
            orig = M["table"]
            M["table"] = copy.deepcopy(orig)
            try:
                ap(M["table"])
                judge(f"[{tag}] {label}", M)
            except Exception as ex:
                fo.write(f"EXC {M['name']} [{tag}] {label}: {ex!r}\n")
            finally:
                M["table"] = orig
                tried += 1
        fo.write(f"# {M['name']} {tag}: {tried - n0} edits, {time.time() - t0:.0f} s\n")
        fo.flush()

    want = lambda k: ONLY is None or k in ONLY
    global SPI_FIRST
    for M, cf in ((F.SEQ, seq_conds), (F.SPI, spi_conds)):
        SPI_FIRST = M is F.SPI
        if want("seq_skip") and M is F.SEQ:
            continue
        if want("copy"):
            table_run(M, copy_edits(M), "copy")
        if want("comp"):
            table_run(M, comp_edits(M), "comp")
        if want("dup"):
            table_run(M, dup_edits(M), "dup")
        if want("ins"):
            table_run(M, ins_edits(M, cf), "ins")
    if want("sb"):
        orig_sb = copy.deepcopy(F.SAMPLE_BYTES)
        n0 = tried
        for i, j in itertools.combinations(range(len(orig_sb)), 2):
            F.SAMPLE_BYTES[:] = copy.deepcopy(orig_sb)
            F.SAMPLE_BYTES[i], F.SAMPLE_BYTES[j] = F.SAMPLE_BYTES[j], F.SAMPLE_BYTES[i]
            try:
                judge(f"[sb] SAMPLE_BYTES {orig_sb[i][0]}<->{orig_sb[j][0]}", F.SPI)
            except Exception as ex:
                fo.write(f"EXC [sb] {i}<->{j}: {ex!r}\n")
            finally:
                F.SAMPLE_BYTES[:] = copy.deepcopy(orig_sb)
                tried += 1
        fo.write(f"# sb: {tried - n0} edits\n")
    if want("prio"):
        n0 = tried
        for lst_name in ("SEQ_PRIORITY", "SEQ_COMMANDS"):
            lst = getattr(F, lst_name)
            orig_l = list(lst)
            variants = [(f"remove {x}", [y for y in orig_l if y != x]) for x in orig_l]
            variants += [(f"double {x}", orig_l[:i + 1] + [x] + orig_l[i + 1:]) for i, x in enumerate(orig_l)]
            for lab, v in variants:
                lst[:] = v
                try:
                    judge(f"[prio] {lst_name} {lab}", F.SEQ)
                except Exception as ex:
                    fo.write(f"EXC [prio] {lst_name} {lab}: {ex!r}\n")
                finally:
                    lst[:] = orig_l
                    tried += 1
        fo.write(f"# prio: {tried - n0} edits\n")
    fo.write(f"# total {tried} edits, {npass} pass the checks, {nneq} of them not equivalent; {time.time() - t0:.0f} s\n")
    fo.close()


main()

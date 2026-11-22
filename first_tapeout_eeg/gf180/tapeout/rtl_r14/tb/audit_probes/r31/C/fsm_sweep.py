#!/usr/bin/env python3
"""Single-edit sweep of fsm_spec.SEQ / SPI tables and SEQ_PRIORITY through the same checks as run_checks (early exit).
Every edit that passes is compared with the original by behaviour (SEQ: seq_resolve over every state, possible event
set and condition values; SPI: spi_walk over every enumerated frame). Usage: fsm_sweep.py <spec dir> <out.txt>"""
import copy
import itertools
import sys
import time

sys.path.insert(0, sys.argv[1])
import fsm_spec as F  # noqa: E402

B, IGN, IMP, ALWAYS = F.B, F.IGN, F.IMP, F.ALWAYS


def passes():
    """run_checks' verdict (no violation), with an early exit."""
    rep = F.check_tables(F.SEQ) + F.check_tables(F.SPI)
    if rep:
        return False
    well = not any(k in r for r in rep for k in F.MALFORMED)
    for fn in (lambda: F.check_vocab(F.SEQ), lambda: F.check_vocab(F.SPI), F.check_seq_columns):
        if fn():
            return False
    if well:
        for fn in (F.check_seq_commands, F.check_seq_branches,
                   lambda: F.check_graph(F.SEQ, ["IDLE", "RUN"], ("RST",)) + F.check_graph(F.SPI, ["IDLE"], ())):
            if fn():
                return False
        for fn in (F.check_seq_ticks, F.check_spi_props, F.check_spi_frames):
            e, _ = fn()
            if e:
                return False
    e, _ = F.check_fifo()
    if e:
        return False
    e, _ = F.check_timing()
    return not e


SEQ_NAMES = [s[0] for s in F.SEQ_STATES]
TIMED = {x[0] for x in F.SEQ_STATES if x[4]}


def seq_behaviour():
    out = {}
    for s in SEQ_NAMES:
        sets = [[]]
        for c in F.SEQ_COMMANDS:
            sets += [[c]] + ([[c, "TMR"]] if s in TIMED else [])
        sets += ([["TMR"]] if s in TIMED else []) + [["OUT"], ["RST"], ["RST", "OUT"]]
        sets += [["RST", c] for c in F.SEQ_COMMANDS] + ([["REL"]] if s == "RESET" else [])
        for p in sets:
            for vals in itertools.product((0, 1), repeat=len(F.SEQ_CONDS)):
                env = dict(zip(F.SEQ_CONDS, vals))
                try:
                    nxt, acts, _w = F.seq_resolve(s, p, env)
                    out[(s, tuple(p), vals)] = (nxt, tuple(sorted(acts)))
                except Exception as ex:          # noqa: BLE001
                    out[(s, tuple(p), vals)] = ("EXC", repr(ex)[:40])
    return out


def spi_behaviour():
    out = {}
    for kind, crc_en, env, nb, ex in F.spi_frame_cases():
        key = (kind, crc_en, tuple(sorted(env.items())), nb, ex)
        try:
            out[key] = F.spi_walk(nb, ex, env)
            if out[key] is not None:
                out[key] = (tuple(out[key][0]), out[key][1])
        except Exception as e_:                 # noqa: BLE001
            out[key] = ("EXC", repr(e_)[:40])
    return out


def guard_variants(g, conds):
    vs = ["1", f"not ({g})"]
    for v in conds:
        vs += [v, f"not {v}", f"({g}) and {v}", f"({g}) and not {v}", f"({g}) or {v}", f"({g}) or not {v}"]
    terms = [t.strip() for t in g.split(" and ")] if " and " in g and "(" not in g else []
    for i in range(len(terms)):
        vs.append(" and ".join(terms[:i] + terms[i + 1:]))
    terms = [t.strip() for t in g.split(" or ")] if " or " in g and "(" not in g else []
    for i in range(len(terms)):
        vs.append(" or ".join(terms[:i] + terms[i + 1:]))
    return [v for v in dict.fromkeys(vs) if v != g]


def edits(M):
    t0 = M["table"]
    states = [s[0] for s in M["states"]] + [None]
    acts_all = list(M["actions"])
    conds = list(M["conds"])
    for key in sorted(t0, key=str):
        cell = t0[key]
        if isinstance(cell, list):
            yield f"{key} -> IGN", key, IGN
            yield f"{key} -> IMP", key, IMP
            for fl in ("STATE_ERR", "CFG_ERR", "FRAME_ERR", "ADDR_ERR"):
                if fl in acts_all:
                    yield f"{key} -> refuse {fl}", key, [B(ALWAYS, [fl])]
            if len(cell) > 1:
                for i in range(len(cell)):
                    yield f"{key} drop branch {i}", key, [copy.deepcopy(b) for j, b in enumerate(cell) if j != i]
            for i, b in enumerate(cell):
                def nb(**kw):
                    c = copy.deepcopy(cell)
                    c[i].update(kw)
                    return c
                for a in b["actions"]:
                    yield f"{key}[{i}] remove {a}", key, nb(actions=[x for x in b["actions"] if x != a])
                    for a2 in acts_all:
                        if a2 not in b["actions"]:
                            yield f"{key}[{i}] replace {a}->{a2}", key, nb(actions=[a2 if x == a else x for x in b["actions"]])
                for a2 in acts_all:
                    if a2 not in b["actions"]:
                        yield f"{key}[{i}] add {a2}", key, nb(actions=b["actions"] + [a2])
                for s2 in states:
                    if s2 != b["next"]:
                        yield f"{key}[{i}] next {b['next']}->{s2}", key, nb(next=s2)
                for fl in ("STATE_ERR", "CFG_ERR", "FRAME_ERR", "ADDR_ERR"):
                    if fl in acts_all and b["actions"] != [fl]:
                        yield f"{key}[{i}] refuse {fl}", key, nb(actions=[fl], next=None)
                for g2 in guard_variants(b["guard"], conds):
                    yield f"{key}[{i}] guard {b['guard']!r}->{g2!r}", key, nb(guard=g2)
        elif cell == IGN:
            yield f"{key} IGN->IMP", key, IMP
            yield f"{key} IGN->nothing", key, [B(ALWAYS, [])]
            for a in acts_all:
                yield f"{key} IGN->{a}", key, [B(ALWAYS, [a])]
            for s2 in states:
                if s2 is not None:
                    yield f"{key} IGN->go {s2}", key, [B(ALWAYS, [], s2)]
        elif cell == IMP:
            yield f"{key} IMP->IGN", key, IGN
            yield f"{key} IMP->nothing", key, [B(ALWAYS, [])]


def main():
    out = open(sys.argv[2], "w")
    t0 = time.time()
    assert passes(), "the unmutated spec does not pass"
    base = {"SEQ": seq_behaviour(), "SPI": spi_behaviour()}
    n = {"SEQ": 0, "SPI": 0}
    passed = {"SEQ": [], "SPI": []}
    for M in (F.SEQ, F.SPI):
        orig = M["table"]
        for name, key, new in edits(M):
            M["table"] = dict(orig)
            M["table"][key] = new
            n[M["name"]] += 1
            ok = False
            try:
                ok = passes()
            except Exception:                    # noqa: BLE001  (a crash of the checker on a malformed table)
                ok = False
            if ok:
                beh = seq_behaviour() if M["name"] == "SEQ" else spi_behaviour()
                diff = [k for k in base[M["name"]] if beh.get(k) != base[M["name"]][k]]
                passed[M["name"]].append((name, len(diff), diff[:3]))
                out.write(f"PASS {M['name']} {name}: {'EQUIVALENT' if not diff else f'DIFFERS in {len(diff)} cases, e.g. {diff[:2]}'}\n")
                out.flush()
        M["table"] = orig
    # SEQ_PRIORITY moves
    orig_p = list(F.SEQ_PRIORITY)
    np_ = 0
    for i in range(len(orig_p)):
        for j in range(len(orig_p)):
            if i == j:
                continue
            p = list(orig_p)
            e = p.pop(i)
            p.insert(j, e)
            if p == orig_p:
                continue
            F.SEQ_PRIORITY[:] = p
            np_ += 1
            if passes():
                beh = seq_behaviour()
                diff = [k for k in base["SEQ"] if beh.get(k) != base["SEQ"][k]]
                out.write(f"PASS PRIO {p}: {'EQUIVALENT' if not diff else f'DIFFERS in {len(diff)} cases, e.g. {diff[:2]}'}\n")
    F.SEQ_PRIORITY[:] = orig_p
    summ = (f"SEQ edits {n['SEQ']}, passed {len(passed['SEQ'])} (not equivalent {sum(1 for x in passed['SEQ'] if x[1])}); "
            f"SPI edits {n['SPI']}, passed {len(passed['SPI'])} (not equivalent {sum(1 for x in passed['SPI'] if x[1])}); "
            f"priority moves {np_}; {time.time() - t0:.0f} s")
    out.write(summ + "\n")
    print(summ)


if __name__ == "__main__":
    main()

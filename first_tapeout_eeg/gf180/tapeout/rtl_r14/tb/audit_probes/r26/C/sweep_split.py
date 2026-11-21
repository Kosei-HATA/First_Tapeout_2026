#!/usr/bin/env python3
"""Audit round 26 (C): sweep of single "partial" edits of fsm_spec's SEQ and SPI tables that earlier sweeps did not
list: a branch split on one condition into two halves, one half edited (an action dropped or added, the next state
changed, all actions dropped); and two branches of a cell exchanging their actions, their next states, or both.
Each edited table goes through fsm_spec.run_checks(); an edit that passes is compared with the original table
(SEQ: seq_resolve over every state, every tick case, reset, release, every condition value; SPI: spi_walk over every
enumerated frame). Usage: sweep_split.py <spec dir> <SEQ|SPI> <out file> [shard k of n]"""
import copy
import itertools
import os
import sys

spec_dir, mach, out = sys.argv[1], sys.argv[2], sys.argv[3]
shard, nshard = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (0, 1)
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import fsm_spec as F  # noqa: E402

M = F.SEQ if mach == "SEQ" else F.SPI
ORIG = M["table"]
ALLC = list(M["conds"])
STATES = [s[0] for s in M["states"]]
ACTS = list(M["actions"])

# cache the other machine's frame check for SEQ edits (check_spi_frames reads only the SPI table and SAMPLE_BYTES)
if mach == "SEQ":
    _spi_frames = F.check_spi_frames()
    F.check_spi_frames = lambda: _spi_frames
    _spi_props = F.check_spi_props()
    F.check_spi_props = lambda: _spi_props


def seq_sig(table):
    M["table"] = table
    timed = {x[0] for x in F.SEQ_STATES if x[4]}
    sig = []
    for s in STATES:
        cases = F.seq_tick_cases(s, timed) if s != "RESET" else [["OUT"]]
        cases = cases + [["RST"], ["RST", "OUT"]] + ([["REL"]] if s == "RESET" else [])
        for present in cases:
            for vals in itertools.product((0, 1), repeat=len(ALLC)):
                env = dict(zip(ALLC, vals))
                try:
                    nxt, acts, win = F.seq_resolve(s, list(present), env)
                    sig.append((s, tuple(present), vals, nxt, tuple(sorted(acts))))
                except Exception as ex:   # noqa: BLE001
                    sig.append((s, tuple(present), vals, "EXC", type(ex).__name__))
    M["table"] = ORIG
    return sig


def spi_sig(table):
    M["table"] = table
    sig = []
    for kind, crc_en, env, nb, ex in F.spi_frame_cases():
        try:
            w = F.spi_walk(nb, ex, env)
        except Exception as e_:   # noqa: BLE001
            w = ("EXC", type(e_).__name__)
        sig.append((kind, crc_en, tuple(sorted(env.items())), nb, ex,
                    None if w is None else (tuple(w[0]), w[1])))
    M["table"] = ORIG
    return sig


SIG = seq_sig if mach == "SEQ" else spi_sig
BASE = SIG(ORIG)


def edits():
    for key in sorted(ORIG, key=str):
        cell = ORIG[key]
        if not isinstance(cell, list):
            continue
        for i, b in enumerate(cell):
            g = b["guard"]
            gv = set(F.guard_vars(g))
            for c in ALLC:
                if c in gv:
                    continue
                for half in (0, 1):
                    ga = f"({g}) and {c}" if g != F.ALWAYS else c
                    gb = f"({g}) and not {c}" if g != F.ALWAYS else f"not {c}"
                    # the variants of the edited half
                    variants = []
                    for a in b["actions"]:
                        variants.append((f"drop {a}", [x for x in b["actions"] if x != a], b["next"]))
                    if b["actions"]:
                        variants.append(("drop all actions", [], b["next"]))
                    for a in ACTS:
                        if a not in b["actions"]:
                            variants.append((f"add {a}", b["actions"] + [a], b["next"]))
                    for n in STATES + [None]:
                        if n != b["next"]:
                            variants.append((f"next {n}", list(b["actions"]), n))
                    for vname, acts, nxt in variants:
                        e1 = F.B(ga, b["actions"], b["next"])
                        e2 = F.B(gb, b["actions"], b["next"])
                        if half == 0:
                            e1 = F.B(ga, acts, nxt)
                        else:
                            e2 = F.B(gb, acts, nxt)
                        desc = f"{key} branch {i} [{g}] split on {c}: the {'' if half == 0 else 'not-'}{c} half {vname}"
                        yield desc, (key, i, [e1, e2])
        # exchanges between two branches of one cell
        for i, j in itertools.combinations(range(len(cell)), 2):
            for what in ("actions", "next", "both"):
                desc = f"{key} branches {i}<->{j} exchange {what}"
                yield desc, (key, ("swap", i, j, what), None)


def apply(t, spec):
    key, i, new = spec
    if isinstance(i, tuple):
        _, a, b, what = i
        A, Bb = t[key][a], t[key][b]
        if what in ("actions", "both"):
            A["actions"], Bb["actions"] = Bb["actions"], A["actions"]
        if what in ("next", "both"):
            A["next"], Bb["next"] = Bb["next"], A["next"]
    else:
        t[key][i:i + 1] = new


n = npass = 0
res = []
for k, (desc, spec) in enumerate(edits()):
    if k % nshard != shard:
        continue
    n += 1
    t = copy.deepcopy(ORIG)
    apply(t, spec)
    M["table"] = t
    try:
        # a cheap pre-filter (a subset of run_checks: any violation here is a violation of run_checks), then the
        # whole run_checks for an edit that passes it
        rep = F.check_tables(M) + F.check_vocab(M)
        if not rep and not any(k in r for r in rep for k in F.MALFORMED):
            rep += (F.check_seq_branches() + F.check_seq_commands()) if mach == "SEQ" else F.check_spi_props()[0]
        if not rep:
            rep, _ = F.run_checks(verbose=False)
    except Exception as ex:   # noqa: BLE001
        rep = [f"CRASH {type(ex).__name__}: {ex}"]
    M["table"] = ORIG
    if not rep:
        npass += 1
        eq = SIG(t) == BASE
        res.append(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {desc}")
    elif any(r.startswith("CRASH") for r in rep):
        res.append(f"CRASH {desc}: {rep[0]}")
with open(out, "w") as fo:
    fo.write(f"{mach} shard {shard}/{nshard}: {n} edits, {npass} pass the check\n")
    fo.write("\n".join(res) + "\n")
print(f"{mach} shard {shard}/{nshard}: {n} edits, {npass} pass")

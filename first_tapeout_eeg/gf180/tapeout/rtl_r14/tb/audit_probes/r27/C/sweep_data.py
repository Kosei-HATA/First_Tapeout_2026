#!/usr/bin/env python3
"""Audit round 27 (C): single edits of fsm_spec's data outside the two tables: the columns of SEQ_STATES and
SPI_STATES (STATE code, parent, AFE_RST, timer), the sets FLAGS and DATA, SEQ_COMMANDS, and TIMING's numbers and lists.
Each edit goes through run_checks(); the ones that pass are listed. Usage: sweep_data.py <spec dir> <out>"""
import copy, os, sys
spec_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import fsm_spec as F

def snapshot():
    return (copy.deepcopy(F.SEQ_STATES), copy.deepcopy(F.SPI_STATES), set(F.FLAGS), set(F.DATA),
            list(F.SEQ_COMMANDS), copy.deepcopy(F.TIMING), copy.deepcopy(F.SEQ_COMPOSITES), copy.deepcopy(F.SPI_COMPOSITES))
S0 = snapshot()
def restore():
    F.SEQ_STATES[:] = copy.deepcopy(S0[0]); F.SPI_STATES[:] = copy.deepcopy(S0[1])
    F.FLAGS.clear(); F.FLAGS.update(S0[2]); F.DATA.clear(); F.DATA.update(S0[3])
    F.SEQ_COMMANDS[:] = list(S0[4]); F.TIMING.clear(); F.TIMING.update(copy.deepcopy(S0[5]))
    F.SEQ_COMPOSITES.clear(); F.SEQ_COMPOSITES.update(copy.deepcopy(S0[6]))
    F.SPI_COMPOSITES.clear(); F.SPI_COMPOSITES.update(copy.deepcopy(S0[7]))
    F.SEQ_STATE.clear(); F.SEQ_STATE.update({s[0]: s for s in F.SEQ_STATES})

def edits():
    names = [s[0] for s in S0[0]]
    codes = [s[1] for s in S0[0]]
    timers = sorted({s[4] for s in S0[0] if s[4]})
    for i, s in enumerate(S0[0]):
        for c in list(range(0, 16)) + [None]:
            if c != s[1]:
                yield f"SEQ_STATES {s[0]}: code {s[1]} -> {c}", ("seqst", i, 1, c)
        for p in [None, "ACTIVE", "AFE_ON"]:
            if p != s[2]:
                yield f"SEQ_STATES {s[0]}: parent {s[2]} -> {p}", ("seqst", i, 2, p)
        yield f"SEQ_STATES {s[0]}: AFE_RST {s[3]} -> {1 - s[3]}", ("seqst", i, 3, 1 - s[3])
        for t in timers + [None]:
            if t != s[4]:
                yield f"SEQ_STATES {s[0]}: timer {s[4]} -> {t}", ("seqst", i, 4, t)
    for i, j in [(a, b) for a in range(len(names)) for b in range(a + 1, len(names))]:
        if codes[i] is not None and codes[j] is not None:
            yield f"SEQ_STATES: codes of {names[i]} and {names[j]} exchanged", ("swapcode", i, j)
    for i, s in enumerate(S0[1]):
        for p in [None, "FRAME"]:
            if p != s[2]:
                yield f"SPI_STATES {s[0]}: parent {s[2]} -> {p}", ("spist", i, 2, p)
    allacts = set(F.SEQ["actions"]) | set(F.SPI["actions"])
    for a in sorted(S0[2]):
        yield f"FLAGS without {a}", ("flags", "del", a)
    for a in sorted(allacts - S0[2]):
        yield f"FLAGS with {a}", ("flags", "add", a)
    for a in sorted(S0[3]):
        yield f"DATA without {a}", ("data", "del", a)
    for a in sorted(allacts - S0[3]):
        yield f"DATA with {a}", ("data", "add", a)
    for c in S0[4]:
        yield f"SEQ_COMMANDS without {c}", ("cmds", c)
    T = S0[5]
    for k, v in T.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for nv in (v + 1, v - 1, v * 2, v / 2 if isinstance(v, float) else v // 2):
                if nv != v:
                    yield f"TIMING {k}: {v} -> {nv}", ("timing", k, nv)
        elif isinstance(v, list):
            for i in range(len(v)):
                for nv in (v[i] * 2, v[i] // 2, v[i] + 1):
                    vv = list(v); vv[i] = nv
                    yield f"TIMING {k}[{i}]: {v[i]} -> {nv}", ("timing", k, vv)
                vv = v[:i] + v[i + 1:]
                yield f"TIMING {k} without item {i}", ("timing", k, vv)
        elif isinstance(v, dict) and k == "timers":
            for tn, (mn, nom, mx) in v.items():
                for idx, val in enumerate((mn, nom, mx)):
                    for nv in (val * 2, val / 2, val * 1.1, val * 0.9, 0.0):
                        if nv != val:
                            tup = [mn, nom, mx]; tup[idx] = nv
                            vv = dict(v); vv[tn] = tuple(tup)
                            yield f"TIMING timers {tn}[{idx}]: {val} -> {nv}", ("timing", k, vv)
        elif isinstance(v, dict) and k == "busy_cycles":
            for c in v:
                vv = {a: b for a, b in v.items() if a != c}
                yield f"TIMING busy_cycles without {c}", ("timing", k, vv)
            for c in (24, 25, 23, 31):
                if c not in v:
                    vv = dict(v); vv[c] = "x"
                    yield f"TIMING busy_cycles with {c}", ("timing", k, vv)

def apply(e):
    if e[0] == "seqst":
        _, i, k, v = e
        s = list(F.SEQ_STATES[i]); s[k] = v; F.SEQ_STATES[i] = tuple(s)
    elif e[0] == "swapcode":
        _, i, j = e
        a, b = list(F.SEQ_STATES[i]), list(F.SEQ_STATES[j])
        a[1], b[1] = b[1], a[1]
        F.SEQ_STATES[i], F.SEQ_STATES[j] = tuple(a), tuple(b)
    elif e[0] == "spist":
        _, i, k, v = e
        s = list(F.SPI_STATES[i]); s[k] = v; F.SPI_STATES[i] = tuple(s)
    elif e[0] == "flags":
        (F.FLAGS.discard if e[1] == "del" else F.FLAGS.add)(e[2])
    elif e[0] == "data":
        (F.DATA.discard if e[1] == "del" else F.DATA.add)(e[2])
    elif e[0] == "cmds":
        F.SEQ_COMMANDS.remove(e[1])
    elif e[0] == "timing":
        F.TIMING[e[1]] = e[2]
    F.SEQ_STATE.clear(); F.SEQ_STATE.update({s[0]: s for s in F.SEQ_STATES})

n = npass = 0
res = []
for desc, e in edits():
    n += 1
    apply(e)
    try:
        rep, _ = F.run_checks(verbose=False)
    except Exception as ex:
        rep = [f"CRASH {type(ex).__name__}: {ex}"]
    restore()
    if not rep:
        npass += 1
        res.append(f"PASS {desc}")
    elif str(rep[0]).startswith("CRASH"):
        res.append(f"CRASH {desc}: {rep[0]}")
with open(out, "w") as fo:
    fo.write(f"{n} edits, {npass} pass\n" + "\n".join(res) + "\n")
print(f"{n} edits, {npass} pass")

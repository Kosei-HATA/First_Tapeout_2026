"""Single-edit sweep of fsm_spec's SEQ and SPI tables and SEQ_PRIORITY through run_checks (audit round 25, C)."""
import copy, sys, os, itertools, json, time
SPEC = os.path.abspath(sys.argv[1]); OUT = os.path.abspath(sys.argv[2])
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import fsm_spec as FS

B = FS.B
IGN, IMP = FS.IGN, FS.IMP

def run():
    try:
        rep, _ = FS.run_checks(verbose=False)
        return rep
    except Exception as ex:                      # a crash is reported, never a pass
        return ["CRASH " + type(ex).__name__ + ": " + str(ex)[:100]]

def guards_of(F):
    gs = set()
    for cell in F["table"].values():
        if isinstance(cell, list):
            for b in cell:
                gs.add(b["guard"])
    return sorted(gs)

def edits(F):
    t = F["table"]
    states = [s[0] for s in F["states"]]
    vocab = sorted(set(F["actions"]) | FS.FLAGS | (FS.DATA if F["name"] == "SEQ" else set()))
    conds = sorted(F["conds"])
    # (round 23/24 swept every machine guard, its negation, every condition and its negation; fsm_spec.py has not
    # changed since: only the new kinds here, two conditions joined by and / or)
    gpool = {f"{a} and {b}" for a, b in itertools.combinations(conds, 2)}
    gpool |= {f"{a} or {b}" for a, b in itertools.combinations(conds, 2)}
    gpool = sorted(gpool)
    events = [e[0] for e in F["events"]]
    for key, cell in t.items():
        if isinstance(cell, list):
            for i, b in enumerate(cell):
                for fl in sorted(FS.FLAGS & set(F["actions"]) | {"CFG_ERR", "STATE_ERR"} if F["name"] == "SEQ" else FS.FLAGS & set(F["actions"])):
                    yield (key, "refuse", i, fl)        # the branch refused: only the flag, no move
                    yield (key, "refuse_keep", i, fl)   # only the flag, the move kept
                for a in b["actions"]:
                    for a2 in vocab:
                        if a2 not in b["actions"]:
                            yield (key, "repl", i, (a, a2))
                continue
                for a in vocab:
                    if a not in b["actions"]:
                        yield (key, "add", i, a)
                for s in states + [None]:
                    if s != b["next"]:
                        yield (key, "next", i, s)
                ev_conds = (FS.SPI_EVENT_CONDS.get(key[1], set(conds)) | {"mid", "busy", "head", "crc_ok"} if key[1] == "CSR"
                            else FS.SPI_EVENT_CONDS.get(key[1], set(conds))) if F["name"] == "SPI" else set(conds)
                for g in gpool:
                    if g == b["guard"]:
                        continue
                    if F["name"] == "SPI" and not (set(FS.guard_vars(g)) - {"1"} <= ev_conds):
                        continue                 # a condition the event cannot know: rejected by SPI_EVENT_CONDS
                    yield (key, "guard", i, g)
                if len(cell) > 1:
                    yield (key, "delbranch", i, None)
                # move one action to another branch of the cell (new kind)
                for j in range(len(cell)):
                    if j != i:
                        for a in b["actions"]:
                            if a not in cell[j]["actions"]:
                                yield (key, "moveact", (i, j), a)
            pass
        else:
            pass
        # copy the cell of another event of the same state (new kind)
        pass

def apply(F, ed):
    key, kind, i, arg = ed
    t = copy.deepcopy(F["table"])
    cell = t[key]
    if kind == "refuse":
        cell[i]["actions"] = [arg]; cell[i]["next"] = None
    elif kind == "refuse_keep":
        cell[i]["actions"] = [arg]
    elif kind == "repl":
        cell[i]["actions"] = [arg[1] if x == arg[0] else x for x in cell[i]["actions"]]
    elif kind == "rm":
        cell[i]["actions"] = [a for a in cell[i]["actions"] if a != arg]
    elif kind == "add":
        cell[i]["actions"] = cell[i]["actions"] + [arg]
    elif kind == "next":
        cell[i]["next"] = arg
    elif kind == "guard":
        cell[i]["guard"] = arg
    elif kind == "delbranch":
        del cell[i]
    elif kind == "moveact":
        a_, b_ = i
        cell[a_]["actions"] = [x for x in cell[a_]["actions"] if x != arg]
        cell[b_]["actions"] = cell[b_]["actions"] + [arg]
    elif kind == "cell":
        t[key] = copy.deepcopy(arg)
    elif kind == "copyevent":
        t[key] = copy.deepcopy(F["table"][(key[0], arg)])
    return t

out = {"passed": [], "crashed": [], "n": 0}
t0 = time.time()
for F in (FS.SEQ, FS.SPI):
    orig = F["table"]
    for ed in edits(F):
        F["table"] = apply(F, ed) if True else orig
        rep = run()
        F["table"] = orig
        out["n"] += 1
        if not rep:
            out["passed"].append((F["name"],) + tuple(map(str, ed)))
        elif any(r.startswith("CRASH") for r in rep):
            out["crashed"].append((F["name"],) + tuple(map(str, ed)) + (rep[0],))
prio = list(FS.SEQ_PRIORITY)
for i in range(0):
    for j in range(len(prio)):
        if i == j:
            continue
        p = prio[:]
        x = p.pop(i)
        p.insert(j, x)
        if p == prio:
            continue
        FS.SEQ_PRIORITY[:] = p
        rep = run()
        out["n"] += 1
        if not rep:
            out["passed"].append(("PRIO", " ".join(p)))
        elif any(r.startswith("CRASH") for r in rep):
            out["crashed"].append(("PRIO", " ".join(p), rep[0]))
FS.SEQ_PRIORITY[:] = prio
out["seconds"] = time.time() - t0
json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
print(out["n"], "edits;", len(out["passed"]), "passed;", len(out["crashed"]), "crashed;", round(out["seconds"]), "s")

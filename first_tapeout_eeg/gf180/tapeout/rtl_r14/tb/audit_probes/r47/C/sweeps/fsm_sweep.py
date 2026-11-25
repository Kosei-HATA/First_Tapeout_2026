"""Sweep single edits of fsm_spec's SEQ / SPI tables and SEQ_PRIORITY through the spec checks (in process).
Reports every edit that passes all checks, with whether its behaviour signature equals the original."""
import copy, itertools, sys, os, time
SPEC = os.path.abspath(sys.argv[1])
WHICH = sys.argv[2]           # seq | spi | prio
PART = int(sys.argv[3]) if len(sys.argv) > 3 else 0
NPART = int(sys.argv[4]) if len(sys.argv) > 4 else 1
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import fsm_spec as F
B, IGN, IMP = F.B, F.IGN, F.IMP

def run_checks_fast(spi_changed):
    rep = F.check_tables(F.SEQ) + F.check_tables(F.SPI)
    if rep: return rep
    rep = F.check_vocab(F.SEQ) + F.check_vocab(F.SPI) + F.check_seq_columns()
    if rep: return rep
    rep = F.check_seq_commands() + F.check_seq_branches()
    if rep: return rep
    rep = F.check_graph(F.SEQ, ["IDLE", "RUN"], ("RST",)) + F.check_graph(F.SPI, ["IDLE"], ())
    if rep: return rep
    rep = F.check_seq_ticks()[0]
    if rep: return rep
    rep = F.check_spi_props()[0]
    if rep: return rep
    if spi_changed:
        rep = F.check_spi_frames()[0]
        if rep: return rep
    rep = F.check_fifo()[0] + F.check_timing()[0] + F.check_doc_blocks()
    return rep

def seq_sig():
    out = []
    timed = {x[0] for x in F.SEQ_STATES if x[4]}
    envs = list(F.all_envs(list(F.SEQ_CONDS), lambda e: True))
    for s in [x[0] for x in F.SEQ_STATES]:
        if s == "RESET":
            cases = [["REL"], ["OUT"]] + [[c] for c in F.SEQ_COMMANDS]
        else:
            cases = F.seq_tick_cases(s, timed)
        cases = cases + [["RST"] + c for c in cases] + [["RST"]]
        for present in cases:
            for env in envs:
                try:
                    nxt, acts = F.seq_tick(s, present, env)
                    out.append((s, tuple(present), tuple(sorted(env.items())), nxt, tuple(sorted(acts))))
                except Exception as ex:
                    out.append((s, tuple(present), tuple(sorted(env.items())), "EXC", str(ex)[:40]))
    return out

def spi_sig():
    out = []
    for kind, crc_en, env, nbytes, extra in F.spi_frame_cases():
        try:
            w = F.spi_walk(nbytes, extra, env)
        except Exception as ex:
            w = ("EXC", str(ex)[:40])
        out.append((kind, crc_en, tuple(sorted(env.items())), nbytes, extra, None if w is None else (tuple(w[0]), w[1])))
    return out

ORIG = {"seq": copy.deepcopy(F.SEQ["table"]), "spi": copy.deepcopy(F.SPI["table"])}
ORIG_PRIO = list(F.SEQ_PRIORITY)
SIG0 = {"seq": seq_sig(), "spi": spi_sig()}

def machine_edits(M):
    t0 = ORIG[M]
    F_ = F.SEQ if M == "seq" else F.SPI
    states = [x[0] for x in F_["states"]]
    acts = list(F_["actions"])
    conds = list(F_["conds"])
    edits = []
    def E(desc, fn): edits.append((desc, fn))
    for key in sorted(t0, key=str):
        cell = t0[key]
        if cell == IGN:
            E(f"{key} IGN->IMP", lambda t, key=key: t.__setitem__(key, IMP))
            for a in acts:
                E(f"{key} IGN->[1:{a}]", lambda t, key=key, a=a: t.__setitem__(key, [B(F.ALWAYS, [a])]))
            for s2 in states:
                E(f"{key} IGN->[1:->{s2}]", lambda t, key=key, s2=s2: t.__setitem__(key, [B(F.ALWAYS, [], s2)]))
            E(f"{key} IGN->[1:]", lambda t, key=key: t.__setitem__(key, [B(F.ALWAYS, [])]))
            continue
        if cell == IMP:
            E(f"{key} IMP->IGN", lambda t, key=key: t.__setitem__(key, IGN))
            E(f"{key} IMP->[1:]", lambda t, key=key: t.__setitem__(key, [B(F.ALWAYS, [])]))
            continue
        if cell is None:
            continue
        E(f"{key} ->IGN", lambda t, key=key: t.__setitem__(key, IGN))
        E(f"{key} ->IMP", lambda t, key=key: t.__setitem__(key, IMP))
        E(f"{key} cell removed", lambda t, key=key: t.pop(key))
        n = len(cell)
        for i, b in enumerate(cell):
            g = b["guard"]
            for a in b["actions"]:
                E(f"{key}[{i}] -{a}", lambda t, key=key, i=i, a=a: t[key][i].__setitem__("actions", [x for x in t[key][i]["actions"] if x != a]))
                for a2 in acts:
                    if a2 not in b["actions"]:
                        E(f"{key}[{i}] {a}->{a2}", lambda t, key=key, i=i, a=a, a2=a2: t[key][i].__setitem__("actions", [a2 if x == a else x for x in t[key][i]["actions"]]))
            for a2 in acts:
                if a2 not in b["actions"]:
                    E(f"{key}[{i}] +{a2}", lambda t, key=key, i=i, a2=a2: t[key][i].__setitem__("actions", t[key][i]["actions"] + [a2]))
            for s2 in states + [None]:
                if s2 != b["next"]:
                    E(f"{key}[{i}] next {b['next']}->{s2}", lambda t, key=key, i=i, s2=s2: t[key][i].__setitem__("next", s2))
            for fl in (["CFG_ERR", "STATE_ERR"] if M == "seq" else ["STATE_ERR", "FRAME_ERR", "ADDR_ERR", "CRC_ERR"]):
                E(f"{key}[{i}] refused {fl}", lambda t, key=key, i=i, fl=fl: t[key].__setitem__(i, B(t[key][i]["guard"], [fl], t[key][i]["next"] if M == "spi" else None)))
            # guards
            alts = [F.ALWAYS, f"not ({g})"]
            for c in conds:
                alts += [c, f"not {c}", f"({g}) and {c}", f"({g}) and not {c}", f"({g}) or {c}", f"({g}) or not {c}"]
            for g2 in alts:
                if g2 != g:
                    E(f"{key}[{i}] guard {g!r}->{g2!r}", lambda t, key=key, i=i, g2=g2: t[key][i].__setitem__("guard", g2))
            if n > 1:
                E(f"{key}[{i}] branch removed", lambda t, key=key, i=i: t[key].pop(i))
        for i, j in itertools.combinations(range(n), 2):
            E(f"{key} guards {i}<->{j} swapped", lambda t, key=key, i=i, j=j: (lambda gi, gj: (t[key][i].__setitem__("guard", gj), t[key][j].__setitem__("guard", gi)))(t[key][i]["guard"], t[key][j]["guard"]))
            E(f"{key} merge {i}+{j} (keep {i})", lambda t, key=key, i=i, j=j: t.__setitem__(key, [b_ for k_, b_ in enumerate(t[key]) if k_ != j and k_ != i] + [B(f"({t[key][i]['guard']}) or ({t[key][j]['guard']})", t[key][i]["actions"], t[key][i]["next"])]))
            E(f"{key} merge {i}+{j} (keep {j})", lambda t, key=key, i=i, j=j: t.__setitem__(key, [b_ for k_, b_ in enumerate(t[key]) if k_ != j and k_ != i] + [B(f"({t[key][i]['guard']}) or ({t[key][j]['guard']})", t[key][j]["actions"], t[key][j]["next"])]))
    return edits

def prio_edits():
    edits = []
    P = ORIG_PRIO
    for i, e in enumerate(P):
        for j in range(len(P)):
            if j == i: continue
            q = [x for x in P if x != e]
            q.insert(j, e)
            if q != P:
                edits.append((f"PRIO {e} to {j}: {q}", q))
    return edits

def main():
    t0 = time.time()
    if WHICH == "prio":
        edits = prio_edits()
    else:
        edits = machine_edits(WHICH)
    edits = edits[PART::NPART]
    npass = 0
    print(f"# {WHICH} part {PART}/{NPART}: {len(edits)} edits", flush=True)
    for k, (desc, fn) in enumerate(edits):
        F.SEQ["table"] = copy.deepcopy(ORIG["seq"]); F.SPI["table"] = copy.deepcopy(ORIG["spi"])
        F.SEQ_PRIORITY[:] = ORIG_PRIO
        try:
            if WHICH == "prio":
                F.SEQ_PRIORITY[:] = fn
            else:
                fn(F.SEQ["table"] if WHICH == "seq" else F.SPI["table"])
            rep = run_checks_fast(WHICH == "spi")
        except Exception as ex:
            rep = [f"EXCEPTION {type(ex).__name__}: {ex}"]
        if not rep:
            npass += 1
            try:
                sig = seq_sig() if WHICH in ("seq", "prio") else spi_sig()
                eq = sig == SIG0["seq" if WHICH in ("seq", "prio") else "spi"]
                ndiff = 0 if eq else sum(1 for a, b in zip(sig, SIG0["seq" if WHICH in ("seq", "prio") else "spi"]) if a != b)
            except Exception as ex:
                eq, ndiff = False, f"sig exception {ex}"
            print(f"PASS {'EQUIV' if eq else 'DIFF '} ndiff={ndiff} :: {desc}", flush=True)
    F.SEQ["table"] = ORIG["seq"]; F.SPI["table"] = ORIG["spi"]; F.SEQ_PRIORITY[:] = ORIG_PRIO
    print(f"# done {len(edits)} edits, {npass} pass, {time.time()-t0:.0f} s", flush=True)

main()

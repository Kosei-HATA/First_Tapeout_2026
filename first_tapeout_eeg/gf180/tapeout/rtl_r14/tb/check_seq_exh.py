#!/usr/bin/env python3
"""tb_seq_exh's trace against the specification (audit round 22, auditor A; the checker of round 21's auditor A).
Every combination of state value 0..15, event (none / tick / output time), pending command, cfg_ok, nr_ok, t_elec0,
valid, timer (0 / 5) and frame_stb appears exactly once (18,432). For the defined states: the next state, the actions
(apply, flush, store, mark, STATE_ERR, CFG_ERR), the command's acknowledge (at a tick with a command), cic_arm (ALIGN
only), the registered state and AFE_RST, and the timer after the edge (loaded with the next state's setting on a change
or a restart, else decremented by frame_stb and held at 0) equal fsm_spec.seq_tick's. For the values 9..15: NFR-05
(STATE_ERR, to IDLE with AFE_RST = 1, nothing else). Coverage: every branch of the table that a tick or an output time
can reach is taken at least MIN_HITS times (tb_seq's random walk reaches its rarest branch once with the suite's seed;
this pass does not depend on a seed). The reset column and the RESET row are tb_seq's (its directed resets).
Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/check_seq_exh.py build/seq_exh.txt
"""
import collections
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import fsm_spec as FS  # noqa: E402

NAME = {x[1]: x[0] for x in FS.SEQ_STATES if x[1] is not None}
CODE = {x[0]: x[1] for x in FS.SEQ_STATES if x[1] is not None}
TIMED = {x[0] for x in FS.SEQ_STATES if x[4]}
AFE = {x[0]: x[3] for x in FS.SEQ_STATES}
TIMER_OF = {x[0]: x[4] for x in FS.SEQ_STATES}
CMDS = [None, "START", "STOP", "APPLY", "APPLY_NR", "FLUSH"]
T = dict(T_WARM=5, T_REC=29, T_PRE=3, T_RST=13)              # the bench's settings (T_ELEC 0 or 7 by t_elec0)
UNIT = {"T_WARM": 1024, "T_ELEC": 1024, "T_REC": 8, "T_PRE": 8, "T_RST": 8}
ACTS = ("apply", "flush", "store", "mark", "STATE_ERR", "CFG_ERR")
MIN_HITS = 8


def main(path):
    errs, n, seen, cover = [], 0, collections.Counter(), collections.Counter()
    for line in open(path):
        a, b, c = line.split("|")
        s, ev, ci, cfg, nr, te0, valid, tz, fs = map(int, a.split())
        seen[(s, ev, ci, cfg, nr, te0, valid, tz, fs)] += 1
        kv = b.split()
        d = {kv[i]: int(kv[i + 1]) for i in range(0, len(kv), 2)}
        kv = c.split()
        r = {kv[i]: int(kv[i + 1]) for i in range(0, len(kv), 2)}
        n += 1
        timer0, tel = (0 if tz else 5), (0 if te0 else 7)
        tag = f"state {s} ev {ev} cmd {CMDS[ci]} cfg {cfg} nr {nr} te0 {te0} valid {valid} tz {tz} fs {fs}"
        if s not in NAME:                                 # NFR-05: an illegal state value
            want = dict(nxt=0, ack=0, apply=0, flush=0, arm=0, store=0, mark=0, serr=1, cerr=0)
            if any(d[k] != v for k, v in want.items()) or r["st"] != 0 or r["afe"] != 1:
                errs.append(f"{tag}: illegal value -> {d} {r} (NFR-05: STATE_ERR, IDLE, AFE_RST 1)")
            continue
        st = NAME[s]
        got = {k for k in ("apply", "flush", "store", "mark") if d[k]} | ({"STATE_ERR"} if d["serr"] else set()) | \
            ({"CFG_ERR"} if d["cerr"] else set())
        if d["arm"] != (1 if st == "ALIGN" else 0):
            errs.append(f"{tag}: cic_arm {d['arm']}")
        if ev == 0:
            exp_nxt, exp_acts = st, []
        else:
            present = ["OUT"] if ev == 2 else ([CMDS[ci]] if ci else []) + (["TMR"] if (timer0 == 0 and st in TIMED) else [])
            env = dict(cfg_ok=cfg, nr_ok=nr, t_elec0=te0, valid=valid)
            exp_nxt, exp_acts = FS.seq_tick(st, present, env)
            for e in present:                             # the branches taken (coverage)
                br = FS.pick(FS.SEQ["table"][(st, e)], env)
                if isinstance(br, dict):
                    cover[(st, e, br["guard"])] += 1
        exp = {x for x in exp_acts if x in ACTS}
        ack = 1 if (ev == 1 and ci) else 0
        if NAME.get(d["nxt"]) != exp_nxt or got != exp or d["ack"] != ack:
            errs.append(f"{tag}: RTL {NAME.get(d['nxt'])} {sorted(got)} ack {d['ack']}; specification {exp_nxt} {sorted(exp)} ack {ack}")
        if r["st"] != CODE[exp_nxt] or r["afe"] != AFE[exp_nxt]:
            errs.append(f"{tag}: registered state {r['st']} AFE_RST {r['afe']}")
        tn = TIMER_OF.get(exp_nxt)
        if exp_nxt != st or "restart" in exp_acts:
            tw = (tel if tn == "T_ELEC" else T[tn]) * UNIT[tn] if tn else 0
        else:
            tw = max(0, timer0 - fs) if timer0 else 0
        if r["timer"] != tw:
            errs.append(f"{tag}: timer {r['timer']}, specification {tw}")
    want = set(itertools.product(range(16), range(3), range(6), range(2), range(2), range(2), range(2), range(2), range(2)))
    missing, twice = want - set(seen), [k for k, v in seen.items() if v > 1]
    branches = {(s_, e_, b_["guard"]) for (s_, e_), cell in FS.SEQ["table"].items()
                if isinstance(cell, list) and s_ != "RESET" and e_ not in ("RST", "REL") for b_ in cell}
    thin = sorted((k, cover[k]) for k in branches if cover[k] < MIN_HITS)
    print(f"{n} combinations ({len(missing)} missing, {len(twice)} twice), {len(errs)} mismatches; "
          f"{len(branches) - len(thin)} of {len(branches)} tick / output branches taken at least {MIN_HITS} times "
          f"(fewest {min(cover[k] for k in branches)})")
    for e in errs[:20]:
        print("  " + e)
    for k, v in thin[:20]:
        print(f"  taken {v} times: {k}")
    ok = n > 0 and not errs and not missing and not twice and not thin
    print("PASS: eeg_seq == specification on every combination, every branch taken" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "build", "seq_exh.txt")))

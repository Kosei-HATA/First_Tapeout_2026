#!/usr/bin/env python3
"""Replay tb_seq's trace through the specification and compare (VER-09 for the sequencer).

For every tick (T) and output time (O) of the trace, fsm_spec.seq_tick gives the next state and the actions from the
state, the events present (the pending command and the timer at a tick, OUT at an output time) and the conditions;
the RTL's next state and actions must be the same. Compared actions: apply, flush, store, mark, STATE_ERR, CFG_ERR,
cic_clear, restart; and at every output time 'seq_inc' (the data path counts every output time, eeg_digital_top) and
'discard' exactly when the RTL does not store (audit round 7: a table that ignored OUT in some states passed). The FIFO
decides OVERRUN.
The timer is modelled here, not taken from the RTL: loaded with the state's setting (T_WARM, T_ELEC x 1024 frames;
T_REC, T_PRE, T_RST x 8 frames) on entering a timed state and on a restart, decremented once per frame, clamped at 0;
TMR is present at a tick when the model is 0. The RTL's timer before and after every event must equal the model.
Coverage: every (state, event, branch) of the transition table that a tick or an output time can reach must have been
hit (not asked with --no-cover: the end-to-end replay of tb_top_r14's trace, build/top_seq_trace.txt). The state is
chained: each event starts in the state the previous one left (or IDLE after a reset), so no change between events
goes unseen.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/check_seq_trace.py build/seq_trace.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import fsm_spec as FS  # noqa: E402

NAME = {x[1]: x[0] for x in FS.SEQ_STATES if x[1] is not None}
CMD = {0x11: "START", 0x22: "STOP", 0x33: "APPLY", 0x44: "APPLY_NR", 0x55: "FLUSH"}
TIMED = {x[0] for x in FS.SEQ_STATES if x[4]}
RTL_ACTS = ["apply", "flush", "store", "mark", "STATE_ERR", "CFG_ERR", "cic_clear", "restart"]
# the trace's setting order and each timer register's unit in frames (1 ms = 1024, 7.8125 us = 8); the state's timer
# from the table (audit round 12, auditor C: the states' timers were written here by hand, so a table that swapped
# PRE's and PULSE's timers was never compared with the RTL)
TIMER_SLOT = {"T_WARM": (0, 1024), "T_ELEC": (1, 1024), "T_REC": (2, 8), "T_PRE": (3, 8), "T_RST": (4, 8)}
UNIT = {x[0]: TIMER_SLOT[x[4]] for x in FS.SEQ_STATES if x[4]}   # state -> (setting, frames)


def load(s, tset):
    if s not in UNIT:
        return 0
    k, unit = UNIT[s]
    return tset[k] * unit


def main(path):
    errs, n, cover, model, nload, nrestart, prev = [], 0, set(), 0, 0, 0, 0
    for ln, line in enumerate(open(path), 1):
        f = line.split()
        if not f:
            continue
        if f[0] == "R":
            model, prev = 0, 0                              # reset: IDLE, timer 0
            continue
        kind, st, cv, cc, tm, cfg, nr, te0, valid, nxt, acts = f[0], *map(int, f[1:10]), f[10]
        t_before, t_after, frames, fs, *tset = map(int, f[11:20])
        s = NAME[st]
        if st != prev:
            errs.append(f"line {ln}: the event starts in {s}, the previous one left {NAME.get(prev, prev)}")
        prev = nxt
        exp_before = max(0, model - frames)                 # the frames since the previous traced event
        if t_before != exp_before:
            errs.append(f"line {ln}: timer before the event {t_before}, model {exp_before}")
        if kind == "T":
            present = ([CMD[cc]] if cv else []) + (["TMR"] if (exp_before == 0 and s in TIMED) else [])
        else:
            present = ["OUT"]
        env = dict(cfg_ok=cfg, nr_ok=nr, t_elec0=te0, valid=valid)
        exp_nxt, exp_acts = FS.seq_tick(s, present, env)
        exp = {a for a in exp_acts if a in RTL_ACTS}
        got = {a for a, b in zip(RTL_ACTS, acts) if b == "1"}
        n += 1
        if NAME.get(nxt) != exp_nxt or got != exp:
            errs.append(f"line {ln}: {s} {present} {env}: RTL -> {NAME.get(nxt, nxt)} {sorted(got)}, "
                        f"specification -> {exp_nxt} {sorted(exp)}")
        if kind == "O" and ("seq_inc" not in exp_acts or ("discard" in exp_acts) == ("store" in got)):
            errs.append(f"line {ln}: {s} OUT: the specification's {sorted(exp_acts)} does not count the output time "
                        f"and {'store' if 'store' in got else 'discard'} it as the RTL does")
        if exp_nxt != s or "restart" in exp:
            model = load(exp_nxt, tset)
            nload += 1
            nrestart += "restart" in exp
        else:
            model = max(0, exp_before - fs)
        if t_after != model:
            errs.append(f"line {ln}: timer after the event {t_after}, model {model} ({s} -> {exp_nxt}, {sorted(exp)})")
        for e in present:
            cell = FS.SEQ["table"][(s, e)]
            b = FS.pick(cell, env)
            if isinstance(b, dict):
                cover.add((s, e, b["guard"]))
    # the cells a tick or an output time can reach
    want = set()
    for (s, e), cell in FS.SEQ["table"].items():
        if s == "RESET" or e in ("RST", "REL") or not isinstance(cell, list):
            continue
        for b in cell:
            want.add((s, e, b["guard"]))
    missing = sorted(want - cover)
    print(f"{n} events replayed through fsm_spec.seq_tick: {len(errs)} mismatches; "
          f"table cells covered {len(want & cover)} of {len(want)}; timer modelled ({nload} loads, {nrestart} restarts)")
    for e in errs[:20]:
        print("  " + e)
    for m in missing:
        print(f"  not covered: {m}")
    ok = not errs and (NO_COVER or not missing) and n > 0
    print(("PASS: sequencer RTL == specification on every traced event" +
           ("" if NO_COVER else ", all cells covered")) if ok else "FAIL")
    return 0 if ok else 1


NO_COVER = "--no-cover" in sys.argv
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0] if args else "build/seq_trace.txt"))

"""Audit 34, A: an independent model of one sequencer tick, written from the requirements' text (SEQ-01..16, 5.0's
priority rules, 4.10), compared with fsm_spec.seq_tick over every state, command, expiry and condition value."""
import itertools, sys
sys.path.insert(0, sys.argv[1])
import fsm_spec as FS

TIMED = {"WARMUP", "RECOVER", "WAIT_E", "PRE", "PULSE"}
AFE_ON = {"RECOVER", "WAIT_E", "ALIGN", "FILL", "RUN"}


def ref_tick(s, cmd, tmr, c):
    """-> (next state, set of control actions)"""
    acts, nxt = set(), s
    restart = False
    if cmd == "STOP":                                   # SEQ-07, 5.0: STOP always wins; IDLE: accepted, nothing
        return "IDLE", acts
    if cmd == "START":                                  # SEQ-07, SEQ-08: from IDLE only; START applies and flushes
        if s == "IDLE":
            if c["cfg_ok"]:
                return "WARMUP", {"apply", "flush"}
            return s, {"CFG_ERR"}
        acts.add("STATE_ERR")
    elif cmd in ("APPLY", "APPLY_NR"):
        if s in ("PRE", "PULSE"):                       # SEQ-05: refused in PRE and PULSE
            acts.add("STATE_ERR")
        elif s in ("IDLE", "WARMUP"):                   # SEQ-05, SEQ-16: no pulse; WARMUP restarts T_WARM
            if c["cfg_ok"]:
                acts.add("apply")
                if s == "WARMUP":
                    acts.add("restart"); restart = True
            else:
                acts.add("CFG_ERR")
        elif cmd == "APPLY":                            # SEQ-05: AFE running -> PRE, FIFO emptied
            if c["cfg_ok"]:
                return "PRE", {"apply", "flush"}
            acts.add("CFG_ERR")
        else:                                           # SEQ-06, SEQ-15: APPLY_NR while the AFE runs
            if c["cfg_ok"] and c["nr_ok"]:
                acts.add("apply")
                if s == "RUN":
                    acts.add("mark")
                elif s == "WAIT_E":
                    acts.add("restart"); restart = True
                elif s == "ALIGN":
                    if not c["t_elec0"]:
                        nxt = "WAIT_E"
                elif s == "FILL":
                    nxt = "WAIT_E" if not c["t_elec0"] else "ALIGN"
            else:
                acts.add("CFG_ERR")
    elif cmd == "FLUSH":                                # DAT-03: FLUSH empties the FIFO in every state
        acts.add("flush")
    # the timer (lower priority than a command that moves; cancelled by a restart)
    if nxt == s and s in TIMED and tmr and not restart:
        nxt = {"WARMUP": "RECOVER", "RECOVER": ("ALIGN" if c["t_elec0"] else "WAIT_E"), "WAIT_E": "ALIGN",
               "PRE": "PULSE", "PULSE": "RECOVER"}[s]
    return nxt, acts


def ref_out(s, c):
    if s == "ALIGN":
        return "FILL", {"cic_clear"}
    if s == "FILL":
        return ("RUN", {"store"}) if c["valid"] else ("FILL", set())
    if s == "RUN":
        return "RUN", {"store"}
    return s, set()


CTRL = {"apply", "flush", "store", "mark", "STATE_ERR", "CFG_ERR", "cic_clear", "restart"}
n = bad = 0
states = [x[0] for x in FS.SEQ_STATES if x[0] != "RESET"]
for s in states:
    for cmd in [None] + FS.SEQ_COMMANDS:
        for tmr in ((0, 1) if s in TIMED else (0,)):
            if cmd is None and not tmr:
                continue
            for vals in itertools.product((0, 1), repeat=4):
                c = dict(zip(("cfg_ok", "nr_ok", "t_elec0", "valid"), vals))
                present = ([cmd] if cmd else []) + (["TMR"] if tmr else [])
                fn, fa = FS.seq_tick(s, present, c)
                rn, ra = ref_tick(s, cmd, tmr, c)
                n += 1
                if fn != rn or set(fa) & CTRL != ra:
                    bad += 1
                    print("MISMATCH", s, present, c, "spec", fn, sorted(set(fa) & CTRL), "ref", rn, sorted(ra))
    for vals in itertools.product((0, 1), repeat=4):
        c = dict(zip(("cfg_ok", "nr_ok", "t_elec0", "valid"), vals))
        fn, fa = FS.seq_tick(s, ["OUT"], c)
        rn, ra = ref_out(s, c)
        n += 1
        if fn != rn or set(fa) & CTRL != ra or "seq_inc" not in fa:
            bad += 1
            print("MISMATCH OUT", s, c, fn, sorted(fa), rn, sorted(ra))
print(f"{n} combinations, {bad} mismatches between fsm_spec.seq_tick and the model written from the requirements")

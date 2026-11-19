#!/usr/bin/env python3
"""Replay tb_fifo's trace through the specification's FIFO model (audit round 2, 11/20; VER-09, DAT-07).

Every cycle: the inputs (push, pop request, flush, snap, the pushed word's identity) go through
gf180/tapeout/rtl/spec/fsm_spec.fifo_step (occupancy, OVERRUN, pop, the copy-is-head flag) and, independently, an
identity model: the FIFO holds identities with the head first; a snap copies the head (or the empty word); a pop
removes the head only if it is the copied word and there is no flush; a flush empties it first; a push appends unless
the FIFO is full after the flush and the pop. The RTL's push_ok, level, held, head identity (or the empty word's
status), ovr_set and nonempty after each edge must equal both. Usage: check_fifo_trace.py build/fifo_trace.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "rtl", "spec")))
import fsm_spec as FS  # noqa: E402

EMPTY = 0x5A


def main(path):
    lines = open(path).read().split("\n")
    depth = int(lines[0].split()[1])
    FS.DEPTH = depth                                  # fifo_step reads the module's DEPTH
    q, copy, held = [], None, 0
    errs, n, npop, nfull, nsnap_empty, nflush_push = [], 0, 0, 0, 0, 0
    for ln, line in enumerate(lines[1:], 2):
        f = line.split()
        if not f:
            continue
        push, pop, flush, snap, ident, push_ok, level, r_held, head, ovr_set, nonempty, empty_st = map(int, f)
        n += 1
        # the specification's model
        c2, ovr, popped, h2 = FS.fifo_step(len(q), push, pop, flush, held, snap)
        # the identity model
        e_pop = bool(pop and not flush and copy is not None and q and q[0] == copy)
        copy2 = (q[0] if q else None) if snap else copy
        nsnap_empty += int(bool(snap and not q))
        nfull += int(bool(push and pop and not flush and e_pop and len(q) == depth))
        nflush_push += int(bool(flush and push))
        q2 = [] if flush else (q[1:] if e_pop else q[:])
        e_ovr = bool(push and len(q2) == depth)
        if push and not e_ovr:
            q2.append(ident)
        e_held = int(copy2 is not None and bool(q2) and q2[0] == copy2)
        npop += int(e_pop)
        bad = []
        if (c2, ovr, popped, h2) != (len(q2), e_ovr, e_pop, e_held):
            bad.append(f"fifo_step gives {c2, ovr, popped, h2}, the identity model {len(q2), e_ovr, e_pop, e_held}")
        if push_ok != int(push and not e_ovr):
            bad.append(f"push_ok {push_ok}, expected {int(push and not e_ovr)}")
        if level != len(q2):
            bad.append(f"level {level}, expected {len(q2)}")
        if r_held != e_held:
            bad.append(f"held {r_held}, expected {e_held}")
        if (head if q2 else -1) != (q2[0] if q2 else -1):
            bad.append(f"head {head}, expected {q2[0] if q2 else 'the empty word'}")
        if not q2 and empty_st != EMPTY:
            bad.append(f"empty word status 0x{empty_st:02X}, expected 0x{EMPTY:02X}")
        if ovr_set != int(e_ovr):
            bad.append(f"ovr_set {ovr_set}, expected {int(e_ovr)}")
        if nonempty != int(bool(q2)):
            bad.append(f"nonempty {nonempty}, expected {int(bool(q2))}")
        if bad:
            errs.append(f"line {ln} (push {push} pop {pop} flush {flush} snap {snap}, before {q[:3]}... copy {copy}): "
                        + "; ".join(bad))
        q, copy, held = q2, copy2, e_held               # identities are unique: a stale copy never matches
    print(f"{n} cycles (depth {depth}) replayed through fsm_spec.fifo_step and the identity model: {len(errs)} "
          f"mismatches; pops {npop}, pops with a push into a full FIFO {nfull}, snaps of the empty FIFO {nsnap_empty}, "
          f"flushes with a push {nflush_push}")
    for e in errs[:10]:
        print("  " + e)
    ok = not errs and npop > 0 and nfull > 0 and nsnap_empty > 0 and nflush_push > 0
    print("PASS: eeg_fifo == fsm_spec.fifo_step" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "build/fifo_trace.txt"))

#!/usr/bin/env python3
"""Replay tb_fifo's trace through the specification's FIFO model (audit round 2, 11/20; VER-09, DAT-07).

Every cycle: the inputs (push, pop request, flush, snap, the pushed word's identity) go through
gf180/tapeout/rtl/spec/fsm_spec.fifo_step (occupancy, OVERRUN, pop, the copy-is-head flag) and, independently, an
identity model: the FIFO holds identities with the head first; a snap copies the head (or the empty word); a pop
removes the head only if it is the copied word and there is no flush; a flush empties it first; a push appends unless
the FIFO is full after the flush and the pop. The RTL's push_ok, level, held, head identity (or the empty word's
status), ovr_set and nonempty after each edge must equal both. r15: lat_snap (the SPI copies LATEST; the copy is then
not the head) and lat_clr; LATEST is the last pushed identity (stored or dropped), emptied by lat_clr (which wins over a push) and by a
flush (a push in that cycle is kept); its identity (or the empty word's status) must equal the model's. Usage: check_fifo_trace.py build/fifo_trace.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "spec")))
import fsm_spec as FS  # noqa: E402

EMPTY = 0x5A


def main(path):
    lines = open(path).read().split("\n")
    depth = int(lines[0].split()[1])
    FS.DEPTH = depth                                  # fifo_step reads the module's DEPTH
    q, copy, held, lat = [], None, 0, None
    nlat_pop, nlclr_push, nlat_drop = 0, 0, 0
    errs, n, npop, nfull, nsnap_empty, nflush_push = [], 0, 0, 0, 0, 0
    for ln, line in enumerate(lines[1:], 2):
        f = line.split()
        if not f:
            continue
        (push, pop, flush, snap, ident, push_ok, level, r_held, head, ovr_set, nonempty, empty_st, lsnap, lclr,
         r_lat, lat_st) = map(int, f)
        n += 1
        # the specification's model
        c2, ovr, popped, h2 = FS.fifo_step(len(q), push, pop, flush, held, snap, lsnap)
        # the identity model
        e_pop = bool(pop and not flush and copy is not None and q and q[0] == copy)
        copy2 = (q[0] if q else None) if snap else ("latest" if lsnap else copy)
        nlat_pop += int(bool(pop and copy == "latest" and q and not flush))
        nlclr_push += int(bool(lclr and push))
        nsnap_empty += int(bool(snap and not q))
        nfull += int(bool(push and pop and not flush and e_pop and len(q) == depth))
        nflush_push += int(bool(flush and push))
        q2 = [] if flush else (q[1:] if e_pop else q[:])
        e_ovr = bool(push and len(q2) == depth)
        if push and not e_ovr:
            q2.append(ident)
        e_held = int(copy2 is not None and bool(q2) and q2[0] == copy2)
        lat2 = None if lclr else (ident if push else (None if flush else lat))
        nlat_drop += int(bool(push and e_ovr and not lclr))
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
        if r_lat != (-1 if lat2 is None else lat2):
            bad.append(f"LATEST {r_lat}, expected {'the empty word' if lat2 is None else lat2}")
        if lat2 is None and lat_st != EMPTY:
            bad.append(f"LATEST's empty word status 0x{lat_st:02X}, expected 0x{EMPTY:02X}")
        if bad:
            errs.append(f"line {ln} (push {push} pop {pop} flush {flush} snap {snap}, before {q[:3]}... copy {copy}): "
                        + "; ".join(bad))
        q, copy, held, lat = q2, copy2, e_held, lat2               # identities are unique: a stale copy never matches
    print(f"{n} cycles (depth {depth}) replayed through fsm_spec.fifo_step and the identity model: {len(errs)} "
          f"mismatches; pops {npop}, pops with a push into a full FIFO {nfull}, snaps of the empty FIFO {nsnap_empty}, "
          f"flushes with a push {nflush_push}; pops after a LATEST copy {nlat_pop}, LATEST clears with a push "
          f"{nlclr_push}, LATEST from a dropped push {nlat_drop}")
    for e in errs[:10]:
        print("  " + e)
    ok = not errs and npop > 0 and nfull > 0 and nsnap_empty > 0 and nflush_push > 0 and nlat_pop > 0 and nlclr_push > 0 and nlat_drop > 0
    print("PASS: eeg_fifo == fsm_spec.fifo_step" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "build/fifo_trace.txt"))

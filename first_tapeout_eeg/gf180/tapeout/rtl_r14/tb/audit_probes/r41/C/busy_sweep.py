#!/usr/bin/env python3
"""audit41 C: single edits of fsm_spec.TIMING's busy_cycles keys (the frame cycles the tick must avoid), which
fsm_sweep2's TIMING class never edits (it changes numeric leaves only); and of the tick's frame/cycle combined with
busy_cycles. Each edit through fsm_spec.run_checks; a passing edit is compared by seq_sig/spi_sig.
Usage: busy_sweep.py <spec dir> <out>"""
import copy, itertools, os, sys
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fsm_sweep_sig.py")).read())
assert not F.run_checks(verbose=False)[0]
sig0 = (seq_sig(), spi_sig())
orig = copy.deepcopy(F.TIMING)
edits = []
bc = orig["busy_cycles"]
for k in sorted(bc):
    edits.append((f"busy_cycles remove {k}", lambda t, k=k: t["busy_cycles"].pop(k)))
    for nk in (k - 1, k + 1, (k + 16) % 32):
        if nk not in bc and 0 <= nk < 32:
            def mv(t, k=k, nk=nk):
                t["busy_cycles"][nk] = t["busy_cycles"].pop(k)
            edits.append((f"busy_cycles move {k}->{nk}", mv))
for nk in (23, 24, 25, 26, 31, 30):
    if nk not in bc:
        edits.append((f"busy_cycles add {nk}", lambda t, nk=nk: t["busy_cycles"].__setitem__(nk, "x")))
fo = open(OUT, "w")
npass = 0
for label, ap in edits:
    F.TIMING.clear(); F.TIMING.update(copy.deepcopy(orig))
    try:
        ap(F.TIMING)
        rep = F.run_checks(verbose=False)[0]
    except Exception as ex:
        rep = [f"exception {ex!r}"]
    if not rep:
        npass += 1
        eq = (seq_sig(), spi_sig()) == sig0
        fo.write(f"PASS {'EQUIV' if eq else 'NOT-EQUIV'} {label}\n")
    else:
        fo.write(f"fail {label}: {len(rep)} violations, e.g. {rep[0][:120]}\n")
    fo.flush()
F.TIMING.clear(); F.TIMING.update(orig)
fo.write(f"# {len(edits)} edits, {npass} pass\n")

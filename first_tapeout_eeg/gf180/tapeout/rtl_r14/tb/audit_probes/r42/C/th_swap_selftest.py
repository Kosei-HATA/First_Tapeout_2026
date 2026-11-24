#!/usr/bin/env python3
"""audit42 C: fsm_spec.TIMING's busy_cycles labels of cycles 1 and 2 exchanged ('TH の確定待ち' <-> 'TH の取り込み（e2）');
then the three checkers, the three self-tests, and what the generated frame diagram draws. Usage: <spec dir>"""
import contextlib, io, json, os, sys
SPEC = sys.argv[1]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
import regmap as R
import wave as W
f0 = json.dumps(W.frame())
bc = F.TIMING["busy_cycles"]
bc[1], bc[2] = bc[2], bc[1]
print("busy_cycles now", bc)
print("fsm_spec check:", len(F.run_checks(verbose=False)[0]), "violations")
print("regmap check:", len(R.check(verbose=False)), "violations")
print("wave check:", len(W.check()), "violations")
for name, fn in (("fsm_spec selftest", F.selftest), ("regmap selftest", R.selftest), ("wave selftest", W.selftest)):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn()
    print(f"{name}: rc {rc}; " + (buf.getvalue().strip().splitlines() or ["?"])[-1])
fr = W.frame()
print("frame diagram changed:", json.dumps(fr) != f0)
for ln in fr["signal"]:
    if isinstance(ln, dict) and ln.get("name", "").startswith(("ADC：CMP", "ADC：TH")):
        print("  ", ln["name"], ln["wave"])
# what fsm_spec.generate / regmap / wave fresh would rewrite: the requirements' generated blocks unchanged?
g = F.generate(write=False)
doc = open(F.DOC, encoding="utf-8").read()
print("requirements' generated blocks unchanged:", g[F.DOC] == doc)

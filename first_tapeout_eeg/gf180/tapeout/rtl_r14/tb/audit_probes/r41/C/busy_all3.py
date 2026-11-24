#!/usr/bin/env python3
"""audit41 C: busy_cycles key edits through fsm_spec.run_checks, regmap.check and wave.check (one shared TIMING), and
the frame diagram's strobe lanes they generate. Usage: <spec dir>"""
import copy, os, sys
SPEC = sys.argv[1]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
import regmap as R
import wave as W
assert not F.run_checks(verbose=False)[0] and not R.check(verbose=False) and not W.check()
orig = copy.deepcopy(F.TIMING)
def lanes():
    out = {}
    pos = [31] + list(range(32))
    for ln in W.frame()["signal"]:
        if isinstance(ln, dict) and "name" in ln and ln["name"].startswith(("出力のフレーム：CIC の出力", "ADC：TH_CAPTURE", "CHOP1 の縁", "ADC：CMP_STROBE")):
            v = W.lane_values(ln["wave"])
            out[ln["name"][:12]] = sorted({pos[i] for i, x in enumerate(v) if x == "1" and i > 0})[:3]
    return out
base = lanes()
print("unedited lanes:", base)
for k_old, k_new in ((8, 9), (8, 7), (16, 17), (16, 15), (2, 3), (1, 17), (0, None), (16, None), (8, None)):
    F.TIMING.clear(); F.TIMING.update(copy.deepcopy(orig))
    bc = F.TIMING["busy_cycles"]
    v = bc.pop(k_old)
    if k_new is not None:
        bc[k_new] = v
    try:
        a = F.run_checks(verbose=False)[0]; b = R.check(verbose=False); c = W.check()
        ln = lanes()
        res = "PASS all three" if not (a or b or c) else f"caught: {(a + b + c)[0][:100]}"
    except Exception as ex:
        res, ln = f"exception {ex!r}"[:120], {}
    print(f"busy {k_old}->{k_new}: {res}; lanes {ln}")
F.TIMING.clear(); F.TIMING.update(orig)

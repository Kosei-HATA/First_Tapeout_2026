#!/usr/bin/env python3
"""Audit 35, C: PROBE_OFF_REACHABLE (regmap) against the requirements' list (rule (c)): drop or add an entry and run
regmap.check() and regmap.selftest() in-process. Usage: <spec dir> <variant>"""
import io, os, sys, contextlib
SPEC, VAR = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as R
P = R.PROBE_OFF_REACHABLE
if VAR == "drop_T_WARM":
    del P["T_WARM"]
elif VAR == "drop_CHOP_CFG":
    del P["CHOP_CFG"]
elif VAR == "drop_T_ELEC_3":
    P["T_ELEC"] = [1]
elif VAR == "none":
    pass
print(VAR, "PROBE_OFF_REACHABLE =", P)
rep = R.check(verbose=False)
print("check:", len(rep), "violations", rep[:2])
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = R.selftest()
out = buf.getvalue().splitlines()
print("selftest rc", rc, "|", [l for l in out if "mutations detected" in l or l.startswith("PROBLEM")][:5])

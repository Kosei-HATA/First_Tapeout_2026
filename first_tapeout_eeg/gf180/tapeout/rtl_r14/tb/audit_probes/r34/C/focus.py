#!/usr/bin/env python3
"""focus.py <spec dir> <old> <new>: fsm_spec checker variant (text edit, in memory) and the single-action edits of every
FLUSH and OUT cell of SEQ (add or remove one action) through run_checks: the edits that pass"""
import copy, os, sys, types
spec, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, spec); os.chdir(spec)
src = open(os.path.join(spec, "fsm_spec.py"), encoding="utf-8").read()
if old:
    assert src.count(old) == 1, old
    src = src.replace(old, new)
M = types.ModuleType("fsm_spec"); M.__file__ = os.path.join(spec, "fsm_spec.py"); sys.modules["fsm_spec"] = M
exec(compile(src, M.__file__, "exec"), M.__dict__)
assert not M.run_checks(verbose=False)[0]
acts = list(M.SEQ_ACTIONS)
t0 = M.SEQ["table"]
n = 0
for key in sorted(t0, key=str):
    s, e = key
    if e not in ("FLUSH", "OUT") or not isinstance(t0[key], list):
        continue
    for i, b in enumerate(t0[key]):
        cands = [("+" + a, b["actions"] + [a]) for a in acts if a not in b["actions"]] + \
                [("-" + a, [x for x in b["actions"] if x != a]) for a in b["actions"]]
        for lab, na in cands:
            t = copy.deepcopy(t0); t[key][i]["actions"] = na
            M.SEQ["table"] = t
            try:
                r = M.run_checks(verbose=False)[0]
            except Exception as ex:
                r = ["EXC " + repr(ex)]
            n += 1
            if not r:
                print(f"PASS {key}#{i} {lab}")
M.SEQ["table"] = t0
print(f"# {n} edits")

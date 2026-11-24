"""audit40 C: rerun, at this version, exactly the regmap.REGS edits that passed regmap.check in round 39's sweep
(r39/C/sweep_regmap.txt), using regmap_sweep2's edit generator. Usage: <spec dir> <r39 list> <out>"""
import copy, os, sys, importlib.util
SPEC, LIST, OUT = sys.argv[1:4]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "regmap_sweep2.py")).read().replace("\nmain()\n", "\n")
sys.argv = ["x", SPEC, "/dev/null"]
g = {"__name__": "rs"}
exec(compile(src, "regmap_sweep2.py", "exec"), g)
R = g["R"]
want = [ln[5:].strip() for ln in open(LIST) if ln.startswith("PASS ")]
base = R.check(verbose=False)
assert not base, base[:3]
orig = copy.deepcopy(R.REGS)
edits = dict(g["edits"]())
with open(OUT, "w") as fo:
    npass = 0
    for label in want:
        if label not in edits:
            fo.write(f"MISSING {label}\n"); continue
        R.REGS[:] = copy.deepcopy(orig)
        g["apply"](edits[label])
        rep = R.check(verbose=False)
        npass += not rep
        fo.write(("PASS " if not rep else "FAILS ") + label + ("" if not rep else f"  ({rep[0][:120]})") + "\n")
    R.REGS[:] = copy.deepcopy(orig)
    fo.write(f"# {len(want)} edits of round 39's list, {npass} still pass\n")

#!/usr/bin/env python3
"""audit43 C: single edits of regmap.REGS in classes rounds 26-42 did not make (exchanges inside one register or
between two fields of one class): rswapv two fields' reset values exchanged; rswapl two fields' legal sets exchanged;
rswapc two fields' classes exchanged; rswapp two fields' pins exchanged; plus the same exchanges between two fields of
two registers of the same class (apply / imm). Each through regmap.check(). Usage: <spec dir> <out>"""
import copy, os, sys, time, itertools
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as R
assert not R.check(verbose=False)
orig = copy.deepcopy(R.REGS)
def edits():
    allf = [(ri, fi) for ri, r in enumerate(orig) for fi in range(len(r[4]))]
    for (ra, fa), (rb, fb) in itertools.combinations(allf, 2):
        A, B = orig[ra][4][fa], orig[rb][4][fb]
        if ra != rb and A["cls"] != B["cls"]:
            continue
        if ra != rb and A["cls"] not in ("apply", "imm"):
            continue
        for key in ("reset", "legal", "cls", "pin"):
            if A.get(key) == B.get(key):
                continue
            if key == "reset":                    # only if each value fits the other's width
                wa, wb = A["msb"] - A["lsb"] + 1, B["msb"] - B["lsb"] + 1
                if B["reset"] >= (1 << wa) or A["reset"] >= (1 << wb):
                    continue
            def ap(t, ra=ra, fa=fa, rb=rb, fb=fb, key=key):
                x, y = t[ra][4][fa], t[rb][4][fb]
                x[key], y[key] = y.get(key), x.get(key)
            yield f"[swap {key}] {orig[ra][1]}.{A['name']} <-> {orig[rb][1]}.{B['name']}", ap
fo = open(OUT, "w"); n = npass = 0; t0 = time.time()
for label, ap in edits():
    R.REGS[:] = copy.deepcopy(orig)
    try:
        ap(R.REGS); rep = R.check(verbose=False)
    except Exception as ex:
        rep = [f"exception {ex!r}"]
    n += 1
    if not rep:
        npass += 1; fo.write(f"PASS {label}\n")
    fo.flush()
R.REGS[:] = copy.deepcopy(orig)
fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n"); fo.close()

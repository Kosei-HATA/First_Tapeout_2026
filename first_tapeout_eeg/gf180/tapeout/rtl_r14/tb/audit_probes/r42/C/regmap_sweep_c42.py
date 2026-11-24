#!/usr/bin/env python3
"""audit42 C: single edits of regmap.REGS in classes round 26-41's sweeps did not make:
  fdrop   one field removed from a register of two or more fields
  fname   two fields' names exchanged (positions, resets, legal values kept): one register's or two registers' of the
          same class
  rname   two registers' names exchanged (addresses and fields kept)
  rswap   two registers' addresses exchanged (a register moved onto another's place)
  legal1  one legal value dropped from a field (every value, not only min / max / mid)
Each through regmap.check(). Usage: <spec dir> <out>"""
import copy, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as R
assert not R.check(verbose=False)
orig = copy.deepcopy(R.REGS)
def edits():
    regs = orig
    for ri, r in enumerate(regs):
        fs = r[4]
        if len(fs) >= 2:
            for fi in range(len(fs)):
                def fd(t, ri=ri, fi=fi):
                    rr = list(t[ri]); rr[4] = [f for j, f in enumerate(rr[4]) if j != fi]; t[ri] = tuple(rr)
                yield f"[fdrop] {r[1]}.{fs[fi]['name']}", fd
    allf = [(ri, fi) for ri, r in enumerate(regs) for fi in range(len(r[4]))]
    for a in range(len(allf)):
        for b in range(a + 1, len(allf)):
            (ra, fa), (rb, fb) = allf[a], allf[b]
            A, B = regs[ra][4][fa], regs[rb][4][fb]
            if ra != rb and A["cls"] != B["cls"]:
                continue
            def fn(t, ra=ra, fa=fa, rb=rb, fb=fb):
                x, y = t[ra][4][fa], t[rb][4][fb]
                x["name"], y["name"] = y["name"], x["name"]
            yield f"[fname] {regs[ra][1]}.{A['name']} <-> {regs[rb][1]}.{B['name']}", fn
    for a in range(len(regs)):
        for b in range(a + 1, len(regs)):
            if regs[a][2] != regs[b][2] or len(regs[a][4]) != len(regs[b][4]):
                continue
            def rn(t, a=a, b=b):
                x, y = list(t[a]), list(t[b]); x[1], y[1] = y[1], x[1]; t[a], t[b] = tuple(x), tuple(y)
            yield f"[rname] {regs[a][1]} <-> {regs[b][1]}", rn
            def rs(t, a=a, b=b):
                x, y = list(t[a]), list(t[b]); x[0], y[0] = y[0], x[0]; t[a], t[b] = tuple(x), tuple(y)
            yield f"[rswap] {regs[a][1]} @0x{regs[a][0]:02X} <-> {regs[b][1]} @0x{regs[b][0]:02X}", rs
    for ri, r in enumerate(regs):
        for fi, f in enumerate(r[4]):
            lg = f["legal"]
            if lg and len(lg) > 3:
                for v in [x for x in lg[1:-1] if x != lg[len(lg) // 2]][:2]:
                    def l1(t, ri=ri, fi=fi, v=v):
                        t[ri][4][fi]["legal"] = [x for x in t[ri][4][fi]["legal"] if x != v]
                    yield f"[legal1] {r[1]}.{f['name']} drop {v}", l1
fo = open(OUT, "w")
n = npass = 0
t0 = time.time()
for label, ap in edits():
    R.REGS[:] = copy.deepcopy(orig)
    try:
        ap(R.REGS)
        rep = R.check(verbose=False)
    except Exception as ex:
        rep = [f"exception {ex!r}"]
    n += 1
    if not rep:
        npass += 1
        fo.write(f"PASS {label}\n")
    if n % 100 == 0:
        fo.write(f"# {n} edits, {time.time() - t0:.0f} s\n")
    fo.flush()
R.REGS[:] = copy.deepcopy(orig)
fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")

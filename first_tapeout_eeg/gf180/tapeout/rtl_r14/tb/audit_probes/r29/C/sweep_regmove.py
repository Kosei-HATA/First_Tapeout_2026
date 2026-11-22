#!/usr/bin/env python3
"""Audit round 29 (C): a new class of single edits of regmap.REGS: one field moved from its register to another
register (RW to RW, at the lowest free bit position where it fits, with its other attributes kept), through
regmap.check(). Usage: sweep_regmove.py <spec dir> <out>"""
import copy, os, sys
spec_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import regmap as R
ORIG = copy.deepcopy(R.REGS)

def used_bits(fields):
    s = set()
    for f in fields:
        s |= set(range(f["lsb"], f["msb"] + 1))
    return s

def edits():
    for si, r in enumerate(ORIG):
        if r[2] != "RW":
            continue
        for fi, f in enumerate(r[4]):
            w = f["msb"] - f["lsb"] + 1
            for di, d in enumerate(ORIG):
                if di == si or d[2] != "RW":
                    continue
                busy = used_bits(d[4])
                pos = next((p for p in range(0, 9 - w) if not (set(range(p, p + w)) & busy)), None)
                if pos is None:
                    continue
                yield f"{r[1]}.{f['name']} -> {d[1]} bit {pos}", (si, fi, di, pos)

n = npass = 0
res = []
for desc, (si, fi, di, pos) in edits():
    n += 1
    regs = copy.deepcopy(ORIG)
    fl = regs[si][4].pop(fi)
    w = fl["msb"] - fl["lsb"]
    fl["lsb"], fl["msb"] = pos, pos + w
    regs[di][4].append(fl)
    if not regs[si][4]:
        continue
    R.REGS[:] = regs
    try:
        errs = R.check(verbose=False)
    except Exception as ex:   # noqa: BLE001
        errs = None
        res.append(f"CRASH {desc}: {type(ex).__name__} {ex}")
    R.REGS[:] = copy.deepcopy(ORIG)
    if errs is not None and not errs:
        npass += 1
        res.append(f"PASS {desc}")
with open(out, "w") as fo:
    fo.write(f"{n} edits, {npass} pass\n" + "\n".join(res) + "\n")
print(f"{n} edits, {npass} pass")

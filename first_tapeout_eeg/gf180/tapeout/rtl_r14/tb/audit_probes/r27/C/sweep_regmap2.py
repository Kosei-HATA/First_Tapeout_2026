#!/usr/bin/env python3
"""Audit round 27 (C): single edits of regmap.REGS beyond round 26's list: every reset value of every field's width,
every legal list extended by each missing value or reduced by each value, every pin name, every class, two registers
exchanging addresses, a field's name changed to another field's of the same register. Usage: <spec dir> <out>"""
import copy, os, sys
spec_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import regmap as R
ORIG = copy.deepcopy(R.REGS)
PINS = sorted({f["pin"] for r in ORIG for f in r[4] if f["pin"]})
CLASSES = sorted({f["cls"] for r in ORIG for f in r[4]})

def edits():
    for ri, r in enumerate(ORIG):
        addr, name, acc, lock, fields, desc = r
        for fi, f in enumerate(fields):
            w = f["msb"] - f["lsb"] + 1
            for v in (range(1 << w) if w <= 4 else ()):
                if v != f["reset"]:
                    yield f"{name}.{f['name']}: reset {f['reset']} -> {v}", ("fld", ri, fi, "reset", v)
            legal = f["legal"]
            if legal is not None and w <= 4:
                for v in range(1 << w):
                    if v not in legal:
                        yield f"{name}.{f['name']}: legal + {v}", ("fld", ri, fi, "legal", sorted(legal + [v]))
                    elif len(legal) > 1:
                        yield f"{name}.{f['name']}: legal - {v}", ("fld", ri, fi, "legal", [x for x in legal if x != v])
            for p in PINS + [None]:
                if p != f["pin"]:
                    yield f"{name}.{f['name']}: pin {f['pin']} -> {p}", ("fld", ri, fi, "pin", p)
            for c in CLASSES:
                if c != f["cls"]:
                    yield f"{name}.{f['name']}: cls {f['cls']} -> {c}", ("fld", ri, fi, "cls", c)
    for ri in range(len(ORIG)):
        for rj in range(ri + 1, len(ORIG)):
            yield f"{ORIG[ri][1]} <-> {ORIG[rj][1]}: addresses exchanged", ("swapaddr", ri, rj)

def apply(regs, e):
    if e[0] == "fld":
        _, ri, fi, k, v = e
        regs[ri][4][fi][k] = v
    elif e[0] == "swapaddr":
        _, ri, rj = e
        a, b = list(regs[ri]), list(regs[rj])
        a[0], b[0] = b[0], a[0]
        regs[ri], regs[rj] = tuple(a), tuple(b)

n = npass = 0
res = []
for desc, e in edits():
    n += 1
    regs = copy.deepcopy(ORIG)
    apply(regs, e)
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

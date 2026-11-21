#!/usr/bin/env python3
"""Audit round 26 (C): single edits of regmap.REGS (one attribute of one register or one field) through regmap.check().
Usage: sweep_regmap.py <spec dir> <out>"""
import copy
import os
import sys

spec_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import regmap as R  # noqa: E402

ORIG = copy.deepcopy(R.REGS)
ADDRS = sorted(r[0] for r in ORIG)
CLASSES = ["apply", "imm", "ro", "w1c", "cmd"]
ACCESS = ["RO", "RW", "WO", "W1C"]
PINS = sorted({f["pin"] for r in ORIG for f in r[4] if f["pin"]}) + [None]


def edits():
    for ri, r in enumerate(ORIG):
        addr, name, acc, lock, fields, desc = r
        for a in sorted({addr + 1, addr - 1, addr ^ 0x10, addr ^ 0x01, addr ^ 0x02, addr ^ 0x04, addr ^ 0x08, addr ^ 0x20,
                         addr ^ 0x40}):
            if 0 <= a < 0x80 and a not in ADDRS:
                yield f"{name}: addr 0x{addr:02X} -> 0x{a:02X}", ("reg", ri, 0, a)
        for a2 in ACCESS:
            if a2 != acc:
                yield f"{name}: access {acc} -> {a2}", ("reg", ri, 2, a2)
        yield f"{name}: lock {lock} -> {not lock}", ("reg", ri, 3, not lock)
        for fi, f in enumerate(fields):
            w = f["msb"] - f["lsb"] + 1
            for d in (-1, 1):
                if 0 <= f["msb"] + d <= 7:
                    yield f"{name}.{f['name']}: msb {f['msb']} -> {f['msb'] + d}", ("fld", ri, fi, "msb", f["msb"] + d)
                if 0 <= f["lsb"] + d <= 7:
                    yield f"{name}.{f['name']}: lsb {f['lsb']} -> {f['lsb'] + d}", ("fld", ri, fi, "lsb", f["lsb"] + d)
                if 0 <= f["lsb"] + d and f["msb"] + d <= 7:
                    yield f"{name}.{f['name']}: shifted by {d}", ("shift", ri, fi, d)
            legal = f["legal"]
            cand = sorted(({min(legal), max(legal)} if legal else set()) | {0, 1, (1 << w) - 1, f["reset"] + 1, max(f["reset"] - 1, 0)})
            for v in cand:
                if v != f["reset"] and v < (1 << w):
                    yield f"{name}.{f['name']}: reset {f['reset']} -> {v}", ("fld", ri, fi, "reset", v)
            if legal is not None:
                pick = sorted({min(legal), max(legal), f["reset"], legal[len(legal) // 2]} & set(legal))
                for v in pick:
                    yield f"{name}.{f['name']}: legal without {v}", ("fld", ri, fi, "legal", [x for x in legal if x != v])
                for v in range(1 << w):
                    if v not in legal:
                        yield f"{name}.{f['name']}: legal with {v}", ("fld", ri, fi, "legal", sorted(legal + [v]))
                        break
                yield f"{name}.{f['name']}: legal None", ("fld", ri, fi, "legal", None)
            for c in CLASSES:
                if c != f["cls"]:
                    yield f"{name}.{f['name']}: cls {f['cls']} -> {c}", ("fld", ri, fi, "cls", c)
            for p in ([None] + [x for x in PINS if x][:3] if f["pin"] else [x for x in PINS if x][:2]):
                if p != f["pin"]:
                    yield f"{name}.{f['name']}: pin {f['pin']} -> {p}", ("fld", ri, fi, "pin", p)
            for fj, g in enumerate(fields):
                if fj > fi:
                    yield f"{name}: fields {f['name']} and {g['name']} exchange positions", ("swap", ri, fi, fj)


def apply(regs, e):
    kind = e[0]
    if kind == "reg":
        _, ri, k, v = e
        r = list(regs[ri])
        r[k] = v
        regs[ri] = tuple(r)
    elif kind == "fld":
        _, ri, fi, k, v = e
        regs[ri][4][fi][k] = v
    elif kind == "shift":
        _, ri, fi, d = e
        regs[ri][4][fi]["msb"] += d
        regs[ri][4][fi]["lsb"] += d
    elif kind == "swap":
        _, ri, fi, fj = e
        a, b = regs[ri][4][fi], regs[ri][4][fj]
        a["msb"], b["msb"], a["lsb"], b["lsb"] = b["msb"], a["msb"], b["lsb"], a["lsb"]


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

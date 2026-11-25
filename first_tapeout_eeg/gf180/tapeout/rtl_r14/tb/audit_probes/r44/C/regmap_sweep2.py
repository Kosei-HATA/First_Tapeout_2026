#!/usr/bin/env python3
"""Single-field edits of regmap.REGS (and a few module constants) through regmap.check(); prints the edits that pass.
Usage: regmap_sweep2.py <spec dir> <out file (absolute)>"""
import copy, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
PART, NPART = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, 1)
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import regmap as R

def edits():
    regs = R.REGS
    used = {r[0] for r in regs} | {r[0] + R.SHADOW_MIRROR for r in regs if any(f["cls"] == "apply" for f in r[4])}
    for ri, r in enumerate(regs):
        a, n, acc, lock, fields, desc = r
        for na in sorted({a ^ (1 << k) for k in range(7)} | {(a + 1) % 128, (a - 1) % 128}):
            if na not in used:
                yield f"{n} addr 0x{a:02X}->0x{na:02X}", ("reg", ri, 0, na)
        for nacc in ("RO", "RW", "W1C", "WO"):
            if nacc != acc:
                yield f"{n} access {acc}->{nacc}", ("reg", ri, 2, nacc)
        yield f"{n} lock {lock}->{not lock}", ("reg", ri, 3, not lock)
        for fi, f in enumerate(fields):
            fn = f"{n}.{f['name']}"
            for k, dv in (("msb", 1), ("msb", -1), ("lsb", 1), ("lsb", -1)):
                v = f[k] + dv
                if 0 <= v <= 7:
                    yield f"{fn} {k} {f[k]}->{v}", ("fld", ri, fi, k, v)
            if f["msb"] + 1 <= 7 and f["lsb"] + 1 <= 7:
                yield f"{fn} shifted +1", ("shift", ri, fi, 1)
            if f["lsb"] - 1 >= 0:
                yield f"{fn} shifted -1", ("shift", ri, fi, -1)
            width = f["msb"] - f["lsb"] + 1
            lg = f["legal"]
            cand = set()
            if lg:
                cand |= {min(lg), max(lg), lg[len(lg) // 2]}
                cand |= {v for v in (min(lg) - 1, max(lg) + 1) if 0 <= v < (1 << width)}
            cand |= {0, (1 << width) - 1}
            for v in sorted(cand):
                if v != f["reset"]:
                    yield f"{fn} reset {f['reset']}->{v}", ("fld", ri, fi, "reset", v)
            if lg is not None:
                if len(lg) > 1:
                    yield f"{fn} legal drop min", ("fld", ri, fi, "legal", [x for x in lg if x != min(lg)])
                    yield f"{fn} legal drop max", ("fld", ri, fi, "legal", [x for x in lg if x != max(lg)])
                    if len(lg) > 2:
                        yield f"{fn} legal drop mid", ("fld", ri, fi, "legal", [x for x in lg if x != lg[len(lg) // 2]])
                if min(lg) - 1 >= 0:
                    yield f"{fn} legal add min-1", ("fld", ri, fi, "legal", sorted(lg + [min(lg) - 1]))
                if max(lg) + 1 < (1 << width):
                    yield f"{fn} legal add max+1", ("fld", ri, fi, "legal", sorted(lg + [max(lg) + 1]))
                yield f"{fn} legal None", ("fld", ri, fi, "legal", None)
            else:
                yield f"{fn} legal full", ("fld", ri, fi, "legal", list(range(1 << width)))
            for c in ("apply", "imm", "ro", "w1c", "cmd"):
                if c != f["cls"]:
                    yield f"{fn} cls {f['cls']}->{c}", ("fld", ri, fi, "cls", c)
            pins = sorted({g["pin"] for rr in regs for g in rr[4] if g["pin"]})
            for p in [None] + pins:
                if p != f["pin"]:
                    yield f"{fn} pin {f['pin']}->{p}", ("fld", ri, fi, "pin", p)
        if len(fields) >= 2:
            for i in range(len(fields) - 1):
                yield f"{n} fields {fields[i]['name']}<->{fields[i+1]['name']} positions", ("swap", ri, i)

def apply(e):
    kind = e[0]
    if kind == "reg":
        _, ri, idx, v = e
        r = list(R.REGS[ri]); r[idx] = v; R.REGS[ri] = tuple(r)
    elif kind == "fld":
        _, ri, fi, k, v = e
        R.REGS[ri][4][fi][k] = v
    elif kind == "shift":
        _, ri, fi, d = e
        f = R.REGS[ri][4][fi]; f["msb"] += d; f["lsb"] += d
    elif kind == "swap":
        _, ri, i = e
        fs = R.REGS[ri][4]
        a, b = fs[i], fs[i + 1]
        a["msb"], a["lsb"], b["msb"], b["lsb"] = b["msb"], b["lsb"], a["msb"], a["lsb"]

def main():
    t0 = time.time()
    base = R.check(verbose=False)
    assert not base, base[:3]
    orig = copy.deepcopy(R.REGS)
    n = npass = 0
    with open(OUT, "w") as fo:
        for idx, (label, e) in enumerate(edits()):
            if idx % NPART != PART:
                continue
            if n % 100 == 0:
                fo.write(f"# progress {n} edits tried, at {idx}, {time.time() - t0:.0f} s\n"); fo.flush()
            R.REGS[:] = copy.deepcopy(orig)
            try:
                apply(e)
                rep = R.check(verbose=False)
            except Exception as ex:
                fo.write(f"EXC {label}: {ex!r}\n"); fo.flush()
                rep = ["exception"]
            n += 1
            if not rep:
                npass += 1
                fo.write(f"PASS {label}\n"); fo.flush()
        R.REGS[:] = copy.deepcopy(orig)
        fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")

main()

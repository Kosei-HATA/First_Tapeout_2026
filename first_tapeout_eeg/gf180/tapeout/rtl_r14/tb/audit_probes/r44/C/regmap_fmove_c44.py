#!/usr/bin/env python3
"""audit 44, auditor C: one field of regmap.REGS moved into another register (same width, at the lowest free bits of
the target; name, reset, legal values, class and pin kept), for every writable field and every other register with
room. Round 29 ran this class at 227 edits (88 passed) and pinned the test and interface fields
(FIELD_REGISTER_REQUIRED); this reruns it on the current checks. Usage: <spec dir> <out>"""
import copy, os, sys, time
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as R
assert not R.check(verbose=False)
orig = copy.deepcopy(R.REGS)


def free_slot(fields, width):
    used = set()
    for f in fields:
        used |= set(range(f["lsb"], f["msb"] + 1))
    for lsb in range(0, 8 - width + 1):
        if not used & set(range(lsb, lsb + width)):
            return lsb
    return None


def edits():
    for ri, r in enumerate(orig):
        for fi, f in enumerate(r[4]):
            if f["cls"] not in ("apply", "imm", "w1c"):
                continue
            w = f["msb"] - f["lsb"] + 1
            for rj, r2 in enumerate(orig):
                if rj == ri or r2[2] in ("RO",):
                    continue
                lsb = free_slot(r2[4], w)
                if lsb is None:
                    continue
                yield f"{r[1]}.{f['name']} -> {r2[1]}[{lsb + w - 1}:{lsb}]", ri, fi, rj, lsb


def main():
    t0 = time.time()
    n = npass = 0
    with open(OUT, "w") as fo:
        for label, ri, fi, rj, lsb in edits():
            R.REGS[:] = copy.deepcopy(orig)
            f = R.REGS[ri][4].pop(fi)
            w = f["msb"] - f["lsb"] + 1
            f["lsb"], f["msb"] = lsb, lsb + w - 1
            R.REGS[rj][4].append(f)
            if not R.REGS[ri][4]:                     # the register emptied: drop it
                R.REGS.pop(ri)
            try:
                rep = R.check(verbose=False)
            except Exception as ex:
                rep = [f"exception {ex!r}"]
            n += 1
            if not rep:
                npass += 1
                fo.write(f"PASS {label}\n")
            else:
                fo.write(f"caught {label}: {rep[0][:140]}\n")
            fo.flush()
        R.REGS[:] = copy.deepcopy(orig)
        fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")


main()

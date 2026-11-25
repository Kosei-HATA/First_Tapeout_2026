#!/usr/bin/env python3
"""Audit 45, auditor C: single edits of regmap's constant tables (COMMANDS, TEST_KEY, RANGE_MAX_M, OVL_RULE,
BLANK_WITH_DAC, SAMPLE_STATUS, SHADOW_MIRROR) and moves of one field to another register (same bit positions, free
there), each through regmap.check(). usage: regmap_sweep45.py <spec dir> <out> [K|M]"""
import copy, itertools, os, sys, time
SPEC, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
CLS = sys.argv[3] if len(sys.argv) > 3 else "K"
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as RM  # noqa: E402
NAMES = ("REGS", "COMMANDS", "TEST_KEY", "RANGE_MAX_M", "OVL_RULE", "BLANK_WITH_DAC", "SAMPLE_STATUS", "SHADOW_MIRROR")
KEEP = {k: copy.deepcopy(getattr(RM, k)) for k in NAMES}
assert not RM.check(verbose=False), "the unedited map must pass"


def restore():
    for k, v in KEEP.items():
        setattr(RM, k, copy.deepcopy(v))


def edits_k():
    C = KEEP["COMMANDS"]
    for n in C:
        for b in range(8):
            yield f"COMMANDS[{n}] 0x{C[n]:02X}->0x{C[n] ^ (1 << b):02X}", ("COMMANDS", {**C, n: C[n] ^ (1 << b)})
    for a, b in itertools.combinations(C, 2):
        yield f"COMMANDS {a}<->{b}", ("COMMANDS", {**C, a: C[b], b: C[a]})
    for b in range(8):
        yield f"TEST_KEY 0x{KEEP['TEST_KEY']:02X}->0x{KEEP['TEST_KEY'] ^ (1 << b):02X}", ("TEST_KEY", KEEP["TEST_KEY"] ^ (1 << b))
    R = KEEP["RANGE_MAX_M"]
    for r in R:
        for d in (-1, 1):
            if 0 <= R[r] + d <= 1023:
                yield f"RANGE_MAX_M[{r}] {R[r]}->{R[r] + d}", ("RANGE_MAX_M", {**R, r: R[r] + d})
    for a, b in itertools.combinations(R, 2):
        yield f"RANGE_MAX_M {a}<->{b}", ("RANGE_MAX_M", {**R, a: R[b], b: R[a]})
    O = KEEP["OVL_RULE"]
    for k, vals in (("window", (31, 33, 16, 64)), ("threshold", (3, 5, 2)),
                    ("codes", ((0,), (31,), (0, 30), (1, 31), (0, 1, 31), (0, 30, 31), (0, 31, 15)))):
        for v in vals:
            yield f"OVL_RULE {k} {O[k]}->{v}", ("OVL_RULE", {**O, k: v})
    for v in (14, 13, 16, 7, 0):
        yield f"BLANK_WITH_DAC {KEEP['BLANK_WITH_DAC']}->{v}", ("BLANK_WITH_DAC", v)
    S = KEEP["SAMPLE_STATUS"]
    for i, j in itertools.combinations(range(len(S)), 2):
        s2 = [list(x) for x in S]
        s2[i][1], s2[j][1] = s2[j][1], s2[i][1]
        yield f"SAMPLE_STATUS bits of {S[i][0]}<->{S[j][0]}", ("SAMPLE_STATUS", [tuple(x) for x in s2])
    for v in (0x08, 0x18, 0x20, 0x40, 0x50, 0x30):
        yield f"SHADOW_MIRROR 0x10->0x{v:02X}", ("SHADOW_MIRROR", v)


def edits_m():
    regs = KEEP["REGS"]
    for ri, (a, n, acc, lock, fields, d) in enumerate(regs):
        if acc not in ("RW", "W1C"):
            continue
        for fi, f in enumerate(fields):
            mask = ((1 << (f["msb"] - f["lsb"] + 1)) - 1) << f["lsb"]
            for rj, (a2, n2, acc2, lock2, fields2, d2) in enumerate(regs):
                if rj == ri or acc2 not in ("RW", "W1C"):
                    continue
                used = 0
                for g in fields2:
                    used |= ((1 << (g["msb"] - g["lsb"] + 1)) - 1) << g["lsb"]
                if used & mask:
                    continue
                r2 = copy.deepcopy(regs)
                fld = r2[ri][4].pop(fi)
                r2[rj][4].append(fld)
                if not r2[ri][4]:
                    continue                        # a register without fields: not a single move
                yield f"{n}.{f['name']} moved to {n2}", ("REGS", r2)


t0 = time.time()
n = npass = 0
with open(OUT, "w") as fo:
    for txt, (name, val) in (edits_k() if CLS == "K" else edits_m()):
        n += 1
        try:
            setattr(RM, name, val)
            try:
                e = RM.check(verbose=False)
            except Exception as ex:   # noqa: BLE001
                e = [f"EXC {type(ex).__name__}"]
                fo.write(f"EXC {txt}: {type(ex).__name__} {ex}\n")
            if not e:
                npass += 1
                fo.write(f"PASS {txt}\n")
                fo.flush()
        finally:
            restore()
    fo.write(f"# {n} edits, {npass} pass, {time.time() - t0:.0f} s\n")
print(f"{n} edits, {npass} pass, {time.time() - t0:.0f} s")

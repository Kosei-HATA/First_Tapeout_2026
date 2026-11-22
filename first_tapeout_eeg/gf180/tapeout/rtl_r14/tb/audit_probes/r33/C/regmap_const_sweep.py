#!/usr/bin/env python3
"""Single edits of regmap's module constants that the RTL takes through eeg_regs_defs.svh (RANGE_MAX_M, BLANK_WITH_DAC,
OVL_RULE, SHADOW_MIRROR, COMMANDS, TEST_KEY, SAMPLE_STATUS bits) through regmap.check(). Usage: <spec dir> <out>"""
import copy, os, sys
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as R
assert not R.check(verbose=False)
edits = []
for rg, v in R.RANGE_MAX_M.items():
    for nv in (v - 1, v + 1, v * 2 + 1, (v + 1) // 2 - 1):
        if nv != v and nv >= 0:
            edits.append((f"RANGE_MAX_M[{rg}] {v}->{nv}", ("dict", "RANGE_MAX_M", rg, nv)))
for nv in (14, 13, 7, 0):
    edits.append((f"BLANK_WITH_DAC 15->{nv}", ("set", "BLANK_WITH_DAC", nv)))
for k, v in R.OVL_RULE.items():
    cands = [(0, 30), (0, 1, 31), (31,), (0, 30, 31), (1, 31)] if k == "codes" else [v - 1, v + 1]
    for nv in cands:
        edits.append((f"OVL_RULE[{k}] {v}->{nv}", ("dict", "OVL_RULE", k, nv)))
for nv in (0x18, 0x20, 0x08):
    edits.append((f"SHADOW_MIRROR 0x10->0x{nv:02X}", ("set", "SHADOW_MIRROR", nv)))
for c, v in R.COMMANDS.items():
    for nv in (v ^ 1, v ^ 0x80, v ^ 0x11):
        edits.append((f"COMMANDS[{c}] 0x{v:02X}->0x{nv:02X}", ("dict", "COMMANDS", c, nv)))
for nv in (0x3D, 0xBC, 0x3C ^ 0x10):
    edits.append((f"TEST_KEY 0x3C->0x{nv:02X}", ("set", "TEST_KEY", nv)))
for i, (n, b, d) in enumerate(R.SAMPLE_STATUS):
    for nb in (b - 1, b + 1):
        if 0 <= nb <= 7:
            edits.append((f"SAMPLE_STATUS {n} bit {b}->{nb}", ("list", "SAMPLE_STATUS", i, (n, nb, d))))

# every register moved to every free address of its half-region (round 32's fix: FIXED_ADDR and the range texts)
used = {r[0] for r in R.REGS} | {r[0] + R.SHADOW_MIRROR for r in R.REGS if any(f["cls"] == "apply" for f in r[4])}
for ri, r in enumerate(R.REGS):
    a = r[0]
    lo = a & ~0x0F
    for na in range(lo, lo + 16):
        if na not in used:
            edits.append((f"{r[1]} addr 0x{a:02X}->0x{na:02X}", ("regaddr", ri, na)))
fo = open(OUT, "w")
npass = 0
for label, e in edits:
    keep = {k: copy.deepcopy(getattr(R, k)) for k in ("REGS", "RANGE_MAX_M", "BLANK_WITH_DAC", "OVL_RULE", "SHADOW_MIRROR",
                                                      "COMMANDS", "TEST_KEY", "SAMPLE_STATUS")}
    try:
        if e[0] == "dict":
            getattr(R, e[1])[e[2]] = e[3]
        elif e[0] == "set":
            setattr(R, e[1], e[2])
        elif e[0] == "list":
            getattr(R, e[1])[e[2]] = e[3]
        elif e[0] == "regaddr":
            rr = list(R.REGS[e[1]]); rr[0] = e[2]; R.REGS[e[1]] = tuple(rr)
        rep = R.check(verbose=False)
    except Exception as ex:
        rep = [f"exception {ex!r}"]
    finally:
        for k, v in keep.items():
            setattr(R, k, v) if not isinstance(v, (dict, list)) else (getattr(R, k).clear(), getattr(R, k).update(v) if isinstance(v, dict) else getattr(R, k).extend(v))
    if not rep:
        npass += 1
        fo.write(f"PASS {label}\n")
    else:
        fo.write(f"fail {label}: {len(rep)} violations, e.g. {rep[0][:110]}\n")
    fo.flush()
fo.write(f"# {len(edits)} edits, {npass} pass\n")

#!/usr/bin/env python3
"""Audit round 30 (C): single edits of regmap.py's spec data outside REGS (the data the RTL constants, the generated
tests and the documents are generated from), through regmap.check(). Usage: sweep_regdata.py <spec dir> <out>"""
import copy, os, sys
spec_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, spec_dir)
os.chdir(spec_dir)
import regmap as R
NAMES = ["RANGE_MAX_M", "BLANK_WITH_DAC", "SHADOW_MIRROR", "COMMANDS", "TEST_KEY", "OVL_RULE", "SAMPLE_STATUS",
         "TICK_UNIT_S", "SEQ_DRIVEN", "DIGITAL_ONLY", "ANALOG_CONTROLS", "PIN_OF_CONTROL", "MASKS"]
ORIG = {k: copy.deepcopy(getattr(R, k)) for k in NAMES}

def restore():
    for k, v in ORIG.items():
        cur = getattr(R, k)
        if isinstance(cur, dict):
            cur.clear(); cur.update(copy.deepcopy(v))
        elif isinstance(cur, list):
            cur[:] = copy.deepcopy(v)
        elif isinstance(cur, set):
            cur.clear(); cur.update(copy.deepcopy(v))
        else:
            setattr(R, k, copy.deepcopy(v))

def setv(k, v):
    cur = getattr(R, k)
    if isinstance(cur, dict):
        cur.clear(); cur.update(v)
    elif isinstance(cur, list):
        cur[:] = v
    elif isinstance(cur, set):
        cur.clear(); cur.update(v)
    else:
        setattr(R, k, v)

def edits():
    rm = ORIG["RANGE_MAX_M"]
    for r, m in rm.items():
        for v in sorted({m - 1, m + 1, m // 2, m * 2 + 1, 1023, 127, 255, 511} - {m}):
            if 0 <= v <= 2047:
                d = dict(rm); d[r] = v
                yield f"RANGE_MAX_M[{r}] {m} -> {v}", ("RANGE_MAX_M", d)
    for v in (0, 1, 7, 8, 14):
        yield f"BLANK_WITH_DAC 15 -> {v}", ("BLANK_WITH_DAC", v)
    for v in (8, 15, 17, 32, 48):
        yield f"SHADOW_MIRROR 16 -> {v}", ("SHADOW_MIRROR", v)
    for c, code in ORIG["COMMANDS"].items():
        for v in sorted({code ^ 1, code ^ 0x80, code + 0x11, (code << 4 | code >> 4) & 0xFF, 0x66, 0x77, 0x99} - {code}):
            d = dict(ORIG["COMMANDS"]); d[c] = v & 0xFF
            yield f"COMMANDS[{c}] 0x{code:02X} -> 0x{v & 0xFF:02X}", ("COMMANDS", d)
    for v in (0x3D, 0x3E, 0xBC, 0xC3, 0x5A, 0x00, 0xA5):
        yield f"TEST_KEY 0x3C -> 0x{v:02X}", ("TEST_KEY", v)
    o = ORIG["OVL_RULE"]
    for k2, vs in (("window", (16, 31, 33, 64)), ("threshold", (3, 5, 2, 8)), ("codes", ((0,), (31,), (0, 1, 30, 31), (1, 30)))):
        for v in vs:
            d = dict(o); d[k2] = v
            yield f"OVL_RULE[{k2}] {o[k2]} -> {v}", ("OVL_RULE", d)
    ss = ORIG["SAMPLE_STATUS"]
    for i in range(len(ss)):
        for j in range(i + 1, len(ss)):
            l = copy.deepcopy(ss)
            a, b = l[i], l[j]
            l[i] = (a[0], b[1], a[2]); l[j] = (b[0], a[1], b[2])
            yield f"SAMPLE_STATUS: bits of {a[0]}({a[1]}) and {b[0]}({b[1]}) exchanged", ("SAMPLE_STATUS", l)
    for v in (2 * 7.8125e-6, 7.8125e-6 / 2, 1e-5):
        yield f"TICK_UNIT_S -> {v}", ("TICK_UNIT_S", v)
    for v in (set(), {"AFE_RST", "CHOP_EN"}, {"CHOP_EN"}):
        yield f"SEQ_DRIVEN -> {sorted(v)}", ("SEQ_DRIVEN", v)
    for x in sorted(ORIG["DIGITAL_ONLY"]):
        yield f"DIGITAL_ONLY without {x}", ("DIGITAL_ONLY", ORIG["DIGITAL_ONLY"] - {x})
    for x in ("TEST_CFG[5]", "CHOP_EN", "DWA_EN", "CHOP1"):
        yield f"DIGITAL_ONLY with {x}", ("DIGITAL_ONLY", ORIG["DIGITAL_ONLY"] | {x})
    for x in ORIG["ANALOG_CONTROLS"]:
        yield f"ANALOG_CONTROLS without {x}", ("ANALOG_CONTROLS", [y for y in ORIG["ANALOG_CONTROLS"] if y != x])
    poc = ORIG["PIN_OF_CONTROL"]
    vals = sorted(set(poc.values()))
    for k2 in poc:
        for v in vals:
            if v != poc[k2]:
                d = dict(poc); d[k2] = v
                yield f"PIN_OF_CONTROL[{k2}] {poc[k2]} -> {v}", ("PIN_OF_CONTROL", d)
    yield "MASKS exchanged", ("MASKS", {"ALERT_MASK": "DFLAG", "ALERT_MASK_D": "ERR"})

n = npass = 0
res = []
for desc, (k, v) in edits():
    n += 1
    setv(k, copy.deepcopy(v))
    try:
        errs = R.check(verbose=False)
    except Exception as ex:   # noqa: BLE001
        errs = None
        res.append(f"CRASH {desc}: {type(ex).__name__} {str(ex)[:120]}")
    restore()
    if errs is not None and not errs:
        npass += 1
        res.append(f"PASS {desc}")
with open(out, "w") as fo:
    fo.write(f"{n} edits, {npass} pass\n" + "\n".join(res) + "\n")
print(f"{n} edits, {npass} pass")

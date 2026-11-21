"""Single field edits of regmap.REGS through regmap.check (audit round 25, C; a light re-run of the kinds of rounds
22-24 on the current check: reset +-1, a legal value added / removed, the class, the pin, the field moved by one bit,
the register's access, lock and address)."""
import copy, os, sys, json
SPEC = os.path.abspath(sys.argv[1]); OUT = os.path.abspath(sys.argv[2])
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as RM
orig = copy.deepcopy(RM.REGS)
def run():
    try:
        return RM.check(verbose=False)
    except Exception as ex:
        return ["CRASH " + type(ex).__name__ + ": " + str(ex)[:100]]
res = {"passed": [], "crashed": [], "n": 0}
def trial(name, mut):
    RM.REGS[:] = copy.deepcopy(orig)
    mut(RM.REGS)
    r = run()
    RM.REGS[:] = copy.deepcopy(orig)
    res["n"] += 1
    if not r:
        res["passed"].append(name)
    elif any(x.startswith("CRASH") for x in r):
        res["crashed"].append((name, r[0]))
classes = ["ro", "w1c", "imm", "apply", "cmd"]
pins = sorted({f["pin"] for r in orig for f in r[4] if f["pin"]})
for ri, (a, n, acc, lock, fields, d) in enumerate(orig):
    for fi, f in enumerate(fields):
        w = f["msb"] - f["lsb"] + 1
        tag = f"{n}.{f['name']}"
        for dv in (-1, 1):
            v = f["reset"] + dv
            if 0 <= v < (1 << w):
                trial(f"{tag} reset {f['reset']}->{v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].__setitem__("reset", v))
        if f["legal"] is not None:
            for v in sorted(set(f["legal"])):
                if v in (min(f["legal"]), max(f["legal"])) and v != f["reset"]:
                    trial(f"{tag} legal -{v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].__setitem__("legal", [x for x in R[ri][4][fi]["legal"] if x != v]))
            for v in (max(f["legal"]) + 1, min(f["legal"]) - 1):
                if 0 <= v < (1 << w) and v not in f["legal"]:
                    trial(f"{tag} legal +{v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].__setitem__("legal", sorted(R[ri][4][fi]["legal"] + [v])))
        for c in classes:
            if c != f["cls"]:
                trial(f"{tag} cls {f['cls']}->{c}", lambda R, ri=ri, fi=fi, c=c: R[ri][4][fi].__setitem__("cls", c))
        if f["pin"]:
            trial(f"{tag} pin -> None", lambda R, ri=ri, fi=fi: R[ri][4][fi].__setitem__("pin", None))
        for p in pins:
            if p != f["pin"]:
                trial(f"{tag} pin -> {p}", lambda R, ri=ri, fi=fi, p=p: R[ri][4][fi].__setitem__("pin", p))
        for s in (-1, 1):
            if 0 <= f["lsb"] + s and f["msb"] + s <= 7:
                trial(f"{tag} bits {f['msb']}:{f['lsb']} {s:+d}", lambda R, ri=ri, fi=fi, s=s: (R[ri][4][fi].__setitem__("msb", R[ri][4][fi]["msb"] + s), R[ri][4][fi].__setitem__("lsb", R[ri][4][fi]["lsb"] + s)))
    for acc2 in ("RO", "RW", "W1C", "WO"):
        if acc2 != acc:
            trial(f"{n} access {acc}->{acc2}", lambda R, ri=ri, acc2=acc2: R.__setitem__(ri, (R[ri][0], R[ri][1], acc2) + tuple(R[ri][3:])))
    trial(f"{n} lock {lock}->{not lock}", lambda R, ri=ri: R.__setitem__(ri, tuple(R[ri][:3]) + (not R[ri][3],) + tuple(R[ri][4:])))
    used = {r[0] for r in orig}
    for a2 in (a ^ 1, a ^ 2, a ^ 8):
        if a2 not in used and 0 <= a2 < 0x80:
            trial(f"{n} address 0x{a:02X}->0x{a2:02X}", lambda R, ri=ri, a2=a2: R.__setitem__(ri, (a2,) + tuple(R[ri][1:])))
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)
print(res["n"], "edits;", len(res["passed"]), "passed;", len(res["crashed"]), "crashed")
for p in res["passed"]:
    print("  PASSED", p)
for c in res["crashed"]:
    print("  CRASH", c)

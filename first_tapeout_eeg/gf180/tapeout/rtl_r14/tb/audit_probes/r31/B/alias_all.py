# CRC-off host writes: every 1-bit header alias, from regmap's REGS (not a hand list): which land silently outside the
# set the round-30 remedy reads back (shadows 0x20-0x28 and timers 0x50-0x54 before START/APPLY/APPLY_NR)
import sys
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as R
by = {a: (n, acc, lock, fl) for a, n, acc, lock, fl, _ in R.REGS}
ro = {a for a, (n, acc, lock, fl) in by.items() if acc == "RO"}
ro |= {a + 0x10 for a, (n, acc, lock, fl) in by.items() if any(f["cls"] == "apply" for f in fl)}
def legal(a, v):
    n, acc, lock, fl = by[a]
    for f in fl:
        x = (v >> f["lsb"]) & ((1 << (f["msb"] - f["lsb"] + 1)) - 1)
        if f["legal"] is not None and f["cls"] not in ("cmd", "imm_key") and n not in ("COMMAND", "TEST_KEY") and x not in f["legal"]:
            return False
    return True
def commit(a, v):
    if a not in by or a in ro: return None
    n, acc, lock, fl = by[a]
    if lock: return None                     # locked (CRC-off hosts never unlock: the bracket is CRC-only)
    if not legal(a, v): return None          # RANGE_ERR
    if n == "COMMAND":
        return {0x11:"START",0x22:"STOP",0x33:"APPLY",0x44:"APPLY_NR",0x55:"FLUSH",0xA5:"SOFT_RESET"}.get(v)
    if n == "TEST_KEY":
        return "unlock" if v == 0x3C else ("lock" if v == 0 else None)
    return f"{n} := 0x{v:02X}"
covered = set(range(0x20, 0x29)) | set(range(0x50, 0x55))
writes = []
for a, (n, acc, lock, fl) in sorted(by.items()):
    if acc in ("RO",) or lock: continue
    vals = range(256)
    if n == "COMMAND": vals = [0x11, 0x22, 0x33, 0x44, 0x55, 0xA5]
    if n == "TEST_KEY": continue
    writes.append((a, n, [v for v in vals if legal(a, v)] if n != "COMMAND" else vals))
for a, n, vals in writes:
    res = {}
    for v in vals:
        for b in range(7):
            a2 = a ^ (1 << b)
            r = commit(a2, v)
            if r and a2 not in covered:
                res.setdefault(a2, []).append(v)
    for a2, vs in res.items():
        nm = by[a2][0]
        show = vs if len(vs) <= 12 else f"{len(vs)} values ({vs[0]:#04x}..)"
        print(f"write {n:12s}(0x{a:02X}) -> 0x{a2:02X} {nm:12s} silently for v in {show}")

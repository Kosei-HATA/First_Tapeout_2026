import sys
sys.path.insert(0, sys.argv[1])
import regmap as R
by = {r[0]: r for r in R.REGS}
copies = {r[0] + R.SHADOW_MIRROR: r for r in R.REGS if any(f["cls"] == "apply" for f in r[4])}
def name_of(a):
    if a in by: return by[a][1]
    if a in copies: return copies[a][1] + ".ACT"
    return None
def reset(a):
    if a in by:
        r = by[a]
        if r[2] == "WO" or r[1] == "SAMPLE": return 0
        return R.reset_of(r[1])
    if a in copies: return R.reset_of(copies[a][1])
    return 0
def values(a):
    if a in by:
        r = by[a]
        if r[2] == "WO" or r[1] == "SAMPLE": return {0}
        return R.reg_values(r[1])
    if a in copies: return R.reg_values(copies[a][1])
    return {0}
print("reset values:", {name_of(a): hex(reset(a)) for a in range(128) if name_of(a)})
# For each readable address: the CRC-off chip's 3-byte answer [STATUS, R(a), R(a+1)]
for a in range(128):
    n = name_of(a)
    if n is None: continue
    h = 0x80 | a
    b = (a + 1) & 0x7F
    # reset values
    v2, v3 = reset(a), reset(b)
    ok_reset = (R.crc8([h, v2]) == v3)
    # any values
    pairs = [(x, y) for x in sorted(values(a)) for y in sorted(values(b)) if R.crc8([h, x]) == y]
    if ok_reset or pairs:
        print(f"{hex(h)} {n:20s} next={name_of(b)}: reset pass={ok_reset} pairs={[(hex(x),hex(y)) for x,y in pairs][:12]} ({len(pairs)})")

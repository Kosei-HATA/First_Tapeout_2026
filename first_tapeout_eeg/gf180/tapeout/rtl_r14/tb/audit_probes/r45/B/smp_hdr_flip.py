import sys
sys.path.insert(0, sys.argv[1])
import regmap as R
c = R.crc8
by = {r[0]: r for r in R.REGS}
copies = {r[0] + R.SHADOW_MIRROR: r for r in R.REGS if any(f["cls"] == "apply" for f in r[4])}
def vals(a):
    if a in by:
        r = by[a]
        if r[2] == "WO" or r[1] == "SAMPLE": return {0}
        return R.reg_values(r[1])
    if a in copies: return R.reg_values(copies[a][1])
    return {0}
# host sends [0xC0, 0 x7]; one MOSI bit flips in the header -> h; CRC on: chip answers per frame kind
for bit in range(8):
    h = 0xC0 ^ (1 << bit)
    a = h & 0x7F
    hits = []
    if h & 0x80:  # a read of a
        for v in sorted(vals(a)):
            resp = [v, c([h, v]), 0, 0, 0, 0]   # data, CRC, then RDONE/OVF zeros
            crcb = 0
            if c([0xC0] + resp) == crcb:
                hits.append((hex(v), 'VALID' if v & 0x80 else 'empty'))
    else:         # write: zeros
        resp = [0]*6
        if c([0xC0]+resp) == 0: hits.append('zeros')
    print(hex(h), by[a][1] if a in by else ('copy' if a in copies else 'undef'), hits)

"""Mode probe [0xD5, 0x00, 0x00] under one SCLK fault (regmap's four kinds): can a CRC-on chip (IF_CFG 0x01 or 0x03)
look CRC-off to the host (byte 2 bit 0 = 0, byte 3 = 0x00, STATUS fixed bits 10)? And can a CRC-off chip at its
defaults look CRC-on (byte 2 bit 0 = 1, byte 3 = CRC(0xD5, byte 2))?"""
import sys
sys.path.insert(0, sys.argv[1])
import regmap as R
crc8 = R.crc8
H = 0xD5
mosi = H << 24
kinds = (("miss", lambda k: R._skip(mosi, k), lambda x, k: R._dup(x, k)),
         ("extra", lambda k: R._dup(mosi, k), lambda x, k: R._skip(x, k)),
         ("bounce", lambda k: R._dup(mosi, k), lambda x, k: R._skip(x, k + 1)),
         ("merge", lambda k: R._skip(mosi, k + 1), lambda x, k: R._dup(x, k)))
# CRC-on chip: regmap.slip_responses gives (data, crc) for the decoded header, CRC-on semantics; IF_CFG itself 0x01/0x03
def resp_on(h_, ifcfg):
    if h_ == H:
        return [(ifcfg, crc8([H, ifcfg]))]
    return R.slip_responses(h_)
# CRC-off chip at defaults: a burst of the decoded address and the next one (values after a reset), or zeros for a write
DEF = {0x00: 0xE6, 0x01: 0x10, 0x02: 0x18, 0x04: 0, 0x05: 0, 0x06: 0x01, 0x07: 0, 0x08: 0xFF, 0x09: 0x03, 0x0A: 0x03,
       0x0B: 0xE8, 0x0C: 0x05, 0x23: 3, 0x24: 8, 0x25: 1, 0x26: 1, 0x27: 0x13, 0x28: 7, 0x33: 3, 0x34: 8, 0x35: 1,
       0x36: 1, 0x37: 0x13, 0x38: 7, 0x50: 5, 0x52: 0x20, 0x53: 3, 0x54: 0x0D}
def resp_off(h_):
    if not h_ & 0x80:
        return [(0, 0)]
    a = h_ & 0x7F
    if a == 0x40:       # the window: the empty word (status may carry OVERRUN/OVL/ERR: ERR=ALERT=1 after reset)
        return [(s, 0) for s in (0x08, 0x28, 0x48, 0x68)]
    return [(DEF.get(a, 0) if a != 0x03 else 0xA1, DEF.get((a + 1) & 0x7F, 0) if a + 1 != 0x03 else 0xA1)]
hits_on, hits_off = [], []
for name, chip, host in kinds:
    for k in range(23 if name == "merge" else 24):
        h_ = chip(k) >> 24
        for st in (range(0x80, 0xC0) if k <= 8 else (0x80, 0xA1, 0x81, 0x89, 0x8D, 0xA5)):
            for ifc in (0x01, 0x03):
                for b1, b2 in resp_on(h_, ifc):
                    hs = host((st << 24) | (b1 << 16) | (b2 << 8), k)
                    s, d, c = hs >> 24, (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                    if (s >> 6) == 2 and not d & 1 and c == 0:
                        hits_on.append((name, k, hex(h_), hex(st), hex(ifc), hex(b1), hex(b2), hex(d), hex(c)))
            for b1, b2 in resp_off(h_):
                hs = host((st << 24) | (b1 << 16) | (b2 << 8), k)
                s, d, c = hs >> 24, (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                if (s >> 6) == 2 and d & 1 and c == crc8([H, d]):
                    hits_off.append((name, k, hex(h_), hex(st), hex(b1), hex(b2), hex(d), hex(c)))
print("CRC-on chip read as CRC-off:", len(hits_on))
for x in sorted(set((a, b, c, f, g, i) for a, b, c, d, f, g, h, i, j in [(*y,) for y in hits_on]))[:20]:
    print("  ", x)
print("CRC-off chip read as CRC-on:", len(hits_off))
for x in hits_off[:20]:
    print("  ", x)
print("distinct (kind, k, decoded header, value sent):")
seen = {}
for name, k, h_, st, ifc, b1, b2, d, c in hits_on:
    seen.setdefault((name, k, h_, b1), set()).add(st)
for key in sorted(seen):
    print("  ", key, "STATUS values:", len(seen[key]))

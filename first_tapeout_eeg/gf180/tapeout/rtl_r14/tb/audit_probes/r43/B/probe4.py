"""Audit 43 B: probe_off_hazards and probe_slip_hazards with the chip's 4th MISO byte modelled (CRC off: the value of
address a + 2 of the continuous read; CRC on: 0x00, or SEQ_L for a window decode)."""
import sys
sys.path.insert(0, sys.argv[1])
import numpy as np
import regmap as RM

h = 0x80 | RM.FIXED_ADDR["IF_CFG"]
crc_bit = RM.FIXED_BITS["CRC_EN"]
mosi = h << 24
names = {0x80 | a: n for a, n, *_ in RM.REGS}
names.update({0x80 | (a + RM.SHADOW_MIRROR): n + ".ACT" for a, n, _acc, _l, fl, _ in RM.REGS
              if any(f["cls"] == "apply" for f in fl)})
vals = {}
for a, n, acc, _l, fl, _ in RM.REGS:
    if acc == "RO" and n != "SAMPLE":
        v = sorted(RM.reg_values(n))
    else:
        v = [sum(f["reset"] << f["lsb"] for f in fl if isinstance(f["reset"], int) and 0 <= f["lsb"] <= f["msb"] <= 7)
             if acc != "WO" and n != "SAMPLE" else 0]
        if n in RM.PROBE_OFF_REACHABLE:
            more = RM.PROBE_OFF_REACHABLE[n]
            v = sorted(set(v) | set(RM.reg_values(n) if more is None else more))
    vals[a] = v
    if any(f["cls"] == "apply" for f in fl):
        vals[a + RM.SHADOW_MIRROR] = v
t8 = np.array([RM.crc8([h, x]) for x in range(256)], dtype=np.int64)

def triples(h_):
    if not h_ & 0x80:
        return np.zeros((1, 3), dtype=np.int64)
    a = h_ & 0x7F
    return np.array([(x, y, z) for x in vals.get(a, [0]) for y in vals.get((a + 1) & 0x7F, [0])
                     for z in vals.get((a + 2) & 0x7F, [0])], dtype=np.int64).reshape(-1, 3)

def hits(hs, b1):
    d = (hs >> 16) & 0xFF
    ok = ((hs >> 30) == 2) & (((d >> crc_bit) & 1) == 1) & (((hs >> 8) & 0xFF) == t8[d])
    return b1[ok]

kinds = ((lambda k: RM._skip(mosi, k), lambda x, k: RM._dup(x, k)),
         (lambda k: RM._dup(mosi, k), lambda x, k: RM._skip(x, k)),
         (lambda k: RM._dup(mosi, k), lambda x, k: RM._skip(x, k + 1)),
         (lambda k: RM._skip(mosi, k + 1), lambda x, k: RM._dup(x, k)))
out = set()
for ki, (chip, host) in enumerate(kinds):
    for k in range(23 if ki == 3 else 24):
        h_ = chip(k) >> 24
        pr = triples(h_)
        b1, b2, b3 = pr[:, 0], pr[:, 1], pr[:, 2]
        for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
            out |= {(names.get(h_, f"0x{h_:02X}"), int(v), ki, k) for v in hits(host((st << 24) | (b1 << 16) | (b2 << 8) | b3, k), b1)}
print("probe_off_hazards (model):", RM.probe_off_hazards())
print("probe_off_hazards with the 4th byte:", sorted(out)[:20], len(out))

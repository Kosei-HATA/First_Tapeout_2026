"""Audit 43 B: regmap.slip_hazards assumes the chip's 4th byte is 0x00. For a header the chip decodes as the sample
window, the 4th byte is SEQ_L (any value for a stored sample). Recompute with the 4th byte enumerated and compare."""
import sys
sys.path.insert(0, sys.argv[1])
import numpy as np
import regmap as RM

def slip_hazards4(key, any_value=False, window_empty=False):
    addr, vals = RM.slip_target(key)
    h = 0x80 | addr
    t8 = np.array([RM.crc8([x]) for x in range(256)], dtype=np.int64)
    legal = np.zeros(256, dtype=bool)
    legal[[v for v in sorted(vals) if 0 <= v < 256]] = True
    if any_value:
        legal[:] = True
    want_crc = t8[t8[h] ^ np.arange(256)]
    mosi = h << 24
    out = set()
    kinds = ((lambda k: RM._skip(mosi, k), lambda x, k: RM._dup(x, k)),
             (lambda k: RM._dup(mosi, k), lambda x, k: RM._skip(x, k)),
             (lambda k: RM._dup(mosi, k), lambda x, k: RM._skip(x, k + 1)),
             (lambda k: RM._skip(mosi, k + 1), lambda x, k: RM._dup(x, k)))
    win = RM.smp_hdr()
    for ki, (chip, host) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24
            pr = RM.slip_responses(h_, window_empty)
            b1 = np.array([p[0] for p in pr], dtype=np.int64)
            b2 = np.array([p[1] for p in pr], dtype=np.int64)
            # the 4th byte: SEQ_L of a stored word (any), 0 for an empty word or anything else
            if h_ == win and not window_empty:
                valid = (b1 >> 7) & 1
                b1 = np.concatenate([b1[valid == 1].repeat(2), b1[valid == 0]])
                b2_ = np.concatenate([b2[valid == 1].repeat(2), b2[valid == 0]])
                b3 = np.concatenate([np.tile([0x00, 0x80], int((valid == 1).sum())), np.zeros(int((valid == 0).sum()), dtype=np.int64)])
                b2 = b2_
            else:
                b3 = np.zeros_like(b1)
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = host((st << 24) | (b1 << 16) | (b2 << 8) | b3, k)
                d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                hit = ((hs >> 30) == 2) & legal[d] & (c == want_crc[d])
                if h_ == h:
                    hit &= d != b1
                out |= {(int(v) if h_ == h else -1, int(x)) for v, x in zip(b1[hit], d[hit])}
    return sorted(out)

keys = list(RM.SLIP_DECIDE_REQUIRED) + list(RM.SLIP_COUNTS_RECORDED)
for key in keys:
    a = RM.slip_hazards(key)
    b = slip_hazards4(key)
    if a != b:
        print(f"{key}: model {len(a)} pairs, with SEQ_L {len(b)}: new {sorted(set(b) - set(a))[:10]}")
for n in ("ID", "VERSION"):
    a = RM.slip_hazards(n, any_value=True, window_empty=True)
    b = slip_hazards4(n, any_value=True, window_empty=True)
    print(n, "empty window any value:", len(a), len(b))
    a = RM.slip_hazards(n, any_value=True)
    b = slip_hazards4(n, any_value=True)
    print(n, "full window any value: model", len(a), "with SEQ_L", len(b), "new", sorted(set(b) - set(a))[:8])
print("CRC8(0x81,0x10)=0x%02X CRC8(0x80,0xE6)=0x%02X" % (RM.crc8([0x81, 0x10]), RM.crc8([0x80, 0xE6])))

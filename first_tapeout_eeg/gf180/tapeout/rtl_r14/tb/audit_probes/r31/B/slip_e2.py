# regmap.slip_hazards covers two slip kinds: the chip misses host pulse k (MOSI bit k skipped, the host samples MISO
# bit k twice) and an extra pulse before pulse k (MOSI bit k read twice, the host skips MISO bit k). A bounce on an
# SCLK edge (a short low dip inside pulse k's high phase, or a bounce on pulse k-1's falling edge before MOSI changes)
# gives a third kind: the chip reads MOSI bit k twice (its extra rise sees the same MOSI bit) but its extra fall
# shifts MISO one bit early only AFTER the host sampled at rise k: the host skips MISO bit k+1.
import sys
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import numpy as np
import regmap as R

def hazards(key, kinds):
    addr, vals = R.slip_target(key)
    h = 0x80 | addr
    t8 = np.array([R.crc8([x]) for x in range(256)], dtype=np.int64)
    legal = np.zeros(256, dtype=bool)
    legal[[v for v in sorted(vals) if 0 <= v < 256]] = True
    want_crc = t8[t8[h] ^ np.arange(256)]
    mosi = h << 24
    out = {}
    for kind in kinds:
        for k in range(24):
            if kind == "miss":
                h_, samp = R._skip(mosi, k) >> 24, (lambda x, k=k: R._dup(x, k))
            elif kind == "extra":
                h_, samp = R._dup(mosi, k) >> 24, (lambda x, k=k: R._skip(x, k))
            else:   # "bounce": MOSI bit k read twice, MISO bit k+1 skipped
                h_, samp = R._dup(mosi, k) >> 24, (lambda x, k=k: R._skip(x, k + 1))
            resp = np.array(R.slip_responses(h_), dtype=np.int64).reshape(-1, 2)
            b1, b2 = resp[:, 0], resp[:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = samp((st << 24) | (b1 << 16) | (b2 << 8))
                d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                hit = ((hs >> 30) == 2) & legal[d] & (c == want_crc[d])
                if h_ == h:
                    hit &= d != b1
                for v, x in zip(b1[hit], d[hit]):
                    pair = (int(v) if h_ == h else -1, int(x))
                    out.setdefault(pair, set()).add((kind, k, h_, st))
    return out

keys = list(R.SLIP_DECIDE_REQUIRED) + list(R.SLIP_COUNTS_RECORDED)
for key in keys:
    base = hazards(key, ("miss", "extra"))
    assert sorted(base) == R.slip_hazards(key), key          # the same model as regmap for the two kinds
    full = hazards(key, ("miss", "extra", "bounce"))
    new = {p: w for p, w in full.items() if p not in base}
    if new:
        ex = []
        for p, w in sorted(new.items())[:6]:
            kind, k, h_, st = sorted(w)[0]
            ex.append(f"{p} (k={k}, chip header 0x{h_:02X}, STATUS 0x{st:02X})")
        print(f"{key:14s} recorded {len(base):3d} pairs; bounce adds {len(new):3d}: {'; '.join(ex)}")
    else:
        print(f"{key:14s} recorded {len(base):3d} pairs; bounce adds none")

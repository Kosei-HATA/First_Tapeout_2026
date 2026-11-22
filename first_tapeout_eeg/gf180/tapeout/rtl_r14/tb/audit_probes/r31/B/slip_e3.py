# The four single SCLK-level faults: a missing high phase (regmap "miss": MOSI bit k lost, MISO bit k sampled twice),
# an extra high phase in a low phase (regmap "extra": MOSI bit k twice, MISO bit k skipped), an extra low phase inside
# pulse k's high phase ("bounce": MOSI bit k twice, MISO bit k+1 skipped) and a missing low phase between pulses k and
# k+1 ("merge": the chip sees one long pulse: MOSI bit k+1 lost, MISO bit k sampled twice).
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
            elif kind == "bounce":
                h_, samp = R._dup(mosi, k) >> 24, (lambda x, k=k: R._skip(x, k + 1))
            else:                                   # merge of pulses k and k+1
                if k == 23: continue
                h_, samp = R._skip(mosi, k + 1) >> 24, (lambda x, k=k: R._dup(x, k))
            resp = np.array(R.slip_responses(h_), dtype=np.int64).reshape(-1, 2)
            b1, b2 = resp[:, 0], resp[:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = samp((st << 24) | (b1 << 16) | (b2 << 8))
                d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                hit = ((hs >> 30) == 2) & legal[d] & (c == want_crc[d])
                if h_ == h:
                    hit &= d != b1
                for v, x, s in zip(b1[hit], d[hit], [st] * int(hit.sum())):
                    pair = (int(v) if h_ == h else -1, int(x))
                    out.setdefault(pair, set()).add((kind, k, h_, st))
    return out

keys = list(R.SLIP_DECIDE_REQUIRED) + list(R.SLIP_COUNTS_RECORDED)
tot = 0
for key in keys:
    base = hazards(key, ("miss", "extra"))
    assert sorted(base) == R.slip_hazards(key), key
    full = hazards(key, ("miss", "extra", "bounce", "merge"))
    new = {p: w for p, w in full.items() if p not in base}
    tot += len(new)
    line = f"{key:14s} recorded {len(base):3d}"
    if new:
        ex = []
        for p, w in sorted(new.items())[:8]:
            kind, k, h_, st = sorted(w)[0]
            ex.append(f"{p[0]:#04x}->{p[1]:#04x} ({kind} k={k}, hdr 0x{h_:02X}, STATUS 0x{st:02X}{'+' if len(w) > 1 else ''})")
        line += f"; new {len(new)}: " + "; ".join(ex)
    print(line)
print("new pairs in total:", tot)

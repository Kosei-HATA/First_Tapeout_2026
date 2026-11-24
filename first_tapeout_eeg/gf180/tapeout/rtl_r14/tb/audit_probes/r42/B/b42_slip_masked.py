# audit round 42, auditor B: regmap.slip_hazards judges "another legal value" on the whole byte (reserved bits 0).
# A host that extracts the fields (ignores the reserved bits, REG-04 says they read 0) takes any byte whose fields are
# legal. Re-run the same four SCLK faults with legality judged on the masked byte.
import sys, importlib.util
import numpy as np
spec = importlib.util.spec_from_file_location("regmap", sys.argv[1])
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)

def field_mask(name):
    r = next(r for r in rm.REGS if r[1] == name)
    m = 0
    for f in r[4]:
        if 0 <= f["lsb"] <= f["msb"] <= 7:
            m |= ((1 << (f["msb"] - f["lsb"] + 1)) - 1) << f["lsb"]
    return m

def hazards(key, masked):
    addr, vals = rm.slip_target(key)
    name = key.split(".")[0]
    mask = field_mask(name)
    h = 0x80 | addr
    t8 = np.array([rm.crc8([x]) for x in range(256)], dtype=np.int64)
    legal = np.zeros(256, dtype=bool)
    for d in range(256):
        legal[d] = ((d & mask) in vals) if masked else (d in vals)
    want_crc = t8[t8[h] ^ np.arange(256)]
    mosi = h << 24
    out = set()
    kinds = ((lambda k: rm._skip(mosi, k), lambda x, k: rm._dup(x, k)),
             (lambda k: rm._dup(mosi, k), lambda x, k: rm._skip(x, k)),
             (lambda k: rm._dup(mosi, k), lambda x, k: rm._skip(x, k + 1)),
             (lambda k: rm._skip(mosi, k + 1), lambda x, k: rm._dup(x, k)))
    cache = {}
    for ki, (chip, host) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24
            if h_ not in cache:
                cache[h_] = np.array(rm.slip_responses(h_, key in ("ID", "VERSION")), dtype=np.int64).reshape(-1, 2)
            b1, b2 = cache[h_][:, 0], cache[h_][:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = host((st << 24) | (b1 << 16) | (b2 << 8), k)
                d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                hit = ((hs >> 30) == 2) & legal[d] & (c == want_crc[d])
                if h_ == h:
                    hit &= (d & mask) != (b1 & mask) if masked else (d != b1)
                for v, x in zip(b1[hit], d[hit]):
                    out.add((int(v) if h_ == h else -1, int(x), int(x) & mask, ki, k))
    return out

for key in rm.SLIP_DECIDE_REQUIRED:
    whole = {(v, x) for v, x, *_ in hazards(key, False)}
    masked = hazards(key, True)
    new = sorted({(v, x, xm) for v, x, xm, *_ in masked if (v, x) not in whole})
    print(f"{key:16s} mask 0x{field_mask(key.split('.')[0]):02X}  whole-byte pairs {sorted(whole)}  "
          f"extra pairs with the fields only: {[(('hdr' if v < 0 else hex(v)), hex(x), hex(xm)) for v, x, xm in new][:12]}"
          f"{' ...' if len(new) > 12 else ''} ({len(new)})")

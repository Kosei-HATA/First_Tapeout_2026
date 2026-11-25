"""Audit 43 B: a sample read (CRC on, RUN, FIFO not empty) with one SCLK fault in its header. The host's view of the
frame against step 6's stop rule: CRC-valid (0xC0 + 6 bytes), VALID 0, header STATUS with the fixed bits 10 and DATA 0.
Kinds as regmap.slip_hazards: 2 = an extra pulse in the low phase before host pulse k (chip reads MOSI bit k twice,
host skips chip bit k); 3 = a bounce in pulse k's high phase (chip reads MOSI bit k twice, host skips chip bit k + 1).
The chip's 72-bit MISO stream: STATUS, the 6 bytes, the CRC, then 0x00 (SDONE loads 0)."""
import random, sys
sys.path.insert(0, sys.argv[1])
import regmap as RM

def crc8(bs, c=0):
    return RM.crc8(bs, c)

def chip_decodes_window(kind, k):
    m = 0xC0 << 24
    h = RM._dup(m, k) >> 24
    return h == 0xC0

def host_view(stat, word6, skip):
    crc = crc8([0xC0] + word6)
    x = [stat] + word6 + [crc, 0x00]
    bits = [(b >> (7 - i)) & 1 for b in x for i in range(8)]
    hb = bits[:skip] + bits[skip + 1:]
    return [sum(hb[8 * j + i] << (7 - i) for i in range(8)) for j in range(8)]

def stop_ok(v):
    hdr, w = v[0], v[1:]
    return (hdr >> 6) == 0b10 and not (hdr >> 2) & 1 and not (w[0] >> 7) & 1 and crc8([0xC0] + w[:6]) == w[6]

def strict_empty(v):
    w = v[1:]
    return stop_ok(v) and (w[0] & 0x97) == 0 and all(b == 0 for b in w[1:6])

random.seed(43)
STATUS = 0x8C          # RUN, FIFO not empty, no overload, ALERT 0, no command pending
N = 200000
for kind, ks in ((2, range(0, 8)), (3, range(0, 7))):
    for k in ks:
        if not chip_decodes_window(kind, k):
            continue
        skip = k if kind == 2 else k + 1
        n = ns = 0
        for _ in range(N):
            sstat = 0x80 | (random.getrandbits(1) << 5) | (random.getrandbits(1) << 4)   # VALID, OVL?, CHANGED?, OVERRUN 0, ERR 0
            seq = random.getrandbits(16); data = random.getrandbits(24)
            w6 = [sstat, seq >> 8, seq & 0xFF, data >> 16, (data >> 8) & 0xFF, data & 0xFF]
            v = host_view(STATUS, w6, skip)
            n += stop_ok(v); ns += strict_empty(v)
        print(f"kind {kind} k {k} (host skips chip bit {skip}): {n} of {N} words read as a CRC-valid empty word "
              f"with header DATA 0 ({n / N * 256:.2f} / 256); with the full empty-word format: {ns}")

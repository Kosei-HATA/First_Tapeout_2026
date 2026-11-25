"""Audit 43 B: one SCLK fault in an 8-byte sample read (CRC on): how often does the host's view pass the sample CRC,
by fault position? Kinds as regmap.slip_hazards (1 missed pulse k, 2 extra low-phase pulse before k, 3 bounce in k,
4 pulses k and k+1 merged); the chip's stream: STATUS, 6 bytes, CRC, then 0x00. Only the chip's MISO side matters here
when the chip still decodes 0xC0 (the host view is a function of the chip stream)."""
import random, sys
sys.path.insert(0, sys.argv[1])
import regmap as RM
random.seed(7)
def bits(bs): return [(b >> (7 - i)) & 1 for b in bs for i in range(8)]
def byts(bl): return [sum(bl[8 * j + i] << (7 - i) for i in range(8)) for j in range(len(bl) // 8)]
N = 20000
res = {}
for _ in range(N):
    st = 0x80 | random.getrandbits(6)
    w = [random.choice([0x80, 0x88, 0xA0, 0xC0, 0x90]), random.getrandbits(8), random.getrandbits(8),
         random.getrandbits(8), random.getrandbits(8), random.getrandbits(8)]
    x = bits([st] + w + [RM.crc8([0xC0] + w), 0x00, 0x00])
    for kind in (1, 2, 3, 4):
        for k in range(63 if kind == 4 else 64):
            if kind in (1, 4):                     # host reads one chip bit twice (k)
                hb = x[:k + 1] + x[k:]
            elif kind == 2:                        # host skips chip bit k
                hb = x[:k] + x[k + 1:]
            else:                                  # host skips chip bit k + 1
                hb = x[:k + 1] + x[k + 2:]
            v = byts(hb[:64])
            ok = RM.crc8([0xC0] + v[1:7]) == v[7]
            key = (kind, 'hdr' if k <= 7 else 'data')
            res[key] = res.get(key, 0) + ok
for k, n in sorted(res.items()):
    print(k, n)

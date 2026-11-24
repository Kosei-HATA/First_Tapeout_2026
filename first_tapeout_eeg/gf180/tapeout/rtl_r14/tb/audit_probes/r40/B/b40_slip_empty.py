"""Audit round 40, B: can one SCLK fault of the four kinds (regmap.slip_hazards) turn the chip's EMPTY word (or a
valid word) of an 8-byte sample read into a host copy with a valid CRC and VALID = 1? Model as regmap.slip_hazards,
extended to the 64-bit sample frame. The chip decodes the header from MOSI 0xC0 + zeros (a missed / extra pulse in
the header can change what it decodes: only frames the chip still decodes as 0xC0 are kept)."""
import sys, itertools
sys.path.insert(0, sys.argv[1])
import regmap as R
crc8 = R.crc8
N = 72                                   # 64 frame bits and 8 bits after (MISO 0 in OVF)
MASK = (1 << N) - 1

def skip(x, k):      # stream of N bits MSB first, bit k left out, a 0 shifted in at the end
    hi = (x >> (N - k)) << (N - k) if k else 0
    lo = (x & ((1 << (N - 1 - k)) - 1)) << 1
    return hi | lo

def dup(x, k):       # bit k repeated, last bit dropped
    hi = (x >> (N - 1 - k)) << (N - 1 - k)
    lo = (x >> 1) & ((1 << (N - 1 - k)) - 1)
    return hi | lo

kinds = (("missed", lambda m, k: skip(m, k), lambda x, k: dup(x, k)),
         ("extra", lambda m, k: dup(m, k), lambda x, k: skip(x, k)),
         ("bounce", lambda m, k: dup(m, k), lambda x, k: skip(x, k + 1)),
         ("merge", lambda m, k: skip(m, k + 1), lambda x, k: dup(x, k)))
mosi = 0xC0 << (N - 8)
empty_flags = [0, 0x08, 0x20, 0x28, 0x40, 0x48, 0x60, 0x68]
hits = []
for st in range(0x80, 0xC0):                # every header STATUS
    for es in empty_flags:
        word = [es, 0, 0, 0, 0, 0]
        chip = ((st << 56) | sum(b << (48 - 8 * i) for i, b in enumerate(word)) | crc8([0xC0] + word)) << (N - 64)
        for name, cm, hm in kinds:
            for k in range(63 if name in ("merge", "bounce") else 64):
                if (cm(mosi, k) >> (N - 8)) != 0xC0:
                    continue                   # the chip decodes another header: not a sample read
                hs = hm(chip, k)
                b = [(hs >> (N - 8 - 8 * i)) & 0xFF for i in range(8)]
                if (b[0] >> 6) != 2:
                    pass                       # rule (a) is not needed for sample words (5.4 (a))
                if b[1] >> 7 and crc8([0xC0] + b[1:7]) == b[7]:
                    hits.append((hex(st), hex(es), name, k, " ".join(f"{x:02X}" for x in b)))
print(len(hits), "host copies of an EMPTY word with a valid CRC and VALID = 1")
for h in hits[:40]:
    print(h)

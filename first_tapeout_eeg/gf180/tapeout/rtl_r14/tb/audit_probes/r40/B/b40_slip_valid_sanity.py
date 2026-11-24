"""Sanity check of b40_slip_empty.py's model: random VALID words, every SCLK fault: the share of host copies that pass
the sample CRC (the documents quote about 0.26 % for the slipped copies)."""
import sys, random
sys.path.insert(0, sys.argv[1])
import regmap as R
crc8 = R.crc8
N = 72
def skip(x, k):
    hi = (x >> (N - k)) << (N - k) if k else 0
    lo = (x & ((1 << (N - 1 - k)) - 1)) << 1
    return hi | lo
def dup(x, k):
    hi = (x >> (N - 1 - k)) << (N - 1 - k)
    lo = (x >> 1) & ((1 << (N - 1 - k)) - 1)
    return hi | lo
kinds = (("missed", skip, dup, 0), ("extra", dup, skip, 0), ("bounce", dup, skip, 1), ("merge", skip, dup, 1))
mosi = 0xC0 << (N - 8)
random.seed(1)
tot = hit = 0
garb = {}
for _ in range(3000):
    st = random.randrange(0x80, 0xC0)
    word = [0x80 | (random.randrange(16) << 3), random.randrange(256), random.randrange(256)] + [random.randrange(256) for _ in range(3)]
    chip = ((st << 56) | sum(b << (48 - 8 * i) for i, b in enumerate(word)) | crc8([0xC0] + word)) << (N - 64)
    for name, cm, hm, off in kinds:
        for k in range(63 if off else 64):
            m = (skip(mosi, k + 1) if name == "merge" else cm(mosi, k))
            if (m >> (N - 8)) != 0xC0:
                continue
            hs = (hm(chip, k + 1) if name == "bounce" else hm(chip, k))
            b = [(hs >> (N - 8 - 8 * i)) & 0xFF for i in range(8)]
            tot += 1
            if crc8([0xC0] + b[1:7]) == b[7]:
                hit += 1
                if b[1:7] != word:
                    garb[name] = garb.get(name, 0) + 1
print(f"{hit}/{tot} = {100.0 * hit / tot:.3f} % of slipped host copies of VALID words pass the CRC")
print('of which the copy differs from the word sent (garbage that passes):', garb, sum(garb.values()), f'= {100.0*sum(garb.values())/tot:.3f} %')

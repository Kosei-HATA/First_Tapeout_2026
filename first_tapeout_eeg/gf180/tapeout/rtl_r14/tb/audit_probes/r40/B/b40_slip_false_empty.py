"""Audit round 40, B: one SCLK fault (the four kinds of regmap.slip_hazards) on an 8-byte read of a VALID word: host
copies that the step-6 stop rule takes for the end of the FIFO: the sample CRC holds, VALID = 0, and the header byte has
STATUS's fixed bits (7..6 = 10) with DATA (bit 2) = 0. The chip decodes the header as 0xC0 (kept only then) and sees 63
or 65 pulses (FRAME_ERR, no pop). Header STATUS values of RUN with data waiting: READY 1, DATA 1, AFE_RST 0, ALERT and
OVL_NOW and CMD_PENDING free."""
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
def host_copy(name, chip, k):
    return {"missed": lambda: dup(chip, k), "extra": lambda: skip(chip, k),
            "bounce": lambda: skip(chip, k + 1), "merge": lambda: dup(chip, k)}[name]()
def chip_hdr(name, k):
    m = 0xC0 << (N - 8)
    return {"missed": lambda: skip(m, k), "extra": lambda: dup(m, k), "bounce": lambda: dup(m, k),
            "merge": lambda: skip(m, k + 1)}[name]() >> (N - 8)
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
statuses = [0x8C | a | c | o for a in (0, 0x20) for c in (0, 0x10) for o in (0, 0x02)]
tot = 0
hits = {}
ex = []
NW = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
for _ in range(NW):
    st = random.choice(statuses)
    sstat = 0x80 | (random.randrange(16) << 3)          # VALID, OVERRUN, OVL, CHANGED, ERR free
    word = [sstat] + [random.randrange(256) for _ in range(5)]
    chip = ((st << 56) | sum(b << (48 - 8 * i) for i, b in enumerate(word)) | crc8([0xC0] + word)) << (N - 64)
    for name in ("missed", "extra", "bounce", "merge"):
        for k in range(63 if name in ("bounce", "merge") else 64):
            if chip_hdr(name, k) != 0xC0:
                continue
            tot += 1
            b = [(host_copy(name, chip, k) >> (N - 8 - 8 * i)) & 0xFF for i in range(8)]
            if crc8([0xC0] + b[1:7]) == b[7] and not b[1] >> 7 and (b[0] >> 6) == 2 and not (b[0] >> 2) & 1:
                hits[(name, k)] = hits.get((name, k), 0) + 1
                if len(ex) < 6:
                    ex.append((name, k, f"sent {st:02X} " + " ".join(f"{x:02X}" for x in word + [crc8([0xC0] + word)]),
                               "host " + " ".join(f"{x:02X}" for x in b)))
n = sum(hits.values())
print(f"{n} of {tot} faulted reads ({100.0 * n / tot:.4f} %) give a CRC-valid copy with VALID 0, fixed bits and DATA 0")
print("by fault and pulse:", dict(sorted(hits.items())))
for e in ex:
    print(e)

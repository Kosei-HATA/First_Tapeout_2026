"""How often a host's copy of an 8-byte sample read passes the sample CRC after one SCLK fault (the chip FRAME_ERRs and
does not pop): split into copies equal to the true word and wrong copies. Random valid words; faults at every pulse
after the header (regmap.slip_hazards' four kinds)."""
import random, sys
sys.path.insert(0, sys.argv[1])
import regmap as R
crc8 = R.crc8
rnd = random.Random(1)
def bits(bs):
    return [(b >> (7 - i)) & 1 for b in bs for i in range(8)]
def tobytes(bl):
    return [int("".join(map(str, bl[i:i + 8])), 2) for i in range(0, len(bl), 8)]
N = 3000
tot_all = wrong_all = right_all = 0
for kind in ("miss", "extra", "bounce", "merge"):
    wrong = right = tot = 0
    for _ in range(N):
        st = 0x80 | rnd.randrange(64)
        w = [0x80 | (rnd.randrange(16) << 3)] + [rnd.randrange(256) for _ in range(5)]
        c = crc8([0xC0] + w)
        miso = bits([st] + w + [c]) + [0] * 8
        for k in range(8, 64 if kind != "merge" else 63):
            if kind in ("miss", "merge"): h = miso[:k + 1] + [miso[k]] + miso[k + 1:]   # bit k read twice
            elif kind == "extra":         h = miso[:k] + miso[k + 1:]                   # bit k skipped
            else:                         h = miso[:k + 1] + miso[k + 2:]               # bit k+1 skipped
            hb = tobytes(h[:64])
            tot += 1
            if crc8([0xC0] + hb[1:7]) == hb[7]:
                if hb[1:8] == w + [c]: right += 1
                else: wrong += 1
    print(f"{kind:6s} {tot} faults: copy right and CRC ok {100.0 * right / tot:.3f} %, copy wrong and CRC ok {100.0 * wrong / tot:.3f} %")
    tot_all += tot; wrong_all += wrong; right_all += right
print(f"all    {tot_all}: right {100.0 * right_all / tot_all:.3f} %, wrong {100.0 * wrong_all / tot_all:.3f} %")

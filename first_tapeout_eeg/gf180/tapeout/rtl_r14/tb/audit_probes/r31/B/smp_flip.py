import sys
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as R
crc8 = R.crc8
by = {a: r for a, *r in [(r[0], r[1], r[2]) for r in R.REGS]}
copies = {r[0] + 0x10: r[1] for r in R.REGS if any(f["cls"] == "apply" for f in r[4])}
def vals(a):
    if a in by and by[a][1] != "WO" and by[a][0] != "SAMPLE": return R.reg_values(by[a][0])
    if a in copies: return R.reg_values(copies[a])
    return {0}
print("CRC(0xC0)=%02X  all-zero word CRC=%02X" % (crc8([0xC0]), crc8([0xC0, 0, 0, 0, 0, 0, 0])))
for b in range(8):
    h = 0xC0 ^ (1 << b)
    if not h & 0x80:
        print(f"0x{h:02X}: write, MISO all 0 -> host CRC over zeros {crc8([0xC0,0,0,0,0,0,0]):02X} != 00: rejected"); continue
    a = h & 0x7F
    hits = []
    for d in sorted(vals(a)):
        resp = [d, crc8([h, d]), 0, 0, 0, 0, 0]          # CRC on: data, CRC, then OVF zeros
        if crc8([0xC0] + resp[:6]) == resp[6]:
            hits.append(d)
    nm = by[a][0] if a in by else copies.get(a, "undefined")
    print(f"0x{h:02X} ({nm}): CRC-on responses that pass the host's sample CRC: {hits}")

def crc8(data, c=0):
    for d in data:
        c ^= d
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c
# CRC on: a sample read [0xC0, 0 x7] whose header arrives as h' (one bit flipped)
def host_ok(resp7):   # resp7 = 7 bytes after the header as received by the host
    return crc8([0xC0] + resp7[:6]) == resp7[6]
for bit in range(8):
    h = 0xC0 ^ (1 << bit)
    a = h & 0x7F
    if not (h & 0x80):
        print("bit %d: header %02X is a write -> zeros: host ok=%s" % (bit, h, host_ok([0]*7)))
        continue
    vals = {0x00: [0xE6], 0x50: range(5, 256), 0x60: range(0, 32)}.get(a, [0x00])
    hits = [v for v in vals if host_ok([v, crc8([h, v]), 0, 0, 0, 0, 0])]
    print("bit %d: header %02X (addr %02X): values passing the host's sample CRC: %s" % (bit, h, a, hits))

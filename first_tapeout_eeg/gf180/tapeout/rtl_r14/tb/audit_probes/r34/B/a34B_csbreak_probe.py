# The mode probe [0xD5, 0x00, 0x00] to a CRC-ON chip (IF_CFG 0x01 or 0x03) with one CS_N break before pulse k: which
# k give the CRC-OFF answer (STATUS bits 7..6 = 10, byte 2 bit 0 = 0, byte 3 = 0x00)? Every reachable STATUS value
# at both frame starts (READY and AFE_RST never both 1); the chip's other registers at their reset values.
import sys
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as RM
crc8 = RM.crc8
REACH = [s for s in range(0x80, 0xC0) if not ((s >> 3) & 1 and s & 1)]
h = 0xD5
res = {}
for ifc in (0x01, 0x03):
    for k in range(1, 24):
        h2 = ((h << k) & 0xFF) if k < 8 else 0x00
        tails = RM.slip_responses(h2) if 24 - k >= 16 else [(0, 0)]
        for st in REACH:
            for st2 in REACH:
                for a2, b2 in tails:
                    f1 = (st << 16) | (ifc << 8) | crc8([h, ifc])
                    f2 = (st2 << 16) | (a2 << 8) | b2
                    V = (f1 & (((1 << k) - 1) << (24 - k))) | (f2 >> k)
                    if (V >> 22) == 2 and not ((V >> 8) & 1) and (V & 0xFF) == 0:
                        res.setdefault((ifc, k), set()).add(st2)
for (ifc, k), s2 in sorted(res.items()):
    print(f"IF_CFG {ifc:02X}, break before pulse {k:2d}: CRC-off answer for frame-2 STATUS in {sorted(hex(x) for x in s2)[:10]}{' ...' if len(s2) > 10 else ''} ({len(s2)} values)")

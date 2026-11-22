# One CS_N break (a short High in the low phase before host pulse k, k = 1..23) during a 3-byte CRC read [hdr, 0, 0].
# The chip ends frame 1 after k bits and starts frame 2 at pulse k, reloading STATUS (STATUS') onto MISO; frame 2's
# MOSI is the host's from position k (the header's last 8-k bits, then zeros), and its response after its own header
# is regmap.slip_responses(h2) (read: value + CRC; window: sample status + SEQ_H; write: zeros; undefined: 0 + CRC).
# Host view V = frame-1 MISO bits 0..k-1, then frame-2 MISO. Hazard: V's byte 0 has bits 7..6 = 10, byte 1 a legal
# value d of the register that is not the true value, byte 2 = CRC-8(hdr, d).
import sys
import numpy as np
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as RM
crc8 = RM.crc8
ALL = np.arange(0x80, 0xC0)
REACH = np.array([s for s in range(0x80, 0xC0) if not ((s >> 3) & 1 and s & 1)])   # READY and AFE_RST never both 1

def hazards(key, stvals):
    addr, vals = RM.slip_target(key)
    h = 0x80 | addr
    legal = np.zeros(256, bool); legal[sorted(v for v in vals if 0 <= v < 256)] = True
    want = np.array([crc8([h, x]) for x in range(256)])
    out = set()
    for k in range(1, 24):
        top = ((1 << k) - 1) << (24 - k)
        h2 = ((h << k) & 0xFF) if k < 8 else 0x00            # frame 2's header (zeros after the read header)
        tails = np.array(RM.slip_responses(h2) if 24 - k >= 16 else [(0, 0)]).reshape(-1, 2)
        f2 = (stvals[:, None] << 16) | (tails[None, :, 0] << 8) | tails[None, :, 1]          # [st2, tail]
        for st in stvals:
            for v in sorted(vals):
                f1 = (int(st) << 16) | (v << 8) | crc8([h, v])
                V = (f1 & top) | (f2 >> k)
                b0, d, c = V >> 16, (V >> 8) & 0xFF, V & 0xFF
                hit = ((b0 >> 6) == 2) & legal[d] & (d != v) & (c == want[d])
                for dd in np.unique(d[hit]):
                    out.add((k, v, int(dd)))
            if k <= 8:                                         # the view does not depend on STATUS or v here
                break
    return out

if __name__ == "__main__":
    keys = ["STATE", "FIFO_LEVEL", "DFLAG", "IF_CFG", "ERR", "STATUS", "OFF_M_L.ACT", "OFF_M_H.ACT", "OFF_CTRL.ACT"]
    for key in keys:
        for name, sv in (("reachable STATUS", REACH), ("any STATUS", ALL)):
            hz = hazards(key, sv)
            ks = sorted({k for k, _, _ in hz})
            reads = sorted({d for _, _, d in hz})
            print(f"{key:12s} {name:16s}: {len(hz):5d} (k, true, read) triples; break positions {ks}; values read {[hex(x) for x in reads][:12]}")
